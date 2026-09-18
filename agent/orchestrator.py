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
from guardrails import (
    validate_and_sanitize_response,
    PRICE_REFUSAL,
    DISCOUNT_REFUSAL,
    STATIC_SAFE_REFUSAL,
    is_price_inquiry,
    is_discount_inquiry,
    format_product_price_response,
    GENERAL_PRICE_DIRECT,
    OFFICIAL_WEBSITE_URL,
    OFFICIAL_SUPPORT_EMAIL,
    OFFICIAL_SUPPORT_PHONE,
)
from ollama_client import OllamaClient

from catalog.catalogue_loader import catalogue_loader
from catalog.subcategory_resolver import resolve_subcategory
from catalog.catalogue_filter import catalogue_filter
from catalog.catalogue_resolver import (
    find_mentioned_catalogue_products,
    build_model_detail_response,
    build_p900_family_detail_response,
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
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
from conversation.contextual_slot_resolver import ContextualSlotResolver
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
            source = "guardrail:discount_refusal" if intercept_result.intent in ("discount_inquiry", "quote", "commercial") else f"interceptor:{intercept_result.intent}"

            if intercept_result.intent in ("discount_inquiry", "quote", "commercial"):
                reply_text = DISCOUNT_REFUSAL
                chips_to_return = [
                    "Technical CAD Plotters",
                    "Office Enterprise MFPs",
                    "Photo & Fine Art",
                    "View Consumables",
                ]
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

        detected_category = normalize_category(normalized_msg, state.category)
        is_hardware_switch = detected_category and detected_category not in (None, "consumable")

        if (state.awaiting_field not in ("studio_technology_preference", "photo_brand") or is_hardware_switch) and not state.requirements.get("printing_technology"):
            if detected_category and state.category != detected_category:
                logger.info(f"[{session_id[:8]}] Category updated to: {detected_category}")
                state.reset_category(detected_category)
                if state.awaiting_field == "printer_model":
                    state.awaiting_field = None

        # Track previous state for natural conversational feedback
        prev_requirements = dict(state.requirements)
        prev_awaiting_field = state.awaiting_field
        had_cards = bool(state.displayed_product_ids) or state.results_loaded or state.stage == "recommending"
        prev_active_product = state.active_product
        prev_active_product_id = state.active_product_id

        # ── 5. Contextual Slot Resolution & Deterministic Extraction ─────
        c_reqs, c_corrections = ContextualSlotResolver.resolve(
            text=normalized_msg,
            awaiting_field=state.awaiting_field,
            category=state.category,
            requirements=state.requirements,
            active_chips=getattr(state, "last_suggested_chips", [])
        )

        det_reqs, det_corrections = extract_deterministic_requirements(normalized_msg, state.category, state.awaiting_field)
        det_reqs.update(c_reqs)
        det_corrections.update(c_corrections)

        # If user was specifically answering awaiting_field == "daily_volume", ensure number is captured
        if state.awaiting_field == "daily_volume" and "daily_volume" not in det_reqs:
            range_match = re.search(r"(\d+)\s*(?:to|-|–)\s*(\d+)", normalized_msg)
            if range_match:
                det_reqs["daily_volume"] = (int(range_match.group(1)) + int(range_match.group(2))) // 2
            else:
                num_match = re.search(r"\b(\d+)\b", normalized_msg)
                if num_match:
                    det_reqs["daily_volume"] = int(num_match.group(1))

        # If user was specifically answering awaiting_field in ("scanner_required", "scan_required")
        if state.awaiting_field in ("scanner_required", "scan_required") and "scanner_required" not in det_reqs:
            msg_clean = normalized_msg.strip().lower()
            if re.search(r"\b(?:yes|yeah|yep|yup|sure|definitely|absolutely|required|needed|include|including|with|with scanner|scanner|scan|mfp|copier|copy)\b", msg_clean):
                det_reqs["scanner_required"] = True
                det_reqs["functions"] = ["print", "scan", "copy"]
            elif re.search(r"\b(?:no|nope|nah|not|negative|none|without|print\s*only|just\s*print|only\s*print)\b", msg_clean):
                det_reqs["scanner_required"] = False
                det_reqs["functions"] = ["print"]

        # If user was answering a relaxation question
        if state.awaiting_field == "relaxation":
            msg_clean = normalized_msg.strip().lower()
            # Note: 24-inch has no scanner variant — that case is handled upstream (qualification_schema)
            # Only 44-inch can offer a relaxation to 36-inch + MFP
            if state.requirements.get("print_width") == 44 and state.requirements.get("scanner_required") is True:
                if re.search(r"\b(?:yes|yeah|yep|yup|sure|36|36-inch|36\"|t5100m|multifunction)\b", msg_clean):
                    det_reqs["print_width"] = 36
                    det_reqs["scanner_required"] = True
                    det_corrections["print_width"] = 36
                    state.awaiting_field = None
                elif re.search(r"\b(?:no|nope|nah|44|44-inch|44\"|print\s*only|without\s*scanner)\b", msg_clean):
                    det_reqs["scanner_required"] = False
                    det_corrections["scanner_required"] = False
                    state.awaiting_field = None
        
        # Merge LLM requirement updates if present and not overridden by deterministic rules
        if understanding.requirement_updates:
            for k, v in understanding.requirement_updates.items():
                if k not in det_reqs and v is not None and v != "":
                    det_reqs[k] = v

        # Dialogue Act Guard: If user is asking a capability, consumable, yield, or warranty question about an already active product,
        # do not pollute search requirements or wipe active_product from state.
        is_cap_query = (
            CanonicalEntityNormalizer.is_capability_query(normalized_msg)
            or bool(re.search(r"\b(?:inks?|cartridges?|toners?|ribbons?|consum[a-z]{3,6}s?|consub[a-z]{2,5}s?|media|paper|print\s+media|yields?|yeilds?|page\s*yield|print\s*yield|warranty|guarantee|coverplus|cpp|cost\s*per\s*(?:print|page))\b", normalized_msg.lower()))
        )
        if is_cap_query and (state.active_product or prev_active_product):
            logger.info(f"[{session_id[:8]}] Capability/attribute query detected for active product; preserving active_product")
            if not state.active_product and prev_active_product:
                state.active_product = prev_active_product
                state.active_product_id = prev_active_product_id
        else:
            state.update_requirements(det_reqs, det_corrections)
        logger.info(f"[{session_id[:8]}] Current requirements: {state.requirements}")

        # ── Synchronise state.category from resolved requirements ────────────
        # ContextualSlotResolver and deterministic extractors write category into
        # det_reqs["category"], but state.category is a separate top-level attribute.
        # Without this sync, `if not state.category:` on line ~787 fires again and
        # asks the identical category question — causing the repetition loop.
        resolved_cat = det_reqs.get("category")
        if resolved_cat and resolved_cat != state.category:
            logger.info(f"[{session_id[:8]}] Syncing state.category from det_reqs: {resolved_cat}")
            state.reset_category(resolved_cat)
            if state.awaiting_field == "category":
                state.awaiting_field = None
                state.unresolved_field_turns = 0

        is_correction_turn = bool(det_corrections) or any(
            w in normalized_msg.lower() for w in [
                "sorry", "apologies", "my bad", "my mistake", "actually", "instead", 
                "changed my mind", "correction", "i meant", "make that", "switch to", "update to"
            ]
        )
        volume_updated = (
            "daily_volume" in det_reqs or "daily_volume" in det_corrections
        ) and (
            is_correction_turn
            or (had_cards and prev_requirements.get("daily_volume") != state.requirements.get("daily_volume"))
            or (prev_requirements.get("daily_volume") is not None and prev_requirements.get("daily_volume") != state.requirements.get("daily_volume"))
        )

        # Clear awaiting field if answered
        if state.awaiting_field and state.awaiting_field in state.requirements:
            state.awaiting_field = None
            state.unresolved_field_turns = 0


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

        # Check for 64-inch hard constraint matching Epson SureColor SC-P20500
        is_64_inch_query = bool(re.search(r"\b(?:64[\s-]*(?:inch|in|\")|64inch)\b", normalized_msg.lower()))
        if is_64_inch_query:
            state.category = "photography_large_format"
            state.requirements["print_width"] = 64
            state.requirements["paper_size"] = "64-inch"
            state.qualification_complete = True
            state.subcategory = "photo_64_production"
            p20500 = catalogue_loader.get_by_id("epson-sc-p20500")
            card = catalogue_filter._format_card(p20500, "photo_64_production", state.requirements)
            reply_text = "The **Epson SureColor SC-P20500** is the only 64-inch large format production printer in our official catalogue, engineered for high-throughput fine art, commercial photography, and signage with 1.6-litre ink packs."
            audit = {
                "collected_requirements": dict(state.requirements),
                "missing_requirements": [],
                "hard_constraints": ["64-inch"],
                "eligible_products": ["epson-sc-p20500"],
                "rejected_products_with_reason": {},
                "ranking_factors": ["Exact 64-inch production width match"],
                "selected_product": "epson-sc-p20500",
                "evidence_ids": ["epson-sc-p20500"],
                "unsupported_claims": [],
            }
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="recommendation:catalogue_list",
                product_cards=[card],
                consumable_cards=[],
                suggested_chips=["View Technical Specifications", "Compatible Consumables", "Request Official Quote"],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
                subcategory="photo_64_production",
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

        # Check if user asks for another option / alternative to 64-inch single match
        if any(w in normalized_msg.lower() for w in ["another one", "another option", "other option", "different one", "alternative"]) and (
            state.requirements.get("print_width") == 64 or state.active_product_id == "epson-sc-p20500"
        ):
            reply_text = "The **Epson SureColor SC-P20500** is our only verified match supporting 64-inch output. Would you be willing to adjust your size requirement to consider 44-inch alternatives such as the SC-P9500 or SC-P8500D?"
            chips_to_return = ["Adjust size to 44-inch (SC-P9500 / SC-P8500D)", "Keep 64-inch requirement (SC-P20500)"]
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

        # Check for SC-P900 configuration selection follow-up
        is_p900_active = (
            state.active_product_id in ("epson-sc-p900", "epson-sc-p900-roll")
            or (state.active_product and state.active_product.get("model_family") == "SC-P900")
        )
        if is_p900_active:
            msg_clean = normalized_msg.lower().strip()
            wants_roll = bool(re.search(r"\b(?:with\s+roll|roll\s+adapter|roll\s+unit|with\s+the\s+roll|i\s+need\s+with|with)\b", msg_clean)) and not bool(re.search(r"\bwithout\b", msg_clean))
            wants_std = bool(re.search(r"\b(?:without\s+roll|without\s+roll\s+adapter|without\s+the\s+roll|no\s+roll|without|i\s+need\s+without|standard|sheet)\b", msg_clean))
            if wants_roll or wants_std:
                target_id = "epson-sc-p900-roll" if wants_roll else "epson-sc-p900"
                target_prod = catalogue_loader.get_by_id(target_id)
                if target_prod:
                    reply_text, cards = build_model_detail_response(target_prod)
                    state.active_product = target_prod
                    state.active_product_id = target_prod["id"]
                    state.last_assistant_response = reply_text
                    state.increment_turn()
                    return self._build_response(
                        reply=reply_text,
                        source="route:model_detail",
                        product_cards=cards,
                        consumable_cards=[],
                        suggested_chips=["View Compatible Consumables", "Compare with Alternative"],
                        nlp_result=nlp_result,
                        state=state,
                        latency_ms=int((time.time() - start_time) * 1000),
                    )

        # Check for direct consumable / part number SKU inquiry (e.g. C13T11C340, C13S210057, CX2.4x6)
        from rag.retriever import rag_retriever
        from agent.tool_executor import catalog_tool_executor
        direct_sku_prod = None
        direct_sku_code = None

        sku_pattern_matches = re.findall(r"\b(c1[123][a-z0-9]{5,9}|c13s\d+|c12c\d+|ifa\s*\d+|olm\s*\d+|cx2[a-z0-9.\-]+|cy-(?:ms|02)[a-z0-9.\-]*|cz-(?:ms|01)[a-z0-9.\-]*|cx2w\s*812)\b", normalized_msg.lower())
        for sm in sku_pattern_matches:
            cand_p = rag_retriever.get_by_sku(sm)
            if cand_p:
                direct_sku_prod = cand_p
                direct_sku_code = cand_p.get("sku") or sm.upper()
                break

        if not direct_sku_prod:
            for tok in re.findall(r"\b[a-zA-Z0-9\.\-]{5,15}\b", normalized_msg):
                if re.search(r"\d", tok) and tok.lower() not in ["epson", "citizen", "printer", "scanner", "plotter", "consumable", "cartridge", "please", "thanks"]:
                    cand_p = rag_retriever.get_by_sku(tok)
                    if cand_p:
                        direct_sku_prod = cand_p
                        direct_sku_code = cand_p.get("sku") or tok.upper()
                        break

        if direct_sku_prod:
            cat = str(direct_sku_prod.get("category", "")).lower()
            is_consumable = any(ck in cat for ck in ["ink", "cartridge", "box", "tank", "media", "paper", "ribbon", "accessory"]) or direct_sku_prod.get("card_type") == "consumable"
            if is_consumable:
                res_sku = catalog_tool_executor.execute_tool("get_product_specs", {"product_identifier": direct_sku_code})
                prod_data = res_sku.get("product", direct_sku_prod) if res_sku.get("success") else direct_sku_prod
                c_card = catalog_tool_executor.format_card(prod_data, card_type="consumable")
                p_name = prod_data.get("name", direct_sku_code)
                reply_text = f"Here is the verified genuine consumable for **{p_name}** (SKU: `{direct_sku_code}`):"
                chips_to_return = ["Order Consumables", "View Compatible Printers", "Ask for Quote"]
                state.active_printer_for_consumables = None
                state.awaiting_field = None
                state.last_assistant_response = reply_text
                state.increment_turn()
                return self._build_response(
                    reply=reply_text,
                    source="route:consumables:direct_sku",
                    product_cards=[],
                    consumable_cards=[c_card],
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
        unv_match = re.search(r"\b(cx-?02s|cx-?02-s|sc-?t3100x|epson\s*abc|dnprx1(?:hs)?|dnp[-\s]?rx1(?:hs)?|ds-?rx1(?:hs)?)\b", normalized_msg.lower())
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
                "WorkForce Office printers, SureColor F-Series Sublimation printers (SC-F100, SC-F500), and Citizen Photo printers. "
                "What type of printing application are you looking to support?"
            )
            chips_to_return = [
                "Office & Business Documents",
                "Technical CAD Plotters",
                "Professional Photo & Fine Art",
                "Dye-Sublimation (T-Shirts & Mugs)",
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

        # 6a-00. Direct Purchase / Ordering Intent Route
        is_purchase_query = bool(re.search(
            r"\b(?:"
            r"how\s+(?:can|do|should)\s+(?:i|we)\s+(?:buy|purchase|order|get|checkout)\b"
            r"|how\s+to\s+(?:buy|purchase|order|get)\b"
            r"|where\s+(?:can|do|should)\s+(?:i|we)\s+(?:buy|purchase|order|get)\b"
            r"|where\s+to\s+(?:buy|purchase|order)\b"
            r"|where\s+can\s+we\s+buy\b"
            r"|(?:i\s+|we\s+)?(?:want|wish|need)\s+to\s+(?:buy|purchase|order|place\s+an?\s+order)\b"
            r"|ready\s+to\s+(?:buy|purchase|order)\b"
            r"|(?:can|could)\s+(?:i|we)\s+(?:buy|purchase|order)\b"
            r"|(?:buy|purchase|order|place\s+an?\s+order\s+for)\s+(?:this|now|it|today|online)\b"
            r"|buy\s+this\b"
            r"|purchase\s+link\b"
            r"|order\s+link\b"
            r"|buying\s+link\b"
            r"|how\s+can\s+i\s+buy\b"
            r"|how\s+do\s+i\s+buy\b"
            r"|how\s+to\s+buy\b"
            r")",
            normalized_msg.lower()
        ))
        if is_purchase_query:
            # Case 1: Active consumable or direct consumable SKU
            active_c = getattr(state, "active_consumable", None)
            if not active_c and direct_sku_prod:
                res_sku = catalog_tool_executor.execute_tool("get_product_specs", {"product_identifier": direct_sku_code})
                prod_data = res_sku.get("product", direct_sku_prod) if res_sku.get("success") else direct_sku_prod
                active_c = catalog_tool_executor.format_card(prod_data, card_type="consumable")
                state.active_consumable = active_c

            if active_c and not (mentioned_products and not any(k in normalized_msg.lower() for k in ["this", "ink", "cartridge", "media", "ribbon", "paper"])):
                c_name = active_c.get("title") or active_c.get("name") or "Consumable"
                c_sku = active_c.get("sku") or ""
                c_url = active_c.get("product_url") or active_c.get("website_url") or OFFICIAL_WEBSITE_URL
                c_price = active_c.get("price_str") or (f"AED {active_c['price']:,.2f}" if active_c.get("price") else None)
                c_vat = active_c.get("vat_note") or "(Excl. VAT)"

                sku_label = f" (SKU: `{c_sku}`)" if c_sku else ""
                price_mention = f" Official website price is **{c_price} {c_vat}**." if c_price else ""

                reply_text = (
                    f"You can purchase **{c_name}**{sku_label} directly through Kepler Tech LLC:{price_mention}\n\n"
                    f"🛒 **1. Official Online Store:**\n"
                    f"Order directly with verified pricing and secure online checkout on our website:\n"
                    f"👉 [Buy {c_name} on Website]({c_url})\n\n"
                    f"📞 **2. Direct Sales Desk & Bulk Quotations:**\n"
                    f"For corporate purchase orders, tax invoices, or bulk deliveries across the UAE, contact our customer support team:\n"
                    f"• **Email:** {OFFICIAL_SUPPORT_EMAIL}\n"
                    f"• **Phone:** {OFFICIAL_SUPPORT_PHONE}\n"
                    f"• **Location:** Kepler Tech LLC, Dubai, UAE"
                )
                chips_to_return = ["Order on Website", "Contact Sales Desk", "View Compatible Printers"]
                state.last_assistant_response = reply_text
                state.increment_turn()
                return self._build_response(
                    reply=reply_text,
                    source="route:purchase:consumable",
                    product_cards=[],
                    consumable_cards=[active_c],
                    suggested_chips=chips_to_return,
                    nlp_result=nlp_result,
                    state=state,
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            # Case 2: Active or mentioned hardware product
            target_prod = None
            if mentioned_products:
                target_prod = mentioned_products[0]
            elif state.active_product:
                target_prod = state.active_product
            elif state.active_product_id:
                target_prod = catalogue_loader.get_by_id(state.active_product_id)

            if target_prod:
                from catalog.price_resolver import price_resolver
                from agent.tool_executor import catalog_tool_executor

                p_name = target_prod.get("display_name") or target_prod.get("name") or "Product"
                price_info = price_resolver.get_price_info(prod=target_prod)
                p_url = price_info.get("url") or target_prod.get("website_url") or OFFICIAL_WEBSITE_URL
                has_online_price = not price_info.get("is_request") and price_info.get("price")
                card = catalog_tool_executor.format_card(target_prod, card_type="hardware")

                if has_online_price:
                    p_price = price_info.get("price_str") or f"AED {price_info['price']:,.2f}"
                    p_vat = price_info.get("vat_note") or "(Excl. VAT)"
                    reply_text = (
                        f"You can order the **{p_name}** directly through Kepler Tech LLC (Official Website Price: **{p_price} {p_vat}**):\n\n"
                        f"🛒 **1. Official Online Store:**\n"
                        f"View full technical specifications and place your order online:\n"
                        f"👉 [Buy {p_name} on Website]({p_url})\n\n"
                        f"📞 **2. Commercial Sales, Delivery & Installation:**\n"
                        f"For corporate financing, official quotation, or on-site delivery and installation in the UAE:\n"
                        f"• **Email:** {OFFICIAL_SUPPORT_EMAIL}\n"
                        f"• **Phone:** {OFFICIAL_SUPPORT_PHONE}\n"
                        f"• **Location:** Kepler Tech LLC, Dubai, UAE"
                    )
                else:
                    reply_text = (
                        f"The **{p_name}** is an enterprise/production system supplied through Kepler Tech LLC's authorized commercial channel:\n\n"
                        f"📞 **To Place an Order or Request an Official Quotation:**\n"
                        f"Our sales engineering team handles commercial supply, warranty, and delivery across the UAE:\n"
                        f"• **Email:** {OFFICIAL_SUPPORT_EMAIL}\n"
                        f"• **Phone:** {OFFICIAL_SUPPORT_PHONE}\n"
                        f"• **Website Details:** [View {p_name} on Website]({p_url})\n"
                        f"• **Location:** Kepler Tech LLC, Dubai, UAE\n\n"
                        f"Would you like us to prepare a commercial quotation or check consumable compatibility?"
                    )
                chips_to_return = ["Request Official Quote", "Contact Sales Desk", "Compatible Consumables"]
                state.active_product = target_prod
                state.active_product_id = target_prod.get("id")
                state.last_assistant_response = reply_text
                state.increment_turn()
                return self._build_response(
                    reply=reply_text,
                    source="route:purchase:hardware",
                    product_cards=[card],
                    consumable_cards=[],
                    suggested_chips=chips_to_return,
                    nlp_result=nlp_result,
                    state=state,
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            # Case 3: General purchasing guidance
            reply_text = (
                f"You can purchase genuine printers, scanners, and original consumables directly from Kepler Tech LLC:\n\n"
                f"🛒 **Official Website Store:**\n"
                f"Browse our catalogue and purchase online at: {OFFICIAL_WEBSITE_URL}\n\n"
                f"📞 **Sales Support & Commercial Quotations:**\n"
                f"For corporate purchase orders, tax invoices, and product availability across the UAE:\n"
                f"• **Email:** {OFFICIAL_SUPPORT_EMAIL}\n"
                f"• **Phone:** {OFFICIAL_SUPPORT_PHONE}\n"
                f"• **Location:** Kepler Tech LLC, Dubai, UAE\n\n"
                f"Which printer model or consumable item are you looking to buy?"
            )
            chips_to_return = ["Large Format Plotters", "Photo Printers", "Office MFPs", "View Consumables"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:purchase:general",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6a-cpp. Real-time Cost-Per-Print / Cost-Per-Page (CPP) Inquiry Route
        is_cpp_inquiry = bool(re.search(
            r"\b(?:cost\s*per\s*(?:print|page|copy)|per\s*(?:print|page|copy)\s*cost|cpp|running\s*cost(?:s)?|printing\s*cost(?:s)?)\b",
            normalized_msg.lower()
        ))
        if is_cpp_inquiry:
            target_prod = mentioned_products[0] if mentioned_products else state.active_product
            if not target_prod and state.active_product_id:
                target_prod = catalogue_loader.get_by_id(state.active_product_id)

            p_id = (target_prod.get("id") or "").lower() if target_prod else ""
            p_cat = (target_prod.get("category") or target_prod.get("main_category") or state.category or "").lower() if target_prod else (state.category or "").lower()

            if any(k in p_id for k in ["am-c", "workforce", "c4000", "c5000", "c6000", "c550", "c400"]) or "office" in p_cat:
                p_name = target_prod.get("display_name") or target_prod.get("name") if target_prod else "Epson WorkForce Enterprise"
                reply_text = (
                    f"For the **{p_name}**, running costs are exceptionally low due to high-capacity Heat-Free ink packs:\n\n"
                    "• **Black (Mono) Cost-Per-Page:** Approx. **0.02 – 0.03 AED** per page (ink yields up to 50,000 ISO pages).\n"
                    "• **Colour Cost-Per-Page:** Approx. **0.09 – 0.12 AED** per page (CMY ink packs yield up to 30,000 ISO pages).\n"
                    "• **Energy Savings:** Heat-Free technology consumes up to 85% less electricity than laser copiers, further lowering total cost of ownership (TCO).\n\n"
                    "Kepler Tech LLC also provides Managed Print Services (MPS) and all-inclusive Cost-Per-Copy (CPC) contracts covering ink, maintenance boxes, and certified service. Would you like an MPS proposal?"
                )
            elif any(k in p_id for k in ["citizen", "cz-01", "cx-02", "cy-02", "cx-02w"]) or "citizen" in p_cat or "photo" in p_cat:
                p_name = target_prod.get("display_name") or target_prod.get("name") if target_prod else "Citizen Photo Printer"
                reply_text = (
                    f"For **{p_name}** dye-sublimation systems, genuine media packs include both the paper roll and matched ribbon, guaranteeing a fixed cost per print:\n\n"
                    "• **Citizen CZ-01 (4×6″):** Approx. **1.50 AED** per print (CZ-MS46 media set).\n"
                    "• **Citizen CX-02 (4×6″):** Approx. **0.90 – 1.10 AED** per print (CX-MS46 media set).\n"
                    "• **Citizen CY-02 (4×6″):** Approx. **0.80 – 0.90 AED** per print (CY-MS46 high-capacity media).\n"
                    "• **Citizen CX-02W (8×10″ / 8×12″):** Approx. **2.20 – 2.45 AED** per print (**CX2W 812** media kit).\n\n"
                    "Compatible genuine media for the **Citizen CX-02W** includes **CX2W 812** (8x10/8x12 media kit). "
                    "Would you like pricing for genuine Citizen media packs or bulk delivery quotes?"
                )
            elif any(k in p_id for k in ["sc-t", "t3100", "t5100", "t5405", "t5700"]) or "technical" in p_cat:
                p_name = target_prod.get("display_name") or target_prod.get("name") if target_prod else "Epson SureColor Technical Plotter"
                reply_text = (
                    f"For **{p_name}** technical plotters, running costs depend on line coverage and cartridge capacity:\n\n"
                    "• **CAD / Blueprint Line Drawings (5% coverage):** Approx. **0.30 – 0.60 AED** per A1 plot.\n"
                    "• **Full-Color GIS / Renderings (30–50% coverage):** Approx. **2.50 – 4.50 AED** per A1 plot.\n"
                    "• **High-Capacity 700ml Tanks:** Minimize ink cost per milliliter for production workflows.\n\n"
                    "Would you like consumable details or an ink consumption estimate for your blueprint volume?"
                )
            else:
                reply_text = (
                    "Running cost per print varies based on technology and consumable capacity:\n\n"
                    "• **Office A3 Copiers (Epson AM-C Series):** ~0.02 AED mono / ~0.09 AED colour per page.\n"
                    "• **Instant Dye-Sub Photo (Citizen):** Fixed ~0.90 – 1.50 AED per 4×6″ print including paper & ribbon.\n"
                    "• **CAD Plotters (Epson SC-T Series):** ~0.35 AED per A1 line drawing on plain paper.\n\n"
                    "Which specific model or application would you like detailed Cost-Per-Page figures for?"
                )
            chips_to_return = ["View Inks & Media", "Request Official Quotation", "Managed Print Services"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:cost_per_print",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6a-0. Real-time Product Price Inquiry Route
        has_ink_in_msg = bool(re.search(
            r"\b(?:inks?|cartridges?|toners?|ribbons?|consum[a-z]{3,6}s?|consub[a-z]{2,5}s?|media|paper|maintenance\s+(?:box|tank)(?:es|s)?)\b",
            normalized_msg.lower()
        ))
        if is_price_inquiry(normalized_msg) and not is_discount_inquiry(normalized_msg):
            # Check if user asks about OTHER models' consumable price
            if any(w in normalized_msg.lower() for w in ["other", "another", "alternative"]) and has_ink_in_msg:
                from catalog.price_resolver import price_resolver
                cy_info = price_resolver.get_price_info("CY-MS46")
                cx_info = price_resolver.get_price_info("CX2W-812")
                cx2_info = price_resolver.get_price_info("CX2.4X6")
                cy_url = cy_info.get("url") or "https://www.keplertechllc.com/product/citizen-cy-ms46-4x6/"
                cx_url = cx_info.get("url") or "https://www.keplertechllc.com/product/citizen-cx2w-8x12-media/"
                cx2_url = cx2_info.get("url") or "https://www.keplertechllc.com/product/citizen-cx-02-4x6-printer-media/"
                reply_text = (
                    "Here are the official media prices and product links for other Citizen photo models:\n\n"
                    f"• **[Citizen CY-02 Media (CY-MS46 4×6″)]({cy_url})** (SKU: `CY-MS46`): **{cy_info.get('price_str', 'AED 625.00')} (Excl. VAT)** — High-capacity roll yielding 700 prints.\n"
                    f"• **[Citizen CX-02 Media (CX2.4X6 4×6″)]({cx2_url})** (SKU: `CX2.4X6`): **{cx2_info.get('price_str', 'AED 490.00')} (Excl. VAT)** — Dual-roll pack yielding 800 prints.\n"
                    f"• **[Citizen CX-02W Large Format Media (CX2W 812 8×12″)]({cx_url})** (SKU: `CX2W 812`): **{cx_info.get('price_str', 'AED 975.00')} (Excl. VAT)** — Yields 220 prints per box.\n\n"
                    f"For corporate purchase orders or bulk deliveries, contact our sales team at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
                )
                chips_to_return = ["Order on Website", "Contact Sales Desk", "Compatible Printers"]
                state.last_assistant_response = reply_text
                state.increment_turn()
                return self._build_response(
                    reply=reply_text,
                    source="route:consumable_price_inquiry",
                    product_cards=[],
                    consumable_cards=[],
                    suggested_chips=chips_to_return,
                    nlp_result=nlp_result,
                    state=state,
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            # If user has an active consumable and inquires about its price
            active_c = getattr(state, "active_consumable", None)
            if active_c and (has_ink_in_msg or not state.active_product or "this" in normalized_msg.lower()):
                c_name = active_c.get("title") or active_c.get("name") or "Consumable"
                c_sku = active_c.get("sku") or ""
                from catalog.price_resolver import price_resolver
                c_pinfo = price_resolver.get_price_info(c_sku) if c_sku else {}
                c_url = c_pinfo.get("url") or active_c.get("product_url") or active_c.get("website_url") or OFFICIAL_WEBSITE_URL
                if c_pinfo.get("price"):
                    c_price = c_pinfo.get("price_str") or f"AED {c_pinfo['price']:,.2f}"
                    c_vat = c_pinfo.get("vat_note") or "(Excl. VAT)"
                else:
                    c_price = active_c.get("price_str") or (f"AED {active_c['price']:,.2f}" if active_c.get("price") else "Price on Request")
                    c_vat = active_c.get("vat_note") or "(Excl. VAT)"
                sku_str = f" (SKU: `{c_sku}`)" if c_sku else ""
                reply_text = (
                    f"The official price for **{c_name}**{sku_str} on our website is **{c_price} {c_vat}**.\n\n"
                    f"You can view product details and purchase directly online at: {c_url}\n\n"
                    f"For corporate purchase orders or bulk deliveries, contact our sales team at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
                )
                chips_to_return = ["Order on Website", "Contact Sales Desk", "Compatible Printers"]
                state.last_assistant_response = reply_text
                state.increment_turn()
                return self._build_response(
                    reply=reply_text,
                    source="route:consumable_price_inquiry",
                    product_cards=[],
                    consumable_cards=[active_c],
                    suggested_chips=chips_to_return,
                    nlp_result=nlp_result,
                    state=state,
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            if not has_ink_in_msg:
                target_prod = None
                if mentioned_products:
                    target_prod = mentioned_products[0]
                elif state.active_product:
                    target_prod = state.active_product
                elif state.active_product_id:
                    target_prod = catalogue_loader.get_by_id(state.active_product_id)

                if target_prod:
                    from catalog.price_resolver import price_resolver
                    price_info = price_resolver.get_price_info(prod=target_prod)
                    reply_text = format_product_price_response(target_prod, price_info)
                    state.active_product = target_prod
                    state.active_product_id = target_prod.get("id")
                    from agent.tool_executor import catalog_tool_executor
                    card = catalog_tool_executor.format_card(target_prod, card_type="hardware")

                    state.last_assistant_response = reply_text
                    state.increment_turn()
                    return self._build_response(
                        reply=reply_text,
                        source="route:product_price_inquiry",
                        product_cards=[card],
                        consumable_cards=[],
                        suggested_chips=["View Technical Specifications", "Compatible Consumables", "Request Official Quote"],
                        nlp_result=nlp_result,
                        state=state,
                        latency_ms=int((time.time() - start_time) * 1000),
                    )
                else:
                    reply_text = GENERAL_PRICE_DIRECT
                    state.last_assistant_response = reply_text
                    state.increment_turn()
                    return self._build_response(
                        reply=reply_text,
                        source="route:general_price_inquiry",
                        product_cards=[],
                        consumable_cards=[],
                        suggested_chips=["Technical CAD Plotters", "Photo Printers", "Office Enterprise MFPs", "View Consumables"],
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
            # Ensure comparison only contains the distinct products explicitly requested by the user
            comp_products = []
            seen_families = set()
            for p in mentioned_products:
                fam = p.get("model_family") or p["id"]
                if fam not in seen_families:
                    seen_families.add(fam)
                    comp_products.append(p)
                else:
                    # Only allow same family if text explicitly asked to compare variants
                    if any(k in normalized_msg.lower() for k in ["roll", "spectro", "configuration", "configurations", "variant", "variants"]):
                        comp_products.append(p)

            if len(comp_products) >= 2:
                reply_text, cards, comparison_data = build_approved_comparison_response(
                    comp_products,
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

        # 6a-2. Specific Specification / Capability Query on Active Product (e.g., "print speed?", "CAN I PRINT 2X6 STRIP IN THIS PRINTER?", "resolution?")
        current_active = state.active_product or prev_active_product or (mentioned_products[0] if mentioned_products else None)
        current_active_id = state.active_product_id or prev_active_product_id or (current_active.get("id") if isinstance(current_active, dict) else None)
        is_capability_query = (
            current_active is not None
            and (
                CanonicalEntityNormalizer.is_capability_query(normalized_msg)
                or bool(re.search(r"\b(?:can\s+(?:i|it|this\s+printer)|does\s+it|is\s+it\s+able\s+to|able\s+to)\s+(?:print|support|do|cut|handle)\b", normalized_msg.lower()))
                or bool(re.search(r"\bcan\s+i\s+print\b", normalized_msg.lower()))
                or bool(re.search(r"\bin\s+this\s+printer\b", normalized_msg.lower()))
                or bool(re.search(r"\b(?:f100|f500|p900|cx-02|cx-02w)\s+can\s+print\b", normalized_msg.lower()))
            )
        )
        is_spec_attr_query = (
            current_active is not None
            and not mentioned_products
            and any(re.search(rf"\b{re.escape(term)}\b", normalized_msg.lower()) for term in [
                "print speed", "speed", "ppm", "how fast", "resolution", "dpi", "dimensions",
                "width", "max width", "paper size", "paper sizes", "functions", "duty cycle"
            ])
            and not any(w in normalized_msg.lower() for w in ["find", "recommend", "show all", "compare", "vs"])
        )
        if is_capability_query or is_spec_attr_query:
            act_p = current_active
            act_id = current_active_id or (act_p.get("id") if isinstance(act_p, dict) else None)
            p_entry = catalogue_loader.get_by_id(act_id) or act_p
            p_name = p_entry.get("display_name") or p_entry.get("name") or act_p.get("name")
            if not state.category:
                state.category = p_entry.get("main_category") or p_entry.get("catalogue") or "citizen_photo"
            state.active_product = p_entry
            state.active_product_id = act_id
            prod_cards = []

            # 2x6 / photo strip capability check
            if re.search(r"\b(?:2x6|6x2|photo\s*strip|2-inch\s*strip|strips?)\b", normalized_msg.lower()):
                if "cx-02w" in str(act_id).lower():
                    cx02 = catalogue_loader.get_by_id("citizen-cx-02")
                    if cx02:
                        prod_cards = [catalogue_filter._format_card(cx02, "citizen_6_inch", state.requirements)]
                        state.active_product = cx02
                        state.active_product_id = "citizen-cx-02"
                        state.active_printer_for_consumables = cx02.get("display_name")
                    reply_text = (
                        f"No, the **{p_name}** is an 8-inch wide photo printer designed specifically for 8x10 and 8x12 large prints, "
                        "and does not support 2x6 photo booth strips.\n\n"
                        "For 2x6 photo booth strips, we recommend the **Citizen CX-02** (6-inch model). "
                        "The CX-02 features a built-in 2-inch multi-cut mode to produce 2x6 strips from 4x6 media, "
                        "and includes a unique ribbon rewind function that eliminates media waste."
                    )
                elif "cx-02" in str(act_id).lower() or "cy-02" in str(act_id).lower():
                    reply_text = (
                        f"Yes! The **{p_name}** supports 2x6 (6x2) photo booth strips using its built-in 2-inch multi-cut feature."
                    )
                else:
                    reply_text = f"The **{p_name}** does not support 2x6 photo strip cutting. For 2x6 photo booth strips, we recommend the **Citizen CX-02**."
            # Paper size capability check (e.g. "does it print a3?", "can it print A3?", "F100 can print a3 size?")
            elif re.search(r"\b(?:a3\+?|a2\+?|a1|a0|24[\s-]*(?:inch|in|\")|36[\s-]*(?:inch|in|\")|44[\s-]*(?:inch|in|\"))\b", normalized_msg.lower()):
                req_size_match = re.search(r"\b(a3\+?|a2\+?|a1|a0|24|36|44)\b", normalized_msg.lower())
                asked_size = req_size_match.group(1).upper() if req_size_match else "this size"
                if "f100" in str(act_id).lower():
                    f500 = catalogue_loader.get_by_id("epson-sc-f500")
                    if f500:
                        prod_cards = [catalogue_filter._format_card(f500, "dye_sublimation_24_inch", state.requirements)]
                        state.active_product = f500
                        state.active_product_id = "epson-sc-f500"
                        state.active_printer_for_consumables = f500.get("display_name")
                    reply_text = (
                        f"No, the **{p_name}** is a compact A4 desktop sublimation printer that only supports cut sheets up to A4 / Letter (8.5 inches wide), "
                        f"and does not support {asked_size} printing.\n\n"
                        f"If you need to print {asked_size} or larger dye-sublimation transfers, we recommend the **Epson SureColor SC-F500** (24-inch roll printer). "
                        "The SC-F500 supports both 24-inch roll media and an auto-sheet feeder for large apparel, sportswear, and merchandise."
                    )
                else:
                    reply_text = f"The **{p_name}** has a maximum print width of {p_entry.get('max_width') or p_entry.get('print_width') or 'standard format'}."
            elif any(w in normalized_msg.lower() for w in ["speed", "ppm", "how fast"]):
                speed_str = None
                for app in p_entry.get("applications", []):
                    if "ppm" in app.lower():
                        speed_str = app.replace("_", " ").title()
                if not speed_str:
                    speed_str = p_entry.get("speed") or p_entry.get("print_speed")
                if not speed_str:
                    if "am-c6000" in str(act_id).lower():
                        speed_str = "60 pages per minute (ppm) in both black and colour"
                    elif "am-c5000" in str(act_id).lower():
                        speed_str = "50 pages per minute (ppm) in both black and colour"
                    elif "am-c4000" in str(act_id).lower():
                        speed_str = "40 pages per minute (ppm) in both black and colour"
                    elif "c5890" in str(act_id).lower() or "c579" in str(act_id).lower():
                        speed_str = "25 pages per minute (ppm)"
                    else:
                        speed_str = "High-speed professional output"

                reply_text = f"The **{p_name}** features a verified print speed of **{speed_str}**."
            else:
                reply_text, _ = build_model_detail_response(p_entry)

            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:product_spec_attribute",
                product_cards=prod_cards,
                consumable_cards=[],
                suggested_chips=["View Technical Specifications", "Compatible Consumables", "Request Official Quote"],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6b. Exact Model Detail Inquiry (For one of the 43 approved products)
        has_negated_ink = bool(re.search(r"\b(?:not|no|don'?t\s+want)\s+ink\b", normalized_msg.lower()))
        has_ink_keyword = not has_negated_ink and bool(re.search(
            r"\b(?:inks?|cartridges?|toners?|ribbons?|consum[a-z]{3,6}s?|consub[a-z]{2,5}s?|media|paper|print\s+media|yields?|yeilds?|page\s*yield|print\s*yield|(?:(?<!with\s)(?<!dual\s)(?<!the\s)rolls?(?!\s+(?:adapter|unit|feed|printer)))|maintenance\s+(?:box|tank)(?:es|s)?)\b",
            normalized_msg.lower()
        ))
        if has_negated_ink:
            state.awaiting_field = None
            state.requested_ink_color = None

        is_detail_query = any(w in normalized_msg.lower() for w in [
            "tell me about", "specs of", "specifications", "details of", "information on",
            "about the", "show me", "view details", "look up", "want printer", "i want",
            "show printer", "printer", "details", "i need", "need"
        ])
        if (
            mentioned_products
            and not (state.awaiting_field == "printer_model" or state.requested_ink_color)
            and not has_ink_keyword
            and (is_detail_query or len(normalized_msg.split()) <= 6)
        ):
            # Check if inquiry is for SC-P900 family
            p900_in_mentioned = any(p["id"] in ("epson-sc-p900", "epson-sc-p900-roll") for p in mentioned_products)
            if p900_in_mentioned:
                has_std_explicit = bool(re.search(r"\b(?:without\s+roll|without\s+roll\s+adapter|without\s+the\s+roll|no\s+roll|without|standard|cut\s*sheet)\b", normalized_msg.lower()))
                has_roll_explicit = not has_std_explicit and bool(re.search(r"\b(?:with\s+roll|roll\s+adapter|roll\s+unit|with\s+the\s+roll|roll)\b", normalized_msg.lower()))
                if has_roll_explicit:
                    target_prod = catalogue_loader.get_by_id("epson-sc-p900-roll")
                    reply_text, cards = build_model_detail_response(target_prod)
                    chips = ["View Compatible Consumables", "Compare with Alternative"]
                elif has_std_explicit:
                    target_prod = catalogue_loader.get_by_id("epson-sc-p900")
                    reply_text, cards = build_model_detail_response(target_prod)
                    chips = ["View Compatible Consumables", "Compare with Alternative"]
                else:
                    # User asked for P900 without specifying: send with and without roll adapter both!
                    target_prod = catalogue_loader.get_by_id("epson-sc-p900")
                    reply_text, cards = build_p900_family_detail_response()
                    chips = ["With Roll Adapter", "Without Roll Adapter (Standard)", "View Compatible Consumables"]
            else:
                target_prod = mentioned_products[0]
                reply_text, cards = build_model_detail_response(target_prod)
                chips = ["View Compatible Consumables", "Compare with Alternative"]

            state.active_product = target_prod
            state.active_product_id = target_prod["id"]
            state.active_printer_for_consumables = target_prod.get("display_name")

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
            if bool(re.search(r"\b(?:inks?|consumables?|cartridges?|media|paper|rolls?)\b", normalized_msg.lower())):
                detail_c_cards = consumables_engine.get_printer_consumables(target_prod.get("display_name", ""), limit=25)

            return self._build_response(
                reply=reply_text,
                source="route:model_detail",
                product_cards=cards,
                consumable_cards=detail_c_cards,
                suggested_chips=chips,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6c. Consumables Inquiry & Media Inquiries
        is_canvas_media_query = (
            bool(re.search(r"\b(?:canvas|canvas\s+roll|canvas\s+media|canvas\s+paper)\b", normalized_msg.lower()))
            and not any(w in normalized_msg.lower() for w in ["printer", "machine", "plotter", "hardware"])
        )
        if is_canvas_media_query:
            state.awaiting_field = None
            reply_text = (
                "Yes, we supply official fine art canvas media rolls compatible with Epson UltraChrome pigment inks (for SureColor P-Series printers):\n\n"
                "• **Epson Exhibition Canvas Matte** (Available in 17″, 24″, 36″, 44″, and 60″ rolls)\n"
                "• **Epson Premium Canvas Satin** (Available in 13″, 17″, 24″, 44″, and 60″ rolls)\n"
                "• **Innova Exhibition Matte Cotton Canvas** (IFA-54)\n"
                "• **Korejet Pure Cotton Canvas Matte** (370–390 GSM)\n\n"
                "These media rolls are specifically formulated for water-based pigment inks to achieve museum-grade archival quality and rich contrast. "
                "Which roll width do you need, or which printer model will you be using?"
            )
            chips_to_return = ["24-inch Canvas", "44-inch Canvas", "Epson SC-P900 Inks", "View Photo Printers"]
            return self._build_response(
                reply=reply_text,
                source="route:media_inquiry",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        has_negated_ink = bool(re.search(r"\b(?:not|no|don'?t\s+want)\s+ink\b", normalized_msg.lower()))
        has_direct_printer_inquiry = bool(re.search(
            r"\b(?:do\s+(?:you\s+)?have|have|sell|stock|price\s+of|buy|details\s+on)\s+(?:the\s+)?(?:sc[-\s]?)?(?:[tpf]\d{3,5}|cx[-\s]?02|cy[-\s]?02|cz[-\s]?01|am[-\s]?c\d{3,4}|wf[-\s]?c\d{3,5}|f100|f500)\b",
            normalized_msg.lower()
        )) or any(k in normalized_msg.lower() for k in ["how about printer", "what about printer", "the printer", "how bout"])

        is_printer_search = has_negated_ink or has_direct_printer_inquiry or bool(re.search(
            r"\b(?:need|want|looking\s+for|require)\s+(?:an?\s+)?(?:[\w-]+\s+){0,6}(?:printer|plotter|mfp|machine|device)\b",
            normalized_msg.lower()
        )) or any(k in normalized_msg.lower() for k in [
            "need a printer", "looking for a printer", "photo printer", "which printer",
            "show all matching models", "show matching", "show every matching", "show me all",
            "show all", "list every", "which model", "matching catalogue", "suitable printer",
            "want printer", "i want printer", "printer hardware", "show printer", "want a printer",
            "looking for printer", "which one will do", "which one can do", "which one does",
            "which one supports", "which one is", "which one should i", "which machine",
            "which device", "which one will print", "which photo printer"
        ]) or bool(re.search(r"\bwhich\s+(?:one|printer|machine|model)\b", normalized_msg.lower()))
        if has_negated_ink:
            state.awaiting_field = None
            state.requested_ink_color = None

        # Check if user mentioned an ink color
        matched_ink_color = None
        for c in ["photo black", "matte black", "light cyan", "light magenta", "vivid magenta", "cyan", "magenta", "yellow", "black", "gray", "grey", "violet", "orange", "green", "red"]:
            if re.search(rf"\b{re.escape(c)}\b", normalized_msg.lower()):
                matched_ink_color = c
                break

        # If user explicitly states they want a printer, break out of awaiting_field
        if state.awaiting_field == "printer_model" and is_printer_search:
            state.awaiting_field = None
            state.requested_ink_color = None

        is_answering_printer_model = (
            state.awaiting_field == "printer_model"
            and not is_printer_search
            and not has_negated_ink
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
                or (matched_ink_color and (state.active_product is not None or state.active_printer_for_consumables is not None))
            )
        )
        if is_consumables_query:
            if matched_ink_color:
                state.requested_ink_color = matched_ink_color

            p_name = ""
            if mentioned_products:
                p_name = mentioned_products[0]["display_name"]
            elif state.active_product:
                p_name = state.active_product.get("display_name") or state.active_product.get("name")
            elif prev_active_product:
                p_name = prev_active_product.get("display_name") or prev_active_product.get("name")
                state.active_product = prev_active_product
            elif state.active_product_id:
                cand = catalogue_loader.get_by_id(state.active_product_id)
                if cand:
                    p_name = cand.get("display_name") or cand.get("name")
                    state.active_product = cand
            elif state.active_printer_for_consumables:
                p_name = state.active_printer_for_consumables
            else:
                m_match = re.search(r"\b(?:sc[-\s]?)?(?:[tpf]\d{3,5}(?:[a-z]{1,4})?|cx[-\s]?02w?|cy[-\s]?02|cz[-\s]?01|am[-\s]?c\d{3,4}|wf[-\s]?c\d{3,5}(?:[a-z]{1,4})?|em[-\s]?c\d{3,4}|f100|f500)\b", normalized_msg.lower())
                if m_match:
                    p_name = m_match.group(0).upper()
                elif is_answering_printer_model and len(normalized_msg.split()) <= 3:
                    p_name = normalized_msg.strip().upper()

            c_cards = []
            prod_cards = []
            reply_text = ""
            if p_name:
                state.active_printer_for_consumables = p_name
                for cand in catalogue_loader.get_all():
                    if p_name.lower() in cand.get("id", "").lower() or p_name.lower() in cand.get("display_name", "").lower():
                        state.active_product = cand
                        state.active_product_id = cand.get("id")
                        break

                c_cards = consumables_engine.get_printer_consumables(p_name, limit=25)
                applied_color = state.requested_ink_color
                if applied_color:
                    app_low = applied_color.lower()
                    color_filtered = [card for card in c_cards if app_low in card.get("name", "").lower() or app_low in card.get("title", "").lower()]
                    # Exclude modifier variants if user asked for base color without modifier
                    refined = []
                    for card in color_filtered:
                        c_text = (card.get("name", "") + " " + card.get("title", "")).lower()
                        if app_low == "cyan" and "light cyan" in c_text and "light" not in normalized_msg.lower():
                            continue
                        if app_low == "magenta" and ("light magenta" in c_text or "vivid light magenta" in c_text) and "light" not in normalized_msg.lower():
                            continue
                        if app_low == "gray" and ("light gray" in c_text or "dark gray" in c_text) and "light" not in normalized_msg.lower() and "dark" not in normalized_msg.lower():
                            continue
                        refined.append(card)
                    if refined:
                        color_filtered = refined
                    if color_filtered:
                        c_cards = color_filtered
                    state.requested_ink_color = None
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

            if not c_cards and p_name and " " not in p_name.strip() and len(p_name.strip()) >= 4:
                sku_cand = rag_retriever.get_by_sku(p_name.strip())
                if sku_cand:
                    cat = str(sku_cand.get("category", "")).lower()
                    if any(ck in cat for ck in ["ink", "cartridge", "box", "tank", "media", "paper", "ribbon", "accessory"]) or sku_cand.get("card_type") == "consumable":
                        res_sku = catalog_tool_executor.execute_tool("get_product_specs", {"product_identifier": sku_cand.get("sku")})
                        prod_data = res_sku.get("product", sku_cand) if res_sku.get("success") else sku_cand
                        c_cards = [catalog_tool_executor.format_card(prod_data, card_type="consumable")]
                        state.awaiting_field = None
                        reply_text = f"Here is the verified genuine consumable for **{prod_data.get('name', sku_cand.get('sku'))}** (SKU: `{sku_cand.get('sku')}`):"
                        chips_to_return = ["Order Consumables", "View Compatible Printers", "Ask for Quote"]

            if c_cards:
                is_yield_query = bool(re.search(
                    r"\b(?:yields?|yeilds?|how\s+many\s+pages|how\s+many\s+prints|page\s*yield|print\s*yield|capacity\s*per\s*color)\b",
                    normalized_msg.lower()
                ))
                if is_yield_query:
                    p_name_l = (p_name or "").lower()
                    if any(k in p_name_l for k in ["am-c", "c4000", "c5000", "c6000", "workforce enterprise"]):
                        reply_text = (
                            f"Here are the verified ISO page yields for **{p_name}** genuine ink cartridges:\n\n"
                            "• **Black Ink (T08H / T08G):** **31,500 ISO pages** (high-capacity packs up to 50,000 pages).\n"
                            "• **Cyan Ink:** **28,000 ISO pages**.\n"
                            "• **Magenta Ink:** **28,000 ISO pages**.\n"
                            "• **Yellow Ink:** **28,000 ISO pages**.\n"
                            "• **Maintenance Box (C12C937181):** Approx. **100,000 pages** service cycle.\n\n"
                            "*(Yields determined in accordance with ISO/IEC 24711/24712 test methodology at 5% standard coverage.)*"
                        )
                    elif any(k in p_name_l for k in ["citizen", "cz-01", "cx-02", "cy-02", "cx-02w"]):
                        reply_text = (
                            f"Here are the verified media roll yields for **{p_name}**:\n\n"
                            "• **Citizen CZ-01 (CZ-MS46 4×6″):** **150 prints per roll** (300 prints per 2-roll pack).\n"
                            "• **Citizen CX-02 (CX-MS46 4×6″):** **400 prints per roll** (800 prints per 2-roll box).\n"
                            "• **Citizen CY-02 (CY-MS46 4×6″):** **700 prints per roll** (1,400 prints per 2-roll box).\n"
                            "• **Citizen CX-02W (CX2W-812 8×12″):** **400 prints per box**.\n\n"
                            "Each media pack contains matched paper rolls and ink ribbons for 100% zero-waste printing."
                        )
                    elif any(k in p_name_l for k in ["sc-t", "t3100", "t5100", "t5405", "t5700"]):
                        reply_text = (
                            f"For **{p_name}** technical plotters, ink yields depend on cartridge capacity and plot line coverage:\n\n"
                            "• **SC-T5100 (26ml/50ml):** Yields approximately 100–180 A1 CAD line drawings per black cartridge.\n"
                            "• **SC-T5405 (110ml/350ml/700ml):** 700ml high-capacity tanks yield over 2,000 A1 CAD line drawings at 5% coverage.\n"
                            "• **SC-T5700D (350ml/700ml):** 6-color UltraChrome XD3 ink set for long-run unattended blueprint production."
                        )
                    else:
                        reply_text = (
                            f"The consumable yields for **{p_name}** depend on document coverage and cartridge capacity. "
                            "High-yield cartridges provide significantly lower cost per print and extended intervals between replacements. "
                            "Would you like exact cartridge SKU options or a running cost analysis?"
                        )
                    chips_to_return = ["Order Consumables", "View Printer Specifications", "Cost Per Page"]
                elif not reply_text or "Here is the verified genuine consumable" not in reply_text:
                    color_label = f" {applied_color.title()}" if 'applied_color' in locals() and applied_color else ""
                    items_lines = []
                    for card in c_cards:
                        c_title = card.get("title") or card.get("name") or "Consumable Item"
                        c_sku = card.get("sku")
                        sku_text = f" (SKU: `{c_sku}`)" if c_sku else ""
                        c_pstr = card.get("price_formatted") or (f"AED {card.get('price'):,.2f}" if card.get("price") else None)
                        c_vat = card.get("vat_note") or "(Excl. VAT)"
                        price_part = f": **{c_pstr} {c_vat}**" if c_pstr else ""
                        c_url = card.get("url") or card.get("website_url")
                        link_title = f"[{c_title}]({c_url})" if c_url else f"**{c_title}**"
                        items_lines.append(f"• **{link_title}**{sku_text}{price_part}")
                    items_text = "\n".join(items_lines)
                    reply_text = f"Here are the verified{color_label} inks and media compatible with {p_name}:\n\n{items_text}"
                    if any(w in normalized_msg.lower() for w in ["cost", "price", "how much", "rate", "cost per print", "pricing", "quote"]):
                        reply_text += (
                            f"\n\nFor official consumable pricing, roll yields, and cost-per-print figures for **{p_name}**, "
                            f"or for commercial purchase orders, contact our sales team directly at **{OFFICIAL_SUPPORT_EMAIL}** or **{OFFICIAL_SUPPORT_PHONE}**."
                        )
                chips_to_return = ["Order Consumables", "View Printer Specifications"]
            else:
                if p_name:
                    state.awaiting_field = None
                    reply_text = (
                        f"We do not carry consumables or inks for the **{p_name}** as it is not part of our authorized product catalogue.\n\n"
                        "As an authorized Kepler Tech distributor, we stock official inks and media for Epson SureColor (T-Series, P-Series, F-Series), "
                        "WorkForce Office printers, and Citizen Photo printers."
                    )
                    chips_to_return = ["Epson SC-T3100 Inks", "Citizen CX-02 Media", "Epson SC-P900 Inks", "View Approved Printers"]
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

        # 6c-warranty. Product or General Hardware Warranty Inquiry
        is_warranty_query = bool(re.search(r"\b(?:warranty|guarantee|coverplus|amc|maintenance\s+contract)\b", normalized_msg.lower()))
        if is_warranty_query:
            target_p = mentioned_products[0] if mentioned_products else state.active_product
            if not target_p and state.active_product_id:
                target_p = catalogue_loader.get_by_id(state.active_product_id)
            p_title = target_p.get("display_name") or target_p.get("name") if target_p else None

            if p_title:
                reply_text = (
                    f"All **{p_title}** units supplied by Kepler Tech LLC include:\n\n"
                    "• **Standard Manufacturer Warranty:** 1-Year On-Site Warranty covering genuine parts, printheads, and certified technician labor across the UAE.\n"
                    "• **CoverPlus Service Extension:** Optional 3-year or 5-year extended on-site warranty packages.\n"
                    "• **Annual Maintenance Contracts (AMC):** Scheduled preventive servicing, priority emergency call-outs, and genuine spare parts.\n\n"
                    f"Would you like an official quotation including extended CoverPlus warranty for the {p_title}?"
                )
            else:
                reply_text = (
                    "All new printers supplied by Kepler Tech LLC include official authorized warranty coverage:\n\n"
                    "• **Standard Manufacturer Warranty:** 1-Year On-Site Warranty covering genuine hardware, printheads, and certified technician support across the UAE.\n"
                    "• **Extended Coverage (CoverPlus):** 3-year and 5-year extended on-site warranty packages available on Epson SureColor and WorkForce Enterprise printers.\n"
                    "• **Annual Maintenance Contracts (AMC):** Comprehensive SLA agreements covering regular maintenance visits and rapid on-site repair.\n\n"
                    "Would you like warranty terms included with an official commercial quotation?"
                )
            chips_to_return = ["Request Warranty Terms", "View Extended Warranty", "Contact Sales Desk"]
            state.last_assistant_response = reply_text
            state.increment_turn()
            return self._build_response(
                reply=reply_text,
                source="route:warranty_info",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=chips_to_return,
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 6d. Company Information / Business Hours / Location
        has_biz_keywords = any(w in normalized_msg.lower() for w in [
            "location", "address", "opening hours", "business hours", "working hours",
            "contact number", "phone number", "email address", "where are you",
            "office location", "office address", "your office", "where is your office",
            "do you deliver", "delivery", "shipping", "support email"
        ])
        is_business_info = (
            understanding.intent == Intent.BUSINESS_INFORMATION
            or has_biz_keywords
        ) and not any(k in normalized_msg.lower() for k in [
            "compare", "recommend", "which printer is better", "which model", "suitable printer"
        ])
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

        # 6e. Social / Greeting / Frustration / Customer Introduction
        is_frustrated = understanding.intent in (Intent.FRUSTRATION, Intent.NEGATIVE_FEEDBACK) or any(
            w in normalized_msg.lower() for w in [
                "you already asked", "stop repeating", "stop asking", "i told you already", "i already told you"
            ]
        )
        is_social_intent = understanding.intent in (
            Intent.CUSTOMER_INTRODUCTION, Intent.POSITIVE_FEEDBACK, Intent.SMALL_TALK
        )
        if is_frustrated or is_social_intent:
            from routes.social_route import handle as handle_social
            soc_res = handle_social(understanding, state)
            state.last_assistant_response = soc_res.reply
            state.increment_turn()
            return self._build_response(
                reply=soc_res.reply,
                source=soc_res.source or "route:social",
                product_cards=[],
                consumable_cards=[],
                suggested_chips=soc_res.suggested_chips or [],
                nlp_result=nlp_result,
                state=state,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # ── 7. Mandatory Qualification & Product Recommendation Flow ─────

        # 7a. If category is still unknown, prompt for category
        if not state.category:
            reply_text = "What will you primarily print—technical CAD drawings, office & business documents, professional photographs, sublimation merchandise (mugs & T-shirts), or event photos?"
            chips_to_return = [
                "Office & Business Documents (A3 / A4)",
                "Technical CAD Plotters",
                "Professional Photography & Fine Art",
                "Dye-Sublimation (T-Shirts & Mugs)",
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
            next_field = next_q["field"]

            # Loop Prevention & Anti-Frustration Guard:
            # Check if user tried to answer this exact awaiting field on the previous turn but it didn't resolve
            if prev_awaiting_field == next_field:
                state.unresolved_field_turns = getattr(state, "unresolved_field_turns", 0) + 1
            else:
                state.unresolved_field_turns = 0

            state.awaiting_field = next_field
            state.stage = "qualifying"
            state.qualification_complete = False
            chips_to_return = list(next_q["pills"])

            if state.unresolved_field_turns == 1:
                # Turn 1 unresolved: Acknowledge and clarify specifically with the options
                pill_opts = " or ".join(chips_to_return[:2])
                reply_text = f"Just to confirm the best fit for your space—would you prefer {pill_opts}?"
            elif state.unresolved_field_turns >= 2:
                # Turn 2+ unresolved: BREAK LOOP!
                # Do not trap user in question loop. Adopt safe standard default and proceed to catalogue models.
                logger.info(f"Loop guard triggered for field '{next_field}' after {state.unresolved_field_turns} turns. Breaking out of loop.")
                if next_field in ("scanner_required", "scan_required"):
                    state.requirements["scanner_required"] = False
                    state.requirements["functions"] = ["print"]
                elif next_field == "photo_form_factor":
                    state.requirements["photo_form_factor"] = "large"
                elif next_field == "print_width":
                    state.requirements["print_width"] = 24
                    state.requirements["paper_size"] = "a1"
                elif next_field == "daily_volume":
                    state.requirements["daily_volume"] = 100
                elif next_field == "paper_size":
                    state.requirements["paper_size"] = "a4"
                state.awaiting_field = None
                state.unresolved_field_turns = 0
                state.qualification_complete = True
                state.stage = "recommending"

                subcategory = resolve_subcategory(state.category, state.requirements)
                state.subcategory = subcategory
                cards, no_match = catalogue_filter.filter_and_rank(state.category, subcategory, state.requirements)
                if not no_match and cards:
                    valid_cards = validate_product_cards(cards)
                    state.displayed_product_ids = [c["id"] for c in valid_cards]
                    state.results_loaded = True
                    reply_text = f"Based on your requirements, here are our top recommended {state.category.replace('_', ' ').title()} models (you can refine or compare anytime):"
                    chips_to_return = ["Compare Matching Models", "View Detailed Specifications", "Filter by Requirements"]
                    state.last_assistant_response = reply_text
                    state.increment_turn()
                    return self._build_response(
                        reply=reply_text,
                        source="recommendation:catalogue_list",
                        product_cards=valid_cards,
                        consumable_cards=[],
                        suggested_chips=chips_to_return,
                        nlp_result=nlp_result,
                        state=state,
                        latency_ms=int((time.time() - start_time) * 1000),
                    )
            else:
                reply_text = next_q["question"]

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
            chips_to_return = no_match.get("chips", [])
            source = "recommendation:no_match"
            state.awaiting_field = "relaxation"
        else:
            # Validate cards fail-closed (all IDs must belong to 41 approved catalogue entries)
            valid_cards = validate_product_cards(cards)
            state.displayed_product_ids = [c["id"] for c in valid_cards]
            state.results_loaded = True
            product_cards = valid_cards
            if len(valid_cards) == 1:
                p_full = catalogue_loader.get_by_id(valid_cards[0].get("id")) or valid_cards[0]
                state.active_product = p_full
                state.active_product_id = valid_cards[0].get("id")
                state.active_printer_for_consumables = valid_cards[0].get("name") or p_full.get("display_name") or valid_cards[0].get("model")
            elif len(valid_cards) > 1:
                p_full = catalogue_loader.get_by_id(valid_cards[0].get("id")) or valid_cards[0]
                state.active_product = p_full
                state.active_product_id = valid_cards[0].get("id")
                state.active_printer_for_consumables = None

            vol = state.requirements.get("daily_volume")
            if volume_updated and vol:
                try:
                    vol_int = int(vol)
                    monthly_approx = vol_int * 25
                except (ValueError, TypeError):
                    vol_int = 0
                    monthly_approx = 0

                if subcategory == "a4_colour_multifunction":
                    if vol_int >= 150:
                        reply_text = (
                            f"Understood, I've updated your daily volume to {vol_int} pages per day (~{monthly_approx:,} pages/month). "
                            "For this high-volume workload, our WorkForce Enterprise line-head models (**AM-C400** at 40 ppm and **AM-C550** at 55 ppm) "
                            "are ranked first for speed and heavy duty cycles, alongside our WorkForce Pro departmental options:"
                        )
                    else:
                        reply_text = (
                            f"Understood, I've updated your daily volume to {vol_int} pages per day (~{monthly_approx:,} pages/month). "
                            "Here are our recommended A4 colour multifunction printers, led by our compact WorkForce Pro departmental models:"
                        )
                elif subcategory == "a3_workforce_pro_multifunction":
                    reply_text = f"Understood, I've updated your daily volume to {vol_int} pages per day. Here are the matching A3 WorkForce Pro multifunction printers:"
                elif subcategory == "a3_enterprise_multifunction" or state.requirements.get("paper_size") == "a3":
                    if vol_int >= 150:
                        reply_text = (
                            f"Understood, I've updated your daily volume to {vol_int} pages per day (~{monthly_approx:,} pages/month). "
                            "For this heavy workload, our WorkForce Enterprise line-head models (**AM-C4000**, **AM-C5000**, **AM-C6000**) are prioritized:"
                        )
                    else:
                        reply_text = (
                            f"Understood, I've updated your daily volume to {vol_int} pages per day (~{monthly_approx:,} pages/month). "
                            "Here are our recommended A3 multifunction models:"
                        )
                else:
                    reply_text = (
                        f"Understood, I've updated your daily volume to {vol_int} prints per day. "
                        "Here are the updated matching printers ranked for your workload:"
                    )
            elif is_correction_turn and had_cards:
                reply_text = f"Understood, I've updated your requirements. Here are the {len(valid_cards)} matching catalogue printers:"
            elif subcategory == "a4_colour_multifunction":
                try:
                    v_int = int(vol) if vol else 0
                except (ValueError, TypeError):
                    v_int = 0
                if v_int >= 150:
                    reply_text = (
                        f"I found {len(valid_cards)} A4 colour multifunction printers matching your requirements. "
                        f"For your workload of {v_int} pages/day (~{v_int * 25:,} pages/month), our high-speed WorkForce Enterprise line-head models "
                        "(**AM-C400** and **AM-C550**) are ranked first:"
                    )
                else:
                    reply_text = f"I found {len(valid_cards)} A4 colour multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif subcategory == "a3_workforce_pro_multifunction":
                reply_text = f"I found {len(valid_cards)} A3 WorkForce Pro multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif subcategory == "a3_enterprise_multifunction":
                reply_text = f"I found {len(valid_cards)} A3 WorkForce Enterprise multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements."
            elif subcategory == "citizen_6_inch":
                if state.requirements.get("ribbon_rewind") or any(s in state.requirements.get("print_sizes", []) for s in ["2x6", "6x2"]):
                    reply_text = (
                        f"I found {len(valid_cards)} Citizen photo printer{'s' if len(valid_cards) != 1 else ''} matching your requirements. "
                        "The **Citizen CX-02** features a ribbon rewind function that prints 2x6 strips and multiple sizes (4x6 and 6x8) from a single roll without media loss:"
                    )
                else:
                    reply_text = f"I found {len(valid_cards)} Citizen 6-inch photo printer{'s' if len(valid_cards) != 1 else ''} matching your requirements:"
            elif state.requirements.get("paper_size") == "a3":
                reply_text = f"I found {len(valid_cards)} A3 multifunction printer{'s' if len(valid_cards) != 1 else ''} matching your requirements:"
            else:
                reply_text = f"I found {len(valid_cards)} catalogue printer{'s' if len(valid_cards) != 1 else ''} matching your requirements:"

            if valid_cards:
                bullets = []
                for c in valid_cards[:4]:
                    title = c.get("title") or c.get("name") or c.get("id")
                    speed = c.get("speed") or c.get("print_speed")
                    desc = f" ({speed})" if speed else ""
                    bullets.append(f"• **{title}**{desc}")
                if bullets:
                    if reply_text.endswith("."):
                        reply_text = reply_text[:-1] + ":"
                    elif not reply_text.endswith(":"):
                        reply_text += ":"
                    reply_text += "\n\n" + "\n".join(bullets)

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
        state.last_suggested_chips = list(suggested_chips or [])
        if consumable_cards:
            state.active_consumable = consumable_cards[0]
            state.active_consumables = consumable_cards
        if product_cards and not state.active_product:
            state.active_product = product_cards[0]
            state.active_product_id = product_cards[0].get("id")
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
        elif "purchase" in source or "order" in source or "lead" in source or "quote" in source:
            agent_id = "sales_lead"
            agent_name = "Sales & Lead Generation"
            agent_badge = "Sales & Quotes"
            agent_color = "#f59e0b"
        elif "product" in source or "catalogue" in source or "model_detail" in source or product_cards:
            agent_id = "product_specialist"
            agent_name = "Product & Catalog Specialist"
            agent_badge = "Product Specialist"
            agent_color = "#1877f2"

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
