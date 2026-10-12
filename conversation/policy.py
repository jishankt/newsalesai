"""
Fallback Policy Engine for Kepler Tech SalesAI.
Phase 4: Decide policy action:
ANSWER, ANSWER_WITH_STATED_ASSUMPTION, CONFIRM, CLARIFY, PARTIAL_ANSWER,
NOT_VERIFIED_HANDOFF, OUT_OF_SCOPE_REDIRECT, REPAIR.
Enforces anti-looping, frustration handling, zero dead-ends, and honest verification.
"""

import os
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from conversation.understanding import DialogueAct, Intent, TurnUnderstanding
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

        # 0a. Unlisted / Near Match Model Check (Never silently substitute unlisted models)
        unlisted_entities = [e for e in und.entities if e.entity_type == "unlisted_model"]
        if unlisted_entities:
            unlisted = unlisted_entities[0]
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
            all_intents = [intent] + und.secondary_intents
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
                    dest_str = "Sharjah and across all UAE emirates" if "sharjah" in und.raw_text.lower() else "across all UAE emirates"
                    d_claim = f"We provide insured direct delivery to {dest_str}, with on-site installation for production systems."
                    claims.append(d_claim)
                    ev_records.append(EvidenceRecord(
                        claim=d_claim,
                        verified=True,
                        status=CompatibilityStatus.VERIFIED_YES,
                        source_file="config.py",
                        field="delivery_policy",
                        entity_ids=[],
                    ))
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
                combined_claim = "\n\n".join(claims)
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
                reason="Request references non-catalogue categories or unapproved brands (3D printers, laser, edible).",
                options_or_chips=["Technical CAD Plotters", "Photo & Fine Art", "Dye-Sublimation", "Office Printers"],
                next_step="Kepler Tech specializes in Epson and Citizen large-format inkjet and dye-sublimation systems. Which category fits your requirements?",
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

        # 3b. Confusion / Context Review / Customer Frustration
        if act == DialogueAct.COMPLAINT or any(w in und.raw_text.lower() for w in ["what you asking", "what do you mean", "previous chat", "priviace chat", "answer after checking"]):
            # Clear stuck state so the customer is never locked in an unwanted flow
            state.category = None
            state.confirmed_slots.clear()
            return PolicyDecision(
                action=PolicyAction.CLARIFY,
                reason="Customer expressed confusion or requested chat review.",
                options_or_chips=["Office Printers", "CAD Technical Plotters", "Photo & Fine Art", "Document Scanners", "Speak to Specialist"],
                clarification_question=(
                    "My apologies for any confusion! Let's get right on track: "
                    "Are you looking for office printers, CAD technical plotters, photo & fine art printers, "
                    "dye-sublimation systems, or document scanners? You can also ask about specific models, delivery, or supplies."
                ),
                next_step="",
            )

        # 4. Repair / Correction Handling
        if act == DialogueAct.CORRECTION or any(w in und.raw_text.lower() for w in ["i meant", "no, i said", "not that", "changed my mind"]):
            # Record in corrections history
            state.corrections_history.append({"turn": state.turn_count, "raw": und.raw_text})
            # Acknowledge correction once, reuse stored answer, do not loop
            return PolicyDecision(
                action=PolicyAction.REPAIR,
                reason="Correction detected from customer.",
                target_entity_id=resolved.resolved_target_product.id if resolved.resolved_target_product else None,
                active_item_id=resolved.resolved_active_item.id if resolved.resolved_active_item else None,
                options_or_chips=["View Technical Specifications", "Compatible Consumables", "Request Official Quotation"],
                next_step="Understood! Let's update that.",
            )

        # 4. Anti-Looping & Clarification Limit Enforcement
        current_topic = intent.value
        topic_clarifications = state.clarifications_asked.get(current_topic, 0)
        if topic_clarifications >= cls.MAX_CLARIFICATIONS_PER_TOPIC:
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
                    clarification_question="Which printer or scanner model do you need consumables for?",
                    options_or_chips=["Epson SC-F500", "Epson SC-T3100", "Citizen CX-02", "Epson SC-P900"],
                    next_step="Please select your printer model.",
                )

        # 7. Comparison Intent
        if intent == Intent.COMPARE:
            models = [e.normalised_id for e in und.entities if e.entity_type == "model"]
            if len(models) >= 2:
                matrix, rec = EvidenceEngine.compare(models, ["category", "width", "resolution", "speed", "connectivity"])
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Compared verified models {models}.",
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
            delivery_text = (
                "Kepler Tech provides insured delivery across Dubai, Abu Dhabi, and all UAE emirates "
                "with fast express dispatch available.\n\n"
                "For heavy large-format printers and production equipment, our technical team provides dedicated "
                "site delivery, uncrating, and professional on-site installation."
            )
            rec = EvidenceRecord(
                claim=delivery_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="config.py",
                field="delivery_policy",
                entity_ids=[],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Customer asked about delivery and shipping services.",
                options_or_chips=["Showroom Location", "Request Official Quote", "Contact Sales Desk"],
                evidence_records=[rec],
                next_step="Would you like to arrange delivery for a specific printer or consumable order?",
            )

        # 8c. Explicit Target Model Request (Case 9: e.g. "I want the Epson SC-P900")
        if intent == Intent.RECOMMEND and resolved.resolved_target_product:
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
            "dye_sublimation": "dye_sublimation",
            "sublimation": "dye_sublimation",
            "scanners": "scanners",
            "scanner": "scanners",
        }
        canonical_new_cat = cat_map.get(new_cat_raw, new_cat_raw) if new_cat_raw else None

        from conversation.product_flows import resolve_flowchart_step, extract_flowchart_requirements
        flow_reqs = extract_flowchart_requirements(und.raw_text)

        is_flowchart_turn = False
        if intent in (Intent.RECOMMEND, Intent.OTHER) and not resolved.resolved_target_product and not resolved.resolved_active_item:
            if canonical_new_cat is not None:
                is_flowchart_turn = True
            elif getattr(state, "category", None) and (bool(flow_reqs) or any(c.lower() in und.raw_text.lower() for c in state.last_shown_chips)):
                is_flowchart_turn = True

        if is_flowchart_turn:
            if canonical_new_cat:
                if state.category != canonical_new_cat:
                    # User explicitly stated a new category: switch category and reset stale slots!
                    state.category = canonical_new_cat
                    state.confirmed_slots.clear()
                    state.focus_stack.clear()
                    state.last_shown_products.clear()
                    state.last_shown_consumables.clear()
            canonical_cat = state.category

            # Accumulate extracted requirements into state.confirmed_slots
            new_reqs = extract_flowchart_requirements(und.raw_text, state.confirmed_slots)
            state.confirmed_slots.update(new_reqs)

            step = resolve_flowchart_step(canonical_cat, state.confirmed_slots, und.raw_text)

            # If a specific product or leaf was reached
            if step.is_leaf and step.target_product_id:
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
                    if "stand" in raw_l:
                        attr = "stand"
                    elif "speed" in raw_l or "fast" in raw_l or "ppm" in raw_l:
                        attr = "print_speed"
                    elif "dpi" in raw_l or "resolution" in raw_l:
                        attr = "dpi"
                    elif "width" in raw_l or "size" in raw_l:
                        attr = "width"
                    elif "connectivity" in raw_l or "wifi" in raw_l or "wi-fi" in raw_l or "network" in raw_l:
                        attr = "connectivity"

                if attr:
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
                        return PolicyDecision(
                            action=PolicyAction.ANSWER,
                            reason=f"Verified attribute '{attr}' retrieved for {target.name}.",
                            target_entity_id=target.id,
                            options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                            evidence_records=[rec],
                            next_step=f"Would you like to see additional specifications or compatible supplies for the {target.name}?",
                        )
                else:
                    # General product info overview from verified attributes
                    p_meta = target.metadata or {}
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

        # 10. Availability & Price Policy Intent (Strict No Chat Pricing Policy)
        if intent == Intent.AVAILABILITY_OR_PRICE_POLICY:
            target = resolved.resolved_target_product
            t_name = target.name if target else "our equipment"
            p_claim = f"Commercial pricing, tax invoices, and volume discounts for the **{t_name}** are provided directly through our official sales desk."
            rec = EvidenceRecord(
                claim=p_claim,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="config.py",
                field="pricing_policy",
                entity_ids=[target.id] if target else [],
            )
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Commercial policy inquiry: adhere strictly to sales desk quotation policy without disclosing digits.",
                target_entity_id=target.id if target else None,
                options_or_chips=["Request Official Quote", "Contact Sales Desk", "View Product Page"],
                evidence_records=[rec],
                next_step=f"Official tax invoices and volume discounts are provided directly by our sales desk at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}.",
            )

        # 11. Contact Showroom Intent
        if intent == Intent.CONTACT_SHOWROOM:
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Showroom and location inquiry.",
                options_or_chips=["Showroom Location", "Opening Hours", "Contact Numbers"],
                next_step="Our showroom is located at D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai (Monday–Friday 8:30 AM – 5:30 PM).",
            )

        # 12. Fallback Clarify
        state.clarifications_asked[current_topic] = topic_clarifications + 1
        q_text = "Which printing application fits your requirements?" if "print" in und.raw_text.lower() else "How can I best assist you with Kepler Tech printing equipment?"
        return PolicyDecision(
            action=PolicyAction.CLARIFY,
            reason="Ambiguous input; clarify customer needs with structured chips.",
            clarification_topic=current_topic,
            clarification_question=q_text,
            options_or_chips=["Technical CAD Plotters", "Professional Photo & Fine Art", "Dye-Sublimation", "Office Printers"],
            next_step="Please select a category or ask a specific model question.",
        )
