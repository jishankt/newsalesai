"""
Comparison Route for Kepler Tech Conversational AI.
Handles product comparison requests using the existing tool_executor.
"""

import logging
from domain.conversation_types import LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState
from agent.tool_executor import catalog_tool_executor
from rag.comparison_engine import detect_comparison_request, generate_comparison_response

logger = logging.getLogger("route:comparison")


def handle(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteResult:
    """Handle product comparison and superlative spec requests."""
    query = raw_message or ""

    # 1. Check if specific models or brand superlatives can be resolved from the query
    comp_detect = detect_comparison_request(query, {"intent": "PRODUCT_COMPARISON"})
    if comp_detect.get("is_comparison") and len(comp_detect.get("models", [])) >= 2:
        model_a = comp_detect["models"][0]
        model_b = comp_detect["models"][1]
        cards = [model_a, model_b]
        state.candidate_products = cards
        state.active_product = model_a

        comp_res = generate_comparison_response(model_a, model_b, query)
        return RouteResult(
            reply=comp_res["text"],
            product_cards=cards,
            source="tool:compare_products",
            needs_composition=False,
            evidence=cards,
        )

    # 2. Check if candidate products already exist in state
    if len(state.candidate_products) >= 2:
        model_a = state.candidate_products[0]
        model_b = state.candidate_products[1]
        cards = state.candidate_products[:2]

        comp_res = generate_comparison_response(model_a, model_b, query)
        return RouteResult(
            reply=comp_res["text"],
            product_cards=cards,
            source="tool:compare_products",
            needs_composition=False,
            evidence=cards,
        )

    # 3. Active product in state
    if state.active_product:
        return RouteResult(
            reply=f"The {state.active_product.get('name', '')} is an authorized system from Kepler Tech LLC. Would you like a direct spec comparison with another model?",
            product_cards=[],
            source="tool:compare_products",
            needs_composition=False,
        )

    # 4. General comparison overview
    return RouteResult(
        reply="Epson and Citizen serve distinct professional printing needs: Epson specializes in Large Format CAD plotters, Fine Art printers, and Enterprise WorkForce MFPs, whereas Citizen specializes in high-speed dye-sublimation photo printers for events and photo booths. Which solution would you like to explore?",
        suggested_chips=["CAD Plotters", "Photo Booth Printers", "Document Scanners"],
        product_cards=[],
        source="route:comparison",
        needs_composition=False,
    )

