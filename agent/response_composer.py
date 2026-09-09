"""
Response Composer for Kepler Tech Conversational AI.
Transforms evidence, route results, and conversational context into
natural, professional customer-facing messages using local LLM composition
with deterministic fallback.
"""

import logging
from typing import Dict, Any, List, Optional

from domain.conversation_types import RouteResult, RouteName
from domain.conversation_state import ConversationState
from ollama_client import OllamaClient
from prompts.response_prompt import build_response_messages
from nlp.response_validator import validate_response

logger = logging.getLogger("response_composer")


class ResponseComposer:
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama_client = ollama_client

    def compose_response(
        self,
        customer_message: str,
        route_result: RouteResult,
        state: ConversationState,
        active_route: RouteName,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Compose a natural response.
        If route is deterministic or Ollama is unavailable or composed output fails
        validation, safely fallback to route_result.reply.
        """
        # 1. Deterministic bypass: Guardrail refusals, reset, or empty replies
        if not route_result.reply:
            return ""

        if not route_result.needs_composition:
            return route_result.reply

        # Certain routes or sources shouldn't be re-composed by LLM
        if (
            route_result.source.startswith("interceptor:")
            or route_result.source == "guardrail:price"
            or route_result.source == "guardrail:discount"
            or route_result.source == "route:qualification"
            or route_result.source == "tool:compare_products"
            or active_route == RouteName.QUALIFICATION
            or active_route == RouteName.BUSINESS_INFO
            or active_route == RouteName.COMPARISON
        ):
            return route_result.reply

        # 2. If no Ollama client is provided or online, use deterministic template
        if not self.ollama_client:
            return route_result.reply

        # 3. Assemble evidence dictionary for LLM grounding
        evidence: Dict[str, Any] = {
            "route": active_route.value if hasattr(active_route, "value") else str(active_route),
            "base_response_template": route_result.reply,
            "product_count": len(route_result.product_cards),
        }

        if route_result.product_cards:
            evidence["top_products"] = [
                {
                    "name": p.get("name"),
                    "sku": p.get("sku"),
                    "category": p.get("category"),
                    "print_size_width": p.get("width"),
                    "speed": p.get("speed"),
                    "ink_technology": p.get("ink_technology"),
                    "features": p.get("features", [])[:3],
                    "intended_use": p.get("intended_usage") or p.get("intended_use") or p.get("description", "")[:250],
                }
                for p in route_result.product_cards[:3]
            ]

        if route_result.evidence:
            evidence["detailed_evidence"] = route_result.evidence

        if route_result.consumable_cards:
            evidence["consumables"] = [
                {
                    "name": c.get("name"),
                    "type": c.get("type"),
                }
                for c in route_result.consumable_cards[:4]
            ]

        # 4. Build prompt messages
        messages = build_response_messages(
            customer_message=customer_message,
            evidence=evidence,
            recent_turns=state.history_turns[-4:] if state.history_turns else [],
            customer_name=state.customer_name,
            qualification_question=state.pending_question,
        )

        # 5. Call Ollama /api/chat compose
        try:
            comp_res = self.ollama_client.compose(messages=messages, model=model_name)
            if comp_res.get("success") and comp_res.get("response"):
                composed_text = comp_res["response"].strip()

                # Validate composed response
                val = validate_response(
                    response=composed_text,
                    previous_response=state.last_assistant_response,
                    context_intent=state.last_intent,
                )

                if val.valid:
                    logger.info(f"Composed natural reply via LLM ({comp_res.get('latency_ms')}ms)")
                    return val.sanitized_response
                else:
                    logger.warning(
                        f"Composed reply failed validation: {val.violations}. Falling back to template."
                    )
        except Exception as e:
            logger.warning(f"Error during response composition: {e}. Falling back to template.")

        # Safe fallback
        return route_result.reply
