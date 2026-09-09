"""
New Orchestrator for Kepler Tech Conversational AI.
Wires together the full pipeline:
  Normalizer → Interceptor → LLM Understanding → Decision Engine → Route Handler → Response

Replaces the monolithic ai_orchestrator.py with a clean, testable pipeline.
"""

import logging
import time
from typing import Dict, Any, List

from nlp.normalizer import normalize_text
from nlp.deterministic_interceptor import intercept
from agent.response_composer import ResponseComposer
from nlp.response_validator import validate_response
from nlp.llm_understanding import LLMUnderstandingEngine
from agent.decision_engine import decide
from agent.route_registry import get_handler
from domain.conversation_types import (
    Intent, LLMUnderstanding, RouteName, RouteResult,
)
from domain.conversation_state import ConversationState
from guardrails import validate_and_sanitize_response
from nlp.grounding_validator import validate_grounding
from ollama_client import OllamaClient

logger = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self, ollama_client: OllamaClient = None):
        self.ollama_client = ollama_client
        self.llm_engine = LLMUnderstandingEngine(ollama_client)
        self.response_composer = ResponseComposer(ollama_client)

    def process_turn(
        self,
        raw_message: str,
        session_id: str,
        history: List[Dict[str, str]],
        state: ConversationState,
        model_name: str = None,
    ) -> Dict[str, Any]:
        """
        Process a single conversational turn through the full pipeline.
        Returns the same response format as the old ai_orchestrator for compatibility.
        """
        start_time = time.time()

        # ── 1. Normalize ─────────────────────────────────────────────────
        norm_result = normalize_text(raw_message)
        normalized_msg = norm_result["normalized_text"]

        nlp_result = {
            "raw_text": norm_result["raw_text"],
            "clean_text": norm_result["clean_text"],
            "normalized_text": normalized_msg,
            "corrections": norm_result["corrections_applied"],
            "intent": "",
            "brands": [],
            "categories": [],
            "models": [],
            "sizes": norm_result["canonical_sizes"],
        }

        # ── 2. Deterministic Intercept ───────────────────────────────────
        intercept_result = intercept(normalized_msg, raw_message)

        if intercept_result.matched and not intercept_result.should_continue:
            nlp_result["intent"] = intercept_result.intent or ""
            source = "guardrail_rule" if intercept_result.intent in ("price_inquiry", "discount_inquiry") else f"interceptor:{intercept_result.intent}"
            
            # Never spam product recommendation cards during price/discount inquiries or general FAQs
            cards_to_return = []
            if intercept_result.intent in ("greeting", "reset"):
                state.candidate_products = []
                state.active_product = None
                state.requirements = {}
                state.category = None
                state.stage = "open"

            return self._build_response(
                reply=intercept_result.response,
                source=source,
                product_cards=cards_to_return,
                consumable_cards=[],
                suggested_chips=[],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )


        # ── 3. LLM Understanding ────────────────────────────────────────
        state_summary = state.to_dict()
        recent_turns = state.history_turns[-6:] if state.history_turns else []

        understanding = self.llm_engine.understand(
            customer_message=raw_message,
            recent_turns=recent_turns,
            state_summary=state_summary,
            model=model_name,
        )

        nlp_result["intent"] = understanding.intent.value
        logger.info(f"[{session_id[:8]}] Understanding: intent={understanding.intent.value} "
                     f"confidence={understanding.confidence:.2f} action={understanding.requested_action}")

        # ── 3b. Apply customer name and category from entities ───────────
        if understanding.entities.get("customer_name") and not state.customer_name:
            state.customer_name = understanding.entities["customer_name"]

        ent_cat = (understanding.entities.get("product_category") or "").strip().lower()
        if ent_cat in ["technical_cad", "photo_fine_art", "photo_booth", "office_enterprise", "scanner", "consumable"]:
            if not state.category or any(w in raw_message.lower() for w in ["switch", "actually", "instead", "change"]):
                state.reset_category(ent_cat)

        # ── 4. Decision Engine ───────────────────────────────────────────
        decision = decide(understanding, state, raw_message=raw_message)
        logger.info(f"[{session_id[:8]}] Decision: route={decision.route.value} "
                     f"tool={decision.tool} reason={decision.reason}")

        state.active_route = decision.route.value
        state.last_intent = understanding.intent.value

        # ── 5. Route Handler ─────────────────────────────────────────────
        handler = get_handler(decision.route)
        route_result = RouteResult()

        if handler:
            # Pass raw_message for routes that need it
            try:
                if decision.route in (RouteName.PRODUCT, RouteName.BUSINESS_INFO, RouteName.QUALIFICATION, RouteName.CONSUMABLES, RouteName.COMPARISON):
                    route_result = handler.handle(understanding, state, raw_message=raw_message)
                else:
                    route_result = handler.handle(understanding, state)
            except Exception as e:
                logger.error(f"Route handler error: {e}", exc_info=True)
                route_result = RouteResult(
                    reply="I apologize for the issue. Could you please rephrase your question?",
                    source="route:error",
                )

        # ── 5b. Handle qualification-ready sentinel ──────────────────────
        if route_result.reply == "__READY_FOR_SEARCH__":
            # Qualification is complete — trigger product search
            from routes import product_route
            route_result = product_route.handle(understanding, state, raw_message=raw_message)

        # ── 6. Clarification fallback ────────────────────────────────────
        if decision.route == RouteName.CLARIFICATION or not route_result.reply:
            route_result = RouteResult(
                reply="I'd like to help — could you tell me a bit more about what you're looking for?",
                suggested_chips=[],
                source="route:clarification",
            )

        # ── 6b. Natural Response Composition ─────────────────────────────
        if route_result.needs_composition:
            composed_reply = self.response_composer.compose_response(
                customer_message=raw_message,
                route_result=route_result,
                state=state,
                active_route=decision.route,
                model_name=model_name,
            )
        else:
            composed_reply = route_result.reply

        # ── 7. Validate, Sanitize & Ground ──────────────────────────────
        val_result = validate_response(
            response=composed_reply,
            previous_response=state.last_assistant_response,
            context_intent=understanding.intent.value,
        )
        candidate_text = val_result.sanitized_response or composed_reply

        sanitized = validate_and_sanitize_response(candidate_text, normalized_msg)
        grounding_result = validate_grounding(sanitized, normalized_msg, nlp_result)

        # ── 8. Update state ──────────────────────────────────────────────
        state.last_assistant_response = grounding_result["sanitized_response"]
        state.last_dialogue_act = understanding.dialogue_act.value
        state.increment_turn()

        latency_ms = int((time.time() - start_time) * 1000)

        return self._build_response(
            reply=grounding_result["sanitized_response"],
            source=route_result.source,
            product_cards=route_result.product_cards,
            consumable_cards=route_result.consumable_cards,
            suggested_chips=route_result.suggested_chips,
            nlp_result=nlp_result,
            state=state,
            grounding_result=grounding_result,
            latency_ms=latency_ms,
        )

    def _build_response(
        self,
        reply: str,
        source: str,
        product_cards: list,
        consumable_cards: list,
        suggested_chips: list,
        nlp_result: dict,
        state: ConversationState,
        grounding_result: dict = None,
        latency_ms: int = 0,
    ) -> Dict[str, Any]:
        """Build the standardized response dict (compatible with old orchestrator)."""
        if grounding_result is None:
            grounding_result = {
                "sanitized_response": reply,
                "is_grounded": True,
                "status": "INTERCEPTED",
                "notes": [],
            }

        return {
            "reply": grounding_result.get("sanitized_response", reply),
            "source": source,
            "product_cards": product_cards,
            "consumable_cards": consumable_cards,
            "suggested_chips": suggested_chips,
            "retrieved_items": (product_cards or []) + (consumable_cards or []),
            "grounding": {
                "is_grounded": grounding_result.get("is_grounded", True),
                "status": grounding_result.get("status", "OK"),
                "notes": grounding_result.get("notes", []),
            },
            "nlp": nlp_result,
            "state": state,
            "metadata": {
                "latency_ms": latency_ms,
                "fallback_used": False,
            },
        }


# Global singleton (client injected in app.py)
orchestrator = Orchestrator()
