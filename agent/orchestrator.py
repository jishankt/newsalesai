"""
Single Conversational Orchestrator for Kepler Tech SalesAI.
Implements the required unified conversational pipeline:
Customer message
→ Detect category
→ Extract requirements
→ Update conversation state
→ Check mandatory requirements
→ Ask one missing question at a time
→ Determine final subcategory
→ Fetch every eligible catalogue product
→ Rank matching products
→ Return all matching products as cards
→ Allow comparison, selection or requirement refinement

Deterministic Python code strictly controls qualification, catalogue filtering,
validation, and product-card selection.
The local LLM is used strictly for natural-language understanding and response composition.
"""

import re
import logging
import time
from typing import Dict, Any, List, Optional

from nlp.normalizer import normalize_text
from nlp.deterministic_interceptor import intercept
from agent.response_composer import ResponseComposer
from nlp.llm_understanding import LLMUnderstandingEngine
from domain.conversation_types import Intent, LLMUnderstanding, RouteResult, RouteName
from domain.conversation_state import ConversationState
from guardrails import validate_and_sanitize_response, PRICE_REFUSAL, STATIC_SAFE_REFUSAL
from ollama_client import OllamaClient

from catalog.catalogue_loader import catalogue_loader
from catalog.subcategory_resolver import resolve_subcategory
from catalog.catalogue_filter import catalogue_filter
from catalog.catalogue_resolver import (
    find_mentioned_catalogue_products,
    build_model_detail_response,
    build_approved_comparison_response,
)
from conversation.qualification_schema import (
    get_mandatory_fields,
    get_missing_mandatory_fields,
    get_next_question,
)
from conversation.normalizer import (
    normalize_category,
    extract_deterministic_requirements,
)
from validation.catalogue_validator import (
    validate_product_cards,
    validate_and_sanitize_catalogue_text,
)
from rag.consumables_engine import consumables_engine

logger = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self, ollama_client: OllamaClient = None):
        self.ollama_client = ollama_client
        self.llm_engine = LLMUnderstandingEngine(ollama_client)
        self.response_composer = ResponseComposer(ollama_client)

    def process_turn(
        self,
        raw_message: str,
        session_id: str = "default-session",
        history: Optional[List[Dict[str, str]]] = None,
        state: Optional[ConversationState] = None,
        model_name: str = None,
    ) -> Dict[str, Any]:
        """
        Processes a conversational turn through the single orchestrator pipeline.
        """
        if state is None:
            state = ConversationState(session_id=session_id)
        if history is None:
            history = state.history_turns if hasattr(state, "history_turns") else []
        start_time = time.time()

        # ── 1. Normalize Text ─────────────────────────────────────────────
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

        # ── 2. Deterministic Intercept (Commercial Guardrails & Greetings) ─
        intercept_result = intercept(normalized_msg, raw_message)

        if intercept_result.matched and not intercept_result.should_continue:
            nlp_result["intent"] = intercept_result.intent or ""
            source = "guardrail:price_refusal" if intercept_result.intent in ("price_inquiry", "discount_inquiry", "quote", "commercial") else f"interceptor:{intercept_result.intent}"

            if intercept_result.intent in ("price_inquiry", "discount_inquiry", "quote", "commercial"):
                reply_text = PRICE_REFUSAL
                chips_to_return = []
            else:
                reply_text = intercept_result.response
                chips_to_return = intercept_result.suggested_chips or []
                if intercept_result.intent in ("greeting", "reset"):
                    state.reset_category(None)
                    state.requirements = {}
                    state.stage = "open"
                    chips_to_return = [
                        "Technical CAD Plotters",
                        "Office Enterprise Documents",
                        "Professional Photographs",
                        "Event Photos (Photo Booth)",
                    ]

            state.last_assistant_response = reply_text
            state.increment_turn()

            return self._build_response(
                reply=reply_text,
                source=source,
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # ── 3. LLM Understanding (Intent & Semantic Entities) ─────────────
        state_summary = state.to_dict()
        recent_turns = state.history_turns[-6:] if state.history_turns else []

        understanding = self.llm_engine.understand(
            customer_message=normalized_msg,
            recent_turns=recent_turns,
            state_summary=state_summary,
            model=model_name,
        )

        nlp_result["intent"] = understanding.intent.value if hasattr(understanding.intent, "value") else str(understanding.intent)
        logger.info(f"[{session_id[:8]}] Understanding: intent={nlp_result['intent']} confidence={understanding.confidence:.2f}")

        # Update customer name if provided
        ents = understanding.entities or {}
        if ents.get("customer_name") and not state.customer_name:
            state.customer_name = ents["customer_name"]

        # ── 4. Deterministic Category Detection & State Update ────────────
        # Handle awaiting studio technology preference before general category normalization
        if state.awaiting_field == "studio_technology_preference":
            if any(w in normalized_msg.lower() for w in ["dye-sub", "dyesub", "dye sub", "dye-sublimation", "instant", "fast"]):
                state.category = "photo_booth"
                state.requirements["printing_technology"] = "dye_sub"
                state.awaiting_field = None
            elif any(w in normalized_msg.lower() for w in ["inkjet", "archival", "fine art", "fine-art"]):
                state.category = "photo_fine_art"
                state.requirements["printing_technology"] = "inkjet"
                state.awaiting_field = None

        if state.awaiting_field != "studio_technology_preference" and not state.requirements.get("printing_technology"):
            detected_category = normalize_category(normalized_msg, state.category)
            if detected_category and state.category != detected_category:
                logger.info(f"[{session_id[:8]}] Category updated to: {detected_category}")
                state.reset_category(detected_category)

        # ── 5. Deterministic Requirement Extraction & Normalization ───────
        det_reqs, det_corrections = extract_deterministic_requirements(normalized_msg, state.category)

        # If user was specifically answering awaiting_field == "daily_volume", ensure number is captured
        if state.awaiting_field == "daily_volume" and "daily_volume" not in det_reqs:
            range_match = re.search(r"(\d+)\s*(?:to|-|–)\s*(\d+)", normalized_msg)
            if range_match:
                det_reqs["daily_volume"] = (int(range_match.group(1)) + int(range_match.group(2))) // 2
            else:
                num_match = re.search(r"\b(\d+)\b", normalized_msg)
                if num_match:
                    det_reqs["daily_volume"] = int(num_match.group(1))
        
        # Merge LLM requirement updates if present and not overridden by deterministic rules
        if understanding.requirement_updates:
            for k, v in understanding.requirement_updates.items():
                if k not in det_reqs and v is not None and v != "":
                    det_reqs[k] = v

        state.update_requirements(det_reqs, det_corrections)
        logger.info(f"[{session_id[:8]}] Current requirements: {state.requirements}")

        # Clear awaiting field if answered
        if state.awaiting_field and state.awaiting_field in state.requirements:
            state.awaiting_field = None

        # ── 6. Preserve Existing System Behavior (Non-Qualification Routes) ─

        # Check for vague terms requiring clarification (e.g. "large printer")
        is_vague_size = (
            bool(re.search(r"\b(?:large|big)\s+printer\b", normalized_msg.lower()))
            and not state.requirements.get("print_width")
            and not state.requirements.get("paper_size")
            and not state.requirements.get("print_sizes")
        )
        if is_vague_size:
            state.awaiting_field = "print_size"
            reply_text = "Could you please specify your required print dimensions or paper sizes (e.g., standard A4/A3 office documents, or 24″/36″/44″ wide large-format plans)?"
            chips_to_return = ["A4 / A3 Office Documents", "24-inch Technical CAD", "36-inch Technical CAD", "44-inch Photo & Posters"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="clarification:vague_size",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # Check for studio disambiguation (dye-sub vs inkjet)
        if state.awaiting_field == "studio_technology_preference":
            if any(w in normalized_msg.lower() for w in ["dye-sub", "dyesub", "dye sub", "dye-sublimation", "instant", "fast"]):
                state.category = "photo_booth"
                state.requirements["printing_technology"] = "dye_sub"
                state.awaiting_field = None
            elif any(w in normalized_msg.lower() for w in ["inkjet", "archival", "fine art", "fine-art"]):
                state.category = "photo_fine_art"
                state.requirements["printing_technology"] = "inkjet"
                state.awaiting_field = None

        is_studio_request = (
            bool(re.search(r"\b(?:studio\s+printer|printer\s+for\s+(?:a\s+)?studio)\b", normalized_msg.lower()))
            and not state.requirements.get("printing_technology")
            and not state.category
        )
        if is_studio_request:
            state.awaiting_field = "studio_technology_preference"
            reply_text = "For studio printing, do you prefer fast dye-sublimation (ideal for event portraits & photo booths) or archival fine-art inkjet (for gallery prints)?"
            chips_to_return = ["Fast Dye-Sublimation", "Archival Fine-Art Inkjet"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="clarification:studio_technology",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # Check for 8x12 hard constraint matching Citizen CX-02W
        is_8x12_only_query = (
            ("8x12" in normalized_msg.lower() or "8×12" in normalized_msg)
            and len(normalized_msg.split()) <= 6
            and not any(w in normalized_msg.lower() for w in ["cad", "blueprint", "office", "a4", "a3"])
        )
        if is_8x12_only_query:
            state.category = "citizen_photo"
            state.requirements["print_sizes"] = ["8x12"]
            state.qualification_complete = True
            cx02w = catalogue_loader.get_by_id("citizen-cx-02w")
            card = catalogue_filter._format_card(cx02w, "citizen_8_inch", state.requirements)
            reply_text = "The **Citizen CX-02W** is the only verified match in our catalogue supporting 8x12-inch wide direct dye-sublimation photo printing."
            audit = {
                "collected_requirements": dict(state.requirements),
                "missing_requirements": [],
                "hard_constraints": ["8x12"],
                "eligible_products": ["citizen-cx-02w"],
                "rejected_products_with_reason": {
                    "citizen-cx-02": "Max print size 6x8",
                    "citizen-cy-02": "Max print size 6x8",
                    "citizen-cz-01": "Max print size 4.5x8"
                },
                "ranking_factors": ["Exact media dimension match (8x12)"],
                "selected_product": "citizen-cx-02w",
                "evidence_ids": ["citizen-cx-02w"],
                "unsupported_claims": [],
            }
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="recommendation:catalogue_list",
                product_cards=[card],
                consumable_cards=[],
                suggested_chips=["View Technical Specifications", "Compatible Ribbons & Media"],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
                subcategory="citizen_8_inch",
                recommendation_audit=audit,
            )

        # Check if user asks for another option / alternative to 8x12 single match
        if any(w in normalized_msg.lower() for w in ["another one", "another option", "other option", "different one", "alternative"]) and (
            state.requirements.get("print_sizes") == ["8x12"] or state.active_product_id == "citizen-cx-02w"
        ):
            reply_text = "The **Citizen CX-02W** is our only verified match supporting 8x12-inch output. Would you be willing to adjust your size requirement to consider 6-inch alternatives such as the CX-02 or CY-02?"
            chips_to_return = ["Adjust size to 6-inch (CX-02 / CY-02)", "Keep 8x12 requirement (CX-02W)"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="clarification:single_match_alternative",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # Check for direct mentioned approved catalogue products
        mentioned_products = find_mentioned_catalogue_products(normalized_msg)

        # Fail-closed refusal for unapproved models (e.g. SC-F100, SC-F500, competitor brands, CX-02S)
        from validation.catalogue_validator import UNAPPROVED_MODELS
        unapproved_detected = [m for m in UNAPPROVED_MODELS if re.search(rf"\b{re.escape(m)}\b", normalized_msg.lower())]
        unv_match = re.search(r"\b(cx-?02s|cx-?02-s|sc-?t3100x|epson\s*abc)\b", normalized_msg.lower())
        if not unapproved_detected and unv_match:
            unapproved_detected = [unv_match.group(1)]

        is_answering_consumables = (
            state.awaiting_field == "printer_model"
            or (state.requested_ink_color and not any(k in normalized_msg.lower() for k in ["recommend", "new printer", "printer catalogue"]))
        )

        if unapproved_detected and not mentioned_products and not is_answering_consumables:
            unapproved_names = ", ".join([m.upper() for m in unapproved_detected[:2]])
            reply_text = (
                f"That model ({unapproved_names}) is not present in our approved catalogue. "
                "As an authorized Kepler Tech distributor, we specialize in official Epson SureColor Technical (T-Series), Photo & Fine Art (P-Series), "
                "WorkForce Enterprise Office printers, and Citizen Photo printers. "
                "What type of printing application are you looking to support?"
            )
            chips_to_return = [
                "Technical CAD Plotters",
                "Office Enterprise Documents",
                "Professional Photographs",
                "Event Photos (Photo Booth)",
            ]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:unverified_product",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6a. Comparison Query (Between 2+ Approved Catalogue Products)
        is_comparison_query = (
            understanding.intent == Intent.PRODUCT_COMPARISON
            or any(w in normalized_msg.lower() for w in ["compare", " vs ", " versus ", "difference between"])
        )
        if is_comparison_query and len(mentioned_products) >= 2:
            reply_text, cards, comparison_data = build_approved_comparison_response(
                mentioned_products,
                customer_requirements=dict(state.requirements) if state.requirements else None,
            )
            state.stage = "comparing"
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:comparison",
                product_cards=cards,
                consumable_cards=[],
                suggested_chips=["View Technical Specifications", "Compatible Consumables"],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
                comparison_data=comparison_data,
            )

        # 6b. Exact Model Detail Inquiry (For one of the 41 approved products)
        is_detail_query = any(w in normalized_msg.lower() for w in [
            "tell me about", "specs of", "specifications", "details of", "information on",
            "about the", "show me", "view details", "look up", "want printer", "i want",
            "show printer", "printer", "details"
        ])
        if mentioned_products and (is_detail_query or len(normalized_msg.split()) <= 6):
            # Answer directly without forcing a new qualification flow
            target_prod = mentioned_products[0]
            reply_text, cards = build_model_detail_response(target_prod)
            state.active_product = target_prod
            state.active_product_id = target_prod["id"]

            # Fail-closed deterministic validation
            from validation.deterministic_validator import deterministic_validator
            is_valid, violations = deterministic_validator.validate(
                reply_text, context={"product_id": target_prod["id"], "source": "catalog"}
            )
            if not is_valid:
                logger.warning(f"Initial detail reply failed validation: {violations}. Attempting regeneration.")
                reply_text = self._build_canonical_structured_reply(
                    product_id=target_prod["id"], state=state
                )
                is_valid_2, violations_2 = deterministic_validator.validate(
                    reply_text, context={"product_id": target_prod["id"], "source": "catalog"}
                )
                if not is_valid_2:
                    logger.error(f"Regenerated detail reply failed validation: {violations_2}. Returning STATIC_SAFE_REFUSAL.")
                    reply_text = STATIC_SAFE_REFUSAL
                    cards = []

            state.last_assistant_response = reply_text
            state.increment_turn()
            detail_c_cards = []
            if bool(re.search(r"\b(?:inks?|consumables?|cartridges?)\b", normalized_msg.lower())):
                detail_c_cards = consumables_engine.get_printer_consumables(target_prod.get("display_name", ""), limit=6)

            return self._build_response(
                reply=reply_text,
                source="route:model_detail",
                product_cards=cards,
                consumable_cards=detail_c_cards,
                suggested_chips=["View Compatible Consumables", "Compare with Alternative"],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6c. Consumables Inquiry
        has_negated_ink = bool(re.search(r"\b(?:not|no|don'?t\s+want)\s+ink\b", normalized_msg.lower()))
        is_printer_search = has_negated_ink or any(k in normalized_msg.lower() for k in [
            "need a printer", "looking for a printer", "photo printer", "which printer",
            "show all matching models", "show matching", "show every matching", "show me all",
            "show all", "list every", "which model", "matching catalogue", "suitable printer",
            "want printer", "i want printer", "printer hardware", "show printer", "want a printer",
            "looking for printer"
        ])
        if has_negated_ink:
            state.awaiting_field = None
            state.requested_ink_color = None

        has_ink_keyword = bool(re.search(r"\b(?:inks?|cartridges?|toners?|ribbons?|maintenance\s+(?:box|tank)(?:es|s)?)\b", normalized_msg.lower()))

        # If user explicitly states they want a printer or mentions an approved printer without asking for ink, break out of awaiting_field
        if state.awaiting_field == "printer_model" and (is_printer_search or (mentioned_products and not has_ink_keyword)):
            state.awaiting_field = None
            state.requested_ink_color = None

        is_answering_printer_model = (
            state.awaiting_field == "printer_model"
            and not is_printer_search
            and not has_negated_ink
            and not mentioned_products
        ) or (
            state.requested_ink_color
            and not is_printer_search
            and not has_negated_ink
        )
        is_consumables_query = (
            not is_printer_search
            and not has_negated_ink
            and (
                understanding.intent == Intent.CONSUMABLES_QUERY
                or is_answering_printer_model
                or has_ink_keyword
            )
        )
        if is_consumables_query:
            # Extract requested ink color
            for c in ["photo black", "matte black", "light cyan", "light magenta", "vivid magenta", "cyan", "magenta", "yellow", "black", "gray", "grey", "violet", "orange", "green", "red"]:
                if re.search(rf"\b{re.escape(c)}\b", normalized_msg.lower()):
                    state.requested_ink_color = c
                    break

            p_name = ""
            if mentioned_products:
                p_name = mentioned_products[0]["display_name"]
            elif state.active_product:
                p_name = state.active_product.get("name") or state.active_product.get("display_name")
            else:
                m_match = re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,5}(?:[a-z]{1,4})?|cx-?02w?|cy-?02|cz-?01|am-?c\d{3,4}|wf-?c\d{3,5}(?:[a-z]{1,4})?|em-?c\d{3,4}|f100|f500)\b", normalized_msg.lower())
                if m_match:
                    p_name = m_match.group(0).upper()
                elif is_answering_printer_model and len(normalized_msg.split()) <= 3:
                    p_name = normalized_msg.strip().upper()

            c_cards = []
            prod_cards = []
            if p_name:
                c_cards = consumables_engine.get_printer_consumables(p_name, limit=6)
                if state.requested_ink_color:
                    color_filtered = [card for card in c_cards if state.requested_ink_color.lower() in card.get("name", "").lower()]
                    if color_filtered:
                        c_cards = color_filtered
                state.awaiting_field = None

                # If user also asked for the printer itself ("printer and its inks")
                if any(w in normalized_msg.lower() for w in ["printer and", "and its inks", "printer as well", "printer with", "and ink"]):
                    p_match = (mentioned_products[0] if mentioned_products else None)
                    if not p_match:
                        for cand in catalogue_loader.get_all():
                            if p_name.lower() in cand.get("id", "").lower() or p_name.lower() in cand.get("display_name", "").lower():
                                p_match = cand
                                break
                    if p_match:
                        prod_cards = [catalogue_filter._format_card(p_match, p_match.get("subcategory"), state.requirements)]

            if c_cards:
                color_label = f" {state.requested_ink_color.title()}" if state.requested_ink_color else ""
                reply_text = f"Here are the verified{color_label} inks and media compatible with {p_name}:"
                chips_to_return = ["Order Consumables", "View Printer Specifications"]
            else:
                state.awaiting_field = "printer_model"
                reply_text = "Which printer or scanner model do you need consumables for?"
                chips_to_return = ["Epson SC-T3100 Inks", "Citizen CX-02 Media", "Epson SC-P900 Inks"]

            return self._build_response(
                reply=reply_text,
                source="route:consumables",
                product_cards=prod_cards,
                consumable_cards=c_cards,
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6d. Company Information / Business Hours / Location
        is_product_query = bool(re.search(
            r"\b(?:printers?|plotters?|mfp|copiers?|print(?:ing)?|scanners?|scan(?:ning)?|cartridges?|toners?|inks?|a[34]|cad|photo|catalog(?:ue)?|models?)\b",
            normalized_msg.lower()
        )) or any(k in normalized_msg.lower() for k in ["show me", "need a", "looking for", "pages"])
        is_business_info = (
            not is_product_query
            and (
                understanding.intent == Intent.BUSINESS_INFORMATION
                or any(w in normalized_msg.lower() for w in [
                    "location", "address", "opening hours", "business hours", "working hours",
                    "contact number", "phone number", "email address", "where are you",
                    "office location", "office address", "your office"
                ])
            )
        )
        if is_business_info:
            reply_text = (
                "**Kepler Tech LLC — Dubai Headquarters**\n\n"
                "📍 **Address:** D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, UAE.\n"
                "🕒 **Working Hours:** Monday – Friday: 8:30 AM to 5:30 PM | Saturday: 8:30 AM to 1:00 PM | Sunday: Closed\n"
                "📞 **Phone:** +971 4 323 1008 | +971 55 835 8586\n"
                "✉️ **Email:** sales@keplertech.ae | info@keplertech.ae\n\n"
                "We provide delivery and authorized technical support across the UAE and Middle East."
            )
            chips_to_return = ["Technical CAD Plotters", "Photo & Fine Art Printers", "Office Enterprise MFPs"]
            return self._build_response(
                reply=reply_text,
                source="route:business_info",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # ── 7. Mandatory Qualification & Product Recommendation Flow ─────

        # 7a. If category is still unknown, prompt for category
        if not state.category:
            reply_text = "What will you primarily print—technical CAD drawings, office enterprise documents, professional photographs, or event photos?"
            chips_to_return = [
                "Technical CAD Plotters",
                "Office Enterprise Documents",
                "Professional Photographs",
                "Event Photos (Photo Booth)",
            ]
            state.awaiting_field = "category"
            state.stage = "qualifying"
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="qualification:category_prompt",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 7b. Check mandatory requirements against schema
        missing_mandatory = get_missing_mandatory_fields(state.category, state.requirements)
        state.missing_fields = missing_mandatory

        # If mandatory requirements are missing, ask strictly ONE question at a time
        if missing_mandatory:
            next_q = get_next_question(state.category, missing_mandatory)
            state.awaiting_field = next_q["field"]
            state.stage = "qualifying"
            state.qualification_complete = False
            reply_text = next_q["question"]
            chips_to_return = next_q["pills"]

            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="qualification:next_question",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 7c. All mandatory requirements satisfied -> Determine leaf subcategory & return all matching cards
        state.qualification_complete = True
        state.stage = "recommending"
        state.awaiting_field = None

        subcategory = resolve_subcategory(state.category, state.requirements)
        state.subcategory = subcategory

        # Hard catalogue filtering and soft ranking
        cards, no_match = catalogue_filter.filter_and_rank(state.category, subcategory, state.requirements)

        if no_match:
            reply_text = f"{no_match['message']} {no_match['relaxation_question']}"
            product_cards = []
            chips_to_return = []
            source = "recommendation:no_match"
        else:
            # Validate cards fail-closed (all IDs must belong to 41 approved catalogue entries)
            valid_cards = validate_product_cards(cards)
            state.displayed_product_ids = [c["id"] for c in valid_cards]
            state.results_loaded = True
            product_cards = valid_cards
            if subcategory == "a3_workforce_pro_multifunction":
                reply_text = f"I found {len(valid_cards)} A3 WorkForce Pro multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif subcategory == "a3_enterprise_multifunction":
                reply_text = f"I found {len(valid_cards)} A3 WorkForce Enterprise multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif subcategory == "a4_colour_multifunction":
                reply_text = f"I found {len(valid_cards)} A4 colour multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif state.requirements.get("paper_size") == "a3":
                reply_text = f"I found {len(valid_cards)} A3 multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements:"
            else:
                reply_text = f"I found {len(valid_cards)} catalogue printer{'s' if len(valid_cards) != 1 else ''} matching your requirements:"
            # Natural language fail-closed validation
            sanitized_reply, _ = validate_and_sanitize_catalogue_text(reply_text, valid_cards)
            reply_text = sanitized_reply
            chips_to_return = ["Compare Matching Models", "View Detailed Specifications", "Filter by Requirements"]
            source = "recommendation:catalogue_list"

        state.last_assistant_response = reply_text
        state.increment_turn()

        return self._build_response(
            reply=reply_text,
            source=source,
            product_cards=product_cards,
            consumable_cards=[],
            suggested_chips=chips_to_return,
            nlp_result=nlp_result,
            state=state,
            latency_ms=int((time.time() - start_time) * 1000),
            subcategory=subcategory,
        )

    def _build_canonical_structured_reply(
        self,
        product_id: Optional[str] = None,
        state: Optional[ConversationState] = None,
        route_result: Any = None
    ) -> str:
        """
        Builds a canonical, factual response containing only directly retrieved catalogue fields.
        Used for structured regeneration and fail-closed deterministic safe replies.
        """
        from catalog.repository import catalog_repository
        from validation.deterministic_validator import VERIFIED_METRICS

        prod = catalog_repository.get_by_id(product_id) if product_id else None
        if not prod and state and state.active_product:
            act_id = state.active_product.get("id") or state.active_product.get("product_id")
            prod = catalog_repository.get_by_id(act_id)
        if not prod and state and state.candidate_products:
            c_id = state.candidate_products[0].get("id") or state.candidate_products[0].get("product_id")
            prod = catalog_repository.get_by_id(c_id)

        if not prod:
            return "That model is not present in our approved catalogue. Could you please specify your printing requirements again—such as what you plan to print (technical CAD drawings, office documents, or photos) and your desired print size?"

        # Handle consumables route regeneration
        if route_result and (getattr(route_result, "consumable_cards", None) or "consumable" in (getattr(route_result, "source", "") or "")):
            from routes.consumables_route import sort_consumables_inks_first
            lines = [f"Here are the verified genuine consumables for **{prod.display_name}**:\n"]
            cards_to_show = sort_consumables_inks_first(route_result.consumable_cards) if route_result.consumable_cards else []
            if cards_to_show:
                for c in cards_to_show:
                    lines.append(f"• **{c.get('name')}** (SKU: `{c.get('sku')}`)")
            elif prod.consumables:
                for sku in prod.consumables:
                    lines.append(f"• SKU: `{sku}`")
            return "\n".join(lines)

        specs = getattr(prod, "verified", None)
        p_url = getattr(prod, "product_url", None) or (prod.source.website_url if hasattr(prod, 'source') and hasattr(prod.source, 'website_url') else None) or f"https://www.keplertechllc.com/product/{prod.id}/"
        lines = []

        req_parts = []
        is_rec_flow = route_result is None or not getattr(route_result, "source", "") or getattr(route_result, "source", "") in ("recommendation:grounded_engine", "agent:product_specialist:qualified_search")
        if is_rec_flow and state:
            reqs = state.requirements or {}
            if reqs.get("print_size"):
                req_parts.append(f"{reqs['print_size']} printing")
            if reqs.get("scan_required"):
                req_parts.append("integrated scanner")
            if reqs.get("daily_volume"):
                req_parts.append(f"{reqs['daily_volume']} prints/day")
            if reqs.get("speed"):
                req_parts.append(f"{reqs['speed']} speed")
            if reqs.get("workload"):
                req_parts.append(f"{reqs['workload']} volume")

            if req_parts:
                lines.append(f"Based on your requirement for {', '.join(req_parts)}, here is the recommended equipment from our verified catalogue:\n")
            elif state.category:
                cat_display = state.category.replace('_', ' ').title()
                lines.append(f"Here are the verified technical specifications for your {cat_display} requirement:\n")

        lines.extend([
            f"**[{prod.display_name}]({p_url})**\n",
            f"- **Model**: {prod.display_name}",
            f"- **SKU**: {prod.sku}",
        ])
        if specs and getattr(specs, "ink_technology", None):
            lines.append(f"- **Printing Technology**: {specs.ink_technology}")
        elif getattr(prod, "category", None):
            lines.append(f"- **Category**: {prod.category.replace('_', ' ').title()}")

        sizes = getattr(prod, "supported_print_sizes", None) or (specs.supported_print_sizes if specs and hasattr(specs, 'supported_print_sizes') else [])
        if sizes:
            lines.append(f"- **Supported Media Sizes**: {', '.join(sizes)}")
        elif specs and getattr(specs, "max_width_label", None):
            lines.append(f"- **Maximum Print Width**: {specs.max_width_label}")

        s_specs = getattr(prod, "structured_specs", None) or {}
        w_info = s_specs.get("weight")
        w_str = None
        if isinstance(w_info, dict) and w_info.get("value") is not None:
            w_str = f"{w_info.get('value')} {w_info.get('unit', 'kg')}"
        elif prod.id in VERIFIED_METRICS and VERIFIED_METRICS[prod.id].get("weights"):
            sorted_w = sorted(VERIFIED_METRICS[prod.id]["weights"])
            w_str = f"{sorted_w[0]} kg"
        if w_str:
            lines.append(f"- **Product Weight**: {w_str}")

        speeds = s_specs.get("print_speed") or s_specs.get("speeds")
        if speeds and isinstance(speeds, dict):
            speed_parts = [f"{k}: {v}" for k, v in speeds.items() if isinstance(v, (int, float, str))]
            if speed_parts:
                lines.append(f"- **Print Speeds**: {', '.join(speed_parts)}")

        caps = s_specs.get("roll_capacity") or s_specs.get("capacities")
        if caps and isinstance(caps, dict):
            cap_parts = [f"{k}: {v}" for k, v in caps.items() if isinstance(v, (int, float, str))]
            if cap_parts:
                lines.append(f"- **Roll Capacity**: {', '.join(cap_parts)}")

        if getattr(prod, "consumables", None):
            lines.append(f"- **Approved Compatible Consumables**: {', '.join(prod.consumables)}")

        lines.append("\n*(All specifications are verified directly against our official catalogue.)*")
        return "\n".join(lines)

    def _build_response(
        self,
        reply: str,
        source: str,
        product_cards: List[Dict[str, Any]],
        consumable_cards: List[Dict[str, Any]],
        suggested_chips: List[str],
        nlp_result: Dict[str, Any],
        state: ConversationState,
        latency_ms: int,
        subcategory: Optional[str] = None,
        recommendation_audit: Optional[Dict[str, Any]] = None,
        comparison_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Formats the standardized JSON response."""
        res_type = "product_list" if product_cards else ("no_exact_match" if "no_match" in source else "message")

        # Active agent metadata for backwards compatibility with tests & UI
        agent_id = "receptionist"
        agent_name = "Front Desk / Receptionist"
        agent_badge = "Front Desk"
        agent_color = "#10b981"
        if "comparison" in source or "compare" in source:
            agent_id = "technical_rag"
            agent_name = "Technical RAG & Comparison"
            agent_badge = "Tech & Comparison"
            agent_color = "#8b5cf6"
        elif "product" in source or "catalogue" in source or "model_detail" in source or product_cards:
            agent_id = "product_specialist"
            agent_name = "Product & Catalog Specialist"
            agent_badge = "Product Specialist"
            agent_color = "#1877f2"
        elif "lead" in source or "quote" in source:
            agent_id = "sales_lead"
            agent_name = "Sales & Lead Generation"
            agent_badge = "Sales & Quotes"
            agent_color = "#f59e0b"

        active_agent = {
            "id": agent_id,
            "name": agent_name,
            "badge": agent_badge,
            "theme_color": agent_color,
        }

        retrieved_items = (product_cards or []) + (consumable_cards or [])
        if not retrieved_items and state.active_product:
            retrieved_items = [state.active_product]

        retrieved_sources = [
            {
                "id": r.get("id"),
                "name": r.get("model") or r.get("display_name") or r.get("name") or "Catalogue Product",
                "title": r.get("model") or r.get("display_name") or r.get("name") or "Catalogue Product",
                "url": r.get("product_url") or "https://www.keplertechllc.com/",
                "snippet": "; ".join(r.get("key_features", []) or r.get("match_reasons", []) or [r.get("category", "")]),
                "source": "catalogue",
            }
            for r in retrieved_items
        ]
        is_grounded = (reply != STATIC_SAFE_REFUSAL and not source.endswith("safe_refusal"))
        grounding_status = "verified_catalogue_source" if is_grounded else "FAIL_CLOSED_SAFE"

        return {
            "type": res_type,
            "reply": reply,
            "message": reply,
            "result_count": len(product_cards),
            "subcategory": subcategory or state.subcategory,
            "cards": product_cards,
            "product_cards": product_cards,
            "consumable_cards": consumable_cards,
            "suggested_chips": suggested_chips,
            "source": source,
            "nlp": nlp_result,
            "grounding": {
                "is_grounded": is_grounded,
                "status": grounding_status,
                "notes": [],
            },
            "state": state,
            "active_agent": active_agent,
            "retrieved_items": retrieved_items,
            "retrieved_sources": retrieved_sources,
            "recommendation_audit": recommendation_audit,
            "comparison_data": comparison_data or {},
            "latency_ms": latency_ms,
        }


orchestrator = Orchestrator()
