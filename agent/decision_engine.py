"""
Decision Engine for Kepler Tech Conversational AI.
The LLM proposes an intent and action, but Python makes the final routing decision.
Enforces a deterministic 10-tier priority order:
1. Price and discount intercept -> RouteName.GUARDRAIL
2. Greeting, thanks and goodbye -> RouteName.SOCIAL
3. Company-information request -> RouteName.BUSINESS_INFO
4. Process/help question -> RouteName.CONVERSATION_HELP
5. Explicit product model -> RouteName.PRODUCT
6. Product comparison -> RouteName.COMPARISON
7. Consumable request -> RouteName.CONSUMABLES
8. Product discovery -> RouteName.PRODUCT or RouteName.QUALIFICATION
9. Answer to awaited qualification field -> RouteName.QUALIFICATION
10. Clarification -> RouteName.CLARIFICATION
"""

import re
import logging
from typing import Optional, List
from domain.conversation_types import (
    Intent, LLMUnderstanding, RouteDecision, RouteName,
    SOCIAL_INTENTS, PRODUCT_INTENTS,
)
from domain.conversation_state import ConversationState
from conversation.requirement_extractor import classify_category

logger = logging.getLogger("decision_engine")

HELP_PHRASES = [
    "can you help me",
    "how does this work",
    "what can you do",
    "help me choose",
    "help me select",
    "where should i start",
    "where do i start",
    "i don't understand specifications",
    "i dont understand specifications",
    "i don't understand printer specifications",
    "i dont understand printer specifications",
    "what can you help me with",
    "guide me",
    "how to choose",
    "how do i choose",
]

COMPANY_INFO_PHRASES = [
    "what products does kepler tech provide",
    "what products do you provide",
    "what does kepler tech provide",
    "products does kepler tech provide",
    "about kepler",
    "who is kepler",
    "what is kepler",
    "what brands do you",
    "what services do you",
    "delivery", "deliver", "shipping", "ship",
    "dubai", "where are you located", "where is your office", "location", "address",
    "office hours", "timings", "opening hours", "contact number", "phone number",
    "whatsapp", "email", "warranty", "amc", "service contract"
]

PRICE_KEYWORDS = [
    "price", "cost", "pricing", "rate", "rates", "quote", "quotation",
    "discount", "discounts", "bargain", "negotiat", "cheapest", "cheaper",
    "official rate", "payment terms"
]


def min_qualification_satisfied(state: ConversationState) -> bool:
    """Checks if minimum qualification requirements are satisfied."""
    if not state or not state.requirements:
        return False
    return bool(state.qualification_complete or len(state.requirements) >= 2)


def qualification_complete(state: ConversationState) -> bool:
    """Checks if full qualification is complete."""
    if not state:
        return False
    return bool(state.qualification_complete)


def decide(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteDecision:
    """
    Deterministic routing decision based on the strict 10-tier priority order.
    """
    intent = understanding.intent
    msg_lower = (raw_message or "").strip().lower()

    # ── Model Code & Specific Product Extraction ─────────────────────────
    model_matches = re.findall(
        r"\b(?:sc-?)?(?:[tpf]\d{3,5}[a-z0-9]*|ds-?\d{3,5}[a-z0-9]*|es-?\d{3,5}[a-z0-9]*|cx-?[0-9o]{1,2}[a-z0-9]*|cy-?[0-9o]{1,2}[a-z0-9]*|cz-?[0-9o]{1,2}[a-z0-9]*|am-?c\d{3,4}[a-z0-9]*|wf-?(?:c|m)?\d{3,5}[a-z0-9]*|em-?c\d{3,4}[a-z0-9]*|12000xl|f100|f500|op900(?:ii)?)\b",
        msg_lower
    )
    unique_models: List[str] = []
    for m in model_matches:
        clean = re.sub(r"[\s\-_]+", "", m.upper())
        if clean not in [re.sub(r"[\s\-_]+", "", u.upper()) for u in unique_models]:
            unique_models.append(m.upper())
    extracted_model = unique_models[0] if unique_models else None

    # Validate candidate model code against entities or catalog lookup
    model_code = None
    if extracted_model:
        model_code = extracted_model
    elif understanding.entities.get("model_code"):
        cand = str(understanding.entities["model_code"]).strip()
        generic_terms = {"cad printer", "printer", "scanner", "plotter", "copier", "inks", "ink", "paper", "media"}
        if cand.lower() not in generic_terms:
            from catalog.product_resolver import normalize_model_identifier
            cand_norm = normalize_model_identifier(cand)
            msg_norm = re.sub(r"[^a-z0-9]", "", msg_lower)
            if cand_norm and cand_norm in msg_norm:
                from rag.retriever import rag_retriever
                if rag_retriever.get_by_sku(cand) or rag_retriever.get_by_name(cand):
                    model_code = cand

    # ── Tier 1: Price and Discount Intercept ──────────────────────────────
    from guardrails import strip_negated_commercial
    neg_clean_msg = strip_negated_commercial(msg_lower)
    is_price_word = any(re.search(rf"\b{re.escape(w)}\b", neg_clean_msg) for w in PRICE_KEYWORDS)
    is_how_much = bool(re.search(r"\bhow much\b", neg_clean_msg)) and not any(non_dim in neg_clean_msg for non_dim in [
        "ink", "paper", "time", "weight", "capacity", "prints", "pages", "roll", "speed"
    ])
    is_price_query = is_price_word or is_how_much

    if is_price_query:
        return RouteDecision(
            route=RouteName.GUARDRAIL,
            reason="Price or commercial terms requested; quote via official sales channel only",
        )

    # Check for direct purchase intent on active product or consumable
    is_purchase_intent = any(k in msg_lower for k in [
        "i want to buy this", "want to buy this", "how to buy this", "ready to buy", "ready to purchase",
        "want to purchase this", "order this", "buy this", "place an order for this", "purchase this",
        "how can i buy this", "how can i buy", "how do i buy this", "how do i buy", "where can i buy this",
        "where to buy", "where can i buy", "how can i order this", "how to order this", "how do i order this",
        "can i buy this", "can i buy this online", "how to purchase this", "how can i purchase this"
    ]) or (
        (state.active_product is not None or getattr(state, "active_consumable", None) is not None) and any(k in msg_lower for k in [
            "i want to buy", "want to buy", "ready to buy", "ready to order", "how to buy", "how can i buy", "buy now", "order now"
        ])
    )
    if is_purchase_intent:
        return RouteDecision(
            route=RouteName.GUARDRAIL,
            reason="Customer expressed purchase intent on product/consumable; routing to Sales & Quotation Specialist",
        )

    # Check for user complaint when bot was off-target
    is_user_complaint_misunderstood = any(k in msg_lower for k in [
        "what i asked what you giving", "that's not what i asked", "thats not what i asked",
        "not what i asked", "i didn't ask for that", "i did not ask for that", "wrong answer"
    ])
    if is_user_complaint_misunderstood:
        return RouteDecision(
            route=RouteName.CLARIFICATION,
            reason="Customer indicated previous answer was off-target; asking for clarification",
        )

    # ── Tier 2: Greeting, Thanks, and Goodbye (Social) ────────────────────
    is_product_related = any(k in msg_lower for k in [
        "printer", "printers", "plotter", "plotters", "scanner", "scanners",
        "cad", "photo", "drawing", "drawings", "blueprint", "blueprints",
        "ink", "inks", "cartridge", "toner", "ribbon", "paper", "equipment", "machine"
    ])
    # Don't treat specification answers, numbers, or corrections as social
    has_spec_or_correction = bool(re.search(r"\b(a[0-4]|4x6|5x7|6x8|6x9|24|36|44|actually|instead|rather|change to|recommend now|yes|no)\b", msg_lower))
    is_answering_flow = bool(state.awaiting_field or state.category)

    is_pure_social = not is_product_related and not has_spec_or_correction and not (is_answering_flow and has_spec_or_correction) and (
        (intent in SOCIAL_INTENTS and not is_answering_flow) or
        msg_lower in [
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "thanks", "thank you", "bye", "goodbye", "see you", "have a nice day", "have a good day"
        ]
    )
    # Ensure greeting doesn't swallow a compound help or business question
    has_help_phrase = any(p in msg_lower for p in HELP_PHRASES)
    has_company_phrase = any(p in msg_lower for p in COMPANY_INFO_PHRASES)

    if is_pure_social and not has_help_phrase and not has_company_phrase and not model_code:
        return RouteDecision(
            route=RouteName.SOCIAL,
            reason="Social greeting, thanks, or goodbye",
        )

    # ── Tier 3: Company-Information Request ───────────────────────────────
    if intent == Intent.BUSINESS_INFORMATION or has_company_phrase:
        return RouteDecision(
            route=RouteName.BUSINESS_INFO,
            reason="Company information request",
        )

    # ── Tier 4: Process / Help Question ───────────────────────────────────
    if intent == Intent.CONVERSATION_HELP or has_help_phrase:
        return RouteDecision(
            route=RouteName.CONVERSATION_HELP,
            reason="Consultative guidance or process help requested",
        )

    # ── Consumables Flags Pre-Check ───────────────────────────────────────
    is_ink_negated = bool(re.search(r"\b(?:not|no|don't want|dont want)\s+(?:the\s+)?(?:ink|inks|cartridge|toner|consumable)\b", msg_lower))
    if is_ink_negated and state.category == "consumable":
        state.reset_category("photo_fine_art")

    is_ink_requested = not is_ink_negated and any(re.search(rf"\b{re.escape(ik)}\b", msg_lower) for ik in [
        "ink", "inks", "cartridge", "cartridges", "toner", "ribbon", "consumable", "consumables", "maintenance tank", "maintenance box", "paper and ribbon", "media"
    ])
    # Ink color follow-up when active printer or consumables route is active
    is_ink_color_followup = (
        bool(state.active_printer_for_consumables or state.active_route in ("consumable", "RouteName.CONSUMABLES"))
        and any(re.search(rf"\b{re.escape(c)}\b", msg_lower) for c in [
            "black", "cyan", "magenta", "yellow", "gray", "grey", "violet", "orange", "green", "red",
            "photo black", "matte black", "light cyan", "light magenta", "vivid magenta"
        ])
    )
    if is_ink_color_followup or state.awaiting_field == "printer_model" or (state.category == "consumable" and state.requested_ink_color):
        is_ink_requested = True

    # Distinguish hardware spec questions about ink (e.g. "does it use liquid ink cartridges?")
    is_spec_question_about_ink = any(phrase in msg_lower for phrase in [
        "does it use liquid ink", "use liquid ink", "liquid ink cartridges", "conventional liquid",
        "uses liquid ink", "uses ink cartridges"
    ])
    if is_spec_question_about_ink:
        is_ink_requested = False

    # ── Comparison Keywords & Multi-Model Check ──────────────────────────
    has_comparison_keyword = any(w in msg_lower for w in [
        "compare", " vs ", " versus ", "difference between", "differences between",
        "which is better", "which one is better", "show another one", "show another option", "compare them"
    ])
    is_multi_model_comparison = (len(unique_models) >= 2 or has_comparison_keyword)

    # If the inquiry is specifically about consumable compatibility / interchangeability across models
    is_consumable_cross_or_compat = any(k in msg_lower for k in ["media", "consumable", "consumables", "ribbon", "paper and ribbon"]) and any(k in msg_lower for k in ["used in", "use in", "interchangeable", "cross", "compatibility", "compatible", "another citizen", "another model", "correct", "should i use", "for 4x6 printing", "for 4×6 printing", "can you help", "verify"])
    if is_consumable_cross_or_compat:
        is_multi_model_comparison = False
        is_ink_requested = True

    # ── Tier 5: Explicit Product Model ────────────────────────────────────
    is_brochure_request = any(b in msg_lower for b in [
        "brochure", "brosure", "broucher", "brousher", "broshur", "brocher",
        "datasheet", "data sheet", "specsheet", "spec sheet",
        "download pdf", "pdf link", "give brochure", "send brochure",
        "give the brosure", "give the brochure", "product sheet", "technical sheet",
        "catalog pdf", "brochure link"
    ])

    if model_code and not is_multi_model_comparison and not is_ink_requested:
        if is_brochure_request:
            return RouteDecision(
                route=RouteName.PRODUCT,
                tool="get_brochure",
                tool_arguments={"product_identifier": model_code},
                reason=f"Brochure requested for product: {model_code}",
            )
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs",
            tool_arguments={"product_identifier": model_code},
            reason=f"Specific product requested: {model_code}",
        )

    # Check for pronoun or attribute inquiry on active product
    is_find_or_rec = any(w in msg_lower for w in [
        "find a", "find me", "looking for", "recommend a", "suggest a", "which printer",
        "which model", "need a printer", "want a printer", "show options"
    ])
    has_pronoun_ref = not is_find_or_rec and (
        any(w in msg_lower.split() for w in ["it", "this", "its", "that"]) or
        any(k in msg_lower for k in [
            "does it", "can it", "what size", "how fast", "specs", "specifications",
            "ribbon rewind", "print speed", "maximum width", "max width", "print technology",
            "resolution", "finishing options", "roll capacity"
        ])
    )
    if state.active_product and has_pronoun_ref and not is_ink_requested and not is_multi_model_comparison:
        if is_brochure_request:
            return RouteDecision(
                route=RouteName.PRODUCT,
                tool="get_brochure",
                tool_arguments={"product_identifier": state.active_product.get("name", "")},
                reason="Brochure requested for active product",
            )
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs",
            tool_arguments={"product_identifier": state.active_product.get("name", "")},
            reason="Question about active product via pronoun/attribute reference",
        )

    # ── Superlative / Cross-Catalog Spec Inquiries ───────────────────────
    is_superlative_query = (
        intent == Intent.PRODUCT_QUESTION
        or understanding.requested_action in ("answer_product_attribute", "answer_product_question")
        or any(k in msg_lower for k in [
            "which citizen printer is the fastest", "fastest citizen", "fastest printer",
            "which printer is the fastest", "fastest photo printer", "highest resolution",
            "fastest cad plotter", "most compact plotter"
        ])
        or any(k in msg_lower for k in [
            "business benefit", "benefit of each relevant feature", "explain the business benefit"
        ])
    )
    if is_superlative_query and not is_ink_requested and not is_multi_model_comparison:
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_product_specs",
            reason="Product question / superlative specification query",
        )

    # ── Tier 6: Product Comparison ────────────────────────────────────────
    is_comparison_query = is_multi_model_comparison or (
        intent == Intent.PRODUCT_COMPARISON and not is_ink_requested and not is_spec_question_about_ink
    )
    if is_comparison_query:
        return RouteDecision(
            route=RouteName.COMPARISON,
            tool="compare_products",
            reason="Product comparison request",
        )

    # ── Tier 7: Consumable Request ────────────────────────────────────────
    # Check if user is currently answering a consumable qualification prompt
    is_answering_consumable_qualification = (
        state.category == "consumable"
        and state.awaiting_field in ("printer_model", "ink_color")
        and not is_ink_negated
        and not any(w in msg_lower for w in ["not ink", "no ink", "printer only", "i want printer", "want the printer", "printer hardware"])
    )
    if is_answering_consumable_qualification:
        args = {}
        if model_code:
            args["printer_identifier"] = model_code
        elif raw_message:
            args["printer_identifier"] = raw_message.strip()
        return RouteDecision(
            route=RouteName.CONSUMABLES,
            tool="get_compatible_consumables" if args.get("printer_identifier") else None,
            tool_arguments=args,
            reason="Customer provided model for awaited consumables qualification",
        )

    # If asking for inks for an active product or pure consumable request without wanting the printer hardware itself
    has_printer_hardware_req = any(w in msg_lower for w in ["printer and its inks", "printer and inks", "printer and the inks"])
    if is_ink_requested and not has_printer_hardware_req:
        args = {}
        has_pronoun_to_active = any(p in msg_lower for p in ["for this", "for it", "for that", "this printer", "that printer", "does it use", "it use", "for it?"]) or bool(re.search(r"\b(?:it|this|that)\b", msg_lower))
        if has_pronoun_to_active and state.active_product:
            args["printer_identifier"] = state.active_product.get("name", "")
        elif model_code and not any(w in msg_lower for w in ["printer", "plotter", "machine", "hardware"]):
            args["printer_identifier"] = model_code
        elif state.active_printer_for_consumables:
            args["printer_identifier"] = state.active_printer_for_consumables
        elif state.active_product:
            args["printer_identifier"] = state.active_product.get("name", "")
        elif model_code:
            args["printer_identifier"] = model_code

        return RouteDecision(
            route=RouteName.CONSUMABLES,
            tool="get_compatible_consumables" if args.get("printer_identifier") else None,
            tool_arguments=args,
            reason="Consumables query for active product or specific supply",
        )

    # ── Tier 7: General Consumable Request ────────────────────────────────
    is_consumable_query = (
        intent == Intent.CONSUMABLES_QUERY
        or understanding.requested_action == "show_consumables"
        or is_ink_requested
        or (state.category == "consumable" and state.awaiting_field in ("printer_model", "ink_color"))
    )
    if is_consumable_query:
        args = {}
        has_pronoun_to_active = any(p in msg_lower for p in ["for this", "for it", "for that", "this printer", "that printer"])
        if model_code:
            args["printer_identifier"] = model_code
        elif has_pronoun_to_active and state.active_product:
            args["printer_identifier"] = state.active_product.get("name", "")
        elif state.active_printer_for_consumables:
            args["printer_identifier"] = state.active_printer_for_consumables
        elif state.active_product:
            args["printer_identifier"] = state.active_product.get("name", "")

        return RouteDecision(
            route=RouteName.CONSUMABLES,
            tool="get_compatible_consumables" if args.get("printer_identifier") else None,
            tool_arguments=args,
            reason="Consumables query or model clarification",
        )

    # ── Tier 8: Product Discovery & Category Switch ───────────────────────
    # Explicit recommendation request when qualification is satisfied
    rec_keywords = [
        "recommend now", "recommend", "show options", "show recommendations",
        "what do you recommend", "suggest options", "show me options",
        "give me options", "show products", "show printers",
        "show another", "another option", "other options", "show alternative"
    ]
    if any(k in msg_lower for k in rec_keywords) and min_qualification_satisfied(state):
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason="Explicit recommendation requested with qualification satisfied",
        )

    # ── Tier 7.5: Taxonomy / Photo Printer Types Overview Inquiry ────────
    is_photo_types_query = (
        any(k in msg_lower for k in [
            "types of photo", "photo printer types", "types have", "what types",
            "types of printer", "kinds of photo", "photo options", "photo lineup"
        ])
        or (("photo" in msg_lower or "printer" in msg_lower) and any(k in msg_lower for k in [
            "what are the types", "what types do you have", "what kinds do you have", "what categories", "options for photo"
        ]))
    ) and not any(w in msg_lower for w in ["i want to buy", "ready to buy", "place an order", "order this"])
    if is_photo_types_query:
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="get_photo_printer_types",
            reason="Customer inquiry regarding photo printer categories and types available",
        )

    # ── Tier 8: Product Discovery ─────────────────────────────────────────
    discovered_category = classify_category(raw_message)
    if not discovered_category and not state.category:
        llm_cat = understanding.entities.get("product_category")
        if llm_cat in ("technical_cad", "photo_fine_art", "photo_booth", "office_enterprise", "scanner"):
            discovered_category = llm_cat

    is_consultative = any(w in msg_lower for w in ["recommend", "suggest", "which printer", "what printer", "guide me", "help me choose"])
    if discovered_category:
        is_category_change = state.category != discovered_category
        if is_category_change:
            state.reset_category(discovered_category)

        if is_consultative and not min_qualification_satisfied(state):
            return RouteDecision(
                route=RouteName.QUALIFICATION,
                tool="ask_qualification_question",
                reason=f"Category {discovered_category} identified — consultative request requires qualification",
            )

        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason=f"Category {discovered_category} identified — routing directly to product search",
        )

    # Check for general printer discovery without category
    is_general_discovery = (
        intent == Intent.PRODUCT_DISCOVERY
        or bool(re.search(r"\b(?:want|buy|need|looking for|get|require|recommend)\b.*?\b(?:a\s*printer|aprinter|printers?|plotters?|equipment|machine)\b", msg_lower))
        or any(k in msg_lower for k in [
            "recommend a printer", "recommend something", "need some printing equipment",
            "printing equipment for my business", "need a printer", "looking for a printer",
            "select the right printer", "what printer", "which printer"
        ])
    )
    if is_general_discovery or state.category:
        return RouteDecision(
            route=RouteName.PRODUCT,
            tool="search_catalog",
            reason="Product discovery — routing directly to product search",
        )

    # ── Tier 10: Clarification / Fallback ─────────────────────────────────
    if intent in (Intent.UNCLEAR, Intent.OUT_OF_SCOPE):
        return RouteDecision(
            route=RouteName.CLARIFICATION,
            reason=f"Intent: {intent.value}",
        )

    logger.warning(f"Unhandled intent: {intent.value} — routing to clarification")
    return RouteDecision(
        route=RouteName.CLARIFICATION,
        reason=f"Unhandled intent: {intent.value}",
    )
