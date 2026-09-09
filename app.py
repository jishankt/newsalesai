"""
Flask Application for Conversational AI Customer Relations Assistant.
Connects with Ollama (gpt-oss:20b), runs NLP normalization, intent extraction,
enforces strict commercial guardrails, and guarantees zero-hallucination grounding.
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import uuid
import logging
from config import PORT, DEBUG, DEFAULT_COMPANY_CONTEXT, DEFAULT_MODEL, OLLAMA_BASE_URL
from prompts import build_system_prompt, format_generate_prompt, format_evidence_grounded_prompt
from guardrails import check_user_intent_for_pricing_or_discount, validate_and_sanitize_response, PRICE_REFUSAL, DISCOUNT_REFUSAL
from ollama_client import OllamaClient
from nlp.intent_extractor import analyze_input, INTENT_PRICE, INTENT_DISCOUNT
from nlp.grounding_validator import validate_grounding
from nlp.discovery_engine import is_broad_query, get_discovery_question
from state.conversation_state import CanonicalState
from state.requirement_updater import RequirementUpdater
from state.next_question_engine import NextQuestionEngine
from nlp.dialogue_act import (
    classify_dialogue_act,
    ACT_ANSWERING_QUESTION,
    ACT_CORRECTING_ANSWER,
    ACT_ASKING_PRODUCT_QUESTION,
    ACT_ASKING_COMPARISON,
    ACT_ASKING_CONSUMABLES,
    ACT_CHANGING_REQUIREMENT,
    ACT_CHANGING_TOPIC,
    ACT_REFERENCING_ITEM,
    ACT_GREETING,
    ACT_ENDING,
    ACT_CONFIRMING,
    ACT_REJECTING,
    ACT_GENERAL_DISCOVERY
)
from agent.orchestrator import orchestrator as new_orchestrator
from agent.ai_orchestrator import ai_orchestrator  # Kept for fallback
from rag.consumables_engine import consumables_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("conversational_ai")

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Session store: session_id -> list of {"role": "user"|"assistant", "content": str}
SESSIONS = {}
# Canonical State store: session_id -> CanonicalState
STATE_STORE = {}

ollama_client = OllamaClient(base_url=OLLAMA_BASE_URL, default_model=DEFAULT_MODEL)

# Run startup health check and log status banner
startup_report = ollama_client.startup_health_check(test_inference=False)
logger.info(
    f"Ollama Startup Diagnostic: status={startup_report.get('status')} "
    f"server_connected={startup_report.get('server_connected')} "
    f"model_available={startup_report.get('model_available')} "
    f"error_kind={startup_report.get('error_kind')}"
)

# Inject Ollama client into new orchestrator
new_orchestrator.ollama_client = ollama_client
new_orchestrator.llm_engine.client = ollama_client
new_orchestrator.response_composer.ollama_client = ollama_client


@app.route("/")
def index():
    """Serves the static store landing page with floating chatbot widget icon."""
    return render_template("landing.html")


@app.route("/chat-widget")
def chat_widget():
    """Serves the embedded chat widget interface for the modal."""
    return render_template("index.html")


@app.route("/chat-full")
def chat_full():
    """Serves the standalone full-screen chat interface."""
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    """Returns current default company context and model configuration."""
    return jsonify({
        "company_context": DEFAULT_COMPANY_CONTEXT,
        "default_model": DEFAULT_MODEL,
        "ollama_base_url": OLLAMA_BASE_URL
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Returns status of Ollama connection and installed models."""
    deep_verify = request.args.get("verify", "false").lower() == "true"
    if deep_verify:
        health_data = ollama_client.startup_health_check(test_inference=True)
    else:
        health_data = ollama_client.check_health()
    return jsonify(health_data)


from persistence import state_repository


@app.route("/api/reset", methods=["POST"])
def reset_session():
    """Resets conversation history and canonical state for a given session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id:
        if session_id in SESSIONS:
            del SESSIONS[session_id]
        if session_id in STATE_STORE:
            del STATE_STORE[session_id]
        state_repository.delete_session(session_id)
        logger.info(f"Session {session_id} reset successfully.")
    return jsonify({"success": True, "message": "Session reset."})


from rag.retriever import rag_retriever
from rag.comparison_engine import detect_comparison_request, generate_comparison_response
from rag.consumables_engine import consumables_engine

req_updater = RequirementUpdater(consumables_engine=consumables_engine)
next_question_engine = NextQuestionEngine()


@app.route("/api/consumables", methods=["GET"])
def get_consumables():
    """Returns compatible inks, maintenance tanks, and media for a given printer."""
    printer_name = request.args.get("printer", "").strip()
    c_type = request.args.get("type", "all").strip()
    if not printer_name:
        return jsonify({"consumables": []})
    consumables = consumables_engine.get_printer_consumables(printer_name, consumable_filter=c_type, limit=6)
    return jsonify({
        "success": True,
        "printer": printer_name,
        "consumables": consumables
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Main conversational endpoint:
    - Normalizes user text and extracts NLP entities & intent
    - Fast-paths commercial rules (price/discount refusal)
    - Performs RAG retrieval over scraped product corpus
    - Handles product comparison (Section D) or deep specifications
    - Attaches rich hardware cards and compatible consumable cards from 833-item catalog
    - Calls Ollama /api/generate with RAG context
    - Validates zero-hallucinations against verified knowledge base
    - Returns sanitized reply, interactive suggestion chips, product cards, and retrieved RAG sources
    """
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    raw_message = data["message"].strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    company_context = data.get("company_context") or DEFAULT_COMPANY_CONTEXT
    model_name = data.get("model") or DEFAULT_MODEL
    ollama_url = data.get("ollama_base_url") or OLLAMA_BASE_URL

    # 1. NLP Analysis: Normalization, Intent Classification, Entity Extraction
    nlp_result = analyze_input(raw_message)
    normalized_msg = nlp_result["normalized_text"]
    detected_intent = nlp_result["intent"]

    # Update client target if client supplied custom base URL
    if ollama_url != ollama_client.base_url:
        ollama_client.base_url = ollama_url.rstrip("/")

    # Initialize session history and canonical state (with SQLite persistence recovery)
    if session_id not in STATE_STORE or session_id not in SESSIONS:
        persisted = state_repository.get_session(session_id)
        if persisted:
            STATE_STORE[session_id], SESSIONS[session_id] = persisted
        else:
            if session_id not in SESSIONS:
                SESSIONS[session_id] = []
            if session_id not in STATE_STORE:
                STATE_STORE[session_id] = CanonicalState(session_id=session_id)

    history = SESSIONS[session_id]
    state = STATE_STORE[session_id]

    logger.info(f"[{session_id[:8]}] Customer: '{raw_message}' -> Normalized: '{normalized_msg}' | Intent: {detected_intent}")

    # Process conversational turn through new orchestrator pipeline
    orchestrator_res = new_orchestrator.process_turn(
        raw_message=raw_message,
        session_id=session_id,
        history=history,
        state=state,
        model_name=model_name
    )

    assistant_reply = orchestrator_res["reply"]
    source = orchestrator_res["source"]
    product_cards = orchestrator_res["product_cards"]
    consumable_cards = orchestrator_res["consumable_cards"]
    suggested_chips = orchestrator_res["suggested_chips"]
    grounding_result = orchestrator_res["grounding"]
    nlp_result = orchestrator_res["nlp"]
    state = orchestrator_res["state"]
    retrieved_items = orchestrator_res.get("retrieved_items", [])

    # Save state and history turns
    state.history_turns.append({"role": "user", "content": normalized_msg})
    state.history_turns.append({"role": "assistant", "content": assistant_reply})
    STATE_STORE[session_id] = state

    history.append({"role": "user", "content": normalized_msg})
    history.append({"role": "assistant", "content": assistant_reply})

    # Persist session to SQLite
    state_repository.save_session(session_id, state, history)

    logger.info(f"[{session_id[:8]}] Assistant ({source} | Grounding: {grounding_result['status']}): {assistant_reply}")

    # Format retrieved sources for frontend UI inspection
    sources_summary = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "score": r.get("similarity_score", 0),
            "width": r.get("width") or r.get("print_sizes") or r.get("speed", ""),
            "ink": r.get("ink_technology") or r.get("technology", ""),
            "url": r.get("url") or r.get("source_url") or r.get("website_url") or "https://www.keplertechllc.com/"
        }
        for r in retrieved_items
    ]

    return jsonify({
        "success": True,
        "session_id": session_id,
        "reply": assistant_reply,
        "source": source,
        "suggested_chips": suggested_chips,
        "retrieved_sources": sources_summary,
        "product_cards": product_cards,
        "consumable_cards": consumable_cards,
        "canonical_state": state.to_dict(),
        "nlp": {
            "raw_input": raw_message,
            "normalized_input": normalized_msg,
            "corrections": nlp_result["corrections"],
            "intent": detected_intent,
            "brands": nlp_result["brands"],
            "categories": nlp_result["categories"],
            "models": nlp_result["models"],
            "sizes": nlp_result["sizes"]
        },
        "grounding": {
            "is_grounded": grounding_result["is_grounded"],
            "status": grounding_result["status"],
            "notes": grounding_result.get("notes", [])
        },
        "turns_count": len(history) // 2
    })


if __name__ == "__main__":
    logger.info(f"Starting Customer Relations Assistant on http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
