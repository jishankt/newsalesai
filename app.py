"""
Flask Application for Conversational AI Customer Relations Assistant.
Connects with Ollama (gpt-oss:20b), runs NLP normalization, intent extraction,
enforces strict commercial guardrails, and guarantees zero-hallucination grounding.
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import uuid
import re
import logging
from config import (
    PORT,
    DEBUG,
    DEFAULT_COMPANY_CONTEXT,
    DEFAULT_MODEL,
    OLLAMA_BASE_URL,
    ALLOWED_MODELS,
    CORS_ORIGINS,
    MAX_REQUEST_BYTES,
    validate_secret_key,
    APP_ENV,
    IS_PRODUCTION,
    LOG_SENSITIVE_DATA,
    EXPOSE_DEBUG_STATE,
    OLLAMA_MANDATORY_FOR_READY,
    RATE_LIMIT_ENABLED,
)
from prompts import build_system_prompt, format_generate_prompt, format_evidence_grounded_prompt
from guardrails import check_user_intent_for_pricing_or_discount, validate_and_sanitize_response, PRICE_REFUSAL, DISCOUNT_REFUSAL
from ollama_client import OllamaClient
from nlp.intent_extractor import analyze_input, INTENT_PRICE, INTENT_DISCOUNT
from nlp.grounding_validator import validate_grounding
from nlp.discovery_engine import is_broad_query, get_discovery_question
from domain.conversation_state import ConversationState
from domain.state_store import state_manager
from agent.orchestrator import orchestrator as new_orchestrator
from rag.consumables_engine import consumables_engine
from agents import list_agent_metadata
from persistence import lead_repository, state_repository
from security.rate_limiter import rate_limiter, get_client_ip

# Production Security Gate: refuse startup if SECRET_KEY is default/insecure in production
validate_secret_key()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("conversational_ai")

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": CORS_ORIGINS}})

# Security: enforce maximum request payload size
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

ollama_client = OllamaClient(base_url=OLLAMA_BASE_URL, default_model=DEFAULT_MODEL)

# Inject Ollama client into new orchestrator
new_orchestrator.ollama_client = ollama_client
new_orchestrator.llm_engine.client = ollama_client
new_orchestrator.response_composer.ollama_client = ollama_client


@app.after_request
def add_security_headers(response):
    """Attach standard security headers and prevent caching of conversation responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"error": "Request payload too large"}), 413


@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e)}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "The requested resource was not found."}), 404


@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/")
def index():
    """Serves the static store landing page with floating chatbot widget icon."""
    return render_template("landing.html")


@app.route("/favicon.ico")
def favicon():
    """Returns 204 No Content for browser favicon requests to avoid 404 noise."""
    return "", 204


@app.route("/chat")
@app.route("/chat/")
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
    """Returns current default company context and model configuration without internal Ollama URL."""
    return jsonify({
        "company_context": DEFAULT_COMPANY_CONTEXT,
        "default_model": DEFAULT_MODEL
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Returns operational health status without exposing internal Ollama URL or raw server endpoints."""
    from catalog.catalogue_loader import catalogue_loader, EXPECTED_CATALOGUE_COUNT
    all_prods = catalogue_loader.get_all()
    catalogue_ok = len(all_prods) == EXPECTED_CATALOGUE_COUNT

    health_info = ollama_client.check_health()
    ollama_ok = bool(health_info.get("online") or health_info.get("model_available"))
    is_ready = catalogue_ok and ollama_ok

    if not DEBUG and not EXPOSE_DEBUG_STATE:
        return jsonify({
            "status": "ok" if is_ready else ("degraded" if catalogue_ok else "unavailable"),
            "online": ollama_ok,
            "catalogue_ok": catalogue_ok
        })

    return jsonify({
        "status": "ok" if is_ready else "degraded",
        "online": ollama_ok,
        "catalogue_ok": catalogue_ok,
        "models_count": len(health_info.get("models", []))
    })


@app.route("/health/live", methods=["GET"])
def liveness():
    """Liveness probe — confirms the server process is alive."""
    return jsonify({"status": "alive", "service": "kepler-salesai"}), 200


@app.route("/health/ready", methods=["GET"])
def readiness():
    """
    Readiness probe — confirms approved 41 catalogue loaded, persistence available,
    and returns 503 when not ready or degraded when Ollama is offline.
    """
    from catalog.catalogue_loader import catalogue_loader, EXPECTED_CATALOGUE_COUNT
    all_prods = catalogue_loader.get_all()
    catalogue_ok = len(all_prods) == EXPECTED_CATALOGUE_COUNT

    persistence_ok = True
    try:
        with state_repository._get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        persistence_ok = False

    health_info = ollama_client.check_health()
    ollama_ok = bool(health_info.get("online") or health_info.get("model_available"))

    if not catalogue_ok or not persistence_ok:
        status_code = 503
        status_str = "unavailable"
    elif ollama_ok:
        status_code = 200
        status_str = "ready"
    else:
        # Ollama is offline. Check policy.
        if OLLAMA_MANDATORY_FOR_READY:
            status_code = 503
            status_str = "unavailable"
        else:
            status_code = 200
            status_str = "degraded"

    return jsonify({
        "status": status_str,
        "catalog_count": len(all_prods),
        "catalogue_count": len(all_prods),
        "catalogue_ok": catalogue_ok,
        "persistence_ok": persistence_ok,
        "ollama_ok": ollama_ok
    }), status_code


@app.route("/api/reset", methods=["POST"])
def reset_session():
    """Resets conversation history and canonical state for a given session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if session_id:
        state_manager.reset(session_id)
        logger.info(f"Session {session_id} reset successfully.")
    return jsonify({"success": True, "message": "Session reset."})


from rag.retriever import rag_retriever
from rag.comparison_engine import detect_comparison_request, generate_comparison_response
from rag.consumables_engine import consumables_engine



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
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Missing or invalid JSON body"}), 400

    # Security: Model allowlist enforcement — do not leak full allowed model list in error
    if data.get("model") and data["model"] not in ALLOWED_MODELS:
        return jsonify({"error": f"Model not allowed: '{data['model']}'"}), 400

    if "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    if not isinstance(data["message"], str):
        return jsonify({"error": "'message' field must be a string"}), 400

    raw_message = data["message"].strip()
    if not raw_message:
        return jsonify({"error": "Empty message", "message": "Message cannot be empty or whitespace only"}), 400

    if len(data["message"]) > 4000:
        return jsonify({"error": "Message exceeds maximum allowed length of 4000 characters"}), 400

    session_id = data.get("session_id")
    if session_id:
        if not isinstance(session_id, str) or len(session_id) > 128 or not re.match(r"^[a-zA-Z0-9_\-\.:]+$", session_id):
            return jsonify({"error": "Invalid session_id format"}), 400
    else:
        session_id = str(uuid.uuid4())

    # Rate Limiting Guard: check IP and session limits
    client_ip = get_client_ip(request)
    allowed, rate_err, retry_after = rate_limiter.check_request(client_ip, session_id=session_id)
    if not allowed:
        resp = jsonify({
            "error": "Too many requests",
            "message": rate_err or "Rate limit exceeded. Please wait a moment before sending another message."
        })
        resp.headers["Retry-After"] = str(retry_after)
        return resp, 429

    model_name = data.get("model") or DEFAULT_MODEL
    request_id = str(uuid.uuid4())[:8]
    session_prefix = session_id[:8] if session_id else "unknown"
    turn_start_time = time.time()

    # 1. NLP Analysis: Normalization, Intent Classification, Entity Extraction
    nlp_result = analyze_input(raw_message)
    normalized_msg = nlp_result["normalized_text"]
    detected_intent = nlp_result["intent"]

    # Retrieve canonical state and history via unified state_manager
    state = state_manager.get_or_create(session_id)
    history = state_manager.get_history(session_id)

    if LOG_SENSITIVE_DATA:
        logger.info(f"[{session_prefix}] req_id={request_id} Customer: '{raw_message}' -> Normalized: '{normalized_msg}' | Intent: {detected_intent}")
    else:
        logger.info(f"[{session_prefix}] req_id={request_id} incoming_chat intent={detected_intent} msg_len={len(raw_message)}")

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

    # Save state and history turns via canonical state_manager
    state.history_turns.append({"role": "user", "content": normalized_msg})
    state.history_turns.append({"role": "assistant", "content": assistant_reply})
    history.append({"role": "user", "content": normalized_msg})
    history.append({"role": "assistant", "content": assistant_reply})
    state_manager.save(state, history)

    latency_ms = int((time.time() - turn_start_time) * 1000)
    if LOG_SENSITIVE_DATA:
        logger.info(f"[{session_prefix}] req_id={request_id} Assistant ({source} | Grounding: {grounding_result['status']}): {assistant_reply}")
    else:
        logger.info(
            f"[{session_prefix}] req_id={request_id} route={source} status=200 "
            f"reply_len={len(assistant_reply)} cards={len(product_cards)} "
            f"grounding={grounding_result.get('status')} latency_ms={latency_ms}"
        )

    # Format retrieved sources for frontend UI inspection
    sources_summary = orchestrator_res.get("retrieved_sources") or [
        {
            "id": r.get("id"),
            "name": r.get("model") or r.get("display_name") or r.get("name") or "Catalogue Product",
            "score": r.get("similarity_score", 0),
            "width": r.get("width") or r.get("print_sizes") or r.get("speed", ""),
            "ink": r.get("ink_technology") or r.get("technology", ""),
            "url": r.get("product_url") or r.get("url") or r.get("source_url") or r.get("website_url") or "https://www.keplertechllc.com/"
        }
        for r in retrieved_items
    ]

    active_agent = orchestrator_res.get("active_agent")

    response_payload = {
        "success": True,
        "session_id": session_id,
        "reply": assistant_reply,
        "message": assistant_reply,
        "type": orchestrator_res.get("type", "message"),
        "result_count": orchestrator_res.get("result_count", len(product_cards)),
        "subcategory": orchestrator_res.get("subcategory"),
        "cards": product_cards,
        "source": source,
        "active_agent": active_agent,
        "suggested_chips": suggested_chips,
        "retrieved_sources": sources_summary,
        "product_cards": product_cards,
        "consumable_cards": consumable_cards,
        "recommendation_audit": orchestrator_res.get("recommendation_audit"),
        "comparison_data": orchestrator_res.get("comparison_data") or {},
        "nlp": {
            "raw_input": raw_message,
            "normalized_input": normalized_msg,
            "corrections": nlp_result.get("corrections", []),
            "intent": detected_intent,
            "brands": nlp_result.get("brands", []),
            "categories": nlp_result.get("categories", []),
            "models": nlp_result.get("models", []),
            "sizes": nlp_result.get("sizes", [])
        },
        "grounding": {
            "is_grounded": grounding_result.get("is_grounded", True),
            "status": grounding_result.get("status", "verified_catalogue_source"),
            "notes": grounding_result.get("notes", [])
        },
        "turns_count": len(history) // 2
    }

    # Debug state isolation: canonical_state is strictly omitted in production
    if EXPOSE_DEBUG_STATE:
        response_payload["canonical_state"] = state.to_dict()

    return jsonify(response_payload)



@app.route("/api/agents", methods=["GET"])
def get_agents():
    """Returns visual and operational metadata for all 4 specialized sub-agents."""
    return jsonify({
        "success": True,
        "agents": list_agent_metadata()
    })


@app.route("/api/leads", methods=["GET"])
def get_leads():
    """Admin endpoint to inspect captured commercial sales leads."""
    limit = int(request.args.get("limit", 50))
    leads = lead_repository.get_leads(limit=limit)
    return jsonify({
        "success": True,
        "count": len(leads),
        "leads": leads
    })


@app.route("/api/compare", methods=["POST"])
def api_compare():
    """Direct API endpoint for comparing approved catalogue products."""
    data = request.get_json(silent=True) or {}
    product_ids = data.get("product_ids") or []
    if not product_ids or not isinstance(product_ids, list):
        return jsonify({"error": "product_ids list required"}), 400

    from catalog.catalogue_resolver import resolve_product_model
    from catalog.comparison_engine import build_comparison
    resolved_prods = []
    for pid in product_ids:
        p = resolve_product_model(str(pid))
        if p:
            resolved_prods.append(p)

    if len(resolved_prods) < 2:
        return jsonify({"error": "At least two approved catalogue products must be resolved"}), 400

    comparison_data = build_comparison(resolved_prods)
    return jsonify({
        "success": True,
        "comparison_data": comparison_data
    })


if __name__ == "__main__":
    logger.info(f"Starting Customer Relations Assistant on http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
