"""
Decision Engine for Kepler Tech Conversational AI.
The LLM proposes an intent and action, but Python makes the final routing decision.
This ensures social messages never trigger product search, and invalid tool
requests are rejected before execution.
"""

import logging
from typing import Optional
from domain.conversation_types import (
    Intent, LLMUnderstanding, RouteDecision, RouteName,
    SOCIAL_INTENTS, PRODUCT_INTENTS,
)
from domain.conversation_state import ConversationState

logger = logging.getLogger("decision_engine")


def min_qualification_satisfied(state: ConversationState) -> bool:
    """Check if minimum requirements are met when customer explicitly asks to recommend now."""
    cat = state.category
    reqs = state.requirements
    if not cat:
        return False
    if cat in ("technical_cad", "photo_booth", "photo_fine_art"):
        return "print_size" in reqs
    if cat == "office_enterprise":
        return "speed" in reqs or "daily_volume" in reqs or "workload" in reqs
    if cat == "scanner":
        return "scanner_type" in reqs
    if cat == "consumable":
        return "printer_model" in reqs or state.active_printer_for_consumables is not None
    return True


def qualification_complete(state: ConversationState) -> bool:
    """Check if all consultative requirements are collected to automatically search for products."""
    cat = state.category
    reqs = state.requirements

    if not cat:
        return False

    if cat == "technical_cad":
        return "print_size" in reqs and "scan_required" in reqs and "daily_volume" in reqs

    if cat == "photo_booth":
        return "print_size" in reqs

    if cat == "photo_fine_art":
        return "print_size" in reqs

    if cat == "office_enterprise":
        return "speed" in reqs or "daily_volume" in reqs or "workload" in reqs

    if cat == "scanner":
        return "scanner_type" in reqs

    if cat == "consumable":
        return "printer_model" in reqs or state.active_printer_for_consumables is not None

    return False


def decide(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteDecision:
    """
    Deterministic routing decision based on LLM understanding, conversation state,
    and message context. The LLM's requested_action is a suggestion — this function validates and overrides.
    """
    intent = understanding.intent
    msg_lower = (raw_message or "").strip().lower()

    # ── Model Code & Specific Product Extraction ─────────────────────────
    import re
    model_match = re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3}[a-z]?|cx-?\d{2}|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?)\b", msg_lower)
    extracted_model = model_match.group(0).upper() if model_match else None

    # Validate candidate model code
    model_code = None
    if extracted_model:
        model_code = extracted_model
    elif understanding.entities.get("model_code"):
        cand = str(understanding.entities["model_code"]).strip()
        generic_terms = {"cad printer", "printer", "scanner", "plotter", "copier", "inks", "ink", "paper", "media"}
        if cand.lower() not in generic_terms:
            from rag.retriever import rag_retriever
            if rag_retriever.get_by_sku(cand) or rag_retriever.get_by_name(cand):
                model_code = cand

    # ── Consumables query ────────────────────────────────────────────────
    is_consumable_query = (
        intent == Intent.CONSUMABLES_QUERY or
        any(k in msg_lower for k in ["ink", "cartridge", "toner", "ribbon", "what ink", "which ink"])
    )
    if is_consumable_query:
        args = {}
        if model_code:
            args["printer_identifier"] = model_code
        elif state.active_product:
            args["printer_identifier"] = state.active_product.get("name", "")
        return RouteDecision(
            route=RouteName.CONSUMABLES,
            tool="get_compatible_consumables",
            tool_arguments=args,
            reason="Consumables query",
        )

    # ── PRIORITY 1: Product Comparison & Superlatives (Bypasses Qualification) ──
    comparison_keywords = [
        "compare", " vs ", " versus ", "which is better", "which is best",
        "which is fastest", "which is faster", "fastest", "faster", "highest speed",
        "quickest", "widest", "highest resolution", "largest width", "most compact",
        "difference between", "which citizen", "which epson", "which printer is faster",
        "which printer is fastest", "epson or citizen", "citizen or epson"
    ]
    if intent == Intent.PRODUCT_COMPARISON or any(w in msg_lower for w in comparison_keywords):
        return RouteDecision(
            route=RouteName.COMPARISON,
            tool="compare_products",
            reason="Product comparison or superlative spec query",
        )

    # ── PRIORITY 1b: Direct Product Attribute / Specification Questions ──
    has_pronoun_ref = (
        any(w in msg_lower.split() for w in ["it", "this", "its", "that"]) or
        any(k in msg_lower for k in ["does it", "can it", "what size", "how fast", "specs", "specifications"])
    )
    is_direct_attr_query = any(w in msg_lower for w in [
        "how fast", "what is the speed", "what speed", "print speed",
        "what width", "how wide", "what resolution", "specs of", "specifications of"
    ])

    if model_code:
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs",
            tool_arguments={"product_identifier": model_code},
            reason=f"Specific product requested: {model_code}",
        )

    if (state.active_product and has_pronoun_ref) or (state.active_product and is_direct_attr_query):
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs",
            tool_arguments={"product_identifier": state.active_product.get("name", "")},
            reason="Question about active product via pronoun/reference",
        )

    if intent == Intent.PRODUCT_QUESTION:
        args = {}
        if state.active_product:
            args["product_identifier"] = state.active_product.get("name", "")
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs" if state.active_product else None,
            tool_arguments=args,
            reason="Direct product question",
        )

    # ── Category Switch Detection (Consultative Workflow) ─────────────────
    new_category = None
    ent_cat = (understanding.entities.get("product_category") or "").strip().lower()
    if ent_cat in ["technical_cad", "photo_fine_art", "photo_booth", "office_enterprise", "scanner", "consumable"]:
        new_category = ent_cat

    if not new_category:
        if any(k in msg_lower for k in ["photo booth", "dye-sub", "citizen cx", "citizen cy", "instant photo"]):
            new_category = "photo_booth"
        elif any(k in msg_lower for k in ["photo fine art", "fine art", "gallery", "exhibition", "p900", "p700", "p5300", "p7500", "p9500"]):
            new_category = "photo_fine_art"
        elif any(k in msg_lower for k in ["cad", "plotter", "blueprint", "architect", "engineering", "technical drawing"]):
            new_category = "technical_cad"
        elif any(k in msg_lower for k in ["office printer", "workforce", "copier", "am-c4000", "am-c550", "office_enterprise", "business printer"]):
            new_category = "office_enterprise"
        elif not any(neg in msg_lower for neg in ["no scanner", "without scanner", "not scanner", "don't need scanner", "dont need scanner"]) and any(k in msg_lower for k in ["document scanner", "sheetfed scanner", "flatbed scanner", "standalone scanner", "dedicated scanner"]):
            new_category = "scanner"
        elif not state.category and not any(neg in msg_lower for neg in ["no scanner", "without scanner", "not scanner", "don't need scanner", "dont need scanner"]) and any(k in msg_lower for k in ["scanner", "document scan", "scanning"]):
            new_category = "scanner"

    is_explicit_switch = "switch" in msg_lower or ("actually" in msg_lower and any(kw in msg_lower for kw in ["need", "want", "switch", "printer", "plotter", "booth", "photo", "cad", "office"]))
    if new_category and (not state.category or is_explicit_switch):
        if not (state.category == "technical_cad" and new_category == "scanner"):
            state.reset_category(new_category)
            return RouteDecision(
                route=RouteName.QUALIFICATION,
                reason=f"Category set/switched to {new_category}",
            )

    # General photo printer query when category is not yet decided
    if not state.category and any(k in msg_lower for k in ["photo printer", "photo printers", "photo printing", "photos", "photo", "pictures", "picture printer"]):
        return RouteDecision(
            route=RouteName.QUALIFICATION,
            reason="Photo category qualification required",
        )

    # ── Explicit recommendation request when minimum qualification is satisfied ──
    rec_keywords = ["recommend now", "recommend", "show options", "show recommendations",
                    "what do you recommend", "suggest options", "show me options",
                    "give me options", "show products", "show printers",
                    "show another", "show another one", "another option", "other options", "show alternative"]
    is_rec_request = any(k in msg_lower for k in rec_keywords)

    if is_rec_request and min_qualification_satisfied(state):
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason="Explicit recommendation requested",
        )

    if intent == Intent.PRODUCT_DISCOVERY and state.category and qualification_complete(state):
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason="Qualification complete — ready to search",
        )

    # ── Social intents → social route (NEVER enters product search) ──────
    if intent in SOCIAL_INTENTS:
        return RouteDecision(
            route=RouteName.SOCIAL,
            reason=f"Social intent: {intent.value}",
        )

    # ── Direct answer to awaiting field (volume, size, etc.) ────────────
    vol_cand = re.search(r"\b\d+\b", msg_lower)
    if state.awaiting_field and (
        vol_cand or
        any(s in msg_lower for s in ["a0", "a1", "a2", "a3", "4x6", "6x8", "24\"", "36\""]) or
        understanding.dialogue_act.value in ("informing", "answering_question")
    ):
        return RouteDecision(
            route=RouteName.QUALIFICATION,
            reason=f"Answering awaiting field: {state.awaiting_field}",
        )

    # ── Confirmation/Rejection while awaiting a field ────────────────────
    if intent == Intent.CONFIRMATION and state.awaiting_field:
        return RouteDecision(
            route=RouteName.QUALIFICATION,
            reason="Confirmation while awaiting field answer",
        )

    if intent == Intent.REJECTION and state.awaiting_field:
        return RouteDecision(
            route=RouteName.QUALIFICATION,
            reason="Rejection while awaiting field answer",
        )

    # ── Correction → update state and re-evaluate ────────────────────────
    if intent == Intent.CORRECTION:
        return RouteDecision(
            route=RouteName.QUALIFICATION,
            reason="Correction of previous answer",
        )

    # ── Business information ─────────────────────────────────────────────
    if intent == Intent.BUSINESS_INFORMATION or any(w in msg_lower for w in ["delivery", "deliver", "shipping", "ship", "address", "location", "dubai", "where are you", "office hours", "timings", "opening hours", "contact number", "phone number", "whatsapp", "email", "what brands", "what services", "amc", "warranty"]):
        return RouteDecision(
            route=RouteName.BUSINESS_INFO,
            reason="Business information request",
        )

    # ── Troubleshooting ──────────────────────────────────────────────────
    if intent == Intent.TROUBLESHOOTING:
        return RouteDecision(
            route=RouteName.SUPPORT,
            reason="Troubleshooting request",
        )

    # ── Product discovery ────────────────────────────────────────────────
    if intent == Intent.PRODUCT_DISCOVERY:
        # Check if we need more qualification first
        if not state.category:
            return RouteDecision(
                route=RouteName.QUALIFICATION,
                reason="No category set yet — need qualification",
            )
        if not qualification_complete(state):
            return RouteDecision(
                route=RouteName.QUALIFICATION,
                reason="Qualification incomplete",
            )
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason="Qualification complete — ready to search",
        )

    # ── Unclear / out of scope ───────────────────────────────────────────
    if intent in (Intent.UNCLEAR, Intent.OUT_OF_SCOPE):
        return RouteDecision(
            route=RouteName.CLARIFICATION,
            reason=f"Intent: {intent.value}",
        )

    # ── Language change ──────────────────────────────────────────────────
    if intent == Intent.LANGUAGE_CHANGE:
        return RouteDecision(
            route=RouteName.SOCIAL,
            reason="Language change request",
        )

    # ── Fallback ─────────────────────────────────────────────────────────
    logger.warning(f"Unhandled intent: {intent.value} — routing to clarification")
    return RouteDecision(
        route=RouteName.CLARIFICATION,
        reason=f"Unhandled intent: {intent.value}",
    )
