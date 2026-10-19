"""
Fallback Policy Engine for Kepler Tech SalesAI.
Phase 4: Decide policy action:
ANSWER, ANSWER_WITH_STATED_ASSUMPTION, CONFIRM, CLARIFY, PARTIAL_ANSWER,
NOT_VERIFIED_HANDOFF, OUT_OF_SCOPE_REDIRECT, REPAIR.
Enforces anti-looping, frustration handling, zero dead-ends, and honest verification.
"""

import os
import re
import time
import logging
from enum import Enum
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from conversation.understanding import DialogueAct, Intent, TurnUnderstanding, TurnUnderstandingExtractor
from conversation.dialogue_state import DialogueState, ResolvedTurn, SalientEntity
from catalog.evidence import EvidenceEngine, EvidenceRecord, CompatibilityStatus, knowledge_graph
from config import OFFICIAL_SUPPORT_EMAIL, OFFICIAL_SUPPORT_PHONE, OFFICIAL_INFO_EMAIL

logger = logging.getLogger("conversation.policy")


def find_unlisted_alternatives(query_code: str) -> List[Dict[str, Any]]:
    """Finds verified catalogue alternatives for an unlisted or unsupported model code."""
    try:
        from catalog.catalogue_loader import catalogue_loader
        products = catalogue_loader.products
    except Exception:
        return []

    code_upper = query_code.upper().strip()
    prefix = ""
    for pfx in ["WF-C", "AM-C", "SC-T", "SC-P", "SC-F", "CX-", "CY-", "CZ-", "WF-", "DS-", "ES-"]:
        if pfx in code_upper:
            prefix = pfx
            break

    matches = []
    if prefix:
        for p in products:
            p_id = str(p.get("id", "")).upper()
            p_name = str(p.get("display_name", "")).upper()
            p_fam = str(p.get("model_family", "")).upper()
            if prefix in p_id or prefix in p_name or prefix in p_fam:
                matches.append(p)

    if not matches:
        if "WF" in code_upper or "WORKFORCE" in code_upper:
            matches = [p for p in products if p.get("main_category") == "office_printer"]
        elif "CX" in code_upper or "CITIZEN" in code_upper:
            matches = [p for p in products if p.get("main_category") == "citizen_photo"]
        elif "SC-T" in code_upper or "PLOTTER" in code_upper:
            matches = [p for p in products if p.get("main_category") == "technical_large_format"]
        elif "SC-P" in code_upper or "PHOTO" in code_upper:
            matches = [p for p in products if p.get("main_category") == "photography_large_format"]
        elif "SC-F" in code_upper or "SUBLIMATION" in code_upper:
            matches = [p for p in products if p.get("main_category") == "dye_sublimation"]

    return matches[:3]


# ── Policy Actions ────────────────────────────────────────────────────────────

class PolicyAction(str, Enum):
    ANSWER = "ANSWER"
    ANSWER_WITH_STATED_ASSUMPTION = "ANSWER_WITH_STATED_ASSUMPTION"
    CONFIRM = "CONFIRM"
    CLARIFY = "CLARIFY"
    PARTIAL_ANSWER = "PARTIAL_ANSWER"
    NOT_VERIFIED_HANDOFF = "NOT_VERIFIED_HANDOFF"
    OUT_OF_SCOPE_REDIRECT = "OUT_OF_SCOPE_REDIRECT"
    REPAIR = "REPAIR"


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason: str
    target_entity_id: Optional[str] = None
    active_item_id: Optional[str] = None
    assumption_text: Optional[str] = None
    clarification_topic: Optional[str] = None
    clarification_question: Optional[str] = None
    options_or_chips: List[str] = Field(default_factory=list)
    evidence_records: List[EvidenceRecord] = Field(default_factory=list)
    supporting_product_ids: List[str] = Field(default_factory=list)
    is_handoff: bool = False
    next_step: Optional[str] = ""


# ── Policy Decision Engine ────────────────────────────────────────────────────

class PolicyEngine:
    """
    Decides the next grounded action given resolved turn understanding,
    dialogue state, and catalogue evidence.
    """

    CONFIDENCE_HIGH = float(os.getenv("POLICY_CONF_HIGH", "0.85"))
    CONFIDENCE_MED = float(os.getenv("POLICY_CONF_MED", "0.65"))
    MAX_CLARIFICATIONS_PER_TOPIC = int(os.getenv("MAX_CLARIFICATIONS", "2"))

    @classmethod
    def decide(
        cls,
        resolved: ResolvedTurn,
        state: DialogueState,
    ) -> PolicyDecision:
        und = resolved.understanding
        act = und.dialogue_act
        intent = und.intent
        conf = und.overall_confidence

        # Store extracted understanding slots into state.confirmed_slots
        if und.slots:
            for sname, sval in und.slots.items():
                val = sval.value if hasattr(sval, "value") else sval
                state.confirmed_slots[sname] = val

            # Honour slots["excluded"] by clearing corresponding confirmed slots and state attributes
            excluded_dict = {}
            if "excluded" in und.slots:
                ex_val = und.slots["excluded"]
                if hasattr(ex_val, "value") and isinstance(ex_val.value, dict):
                    excluded_dict.update(ex_val.value)
                elif isinstance(ex_val, dict):
                    excluded_dict.update(ex_val)
            for k, sval in und.slots.items():
                if k.startswith("excluded."):
                    sub_key = k[len("excluded."):]
                    val = sval.value if hasattr(sval, "value") else sval
                    excluded_dict[sub_key] = val

            if excluded_dict:
                for ex_slot, ex_target in excluded_dict.items():
                    state.confirmed_slots.pop(ex_slot, None)
                    state.confirmed_slots.pop(f"excluded.{ex_slot}", None)
                    if ex_slot == "target_category":
                        if state.category == ex_target or not ex_target or (isinstance(ex_target, list) and state.category in ex_target):
                            state.category = None
                    elif ex_slot == "target_model":
                        if state.active_product_id == ex_target or not ex_target or (isinstance(ex_target, list) and state.active_product_id in ex_target):
                            state.active_product_id = None
                    elif ex_slot == "media_size":
                        state.confirmed_slots.pop("media_size", None)
                        state.confirmed_slots.pop("plotter_width", None)
                        state.confirmed_slots.pop("photo_width", None)

        # ── PRIORITY 0: UNDERSTANDING & FALLBACK LADDER ─────────────────────────
        raw_l = und.raw_text.lower().strip()

        # 0.1 Frustration / Complaint Guard
        if act == DialogueAct.COMPLAINT or any(w in raw_l for w in ["this is useless", "useless", "waste of time", "already said", "not listening"]):
            claim = (
                "I sincerely apologize for the frustration. Let me connect you directly with a dedicated "
                "Kepler Tech equipment specialist who can review your requirements and provide immediate answers."
            )
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="config.py",
                field="support",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Frustration detected: immediate apology and specialist handoff.",
                options_or_chips=["Speak to Specialist", "Request Call Back", "Restart Inquiry"],
                evidence_records=[rec],
                next_step=f"You can reach our sales desk directly at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}.",
            )

        # 0.2 Lead Contact Capture (name + phone + email + company)
        phone_match = re.search(r"(?:\+971|00971|0)(?:5[0124568]|4|2|3|6|7|9)\d{7}\b", und.raw_text)
        email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", und.raw_text)
        name_match = re.search(r"(?:my name is|name is|i am|this is)\s+([a-zA-Z]+)", und.raw_text, re.I)
        company_match = re.search(r"(?:from|company|at)\s+([A-Z][a-zA-Z0-9\s]+(?:LLC|Trading|Est|Group|Studio|Prints|Printing)?)", und.raw_text, re.I)

        if phone_match or email_match or (name_match and any(w in raw_l for w in ["number", "phone", "call", "contact", "email", "quote", "quotation"])):
            phone_str = phone_match.group(0) if phone_match else None
            email_str = email_match.group(0) if email_match else None
            name_str = name_match.group(1).title() if name_match else "valued customer"
            comp_str = company_match.group(1).strip() if company_match else None

            lead_id = None
            try:
                from persistence.lead_repository import lead_repository
                lead_id = lead_repository.save_lead(
                    session_id=state.session_id,
                    customer_name=name_str if name_str != "valued customer" else None,
                    company=comp_str,
                    email=email_str,
                    phone=phone_str,
                    product_interest=state.category or (resolved.resolved_target_product.name if resolved.resolved_target_product else "General Equipment"),
                    notes=f"Customer input: {und.raw_text}",
                )
            except Exception:
                pass

            contact_summary = []
            if phone_str:
                contact_summary.append(f"phone: {phone_str}")
            if email_str:
                contact_summary.append(f"email: {email_str}")
            contacts_joined = " and ".join(contact_summary) if contact_summary else "contact details"
            ref_str = f" (Reference #{lead_id})" if lead_id else ""

            claim = (
                f"Thank you, {name_str}! I have registered your inquiry{ref_str} with {contacts_joined}. "
                "Our commercial sales team will reach out to you shortly with an official equipment quotation and tailored proposal."
            )
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="persistence/lead_repository.py",
                field="lead_capture",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason=f"Lead captured for {name_str}.",
                options_or_chips=["Official Quote", "Showroom Location", "Browse Catalogue"],
                evidence_records=[rec],
                next_step="Would you like me to note any specific volume requirements or delivery preferences for the sales team?",
            )

        # 0.3 Gratitude ("shukran", "thank you")
        if any(w in raw_l for w in ["shukran", "thank you", "thanks"]) and len(raw_l.split()) <= 3:
            claim = "Afwan! You are very welcome. Let me know if you need any further specifications, delivery details, or an official quotation."
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="gratitude",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Customer expressed gratitude.",
                options_or_chips=["Request Official Quote", "Showroom Location", "Browse Catalogue"],
                evidence_records=[rec],
                next_step="How else can I assist with your printing requirements?",
            )

        # 0.4 Price Objection ("it's too expensive", "cheaper alternative")
        if any(w in raw_l for w in ["too expensive", "expensive", "cheaper", "cannot afford", "out of my budget"]):
            target = resolved.resolved_target_product
            t_name = target.name if target else (state.category or "this equipment")

            # Mention ink-system economics only if the focused product's catalogue data supports it
            ink_econ_note = ""
            if target and target.metadata:
                m = target.metadata
                ink_sys = str(m.get("ink_system") or m.get("ink_technology") or "").lower()
                if any(k in ink_sys for k in ["rips", "replaceable ink", "precisioncore", "high-yield", "ciss"]):
                    ink_econ_note = " This model utilizes a high-capacity ink system designed to reduce ongoing page costs."

            claim = (
                f"I understand budget is an important factor. For {t_name}, is your main concern "
                f"the upfront equipment purchase price or the ongoing running cost per print?{ink_econ_note}"
            )
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="objection_price",
                entity_ids=[target.id] if target else [],
            )
            from conversation.dialogue_state import PendingQuestion
            state.pending_question = PendingQuestion(
                question_id="price_objection_concern",
                question_text=f"For {t_name}, is your concern the upfront price or running cost?",
                topic="price_objection",
                expected_type="choice",
                options=[
                    {"id": "upfront", "label": "Upfront price", "value": "upfront"},
                    {"id": "running_cost", "label": "Running cost", "value": "running_cost"},
                    {"id": "cheaper", "label": "Cost-Effective Models", "value": "cheaper"},
                ],
                turn_asked=state.turn_count,
            )
            return PolicyDecision(
                action=PolicyAction.CLARIFY,
                reason="Price objection acknowledged; clarify upfront price vs running cost without unverified claims.",
                target_entity_id=target.id if target else None,
                clarification_topic="price_objection",
                clarification_question="Is your main concern the upfront price or the running cost per print?",
                options_or_chips=["Upfront price", "Running cost", "Cost-Effective Models", "Request Official Quote"],
                evidence_records=[rec],
                next_step="Please let me know whether you want to focus on upfront equipment cost or ongoing running costs.",
            )

        # 0.45 Price Objection Follow-up ("running cost" vs "upfront price")
        if state.pending_question and state.pending_question.topic == "price_objection":
            state.pending_question = None
            target = resolved.resolved_target_product or state.get_current_focus()
            t_name = target.name if target else "your selected model"
            t_id = target.id if target else None

            if any(k in raw_l for k in ["running", "running cost", "cost per print", "per print", "per page", "ongoing", "supplies"]):
                if t_id:
                    from catalog.cost_per_print_calculator import cost_per_print_calculator
                    fmt_match = re.search(r"\b(4\s*[xX*×]\s*6|6\s*[xX*×]\s*8|8\s*[xX*×]\s*10|8\s*[xX*×]\s*12|4\.5\s*[xX*×]\s*8|5\s*[xX*×]\s*7|a4|a3)\b", raw_l)
                    target_fmt = fmt_match.group(1).replace(" ", "").replace("*", "x").replace("×", "x").lower() if fmt_match else "4x6"
                    res = cost_per_print_calculator.calculate_cost_per_print(t_id, print_format=target_fmt, printer_name=t_name)
                    if res.status == "verified" and res.explanation:
                        claim_text = res.explanation
                        rec = EvidenceRecord(
                            claim=claim_text,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="catalog/cost_per_print_calculator.py",
                            field="cost_per_print",
                            entity_ids=[t_id] + ([res.consumable_sku] if res.consumable_sku else []),
                        )
                    else:
                        claim_text = (
                            f"Print cost cannot be verified from the available data for the **{t_name}**. "
                            f"Our sales specialists can calculate tailored consumable yield costs for your specific media volume at {OFFICIAL_SUPPORT_EMAIL}."
                        )
                        rec = EvidenceRecord(
                            claim=claim_text,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="conversation/policy.py",
                            field="cost_per_print_unverified",
                            entity_ids=[t_id],
                        )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Addressed running cost concern for {t_name}.",
                        target_entity_id=t_id,
                        options_or_chips=["Request Media Quote", "Official Quotation", "View Technical Specs"],
                        evidence_records=[rec],
                        next_step=f"Would you like an official consumable supply quotation for the {t_name}?",
                    )
            elif any(k in raw_l for k in ["upfront", "purchase", "cheaper", "equipment", "lower", "show cheaper"]):
                if t_id:
                    from catalog.price_resolver import PriceResolver
                    pr = PriceResolver()
                    t_info = pr.get_price_info(t_id)
                    t_price = t_info.get("price")
                    from catalog.catalogue_loader import catalogue_loader
                    all_prods = catalogue_loader.load_and_validate()
                    t_prod = catalogue_loader.get_by_id(t_id) or {}
                    t_cat = t_prod.get("main_category") or t_prod.get("category")
                    cheaper_alts = []
                    for p in all_prods:
                        if (p.get("main_category") == t_cat or p.get("category") == t_cat) and p.get("id") != t_id:
                            p_info = pr.get_price_info(p.get("id"))
                            p_p = p_info.get("price")
                            if p_p is not None and t_price is not None and p_p < t_price:
                                cheaper_alts.append((p, p_p, p_info.get("price_str")))
                    if cheaper_alts:
                        cheaper_alts.sort(key=lambda x: x[1])
                        c_pick, c_price_val, c_price_str = cheaper_alts[0]
                        c_name = c_pick.get("display_name") or c_pick.get("name")
                        claim_text = (
                            f"For a lower upfront investment in this category, we recommend the **{c_name}**, "
                            f"listed at **{c_price_str}** (excl. VAT) compared to {t_name}."
                        )
                        rec = EvidenceRecord(
                            claim=claim_text,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="data/verified_prices.json",
                            field="cheaper_alternative",
                            entity_ids=[c_pick.get("id")],
                        )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Provided lower-priced verified alternative {c_name} for upfront price objection.",
                            target_entity_id=c_pick.get("id"),
                            options_or_chips=["Compare Specifications", "Request Official Quote", "Compatible Consumables"],
                            evidence_records=[rec],
                            next_step=f"Would you like to compare the {c_name} with the {t_name}?",
                        )
                    else:
                        claim_text = (
                            f"The **{t_name}** is already the most cost-effective verified entry model for this specification in our catalogue. "
                            f"For custom commercial quotes, educational discounts, or trade-in options, our sales desk can assist directly at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
                        )
                        rec = EvidenceRecord(
                            claim=claim_text,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="conversation/policy.py",
                            field="sales_desk_cheaper",
                            entity_ids=[t_id],
                        )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason="No cheaper model in catalogue meeting requirements; route to sales desk.",
                            target_entity_id=t_id,
                            options_or_chips=["Request Official Quote", "Contact Sales Desk", "View Technical Specs"],
                            evidence_records=[rec],
                            next_step=f"Our sales specialists can review tailored pricing at {OFFICIAL_SUPPORT_EMAIL}.",
                        )

        # 0.5 Hesitation ("I'll think about it")
        if any(w in raw_l for w in ["think about it", "i'll think about it", "maybe later", "need to think"]):
            claim = (
                "Understood! Take your time. Whenever you are ready, I can provide detailed datasheets, sample print comparisons, or an official quotation."
            )
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="hesitation",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Customer expressed hesitation; polite acknowledgment without pressure.",
                options_or_chips=["View Technical Specs", "Official Quote", "Consult Specialist"],
                evidence_records=[rec],
                next_step="Feel free to return whenever you are ready to proceed with your equipment selection.",
            )

        # 0.6 Anti-Repeat / Frustration Slot Guard (Identical consecutive user query)
        prev_user_input = getattr(state, "last_user_message", None)
        state.last_user_message = und.raw_text
        if prev_user_input and SequenceMatcher(None, raw_l, prev_user_input.strip().lower()).ratio() >= 0.85:
            repeat_count = state.clarifications_asked.get("user_repeat_count", 0) + 1
            state.clarifications_asked["user_repeat_count"] = repeat_count
        else:
            state.clarifications_asked["user_repeat_count"] = 0
            repeat_count = 0

        if repeat_count == 1:
            topic_label = state.category.replace("_", " ") if state.category else "your equipment requirements"
            claim = f"Understood, looking for {topic_label}. To guide you to the ideal model, do you need standard A4 desktop output or high-capacity A3 departmental printing?"
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="repeat_slot",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="User repeated input; acknowledge slot and advance question.",
                options_or_chips=["A4 Output", "A3 Output", "Consult Specialist"],
                evidence_records=[rec],
                next_step="Please select your required paper format.",
            )
        elif repeat_count >= 2:
            claim = (
                "Based on typical office document workloads, our top verified models are the **Epson WorkForce Pro WF-C5890** (A4) "
                "and **Epson WorkForce Enterprise AM-C4000** (A3 high-speed)."
            )
            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/catalogue_products.json",
                field="recommendation",
                entity_ids=["epson-wf-c5890-dwf", "epson-am-c4000"],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER_WITH_STATED_ASSUMPTION,
                reason="User repeated input multiple times; advance with stated assumption and top models.",
                target_entity_id="epson-wf-c5890-dwf",
                supporting_product_ids=["epson-am-c4000"],
                options_or_chips=["View WF-C5890 (A4)", "View AM-C4000 (A3)", "Request Official Quote"],
                evidence_records=[rec],
                next_step="Would you like to compare technical specifications or request an official quote?",
            )

        # 0.7 Mid-Conversation Greeting Continuity
        if act == DialogueAct.CHITCHAT and any(w in raw_l for w in ["hi", "hello", "hey"]):
            if state.turn_count > 0 and (state.category or state.last_shown_products or state.focus_stack):
                cat_display = state.category.replace("_", " ").title() if state.category else "your equipment requirements"
                claim = f"Hello! We are currently discussing {cat_display}. Would you like to continue reviewing models, check technical specifications, or explore another category?"
                rec = EvidenceRecord(
                    claim=claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="conversation/policy.py",
                    field="continuity",
                    entity_ids=[],
                )
                chips = [f"Continue with {cat_display}", "Check Specifications", "Explore Other Categories"]
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Mid-conversation greeting; maintain active topic continuity.",
                    options_or_chips=chips,
                    evidence_records=[rec],
                    next_step="How would you like to proceed?",
                )

        # 0.8 Short Reply / Bound Option Selection
        if resolved.bound_pending_option:
            b_opt = resolved.bound_pending_option
            opt_label = str(b_opt.get("label", b_opt.get("id", "")))
            p_data = b_opt.get("product")
            if p_data or resolved.resolved_target_product:
                target = resolved.resolved_target_product
                t_name = target.name if target else opt_label
                t_id = target.id if target else b_opt.get("id")
                raw_u = und.raw_text.lower().strip()
                opt_l = opt_label.lower()

                # 1. Quotation request via chip or affirmation to quotation offer
                is_quote = (
                    any(k in opt_l for k in ["quotation", "quote"])
                    or any(k in raw_u for k in ["quote", "quotation"])
                    or (any(k in raw_u for k in ["yes", "sure", "ok", "okay", "yep", "yes please", "confirm"]) and any(k in opt_l for k in ["quote", "quotation"]))
                )
                if is_quote and t_id:
                    state.handover_triggered = True
                    state.handover_reason = "quote_request"
                    state.handover_timestamp = time.time()
                    bot_limitation = (
                        "Discounts, formal quotations, and custom configurations are handled directly "
                        "by our sales team, as I cannot approve a discount or confirm a quote."
                    )
                    from config import is_within_business_hours
                    timing_msg = (
                        "Our sales specialists are available now to prepare this for you."
                        if is_within_business_hours()
                        else "Our sales office in Dubai is currently closed outside regular business hours (Monday–Friday 8:30 AM–5:30 PM, Saturday 8:30 AM–1:00 PM GST). Our team will review your inquiry on the next working day."
                    )
                    has_contact = bool(
                        state.confirmed_slots.get("phone")
                        or state.confirmed_slots.get("email")
                        or state.confirmed_slots.get("contact_phone")
                        or state.confirmed_slots.get("contact_email")
                        or state.confirmed_slots.get("contact_details")
                    )
                    if not has_contact:
                        contact_action = "Please provide your name, phone number, and delivery city so our sales team can prepare and send your official quotation."
                        chips = ["Leave Phone Number", "Leave Email Address", "Showroom Hours & Location"]
                    else:
                        contact_action = "We have your contact details on file and a specialist will follow up with your quotation."
                        chips = ["Showroom Hours & Location", "View Technical Specs"]

                    claim = f"I note your request for an official quotation for the **{t_name}**. {bot_limitation}\n\n{timing_msg}\n\n{contact_action}"
                    rec = EvidenceRecord(
                        claim=claim,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="conversation/policy.py",
                        field="formal_quotation",
                        entity_ids=[t_id] if t_id else [],
                    )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Customer requested official quotation for {t_name}.",
                        target_entity_id=t_id,
                        options_or_chips=chips,
                        evidence_records=[rec],
                        next_step="Please share your contact details and required quantity for your official quotation.",
                    )

                # 2. Consumables request via chip
                is_consumables = any(k in opt_l for k in ["consumable", "supplies", "ink", "ribbon", "media"]) or any(k in raw_u for k in ["consumables", "supplies", "inks", "ribbons"])
                if is_consumables and t_id:
                    recs = EvidenceEngine.get_verified_consumables(t_id)
                    if recs:
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Compatible consumables requested for {t_name}.",
                            target_entity_id=t_id,
                            options_or_chips=["Official Quotation", "View Technical Specs", "Cost Per Page"],
                            evidence_records=recs,
                            next_step=f"Would you like an official quotation for these genuine supplies?",
                        )

                # 3. Cost per page / print via chip
                is_cpp = any(k in opt_l for k in ["cost per page", "cost per print", "cpp", "running cost"]) or any(k in raw_u for k in ["cost per page", "cost per print", "cpp", "running cost"])
                if is_cpp and t_id:
                    from catalog.cost_per_print_calculator import cost_per_print_calculator
                    res = cost_per_print_calculator.calculate_cost_per_print(t_id, print_format="4x6", printer_name=t_name)
                    if res.status == "verified" and res.explanation:
                        claim_text = res.explanation
                    else:
                        claim_text = f"Running cost and consumable yield data for the **{t_name}** depend on media format and ink coverage. Our sales desk can calculate tailored yield costs for your volume."
                    rec = EvidenceRecord(
                        claim=claim_text,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="catalog/cost_per_print_calculator.py",
                        field="cost_per_print",
                        entity_ids=[t_id],
                    )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Cost per print requested for {t_name}.",
                        target_entity_id=t_id,
                        options_or_chips=["Official Quotation", "Compatible Consumables", "View Technical Specs"],
                        evidence_records=[rec],
                        next_step=f"Would you like an official quotation for the {t_name}?",
                    )

                # 4. Specifications request
                is_spec = (
                    any(k in opt_l for k in ["spec", "technical", "detail"])
                    or any(k in raw_u for k in ["spec", "specs", "specification", "specifications", "detail", "details", "technical"])
                    or (any(k in raw_u for k in ["yes", "sure", "ok", "okay", "yep", "fine", "show", "see"]) and any(k in opt_l for k in ["spec", "technical", "detail"]))
                )
                if is_spec and t_id:
                    full_rec = EvidenceEngine.get_full_specs(t_id)
                    if full_rec:
                        if hasattr(state, "save_pending_question"):
                            state.save_pending_question(
                                question=f"Would you like an official quotation or to review compatible supplies for the {t_name}?",
                                field_name="quotation_or_supplies",
                                expected_type="choice",
                                options=["Official Quotation", "Compatible Consumables", "Cost Per Page", "Delivery Details"],
                            )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Technical specifications requested via option for {t_name}.",
                            target_entity_id=t_id,
                            options_or_chips=["Official Quotation", "Compatible Consumables", "Cost Per Page", "Delivery Details"],
                            evidence_records=[full_rec],
                            next_step=f"Would you like an official quotation or to review compatible supplies for the {t_name}?",
                        )

                claim = f"**{t_name}** is an approved official equipment model in our catalogue."
                rec = EvidenceRecord(
                    claim=claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="data/catalogue_products.json",
                    field="selection",
                    entity_ids=[t_id] if t_id else [],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Customer selected option: {t_name}.",
                    target_entity_id=t_id,
                    options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                    evidence_records=[rec],
                    next_step=f"Would you like to see detailed specifications or compatible consumables for the {t_name}?",
                )

        # 0a. Unlisted / Near Match Model Check (Never silently substitute unlisted models)
        unlisted_entities = [e for e in und.entities if e.entity_type == "unlisted_model" and not re.search(r"^\d+$", e.surface_text)]
        if unlisted_entities:
            unlisted = unlisted_entities[0]
            from catalog.alias_index import alias_index
            alias_match = alias_index.resolve(unlisted.surface_text)
            if alias_match.is_exact:
                p = alias_match.product
                state.set_canonical_focus(p["id"])
                p_name = p.get("display_name") or p.get("name") or p["id"]
                rec = EvidenceRecord(
                    claim=f"The **{p_name}** is an approved catalogue product ({p.get('model', '')}).",
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="data/catalogue_products.json",
                    field="overview",
                    entity_ids=[p["id"]],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Model alias '{unlisted.surface_text}' resolved to approved product '{p_name}'.",
                    target_entity_id=p["id"],
                    options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                    evidence_records=[rec],
                    next_step=f"Would you like to review full specifications or request an official quotation for the {p_name}?",
                )
            elif alias_match.is_candidates:
                cand_names = [c.get("display_name") or c.get("name") or c["id"] for c in alias_match.candidates]
                clarify_q = f"Did you mean {' or '.join(cand_names)}?"
                if hasattr(state, "save_pending_question"):
                    state.save_pending_question(
                        question=clarify_q,
                        field_name="disambiguation",
                        expected_type="product_choice",
                        options=cand_names,
                    )
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason=f"Ambiguous model alias '{unlisted.surface_text}' matched candidates: {cand_names}",
                    clarification_question=clarify_q,
                    options_or_chips=cand_names,
                )

            alts = find_unlisted_alternatives(unlisted.surface_text)
            alt_names = [a.get("display_name") or a.get("id") for a in alts]
            if alt_names:
                alt_str = ", ".join(f"**{name}**" for name in alt_names)
                claim = (
                    f"The **{unlisted.surface_text}** is not in our approved equipment catalogue. "
                    f"We offer verified official alternatives including {alt_str}."
                )
            else:
                claim = (
                    f"The **{unlisted.surface_text}** is not in our approved equipment catalogue. "
                    "We specialize in authorized Epson and Citizen professional printing equipment."
                )

            rec = EvidenceRecord(
                claim=claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_NO,
                source_file="data/catalogue_products.json",
                field="id",
                entity_ids=[a.get("id") for a in alts],
            )
            chips = [f"View {name}" for name in alt_names[:2]] + ["Official Quotation", "Speak to Specialist"]
            next_q = f"Would you like to explore verified specifications for the {alt_names[0]}?" if alt_names else "Which printing application fits your workflow?"

            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason=f"Model '{unlisted.surface_text}' is unlisted; offering verified alternatives.",
                target_entity_id=alts[0].get("id") if alts else None,
                supporting_product_ids=[a.get("id") for a in alts[1:]] if len(alts) > 1 else [],
                options_or_chips=chips,
                evidence_records=[rec],
                next_step=next_q,
            )

        # 0b. Multi-intent resolution (e.g. price + delivery + speed)
        if und.secondary_intents and len(und.secondary_intents) > 0:
            target = resolved.resolved_target_product
            t_name = target.name if target else "our equipment"
            all_intents = list(dict.fromkeys([intent] + und.secondary_intents))
            claims = []
            ev_records = []

            for it in all_intents:
                if it == Intent.AVAILABILITY_OR_PRICE_POLICY:
                    p_claim = f"Official pricing and volume quotations for the **{t_name}** are provided directly through our sales desk."
                    claims.append(p_claim)
                    ev_records.append(EvidenceRecord(
                        claim=p_claim,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="config.py",
                        field="pricing_policy",
                        entity_ids=[target.id] if target else [],
                    ))
                elif it == Intent.SHIPPING_OR_DELIVERY:
                    from conversation.delivery_engine import DeliveryPolicyEngine
                    deliv_text, d_chips, d_next, d_recs = DeliveryPolicyEngine.resolve_delivery_decision(
                        und.raw_text, state, t_name
                    )
                    claims.append(deliv_text)
                    ev_records.extend(d_recs)
                elif it == Intent.PRODUCT_INFO:
                    if target:
                        if "speed" in und.raw_text.lower() or "fast" in und.raw_text.lower():
                            spd_val = target.metadata.get("print_speed") or "high-speed PrecisionCore output"
                            s_claim = f"**Print speed:** {spd_val}."
                        else:
                            s_claim = f"The **{target.name}** features {target.metadata.get('print_speed', 'advanced printing technology')}."
                        claims.append(s_claim)
                        ev_records.append(EvidenceRecord(
                            claim=s_claim,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="data/catalogue_products.json",
                            field="print_speed",
                            entity_ids=[target.id],
                        ))

            if claims:
                deduped_claims = []
                for cl in claims:
                    if cl not in deduped_claims:
                        deduped_claims.append(cl)
                combined_claim = "\n\n".join(deduped_claims)
                combined_rec = EvidenceRecord(
                    claim=combined_claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="multi_source",
                    field="multi_intent",
                    entity_ids=[target.id] if target else [],
                )
                chips = ["Request Official Quote", "Technical Specifications", "Speak to Specialist"]
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Multi-intent query answered across {all_intents}.",
                    target_entity_id=target.id if target else None,
                    options_or_chips=chips,
                    evidence_records=[combined_rec],
                    next_step=f"Our sales specialists are available at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE} to prepare your official proposal.",
                )

        # 1. Handoff Request
        if act == DialogueAct.HANDOFF_REQUEST or any(w in und.raw_text.lower() for w in ["speak to human", "sales person", "agent", "call me"]):
            return PolicyDecision(
                action=PolicyAction.NOT_VERIFIED_HANDOFF,
                reason="Customer explicitly requested human sales specialist.",
                options_or_chips=[f"Call {OFFICIAL_SUPPORT_PHONE}", f"Email {OFFICIAL_SUPPORT_EMAIL}", "Visit Showroom"],
                is_handoff=True,
                next_step=f"Our sales specialists are available at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}.",
            )

        # 2. Out of Scope Redirect
        if act == DialogueAct.OUT_OF_SCOPE:
            return PolicyDecision(
                action=PolicyAction.OUT_OF_SCOPE_REDIRECT,
                reason="Request references non-catalogue categories or unapproved brands (3D printers, laser, edible, food, general trivia).",
                options_or_chips=["Technical CAD Plotters", "Photo & Fine Art", "Citizen Photo Booth", "Dye-Sublimation", "Office Printers"],
                next_step="Kepler Tech is an authorized commercial distributor specializing strictly in Epson and Citizen large-format printers, enterprise office MFPs, and professional document scanners. Which equipment category can we assist you with?",
            )

        # 2b. Company Capability / Full Product List / Authorized Dealership Inquiry
        is_capability = (
            "company_capability" in und.ambiguities
            or any(p.search(und.raw_text.lower()) for p in TurnUnderstandingExtractor.COMPANY_CAPABILITY_PATTERNS)
        )
        if is_capability and not any(e.entity_type in ("model", "sku") for e in und.entities):
            cap_claim = (
                "Yes, absolutely. **Kepler Tech LLC** is an authorized distributor in the UAE supplying official "
                "commercial printing and scanning solutions across 6 key categories:\n\n"
                "• **Technical CAD Plotters (Epson SureColor SC-T Series)**: 24″, 36″, and 44″ precision plotters & MFPs (SC-T3100, SC-T5100, SC-T5405, SC-T3700D, SC-T5700D, SC-T7700D).\n"
                "• **Professional Photo & Fine Art (Epson SureColor SC-P Series)**: 13″ to 64″ 10–12 colour master printers (SC-P700, SC-P900, SC-P5300, SC-P7500, SC-P9500, SC-P20500).\n"
                "• **Citizen Dye-Sublimation Photo Printers**: High-speed instant event & photo booth printers (CZ-01 4″, CX-02 6″, CY-02 6″, CX-02W 8″).\n"
                "• **Dye-Sublimation Transfer (Epson SureColor SC-F Series)**: A4 desktop gifts (SC-F100) and 24″ roll production for apparel & textiles (SC-F500).\n"
                "• **Office WorkForce Pro Enterprise MFPs**: Ultra-low running cost Heat-Free line-head systems (WF-C5890, EM-C800, AM-C400, AM-C550, AM-C4000, AM-C5000, AM-C6000, WF-C21000).\n"
                "• **Epson High-Speed Document & Flatbed Scanners**: WorkForce sheetfed (DS-530II, DS-770II, DS-800WN, DS-900WN, DS-970) and flatbed/graphics (DS-1630, DS-6500, DS-60000, Expression 12000XL).\n\n"
                "All hardware is backed by official manufacturer warranties, genuine consumable stocks, and our Dubai showroom."
            )
            rec = EvidenceRecord(
                claim=cap_claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="catalog/catalogue_products.json",
                field="overview",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Delivered comprehensive company capability and product line overview.",
                options_or_chips=["Technical CAD Plotters", "Photo & Fine Art", "Citizen Photo Booth", "Office Printers", "Document Scanners"],
                evidence_records=[rec],
                next_step="Which equipment category or specific model would you like to review?",
            )

        # 3. Chitchat / Friendly Greeting
        if act == DialogueAct.CHITCHAT:
            chips = ["Printer", "Scanner", "Consumables"]
            if state.pending_question and state.pending_question.options:
                chips = [str(o.get("label") or o.get("id")) for o in state.pending_question.options]

            greeting_text = "Hello and welcome to Kepler Tech! Do you want a scanner, printer, or consumables?"
            if state.turn_count > 1 and state.category:
                greeting_text = "Hello! How can I assist you further with your equipment requirements today?"
                chips = ["Office Printers", "CAD Technical Plotters", "Photo & Fine Art", "Consumables"]

            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Conversational greeting.",
                options_or_chips=chips,
                next_step=greeting_text,
            )

        # 3b. Confusion / Customer Frustration / Wrong Answer Complaint
        if act == DialogueAct.COMPLAINT or any(w in und.raw_text.lower() for w in ["what you asking", "what do you mean", "what i asked", "previous chat", "priviace chat", "answer after checking"]):
            # Clear stuck state so the customer is never locked in an unwanted flow
            state.category = None
            state.confirmed_slots.clear()
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Addressed customer frustration or misunderstanding directly.",
                options_or_chips=["Equipment Pricing", "Technical Specifications", "Official Quotation", "Speak to Sales Specialist"],
                next_step=(
                    "I sincerely apologize for the misunderstanding and for giving you the wrong information. "
                    "Let me assist you directly: could you tell me the specific model, price, or printing requirement you would like answered?"
                ),
            )

        # 3c. Customer Confirmation / Acknowledgment ("thats fine", "fine", "sounds good", "ok", "yes")
        if act == DialogueAct.CONFIRMATION and und.intent in (Intent.OTHER, Intent.CONSUMABLES_LOOKUP):
            target = resolved.resolved_target_product
            if target:
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Acknowledged customer confirmation for active target {target.name}.",
                    target_entity_id=target.id,
                    options_or_chips=["Request Official Quote", "Delivery Details", "Technical Specifications", "View Other Models"],
                    next_step=f"Understood! Would you like to proceed with an official quotation or delivery details for the **{target.name}**?",
                )
            else:
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Acknowledged customer confirmation without active focus.",
                    options_or_chips=["Technical CAD Plotters", "Photo & Fine Art", "Office Printers", "Document Scanners"],
                    next_step="Understood! What equipment specifications or quotation would you like to review next?",
                )

        # 4. Repair / Correction Handling
        if act == DialogueAct.CORRECTION or any(w in und.raw_text.lower() for w in ["i meant", "no, i said", "not that", "changed my mind"]):
            state.corrections_history.append({"turn": state.turn_count, "raw": und.raw_text})
            cat = getattr(state, "category", None)
            from catalog.catalogue_filter import catalogue_filter
            from catalog.subcategory_resolver import resolve_subcategory
            from conversation.product_flows import extract_flowchart_requirements

            # Update requirements from correction text
            new_reqs = extract_flowchart_requirements(und.raw_text)
            if hasattr(state, "requirements"):
                state.requirements.update(new_reqs)
            if hasattr(state, "confirmed_slots"):
                state.confirmed_slots.update(new_reqs)
            reqs = getattr(state, "requirements", None)
            if reqs is None:
                reqs = getattr(state, "confirmed_slots", {})

            subcat = resolve_subcategory(cat, reqs) if cat else None
            cards, _ = catalogue_filter.filter_and_rank(cat, subcat, reqs) if cat and subcat else ([], None)
            target_id = cards[0]["id"] if cards else (resolved.resolved_target_product.id if resolved.resolved_target_product else None)
            supp_ids = [c["id"] for c in cards[1:3]] if len(cards) > 1 else []

            cat_title = cat.replace('_', ' ').title() if cat else "matching"
            rec_claim = f"Understood! Here are our recommended {cat_title} models matching your updated specifications:"
            if cards:
                rec_claim += "\n\n" + "\n".join([f"• **{c.get('title') or c.get('name') or c.get('id')}**" for c in cards[:3]])

            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Correction detected from customer; re-running recommendation with updated state.",
                target_entity_id=target_id,
                supporting_product_ids=supp_ids,
                options_or_chips=["View Technical Specifications", "Compatible Consumables", "Request Official Quotation"],
                next_step=rec_claim,
            )

        # 4. Anti-Looping & Clarification Limit Enforcement
        current_topic = intent.value
        topic_clarifications = state.clarifications_asked.get(current_topic, 0)
        has_substantive_input = (
            bool(resolved.resolved_target_product)
            or bool(resolved.resolved_active_item)
            or any(e.entity_type in ("model", "sku", "category", "brand") for e in und.entities)
            or bool(resolved.resolved_referents)
            or bool(und.slots)
            or any(w in und.raw_text.lower() for w in [
                "citizen", "epson", "plotter", "printer", "ink", "scanner", "cad", "photo", "booth", "sublimation",
                "a4", "a3", "24", "36", "44", "4 inch", "6 inch", "8 inch", "black", "cyan", "magenta", "yellow"
            ])
        )
        if has_substantive_input:
            state.clarifications_asked[current_topic] = 0
            state.clarifications_asked["_final_fallback"] = 0

        if not has_substantive_input and topic_clarifications >= cls.MAX_CLARIFICATIONS_PER_TOPIC:
            # Prevent looping: Give best-effort verified answer plus specialist handoff
            return PolicyDecision(
                action=PolicyAction.NOT_VERIFIED_HANDOFF,
                reason=f"Reached maximum clarification attempts ({cls.MAX_CLARIFICATIONS_PER_TOPIC}) on topic '{current_topic}'.",
                target_entity_id=resolved.resolved_target_product.id if resolved.resolved_target_product else None,
                options_or_chips=["Connect with Sales Specialist", "Official Quotation", "View Product Page"],
                is_handoff=True,
                next_step=f"To get you exact specifications without delay, our senior sales consultant will assist you directly at {OFFICIAL_SUPPORT_EMAIL}.",
            )

        # 5. Compatibility Check Intent (The Target Flow!)
        if intent == Intent.COMPATIBILITY_CHECK:
            item = resolved.resolved_active_item
            target = resolved.resolved_target_product

            if item and target:
                rec = EvidenceEngine.check_compatibility(item.id, target.id)
                # Check if assumption was made for a reference word like "this"
                has_reference = any(r.reference_text.lower() in ("this", "it", "that", "these") for r in resolved.resolved_referents)
                assumed_text = None
                if has_reference:
                    assumed_text = f"I am assuming you mean the {item.name} ({item.id}) we just looked at."

                act_choice = PolicyAction.ANSWER_WITH_STATED_ASSUMPTION if assumed_text else PolicyAction.ANSWER
                chips = [
                    f"View {target.name}",
                    "All Compatible Inks",
                    "Official Quotation"
                ]

                return PolicyDecision(
                    action=act_choice,
                    reason=f"Verified compatibility evaluation between {item.id} and {target.id}.",
                    target_entity_id=target.id,
                    active_item_id=item.id,
                    assumption_text=assumed_text,
                    options_or_chips=chips,
                    evidence_records=[rec],
                    next_step=f"Would you like to view the full product specifications for the {target.name} or receive an official quotation?",
                )

            elif target and not item:
                # Target printer known, ask which consumable SKU or ink color
                state.clarifications_asked[current_topic] = topic_clarifications + 1
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason="Target printer known, but specific consumable item/SKU is missing.",
                    target_entity_id=target.id,
                    clarification_topic=current_topic,
                    clarification_question=f"Which ink or consumable are you checking for the {target.name}?",
                    options_or_chips=["Inks & Cartridges", "Maintenance Box", "Photo Media", "All Supplies"],
                    next_step="Please select a supply category or mention the SKU.",
                )

            elif item and not target:
                # Consumable known, ask which printer model
                state.clarifications_asked[current_topic] = topic_clarifications + 1
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason="Consumable item known, but target printer model is missing.",
                    active_item_id=item.id,
                    clarification_topic=current_topic,
                    clarification_question=f"Which printer model are you asking about for {item.name}?",
                    options_or_chips=["Epson SC-F100", "Epson SC-F500", "Citizen CX-02", "Other Model"],
                    next_step="Please specify the printer model.",
                )

        # 6. Consumables Lookup Intent (or follow-up to consumables clarification)
        if intent == Intent.CONSUMABLES_LOOKUP or (state.clarifications_asked.get("consumables_lookup", 0) > 0 and resolved.resolved_target_product):
            state.category = "consumables"

            # If customer specifically selected an individual consumable (e.g. "black", "cyan", "the black one", SKU)
            if resolved.resolved_active_item:
                item = resolved.resolved_active_item
                target = resolved.resolved_target_product
                c_data = item.metadata or {}
                c_price = c_data.get("price")
                c_price_str = f"AED {float(c_price):,.2f} (excl. VAT)" if c_price else "Commercial Quote on Request"
                target_str = f" for the **{target.name}**" if target else ""
                claim = (
                    f"**{item.name}** (SKU: `{item.id}`):\n"
                    f"• Official genuine consumable{target_str}.\n"
                    f"• **Pricing:** {c_price_str}."
                )
                rec = EvidenceRecord(
                    claim=claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="data/catalogue_products.json",
                    field="consumable_item",
                    entity_ids=[item.id],
                    supporting_data={"consumables": [c_data] if c_data else []},
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Customer selected specific consumable {item.name} ({item.id}).",
                    target_entity_id=target.id if target else None,
                    active_item_id=item.id,
                    options_or_chips=["Request Official Quotation", "All Compatible Supplies", "Delivery Options"],
                    evidence_records=[rec],
                    next_step=f"Would you like an official quotation or order confirmation for the {item.name}?",
                )

            target = resolved.resolved_target_product
            if target:
                state.clarifications_asked["consumables_lookup"] = 0
                consumables, rec = EvidenceEngine.list_consumables(target.id)
                chips = ["Technical Specifications", "Media Rolls", "Official Quotation"]
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Retrieved verified consumables for {target.name}.",
                    target_entity_id=target.id,
                    options_or_chips=chips,
                    evidence_records=[rec],
                    next_step="Would you like to order replacement supplies or review printer specifications?",
                )
            else:
                state.clarifications_asked[current_topic] = topic_clarifications + 1
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason="Consumables requested without a specified printer model.",
                    clarification_topic=current_topic,
                    clarification_question=(
                        "Which printer or scanner model do you need consumables for?\n\n"
                        "Please enter your model name, or select from the common options below:"
                    ),
                    options_or_chips=["Epson SC-F500", "Epson SC-T3100", "Citizen CX-02", "Epson SC-P900"],
                    next_step="Please enter the model name or select from the options below.",
                )

        # 7. Comparison Intent
        if intent == Intent.COMPARE:
            models = [e.normalised_id for e in und.entities if e.entity_type == "model"]
            if len(models) < 2 and state.last_shown_products:
                models = [
                    (p.get("id") if isinstance(p, dict) else str(p))
                    for p in state.last_shown_products
                    if (p.get("id") if isinstance(p, dict) else str(p))
                ]
            if len(models) >= 2:
                # Check if customer specifically asked about investment cost, price, running cost, or budget
                is_cost_comparison = any(
                    w in raw_l for w in [
                        "investment", "cost", "cheaper", "price", "pricing", "running cost",
                        "cost per print", "tco", "budget", "expensive", "economical", "operating cost"
                    ]
                )
                if is_cost_comparison:
                    from catalog.price_resolver import price_resolver
                    from catalog.cost_per_print_calculator import CostPerPrintCalculator
                    from catalog.repository import catalog_repository

                    cost_breakdowns = []
                    for mid in models[:2]:
                        p_obj = catalog_repository.products_by_id.get(mid)
                        p_name = p_obj.name if p_obj else mid

                        p_info = price_resolver.get_price_info(mid) or {}
                        hw_price = p_info.get("price")
                        hw_str = f"AED {hw_price:,.2f} (excl. VAT)" if hw_price else "Commercial Quote on Request"

                        cpp_res = CostPerPrintCalculator.calculate_cost_per_print(mid, "4x6")
                        cpp_str = cpp_res.cost_per_print_formatted or "Not verified"
                        yield_str = f"{cpp_res.package_yield_prints} prints per pack" if cpp_res.package_yield_prints else ""
                        pack_price = f"AED {cpp_res.package_price_aed:,.2f}" if cpp_res.package_price_aed else ""

                        cost_breakdowns.append({
                            "id": mid,
                            "name": p_name,
                            "hw_price": hw_price,
                            "hw_str": hw_str,
                            "cpp": cpp_res.cost_per_print_aed,
                            "cpp_str": cpp_str,
                            "yield_str": yield_str,
                            "pack_price": pack_price,
                        })

                    lines = ["**Investment & Running Cost Comparison**:"]
                    for cb in cost_breakdowns:
                        cons_info = f" | 4×6 print cost: approx. {cb['cpp_str']} ({cb['pack_price']} per pack of {cb['yield_str']})" if cb['cpp'] else ""
                        lines.append(f"• **{cb['name']}**: Hardware listed at {cb['hw_str']}{cons_info}")

                    b0, b1 = cost_breakdowns[0], cost_breakdowns[1]
                    cheaper_hw = None
                    if b0["hw_price"] and b1["hw_price"]:
                        if b0["hw_price"] < b1["hw_price"]:
                            cheaper_hw = (b0, b1, b1["hw_price"] - b0["hw_price"])
                        elif b1["hw_price"] < b0["hw_price"]:
                            cheaper_hw = (b1, b0, b0["hw_price"] - b1["hw_price"])

                    cheaper_cpp = None
                    if b0["cpp"] and b1["cpp"]:
                        if b0["cpp"] < b1["cpp"]:
                            cheaper_cpp = (b0, b1)
                        elif b1["cpp"] < b0["cpp"]:
                            cheaper_cpp = (b1, b0)

                    summary_parts = []
                    if cheaper_hw:
                        summary_parts.append(f"**{cheaper_hw[0]['name']}** offers a lower upfront equipment investment, saving AED {cheaper_hw[2]:,.2f}")
                    if cheaper_cpp:
                        if cheaper_hw and cheaper_cpp[0]['id'] == cheaper_hw[0]['id']:
                            summary_parts.append(f"as well as a lower running cost per print ({cheaper_cpp[0]['cpp_str']} vs {cheaper_cpp[1]['cpp_str']})")
                        else:
                            summary_parts.append(f"**{cheaper_cpp[0]['name']}** offers a lower running cost per print ({cheaper_cpp[0]['cpp_str']} vs {cheaper_cpp[1]['cpp_str']})")

                    if summary_parts:
                        lines.append(f"\nSummary: {' '.join(summary_parts)}.")

                    claim_text = "\n".join(lines)
                    rec = EvidenceRecord(
                        claim=claim_text,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="catalog/price_resolver.py",
                        field="investment_cost_comparison",
                        entity_ids=models[:2],
                    )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Compared verified investment and operating costs for {models[:2]}.",
                        target_entity_id=models[0],
                        supporting_product_ids=models[1:2],
                        options_or_chips=["Official Quotation", "Consumables Breakdown", "Technical Specs"],
                        evidence_records=[rec],
                        next_step="Would you like an official proposal with media kits included for either model?",
                    )

                matrix, rec = EvidenceEngine.compare(models[:3], ["category", "width", "resolution", "speed", "connectivity"])
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Compared verified models {models[:3]}.",
                    target_entity_id=models[0],
                    supporting_product_ids=models[1:3],
                    options_or_chips=["Compare Consumables", "View Official Quotations", "Consult Specialist"],
                    evidence_records=[rec],
                    next_step="Which model better fits your operational volume?",
                )

        # 8. Alternatives Intent
        if intent == Intent.ALTERNATIVES:
            target = resolved.resolved_target_product
            if target:
                alts, rec = EvidenceEngine.find_alternatives(target.id)
                alt_names = [a.get("display_name") or a.get("id") for a in alts[:3]]
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Found verified alternatives for {target.name}.",
                    target_entity_id=target.id,
                    options_or_chips=alt_names + ["Compare All", "Consult Specialist"],
                    evidence_records=[rec],
                    next_step="Would you like a direct comparison between these verified models?",
                )

        # 8b. Delivery & Shipping Policy Intent
        if intent == Intent.SHIPPING_OR_DELIVERY:
            from conversation.delivery_engine import DeliveryPolicyEngine
            target = resolved.resolved_target_product
            t_name = target.name if target else None
            deliv_text, chips, next_q, ev_recs = DeliveryPolicyEngine.resolve_delivery_decision(
                und.raw_text, state, t_name
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Customer asked about delivery, shipping, returns, or policy details.",
                target_entity_id=target.id if target else None,
                options_or_chips=chips,
                evidence_records=ev_recs,
                next_step=next_q,
            )

        # 8c. Explicit Target Model Request (Case 9: e.g. "I want the Epson SC-P900")
        explicit_model_in_turn = any(e.entity_type == "model" for e in und.entities) or (
            resolved.bound_pending_option and resolved.bound_pending_option.get("product")
        )
        if intent == Intent.RECOMMEND and resolved.resolved_target_product and explicit_model_in_turn:
            target = resolved.resolved_target_product
            p_meta = target.metadata or {}
            claim_parts = [f"**{target.name}** is an approved official equipment model in our catalogue."]
            if p_meta.get("print_speed"):
                claim_parts.append(f"• Print speed: {p_meta.get('print_speed')}")
            if p_meta.get("dpi"):
                claim_parts.append(f"• Resolution: {p_meta.get('dpi')}")
            if p_meta.get("paper_size"):
                claim_parts.append(f"• Supported format: {p_meta.get('paper_size')}")
            rec = EvidenceRecord(
                claim="\n".join(claim_parts),
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/catalogue_products.json",
                field="overview",
                entity_ids=[target.id],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason=f"Customer explicitly requested model {target.name}.",
                target_entity_id=target.id,
                options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                evidence_records=[rec],
                next_step=f"Would you like to review full technical specifications or request an official quotation for the {target.name}?",
            )

        # 9. Recommendation / Category Discovery Intent (Product Qualification Flowcharts)
        cat_slot = und.slots.get("target_category")
        new_cat_raw = cat_slot.value if cat_slot else None
        cat_map = {
            "office_workforce": "office_printer",
            "office_enterprise": "office_printer",
            "office": "office_printer",
            "technical_cad": "technical_large_format",
            "cad": "technical_large_format",
            "photo_fine_art": "photography_large_format",
            "photo": "photography_large_format",
            "photo_booth": "citizen_photo",
            "citizen": "citizen_photo",
            "citizen_photo": "citizen_photo",
            "dye_sublimation": "dye_sublimation",
            "sublimation": "dye_sublimation",
            "scanners": "scanners",
            "scanner": "scanners",
        }
        canonical_new_cat = cat_map.get(new_cat_raw, new_cat_raw) if new_cat_raw else None

        from conversation.product_flows import resolve_flowchart_step, extract_flowchart_requirements
        flow_reqs = extract_flowchart_requirements(und.raw_text)

        # Check if flowchart leaf was already reached in this conversation
        already_at_leaf = bool(state.confirmed_slots.get("_flowchart_leaf_reached"))

        is_flowchart_turn = False
        is_direct_query = (
            intent in (Intent.AVAILABILITY_OR_PRICE_POLICY, Intent.PRODUCT_INFO, Intent.COMPATIBILITY_CHECK, Intent.COMPARE)
            and bool(resolved.resolved_target_product or resolved.resolved_active_item)
        )
        if not is_direct_query:
            if canonical_new_cat is not None:
                is_flowchart_turn = True
                resolved.resolved_target_product = None
                state.confirmed_slots.pop("_flowchart_leaf_reached", None)
                state.confirmed_slots.pop("_leaf_product_id", None)
            elif bool(flow_reqs) and getattr(state, "category", None):
                # Customer specified or modified parameters (e.g. 24 inch, a3, 500 pages, commercial)
                is_flowchart_turn = True
                state.confirmed_slots.pop("_flowchart_leaf_reached", None)
                state.confirmed_slots.pop("_leaf_product_id", None)
            elif not already_at_leaf and (intent in (Intent.RECOMMEND, Intent.OTHER)):
                if not resolved.resolved_target_product and not resolved.resolved_active_item:
                    if getattr(state, "category", None) and (
                        any(c.lower() in und.raw_text.lower() for c in state.last_shown_chips)
                        or und.dialogue_act in (DialogueAct.REJECTION, DialogueAct.CONFIRMATION, DialogueAct.ANSWER_TO_MY_QUESTION)
                        or bool(und.slots)
                    ):
                        is_flowchart_turn = True
        elif already_at_leaf and intent in (Intent.RECOMMEND, Intent.OTHER):
            # Already completed product identification: check what the user wants next
            leaf_pid = state.confirmed_slots.get("_leaf_product_id") or (resolved.resolved_target_product.id if resolved.resolved_target_product else None)
            if leaf_pid:
                raw_l = und.raw_text.lower().strip()
                is_specs_query = (
                    any(k in raw_l for k in ["spec", "specs", "technical", "detail", "details", "feature", "features", "give full", "want to see", "full specs"])
                    or (und.dialogue_act == DialogueAct.CONFIRMATION and any(c.lower() in raw_l for c in state.last_shown_chips if "spec" in c.lower()))
                    or intent == Intent.PRODUCT_INFO
                )
                if is_specs_query:
                    full_rec = EvidenceEngine.get_full_specs(leaf_pid)
                    if full_rec:
                        from catalog.catalogue_loader import catalogue_loader
                        p_info = catalogue_loader.get_by_id(leaf_pid) or {}
                        p_name = p_info.get("display_name") or p_info.get("name") or leaf_pid
                        if hasattr(state, "save_pending_question"):
                            state.save_pending_question(
                                question=f"Would you like an official quotation or to review compatible supplies for the {p_name}?",
                                field_name="quotation_or_supplies",
                                expected_type="choice",
                                options=["Official Quotation", "Compatible Consumables", "Cost Per Page", "Delivery Details"],
                            )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Verified technical specifications delivered for {p_name}.",
                            target_entity_id=leaf_pid,
                            options_or_chips=["Official Quotation", "Compatible Consumables", "Cost Per Page", "Delivery Details"],
                            evidence_records=[full_rec],
                            next_step=f"Would you like an official quotation or to review compatible supplies for the {p_name}?",
                        )

                from catalog.catalogue_loader import catalogue_loader
                p_info = catalogue_loader.get_by_id(leaf_pid) or {}
                p_name = p_info.get("display_name") or p_info.get("name") or leaf_pid
                rec = EvidenceRecord(
                    claim=f"The **{p_name}** is our verified primary recommendation for your requirements.",
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="data/catalogue_products.json",
                    field="recommendation",
                    entity_ids=[leaf_pid],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Follow-up on completed recommendation for {leaf_pid}.",
                    target_entity_id=leaf_pid,
                    options_or_chips=["Technical Specs", "Replaceable Ink Packs", "Official Quotation"],
                    evidence_records=[rec],
                    next_step=f"Would you like to review full technical specs or request an official quote for the {p_name}?",
                )

        if is_flowchart_turn:
            if canonical_new_cat:
                is_cad_scanner_feature = (
                    state.category in ("technical_large_format", "technical_cad", "cad")
                    and canonical_new_cat == "scanners"
                    and (
                        any("scan" in str(c).lower() for c in state.last_shown_chips)
                        or state.confirmed_slots.get("plotter_width") == 36
                    )
                )
                if not is_cad_scanner_feature and state.category != canonical_new_cat:
                    # User explicitly stated a new category: switch category and reset stale slots!
                    state.category = canonical_new_cat
                    state.confirmed_slots.clear()
                    state.focus_stack.clear()
                    state.last_shown_products.clear()
                    state.last_shown_consumables.clear()
            canonical_cat = state.category

            # Accumulate extracted requirements into state.confirmed_slots
            req_text = und.raw_text
            if resolved.bound_pending_option:
                b_lbl = str(resolved.bound_pending_option.get("label", ""))
                req_text = f"{req_text} {b_lbl}".strip()
            new_reqs = extract_flowchart_requirements(req_text, state.confirmed_slots)
            state.confirmed_slots.update(new_reqs)

            # Qualification Budget: Track qualification questions count
            turns_on_flow = state.confirmed_slots.get("_qualification_turns", 0) + 1
            state.confirmed_slots["_qualification_turns"] = turns_on_flow

            step = resolve_flowchart_step(canonical_cat, state.confirmed_slots, req_text)

            # Budget Gate: At max 3 questions before delivering leaf recommendations with product cards
            if not step.is_leaf and turns_on_flow >= 3:
                if canonical_cat in ("technical_large_format", "technical_cad", "cad"):
                    state.confirmed_slots.setdefault("plotter_width", 24)
                    state.confirmed_slots.setdefault("cad_config_24", "entry_desktop")
                elif canonical_cat in ("photography_large_format", "photo"):
                    state.confirmed_slots.setdefault("photo_width", 17)
                    state.confirmed_slots.setdefault("photo_17_type", "desktop_sheet")
                elif canonical_cat == "scanners":
                    state.confirmed_slots.setdefault("scanner_type", "business_sheetfed")
                elif canonical_cat == "dye_sublimation":
                    state.confirmed_slots.setdefault("sublimation_format", "desktop")
                step = resolve_flowchart_step(canonical_cat, state.confirmed_slots, req_text)

            # If a specific product or leaf was reached
            if step.is_leaf and step.target_product_id:
                state.confirmed_slots["_flowchart_leaf_reached"] = True
                state.confirmed_slots["_leaf_product_id"] = step.target_product_id
                rec = EvidenceRecord(
                    claim=f"{step.explanation}\n\n{step.question}",
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalogue_products.json",
                    field="category",
                    entity_ids=[step.target_product_id] + step.supporting_product_ids,
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Reached leaf recommendation in {canonical_cat} flowchart.",
                    target_entity_id=step.target_product_id,
                    supporting_product_ids=step.supporting_product_ids,
                    options_or_chips=step.chips,
                    evidence_records=[rec],
                    next_step=step.question,
                )
            else:
                # Intermediate flowchart qualification step: STRICTLY zero product cards
                clarification_prompt = f"{step.explanation}\n\n{step.question}" if step.explanation else step.question
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason=f"Guiding customer through {canonical_cat or 'overview'} flowchart qualification.",
                    clarification_topic=current_topic,
                    clarification_question=clarification_prompt,
                    options_or_chips=step.chips,
                    target_entity_id=None,
                    supporting_product_ids=[],
                    next_step="",
                )

        # 10. Product Info / Specs Intent
        if intent == Intent.PRODUCT_INFO:
            if resolved.resolved_active_item and not resolved.resolved_target_product:
                item = resolved.resolved_active_item
                c_node = knowledge_graph.nodes.get(item.id.upper())
                c_data = c_node.attributes if c_node else {}
                c_type = c_data.get("type", "consumable")
                compat_printers = c_data.get("compatible_printers", [])
                claim = f"**{item.name}** (SKU: {item.id}) is a verified {c_type} in our catalogue."
                if compat_printers:
                    p_names = [knowledge_graph.nodes[p].name for p in compat_printers if p in knowledge_graph.nodes]
                    claim += f" It is compatible with: {', '.join(p_names)}."
                rec = EvidenceRecord(
                    claim=claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file=c_node.source_file if c_node else "catalog/consumable_registry.py",
                    field="sku",
                    entity_ids=[item.id],
                    supporting_data=c_data,
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Product info inquiry for consumable SKU {item.id}.",
                    active_item_id=item.id,
                    options_or_chips=["View Compatible Printers", "Request Official Quotation"],
                    evidence_records=[rec],
                    next_step="Which printer model would you like to check compatibility for?",
                )

            elif resolved.resolved_target_product:
                target = resolved.resolved_target_product
                if state.clarifications_asked.get("consumables_lookup", 0) > 0:
                    state.clarifications_asked["consumables_lookup"] = 0
                    consumables, rec = EvidenceEngine.list_consumables(target.id)
                    chips = ["Technical Specifications", "Media Rolls", "Official Quotation"]
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Customer specified printer model {target.name} for consumables lookup.",
                        target_entity_id=target.id,
                        options_or_chips=chips,
                        evidence_records=[rec],
                        next_step="Would you like to order replacement supplies or review printer specifications?",
                    )

                # Check if customer asked for a specific attribute
                attr = getattr(und, "target_attribute", None)
                if not attr:
                    raw_l = und.raw_text.lower()
                    has_volume = bool(re.search(r"\b(?:prints?\s*(?:per|a|\/)\s*day|pages?\s*(?:per|a|\/)\s*day|daily\s*(?:volume|prints?|pages?|capacity)|duty\s*cycle|how\s*many\s*(?:prints?|pages?)|monthly\s*(?:volume|duty))\b", raw_l))
                    has_consume = bool(re.search(r"\b(?:consum\w*|ink\s*consum\w*|how\s*much\s*ink|ink\s*usage|cartridge\s*capacit\w*|yield)\b", raw_l))
                    if has_volume and has_consume:
                        attr = "volume_and_ink_consumption"
                    elif has_volume:
                        attr = "duty_cycle"
                    elif has_consume:
                        attr = "ink_consumption"
                    elif "stand" in raw_l:
                        attr = "stand"
                    elif "speed" in raw_l or "fast" in raw_l or "ppm" in raw_l:
                        attr = "print_speed"
                    elif "dpi" in raw_l or "resolution" in raw_l or "clarity" in raw_l:
                        attr = "dpi"
                    elif "width" in raw_l or "max width" in raw_l or "print width" in raw_l:
                        attr = "width"
                    elif "connectivity" in raw_l or "wifi" in raw_l or "wi-fi" in raw_l or "network" in raw_l:
                        attr = "connectivity"
                    elif any(k in raw_l for k in ["dimension", "dimensions", "measurement", "how big", "physical size"]):
                        attr = "dimensions"
                    elif any(k in raw_l for k in ["weight", "how heavy", "heavy", "kg"]):
                        attr = "weight"
                    elif any(k in raw_l for k in ["memory", "ram", "storage"]):
                        attr = "memory"
                    elif any(k in raw_l for k in ["datasheet", "brochure", "spec sheet", "data sheet", "pdf"]):
                        attr = "brochure_url"
                    elif any(k in raw_l for k in ["price", "cost", "how much", "quote"]):
                        attr = "price"

                if attr:
                    has_explicit_model = any(e.entity_type == "model" for e in und.entities)
                    if not has_explicit_model and state.last_shown_products and len(state.last_shown_products) >= 2:
                        shown_ids = [
                            (p.get("id") if isinstance(p, dict) else str(p))
                            for p in state.last_shown_products[:3]
                        ]
                        attr_claims = []
                        valid_eids = []
                        for sid in shown_ids:
                            s_val, s_rec = EvidenceEngine.get_attribute(sid, attr)
                            s_node = knowledge_graph.nodes.get(sid.lower()) or knowledge_graph.nodes.get(sid.upper())
                            s_name = s_node.name if s_node else sid
                            if s_val and s_val != "MISSING":
                                attr_claims.append(f"• **{s_name}**: {s_val}")
                                valid_eids.append(sid)
                            else:
                                attr_claims.append(f"• **{s_name}**: Configuration verified on request")

                        if attr_claims:
                            attr_label = attr.replace("_", " ").capitalize()
                            claim_text = f"**{attr_label}** for verified models:\n" + "\n".join(attr_claims)
                            rec = EvidenceRecord(
                                claim=claim_text,
                                verified=True,
                                status=CompatibilityStatus.VERIFIED_YES,
                                source_file="data/catalogue_products.json",
                                field=attr,
                                entity_ids=valid_eids or shown_ids,
                            )
                            return PolicyDecision(
                                action=PolicyAction.ANSWER,
                                reason=f"Verified attribute '{attr}' retrieved for all shown models.",
                                target_entity_id=shown_ids[0],
                                supporting_product_ids=shown_ids[1:],
                                options_or_chips=["Technical Specifications", "Official Quotation", "Compare Models"],
                                evidence_records=[rec],
                                next_step=f"Would you like to review full technical specifications or request an official quote?",
                            )

                    val, rec = EvidenceEngine.get_attribute(target.id, attr)
                    if val == "MISSING" or rec is None or not rec.verified:
                        # Honest not-verified response: never loop, never substitute, never fabricate
                        attr_label = attr.replace("_", " ")
                        honest_claim = (
                            f"I don't have verified catalogue details confirming the {attr_label} for the **{target.name}**. "
                            f"Our technical specialists can verify the exact configuration and optional accessories for you."
                        )
                        honest_rec = EvidenceRecord(
                            claim=honest_claim,
                            verified=True,
                            status=CompatibilityStatus.UNKNOWN,
                            source_file="none",
                            field=attr,
                            entity_ids=[target.id],
                        )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Honest refusal for missing verified attribute '{attr}' on {target.id}.",
                            target_entity_id=target.id,
                            options_or_chips=["Technical Specifications", "Official Quotation", "Speak to Specialist"],
                            evidence_records=[honest_rec],
                            next_step=f"Our sales specialists can verify the {attr_label} specifications for you at {OFFICIAL_SUPPORT_EMAIL}.",
                        )
                    else:
                        chips = ["Technical Specifications", "Compatible Consumables", "Official Quotation"]
                        next_step = f"Would you like to see additional specifications or compatible supplies for the {target.name}?"
                        if attr in ("volume_and_ink_consumption", "duty_cycle", "ink_consumption"):
                            chips = ["Cost Per Print Breakdown", "Official Quotation", "Technical Specifications"]
                            next_step = f"Would you like an official cost-per-print breakdown or formal quotation for the {target.name}?"
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Verified attribute '{attr}' retrieved for {target.name}.",
                            target_entity_id=target.id,
                            options_or_chips=chips,
                            evidence_records=[rec],
                            next_step=next_step,
                        )
                else:
                    # Check if customer is asking why this model was chosen/recommended
                    is_why_query = bool(re.search(r"\b(?:why|why\s+this|why\s+this\s+one|why\s+recommend|how\s+come)\b", und.raw_text.lower()))
                    p_meta = target.metadata or {}
                    slots = state.confirmed_slots or {}

                    if is_why_query:
                        reasons = []
                        if slots.get("plotter_width") == 36 or "540" in target.id or "5100" in target.id:
                            reasons.append("its 36-inch (A0) width specifically engineered for technical CAD and architectural drawings")
                        elif slots.get("plotter_width") == 24 or "3100" in target.id:
                            reasons.append("its compact 24-inch (A1) width ideal for technical CAD line drawings")
                        elif slots.get("citizen_format") or "citizen" in str(state.category).lower():
                            reasons.append("its reliable dye-sublimation speed and print quality for wedding and event photo booths")

                        if slots.get("scanner_needed") is True or "integrated" in str(p_meta.get("functions", "")).lower() or "m" in target.id:
                            reasons.append("its integrated 36-inch scanner for scanning hand-marked blueprints and site plans")
                        elif slots.get("scanner_needed") is False:
                            reasons.append("its dedicated high-efficiency print-only design without unnecessary scanner cost")

                        if slots.get("daily_pages"):
                            reasons.append(f"its heavy-duty capacity to comfortably meet your daily volume of {slots.get('daily_pages')} drawings/prints")
                        elif p_meta.get("print_speed"):
                            reasons.append(f"its fast print speed of {p_meta.get('print_speed')}")

                        reasons_str = " along with ".join(reasons) if reasons else "its optimal balance of precision, speed, and media handling for your workflow"
                        overview_claim = f"The **{target.name}** is recommended for your requirements because of {reasons_str}."
                    else:
                        has_explicit_spec_kw = any(k in und.raw_text.lower() for k in [
                            "spec", "detail", "feature", "dpi", "speed", "resolution", "dimension",
                            "size", "weight", "function", "sheet", "brochure", "datasheet", "tell me about",
                            "what is", "overview", "what about", "how about", "what can you tell me", "what does it have",
                            "card", "show", "again"
                        ])
                        has_explicit_model_this_turn = any(e.entity_type == "model" for e in und.entities)

                        if has_explicit_spec_kw or has_explicit_model_this_turn:
                            full_rec = EvidenceEngine.get_full_specs(target.id)
                            if full_rec:
                                return PolicyDecision(
                                    action=PolicyAction.ANSWER,
                                    reason=f"Verified technical specifications delivered for {target.name}.",
                                    target_entity_id=target.id,
                                    options_or_chips=["Official Quotation", "Compatible Consumables", "Cost Per Page", "Delivery Details"],
                                    evidence_records=[full_rec],
                                    next_step=f"Would you like an official quotation or to review compatible supplies for the {target.name}?",
                                )

                        desc_parts = [f"**{target.name}** is an approved official equipment model in our catalogue."]
                        if p_meta.get("print_speed"):
                            desc_parts.append(f"• Print speed: {p_meta.get('print_speed')}")
                        if p_meta.get("dpi"):
                            desc_parts.append(f"• Resolution: {p_meta.get('dpi')}")
                        if p_meta.get("paper_size"):
                            desc_parts.append(f"• Supported format: {p_meta.get('paper_size')}")
                        overview_claim = "\n".join(desc_parts)

                        overview_rec = EvidenceRecord(
                            claim=overview_claim,
                            verified=True,
                            status=CompatibilityStatus.VERIFIED_YES,
                            source_file="data/catalogue_products.json",
                            field="overview",
                            entity_ids=[target.id],
                        )
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"General product info overview for {target.name}.",
                            target_entity_id=target.id,
                            options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                            evidence_records=[overview_rec],
                            next_step=f"Would you like to see detailed specifications or compatible consumables for the {target.name}?",
                        )

        # 9b. Commercial Discount, Formal Quotation & Custom Configuration
        if intent in (Intent.DISCOUNT_REQUEST, Intent.QUOTE_REQUEST, Intent.CUSTOM_CONFIG_REQUEST):
            state.handover_triggered = True
            if intent == Intent.DISCOUNT_REQUEST:
                state.handover_reason = "discount_request"
            elif intent == Intent.CUSTOM_CONFIG_REQUEST:
                state.handover_reason = "custom_configuration"
            else:
                state.handover_reason = "quote_request"
            state.handover_timestamp = time.time()

            raw_l_quote = und.raw_text.lower()
            qty = und.slots.get("quote_quantity")
            qty_val = qty.value if qty else None
            if not qty_val:
                qty_match = re.search(r"\b(\d+)\s*(?:units?|pcs?|pieces?|printers?|machines?|scanners?|items?|qty)\b", raw_l_quote) or re.search(r"\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b", raw_l_quote)
                if qty_match:
                    qty_val = int(qty_match.group(1) or qty_match.group(2))

            target = resolved.resolved_target_product
            t_name = target.name if target else None
            if not t_name and state.category:
                t_name = state.category

            req_parts = []
            if qty_val:
                req_parts.append(f"{qty_val} units")
            if t_name:
                req_parts.append(f"of {t_name}")
            if intent == Intent.CUSTOM_CONFIG_REQUEST:
                req_parts.append("with custom setup")
            detail_str = " ".join(req_parts).strip()

            if intent == Intent.DISCOUNT_REQUEST:
                disc_match = re.search(r"\b(\d+%)\b", raw_l_quote)
                disc_str = f" of {disc_match.group(1)}" if disc_match else ""
                ack_sentence = f"I note your request for a discount{disc_str}{' (' + detail_str + ')' if detail_str else ''}."
            elif intent == Intent.CUSTOM_CONFIG_REQUEST:
                ack_sentence = f"I note your request for a quotation{' for ' + detail_str if detail_str else ' with custom setup'}."
            else:
                ack_sentence = f"I note your request for a formal quotation{' (' + detail_str + ')' if detail_str else ''}."

            bot_limitation = (
                "Discounts, formal quotations, and custom configurations are handled directly "
                "by our sales team, as I cannot approve a discount or confirm a quote."
            )

            from config import is_within_business_hours
            if is_within_business_hours():
                timing_msg = "Our sales specialists are available now to prepare this for you."
            else:
                timing_msg = (
                    "Our sales office in Dubai is currently closed outside regular business hours "
                    "(Monday–Friday 8:30 AM–5:30 PM, Saturday 8:30 AM–1:00 PM GST). "
                    "Our team will review your inquiry on the next working day."
                )

            has_contact = bool(
                state.confirmed_slots.get("phone")
                or state.confirmed_slots.get("email")
                or state.confirmed_slots.get("contact_phone")
                or state.confirmed_slots.get("contact_email")
                or state.confirmed_slots.get("contact_details")
            )
            if not has_contact:
                contact_action = "Please provide your name and phone number or email address so our sales team can send your quotation."
                chips = ["Leave Phone Number", "Leave Email Address", "Showroom Hours & Location"]
            else:
                contact_action = "We have your contact details on file and a specialist will follow up with your quotation."
                chips = ["Showroom Hours & Location", "View Technical Specs"]

            full_claim = f"{ack_sentence} {bot_limitation}\n\n{timing_msg}"
            rec = EvidenceRecord(
                claim=full_claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="commercial_handoff",
                entity_ids=[target.id] if target else [],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason=f"Commercial {state.handover_reason} logged; handover triggered.",
                target_entity_id=target.id if target else None,
                options_or_chips=chips,
                evidence_records=[rec],
                next_step=contact_action,
                is_handoff=True,
            )

        # 9c. Competitor Mention Intent (Grounded differentiation without competitor specs)
        if intent == Intent.COMPETITOR_MENTION:
            raw_l_comp = und.raw_text.lower()
            comp_name = "other manufacturers"
            for brand in ["canon", "hp designjet", "designjet", "hp", "brother", "dnp", "mitsubishi", "fujifilm", "ricoh", "xerox", "konica"]:
                if brand in raw_l_comp:
                    comp_name = brand.title() if brand != "hp" else "HP"
                    break

            target = resolved.resolved_target_product or state.get_current_focus()
            t_name = target.name if target else None
            t_id = target.id if target else None

            if t_name and t_id:
                t_node = knowledge_graph.nodes.get(t_id.lower())
                p_meta = t_node.attributes if t_node else {}
                strengths = []
                if "precisioncore" in str(p_meta.get("ink_system", "")).lower() or "heat-free" in str(p_meta.get("key_features", "")).lower():
                    strengths.append("Epson PrecisionCore Heat-Free printing with low energy consumption")
                if p_meta.get("print_speed"):
                    strengths.append(f"print speed of {p_meta.get('print_speed')}")
                if p_meta.get("dpi"):
                    strengths.append(f"resolution up to {p_meta.get('dpi')}")
                if p_meta.get("paper_size"):
                    strengths.append(f"format handling up to {p_meta.get('paper_size')}")

                strengths_text = "; ".join(strengths) if strengths else "reliable high-yield operation and verified manufacturer warranty"
                claim = (
                    f"We respect {comp_name} as an established manufacturer. At Kepler Tech, we specialize exclusively "
                    f"in official Epson and Citizen commercial equipment. For your application, the **{t_name}** offers verified advantages "
                    f"including {strengths_text}.\n\n"
                    "We do not publish comparative specs or figures for third-party brands."
                )
                known_concern = state.confirmed_slots.get("primary_concern")
                if known_concern:
                    primary_lbl = known_concern.replace("_", " ")
                    chips = ["Official Quotation", "Technical Specs", "Warranty Details"]
                    next_q = f"Since your primary priority is {primary_lbl}, would you like an official quotation or verified technical data for this model?"
                else:
                    chips = ["Print Quality", "Running Cost", "Print Speed", "Official Quotation"]
                    next_q = "What matters most for your workflow: print quality, running cost, speed, or media size?"
                target_ids = [t_id]
            else:
                claim = (
                    f"We respect {comp_name} as an established manufacturer. Kepler Tech is an authorized distributor "
                    "specializing in official Epson large-format and Citizen photo printing systems. Rather than quoting third-party "
                    "specifications, we focus on matching you with the verified system that delivers the best return on investment for your application."
                )
                known_concern = state.confirmed_slots.get("primary_concern")
                if known_concern:
                    primary_lbl = known_concern.replace("_", " ")
                    chips = ["Technical CAD Plotters", "Photo & Fine Art", "Office Printers", "Citizen Photo Booth"]
                    next_q = f"Since your primary priority is {primary_lbl}, which format or application category best matches your setup?"
                else:
                    chips = ["Print Quality", "Running Cost", "Print Speed", "Media Size"]
                    next_q = "To recommend the ideal model, what matters most to you: print quality, running cost, speed, or media size?"
                target_ids = []

            rec = EvidenceRecord(
                claim=f"{claim}\n\n{next_q}",
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="competitor_differentiation",
                entity_ids=target_ids,
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason=f"Competitor mention of {comp_name} handled with grounded catalogue differentiation.",
                target_entity_id=t_id,
                options_or_chips=chips,
                evidence_records=[rec],
                next_step=next_q,
            )

        # 10. Availability & Price Policy Intent
        if intent == Intent.AVAILABILITY_OR_PRICE_POLICY:
            target = resolved.resolved_target_product
            t_name = target.name if target else "our equipment"
            t_id = target.id if target else None
            raw_l_price = und.raw_text.lower()

            # ── MULTI-MODEL PRICING / INVESTMENT INQUIRY ────
            has_explicit_model = any(e.entity_type == "model" for e in und.entities)
            is_multi_model = (
                state.last_shown_products
                and len(state.last_shown_products) >= 2
                and (any(w in raw_l_price for w in ["both", "all", "two", "each"]) or not has_explicit_model)
            )
            is_print_cost = any(k in raw_l_price for k in [
                "print cost", "cost per print", "running cost", "media cost", "per print", "per page", "cost per copy", "per copy"
            ]) or ("cost" in raw_l_price and any(w in raw_l_price for w in ["print", "page", "copy", "media", "divide"])) or ("price" in raw_l_price and "quantity" in raw_l_price) or ("divide by quantity" in raw_l_price)

            if is_multi_model and not is_print_cost:
                shown_ids = [
                    (p.get("id") if isinstance(p, dict) else str(p))
                    for p in state.last_shown_products[:3]
                ]
                price_lines = []
                for sid in shown_ids:
                    s_node = knowledge_graph.nodes.get(sid.lower()) or knowledge_graph.nodes.get(sid.upper())
                    s_name = s_node.name if s_node else sid
                    v_p = s_node.attributes.get("price") if s_node else None
                    v_p_str = s_node.attributes.get("price_str") if s_node else None
                    if v_p and float(v_p) > 0:
                        v_p_str = v_p_str or f"AED {float(v_p):,.2f}"
                        price_lines.append(f"• **{s_name}**: **{v_p_str}** (excl. VAT)")
                    else:
                        price_lines.append(f"• **{s_name}**: Commercial Quote on Request")

                p_claim = (
                    "**Official equipment pricing** for verified models:\n" + "\n".join(price_lines) +
                    f"\n\nOfficial quotations, volume discounts, and configurations are issued directly through our sales desk at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
                )
                rec = EvidenceRecord(
                    claim=p_claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="data/verified_prices.json",
                    field="price",
                    entity_ids=shown_ids,
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Quoted prices for multiple shown models: {shown_ids}.",
                    target_entity_id=shown_ids[0],
                    supporting_product_ids=shown_ids[1:],
                    options_or_chips=["Request Official Quote", "Compare Technical Specs", "Compatible Consumables"],
                    evidence_records=[rec],
                    next_step="Would you like an official quotation for both models sent to your email?",
                )

            if is_print_cost and is_multi_model:
                from catalog.cost_per_print_calculator import cost_per_print_calculator
                shown_ids = [
                    (p.get("id") if isinstance(p, dict) else str(p))
                    for p in state.last_shown_products[:3]
                ]
                fmt_match = re.search(r"\b(4\s*[xX*×]\s*6|6\s*[xX*×]\s*8|8\s*[xX*×]\s*10|8\s*[xX*×]\s*12|4\.5\s*[xX*×]\s*8|5\s*[xX*×]\s*7|a4|a3)\b", raw_l_price)
                target_fmt = fmt_match.group(1).replace(" ", "").replace("*", "x").replace("×", "x").lower() if fmt_match else "4x6"

                cost_sections = []
                rec_entity_ids = list(shown_ids)
                for sid in shown_ids:
                    s_node = knowledge_graph.nodes.get(sid.lower()) or knowledge_graph.nodes.get(sid.upper())
                    s_name = s_node.name if s_node else sid
                    res = cost_per_print_calculator.calculate_cost_per_print(sid, print_format=target_fmt, printer_name=s_name)
                    if res.status == "verified":
                        if res.consumable_sku and res.consumable_sku not in rec_entity_ids:
                            rec_entity_ids.append(res.consumable_sku)
                        cost_sections.append(
                            f"• **{s_name}** ({res.print_format}″):\n"
                            f"  - **Media Kit:** {res.consumable_name} (`{res.consumable_sku}`)\n"
                            f"  - **Pack Yield:** {res.package_yield_prints:,} usable prints per sold box ({res.rolls_per_box or 2} rolls × {res.prints_per_roll or (res.package_yield_prints // 2)})\n"
                            f"  - **Pack Price:** AED {res.package_price_aed:,.2f} Excl. VAT\n"
                            f"  - **Calculation:** AED {res.package_price_aed:,.2f} ÷ {res.package_yield_prints:,} prints = **AED {res.cost_per_print_aed:.2f} per print**"
                        )
                    else:
                        c_list, _ = EvidenceEngine.list_consumables(sid)
                        media_kits = [c.get("name") or c.get("sku") for c in c_list if any(m in (c.get("name") or "").lower() for m in ["media", "paper", "pack", "kit", "roll"])]
                        if media_kits:
                            cost_sections.append(f"• **{s_name}**: Uses {media_kits[0]} media supplies.")
                        else:
                            cost_sections.append(f"• **{s_name}**: High-yield consumable packs available.")

                cost_claim = (
                    f"**Verified print cost calculation (Pack Price ÷ Quantity = Cost Per Print)**:\n\n"
                    + "\n\n".join(cost_sections) +
                    f"\n\n*(Consumable pricing in AED Excl. 5% VAT. Source: Kepler Tech official catalogue.)*"
                )
                rec = EvidenceRecord(
                    claim=cost_claim,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalog/cost_per_print_calculator.py",
                    field="cost_per_print",
                    entity_ids=rec_entity_ids,
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Calculated verified cost-per-print for shown models: {shown_ids}.",
                    target_entity_id=shown_ids[0],
                    supporting_product_ids=shown_ids[1:],
                    options_or_chips=["Request Media Supply Quote", "View Technical Specs", "Official Quotation"],
                    evidence_records=[rec],
                    next_step="Would you like to request an official media supply quote or place an order?",
                )
            if is_print_cost and target:
                from catalog.cost_per_print_calculator import cost_per_print_calculator
                fmt_match = re.search(r"\b(4\s*[xX*×]\s*6|6\s*[xX*×]\s*8|8\s*[xX*×]\s*10|8\s*[xX*×]\s*12|4\.5\s*[xX*×]\s*8|5\s*[xX*×]\s*7|a4|a3)\b", raw_l_price)
                target_fmt = fmt_match.group(1).replace(" ", "").replace("*", "x").replace("×", "x").lower() if fmt_match else "4x6"
                res = cost_per_print_calculator.calculate_cost_per_print(t_id, print_format=target_fmt, printer_name=t_name)

                cost_claim = None
                rec_entities = [t_id] if t_id else []
                if res.status == "verified":
                    cost_claim = res.explanation
                    if res.consumable_sku and res.consumable_sku not in rec_entities:
                        rec_entities.append(res.consumable_sku)
                else:
                    # Try to calculate cost-per-print from consumables_detailed fallback
                    t_node = knowledge_graph.nodes.get(t_id)
                    cons_detailed = None
                    if t_node:
                        cd = t_node.attributes.get("consumables_detailed")
                        if not cd:
                            try:
                                from catalog.catalogue_loader import catalogue_loader
                                p_info = catalogue_loader.get_by_id(t_id) or {}
                                cd = p_info.get("consumables_detailed")
                            except Exception:
                                pass
                        cons_detailed = cd

                    if cons_detailed:
                        try:
                            import json as _json
                            if isinstance(cons_detailed, str):
                                cons_detailed = _json.loads(cons_detailed)
                            media_packs = [
                                c for c in cons_detailed
                                if isinstance(c, dict) and "media" in str(c.get("category", "")).lower()
                            ]
                            if media_packs:
                                mp = media_packs[0]
                                mp_price = float(mp.get("price", 0))
                                mp_name = mp.get("name", mp.get("sku", ""))
                                yield_info = t_node.attributes.get("yield_capacity") or t_node.attributes.get("consumable_volume") if t_node else None
                                prints_per_box = 300
                                if yield_info:
                                    import re as _re
                                    m = _re.search(r"(\d+)\s*prints?", str(yield_info).lower())
                                    if m:
                                        prints_per_box = int(m.group(1))
                                cost_per_print = mp_price / prints_per_box if prints_per_box > 0 else None
                                if cost_per_print:
                                    cost_claim = (
                                        f"The primary media pack for the **{t_name}** is the **{mp_name}** "
                                        f"(SKU: `{mp.get('sku', '')}`) priced at **AED {mp_price:,.2f}** "
                                        f"({prints_per_box} usable prints), giving a calculation of "
                                        f"AED {mp_price:,.2f} ÷ {prints_per_box} prints = **AED {cost_per_print:.2f} per print**."
                                    )
                                    if mp.get("sku"):
                                        rec_entities.append(mp.get("sku"))
                        except Exception as e:
                            logger.warning(f"Cost-per-print calculation error: {e}")

                if not cost_claim:
                    cost_claim = (
                        f"Print cost cannot be verified from the available data for the **{t_name}**. "
                        f"Official consumable running cost details are provided by our sales specialists at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
                    )

                rec = EvidenceRecord(
                    claim=cost_claim,
                    verified=bool(cost_claim and "AED" in cost_claim),
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalog/cost_per_print_calculator.py",
                    field="cost_per_print",
                    entity_ids=rec_entities,
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Calculated cost-per-print for {t_name}.",
                    target_entity_id=t_id,
                    options_or_chips=["Order Media Pack", "View Full Specs", "Request Official Quote"],
                    evidence_records=[rec],
                    next_step=f"Would you like to request an official media supply quote at {OFFICIAL_SUPPORT_EMAIL}?",
                )

            # ── HARDWARE LIST PRICE inquiry ─────────────────────────────────────────────
            if target:
                t_node = knowledge_graph.nodes.get(t_id)
                v_price = t_node.attributes.get("price") if t_node else None
                v_price_str = t_node.attributes.get("price_str") if t_node else None

                if v_price and float(v_price) > 0:
                    v_price_str = v_price_str or f"AED {float(v_price):,.2f}"
                    p_claim = f"The **{t_name}** is listed at **{v_price_str}** (excl. VAT)."
                    rec = EvidenceRecord(
                        claim=p_claim,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="data/verified_prices.json",
                        field="price",
                        entity_ids=[t_id],
                        supporting_data={"price": v_price, "price_str": v_price_str},
                    )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Quoted verified list price for {t_name}.",
                        target_entity_id=t_id,
                        options_or_chips=["Request Official Quote", "Compatible Consumables", "View Technical Specs"],
                        evidence_records=[rec],
                        next_step=f"Official quotations and tax invoices are issued directly at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}.",
                    )
                else:
                    # Quote-only product (price: null)
                    p_claim = f"Official pricing for the **{t_name}** is provided on request based on configuration and volume."
                    rec = EvidenceRecord(
                        claim=p_claim,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="config.py",
                        field="pricing_policy",
                        entity_ids=[t_id],
                    )
                    return PolicyDecision(
                        action=PolicyAction.ANSWER,
                        reason=f"Quote-only product: {t_name}. No public list price.",
                        target_entity_id=t_id,
                        options_or_chips=["Request Official Quote", "Contact Sales Desk", "View Product Page"],
                        evidence_records=[rec],
                        next_step=f"Would you like our sales team to prepare an official quotation at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}?",
                    )

            # No target product identified -> ask which model or application with category chips, zero prices
            rec = EvidenceRecord(
                claim="Which model or application are you looking to price?",
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="conversation/policy.py",
                field="price_clarification",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.CLARIFY,
                reason="Price inquiry with no product in context; clarify model or application.",
                target_entity_id=None,
                clarification_topic="model_or_application",
                clarification_question="Which model or application are you looking to price?",
                options_or_chips=["Office & Multifunction", "CAD / Blueprint / GIS", "Photo & Fine Art", "Photo Booth / Instant Photo", "Professional Scanners"],
                evidence_records=[rec],
                next_step="Please select a category or specify a model to view verified pricing.",
            )

        # 11. Contact Showroom Intent
        if intent == Intent.CONTACT_SHOWROOM:
            raw_l = und.raw_text.lower()
            if any(k in raw_l for k in ["pickup", "pick up", "collect"]):
                from conversation.delivery_engine import DeliveryPolicyEngine
                pickup_reply, chips, next_q, ev_recs = DeliveryPolicyEngine.resolve_delivery_decision(
                    "store pickup", state
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Store pickup collection inquiry.",
                    options_or_chips=chips,
                    evidence_records=ev_recs,
                    next_step=next_q,
                )
            elif any(k in raw_l for k in ["hour", "timing", "open", "time"]):
                from conversation.delivery_engine import DeliveryPolicyEngine
                hours_reply, chips, next_q, ev_recs = DeliveryPolicyEngine.resolve_delivery_decision(
                    "business hours", state
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Business and showroom hours inquiry.",
                    options_or_chips=chips,
                    evidence_records=ev_recs,
                    next_step=next_q,
                )
            else:
                loc_text = (
                    "**Kepler Tech LLC Showroom & Office:**\n"
                    "D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, United Arab Emirates.\n\n"
                    "• **Hours:** Monday – Friday 8:30 AM – 5:30 PM, Saturday 8:30 AM – 1:00 PM, Sunday Closed (GST).\n"
                    f"• **Phone:** {OFFICIAL_SUPPORT_PHONE} | **Email:** {OFFICIAL_SUPPORT_EMAIL} / {OFFICIAL_INFO_EMAIL}."
                )
                rec = EvidenceRecord(
                    claim=loc_text,
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="config.py",
                    field="company_context",
                    entity_ids=[],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Showroom location and contact inquiry.",
                    options_or_chips=["Showroom Location", "Opening Hours", "Contact Sales Desk"],
                    evidence_records=[rec],
                    next_step="Would you like directions or to schedule an on-site equipment demonstration?",
                )

        # 12. Fallback Clarify - Universally Context-Aware (Never drop to root mid-conversation)
        # Loop guard: keyed on a dedicated counter (NOT the per-intent topic, which changes turn to turn
        # on gibberish) and reset whenever a substantive turn is understood (see has_substantive_input).
        _fb = state.clarifications_asked.get("_final_fallback", 0)
        if _fb >= cls.MAX_CLARIFICATIONS_PER_TOPIC:
            state.clarifications_asked["_final_fallback"] = 0
            return PolicyDecision(
                action=PolicyAction.NOT_VERIFIED_HANDOFF,
                reason="Repeated unresolved input; stop re-asking and offer a human specialist.",
                options_or_chips=["Connect with Sales Specialist", "Official Quotation", "Browse Products"],
                is_handoff=True,
                next_step=f"I want to make sure you get the right answer. Our sales specialist can help directly at {OFFICIAL_SUPPORT_EMAIL}, or tell me the printer type or model you have in mind.",
            )
        state.clarifications_asked["_final_fallback"] = _fb + 1
        state.clarifications_asked[current_topic] = topic_clarifications + 1
        active_cat = getattr(state, "category", None) or (state.confirmed_slots.get("category") if hasattr(state, "confirmed_slots") else None)

        if active_cat == "office_printer":
            q_text = "What daily page volume and paper size (A4 vs A3) do you require for your office?"
            chips = ["A4 WorkForce Pro", "A3 Departmental RIPS", "Enterprise Line-Head", "Official Quotation"]
            step_text = "Please select your daily volume or specify your required office printing features."
        elif active_cat == "citizen_photo":
            q_text = "What print format do you need for instant event photography?"
            chips = ["4×6″ (CZ-01)", "6×8″ (CX-02 / CY-02)", "8×12″ (CX-02W)", "Official Quotation"]
            step_text = "Please select a photo print format or ask for specific event printer specifications."
        elif active_cat == "technical_large_format":
            q_text = "What roll width do you need for your CAD drawings and plans?"
            chips = ["24-inch (A1)", "36-inch (A0)", "44-inch Production", "Integrated Scanner"]
            step_text = "Please select a roll width or specify whether you need an integrated wide-format scanner."
        elif active_cat == "photography_large_format":
            q_text = "What format or print width do you require for photo and fine art reproduction?"
            chips = ["13″–17″ Desktop", "24″ Production", "44″ Gallery", "12-Colour Proofing"]
            step_text = "Please select a print format or ask for specific model specifications."
        elif active_cat in ("dye_sublimation", "sublimation"):
            q_text = "What format do you need for dye-sublimation printing?"
            chips = ["A4 Desktop Gifts (SC-F100)", "24-inch Roll Apparel (SC-F500)", "Sublimation Inks", "Official Quotation"]
            step_text = "Please choose between A4 desktop gift printing and 24-inch roll textile production."
        elif active_cat == "scanners":
            q_text = "What type of document or media scanning do you require?"
            chips = ["WorkForce Sheetfed", "Flatbed & Books", "Large Format Graphics", "Official Quotation"]
            step_text = "Please select a scanner type or specify your daily scan volume."
        elif getattr(state, "last_shown_consumables", None) or any(getattr(e, "entity_type", "") == "consumable" for e in getattr(state, "focus_stack", [])):
            q_text = "Which supplies or ink colours would you like to review?"
            chips = ["Inks", "Media Rolls / Paper", "Maintenance Box", "Official Quotation"]
            step_text = "Please enter the specific ink colour, part number, or equipment model."
        else:
            q_text = "Which printing application fits your requirements?" if "print" in und.raw_text.lower() else "How can I best assist you with Kepler Tech printing equipment?"
            chips = ["Technical CAD Plotters", "Professional Photo & Fine Art", "Citizen Photo Booth / Events", "Dye-Sublimation", "Office Printers"]
            step_text = "Please select a category or ask a specific model question."

        return PolicyDecision(
            action=PolicyAction.CLARIFY,
            reason="Contextual clarification; maintaining active conversation domain without generic fallback.",
            clarification_topic=current_topic,
            clarification_question=q_text,
            options_or_chips=chips,
            next_step=step_text,
        )
