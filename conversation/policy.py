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

logger = logging.getLogger("conversation.policy")


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
    next_step: str = ""


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

        # 1. Handoff Request
        if act == DialogueAct.HANDOFF_REQUEST or any(w in und.raw_text.lower() for w in ["speak to human", "sales person", "agent", "call me"]):
            return PolicyDecision(
                action=PolicyAction.NOT_VERIFIED_HANDOFF,
                reason="Customer explicitly requested human sales specialist.",
                options_or_chips=["Call +971 4 323 1008", "Email sales@keplertech.ae", "Visit Showroom"],
                is_handoff=True,
                next_step="Our sales specialists are available at sales@keplertech.ae or +971 4 323 1008.",
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
            chips = ["Office Printers", "Technical CAD Plotters", "Photo & Fine Art", "Dye-Sublimation"]
            if state.pending_question and state.pending_question.options:
                chips = [str(o.get("label") or o.get("id")) for o in state.pending_question.options]

            if state.turn_count == 0 and not state.pending_question:
                greeting_text = (
                    "Hello and welcome to Kepler Tech! Are you looking for technical CAD plotters, "
                    "photo & fine art printers, dye-sublimation systems, or high-speed office printers?"
                )
            else:
                greeting_text = "Hello! How can I assist you further with your equipment requirements today?"

            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Conversational greeting.",
                options_or_chips=chips,
                next_step=greeting_text,
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
                next_step="To get you exact specifications without delay, our senior sales consultant will assist you directly at sales@keplertech.ae.",
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

        # 6. Consumables Lookup Intent
        if intent == Intent.CONSUMABLES_LOOKUP:
            target = resolved.resolved_target_product
            if target:
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

        # 9. Recommendation / Category Discovery Intent
        if intent == Intent.RECOMMEND:
            cat_slot = und.slots.get("target_category")
            cat_val = cat_slot.value if cat_slot else getattr(state, "category", None)

            if cat_val in ("office_workforce", "office_printer", "office"):
                state.category = "office_printer"
                rec = EvidenceRecord(
                    claim=(
                        "For office and business document printing, Kepler Tech supplies the Epson WorkForce "
                        "and WorkForce Enterprise series with Heat-Free inkjet technology:\n\n"
                        "• **Epson WorkForce Pro WF-C5890**: Fast A4 desktop color MFP for workgroups.\n"
                        "• **Epson WorkForce Pro WF-C878R**: Departmental A3 MFP with high-yield Replaceable Ink Packs (up to 86,000 pages).\n"
                        "• **Epson WorkForce Enterprise AM-C4000**: Ultra-fast 40 ppm departmental color MFP.\n\n"
                        "What is your typical monthly print volume or preferred paper format (A4 or A3)?"
                    ),
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalogue_products.json",
                    field="category",
                    entity_ids=["epson-wf-c5890-dwf", "epson-wf-c878r-dwf", "epson-am-c4000"],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Recommended verified office printers.",
                    target_entity_id="epson-wf-c5890-dwf",
                    supporting_product_ids=["epson-wf-c878r-dwf", "epson-am-c4000"],
                    options_or_chips=["A4 Desktop (WF-C5890)", "A3 Workgroup (WF-C878R)", "Enterprise MFP (AM-C4000)", "Request Official Quote"],
                    evidence_records=[rec],
                    next_step="What is your typical monthly print volume or preferred paper format (A4 or A3)?",
                )

            elif cat_val == "dye_sublimation":
                state.category = "dye_sublimation"
                rec = EvidenceRecord(
                    claim=(
                        "Kepler Tech is an official distributor for Epson SureColor dye-sublimation systems:\n\n"
                        "• **Epson SureColor SC-F100**: Compact A4 desktop printer for custom mugs and small merchandise.\n"
                        "• **Epson SureColor SC-F500**: 24-inch desktop sublimation printer with refillable 140 ml ink bottles.\n\n"
                        "Are you printing smaller gift items (A4) or larger apparel & textile transfers (24-inch)?"
                    ),
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalogue_products.json",
                    field="category",
                    entity_ids=["epson-sc-f100", "epson-sc-f500"],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Recommended verified dye-sublimation printers.",
                    target_entity_id="epson-sc-f500",
                    supporting_product_ids=["epson-sc-f100"],
                    options_or_chips=["A4 Desktop (SC-F100)", "24-inch Desktop (SC-F500)", "Sublimation Inks", "Official Quote"],
                    evidence_records=[rec],
                    next_step="Are you printing smaller gift items (A4) or larger apparel & textile transfers (24-inch)?",
                )

            elif cat_val in ("technical_cad", "technical_large_format"):
                state.category = "technical_large_format"
                rec = EvidenceRecord(
                    claim=(
                        "For architectural drawings, engineering blueprints, and line maps, Kepler Tech offers the Epson SureColor T-Series:\n\n"
                        "• **Epson SureColor SC-T3100**: Compact 24-inch wireless desktop technical plotter.\n"
                        "• **Epson SureColor SC-T5400**: High-speed 36-inch production plotter for commercial CAD & GIS.\n\n"
                        "Do you need a 24-inch (A1) or 36-inch (A0) plotter format?"
                    ),
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalogue_products.json",
                    field="category",
                    entity_ids=["epson-sc-t3100", "epson-sc-t5400"],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Recommended verified CAD & technical plotters.",
                    target_entity_id="epson-sc-t3100",
                    supporting_product_ids=["epson-sc-t5400"],
                    options_or_chips=["24-inch (SC-T3100)", "36-inch (SC-T5400)", "UltraChrome XD2 Inks", "Official Quote"],
                    evidence_records=[rec],
                    next_step="Do you need a 24-inch (A1) or 36-inch (A0) plotter format?",
                )

            elif cat_val in ("photo_fine_art", "photography_large_format"):
                state.category = "photography_large_format"
                rec = EvidenceRecord(
                    claim=(
                        "For professional photography, fine art galleries, and proofing, we offer the Epson SureColor P-Series:\n\n"
                        "• **Epson SureColor SC-P700**: 13-inch (A3+) professional photo printer with 10-color UltraChrome PRO10 ink.\n"
                        "• **Epson SureColor SC-P900**: 17-inch (A2+) professional photo printer with dedicated matte and photo black channels.\n\n"
                        "What is your target print format (13-inch A3+ or 17-inch A2+)?"
                    ),
                    verified=True,
                    status=CompatibilityStatus.VERIFIED_YES,
                    source_file="catalogue_products.json",
                    field="category",
                    entity_ids=["epson-sc-p700", "epson-sc-p900"],
                )
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason="Recommended verified photo & fine art printers.",
                    target_entity_id="epson-sc-p700",
                    supporting_product_ids=["epson-sc-p900"],
                    options_or_chips=["13-inch A3+ (SC-P700)", "17-inch A2+ (SC-P900)", "UltraChrome PRO10 Inks", "Official Quote"],
                    evidence_records=[rec],
                    next_step="What is your target print format (13-inch A3+ or 17-inch A2+)?",
                )

            else:
                # Broad inquiry without category specified ("I want to buy a printer")
                state.clarifications_asked[current_topic] = topic_clarifications + 1
                return PolicyDecision(
                    action=PolicyAction.CLARIFY,
                    reason="Customer stated general purchase inquiry without category.",
                    clarification_topic=current_topic,
                    clarification_question="Kepler Tech supplies specialized commercial printers for different applications. What type of printing do you need?",
                    options_or_chips=["Office & Business Documents", "Technical CAD Drawings", "Photography & Fine Art", "Dye-Sublimation Merchandise"],
                    next_step="Please select your application.",
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
                val, rec = EvidenceEngine.get_attribute(target.id, "display_name")
                return PolicyDecision(
                    action=PolicyAction.ANSWER,
                    reason=f"Product info inquiry for {target.name}.",
                    target_entity_id=target.id,
                    options_or_chips=["Technical Specifications", "Compatible Consumables", "Official Quotation"],
                    evidence_records=[rec] if rec else [],
                    next_step=f"Would you like to see detailed specifications or compatible consumables for the {target.name}?",
                )

        # 10. Availability & Price Policy Intent (Strict No Chat Pricing Policy)
        if intent == Intent.AVAILABILITY_OR_PRICE_POLICY:
            target = resolved.resolved_target_product
            t_name = target.name if target else "our equipment"
            return PolicyDecision(
                action=PolicyAction.ANSWER,
                reason="Commercial policy inquiry: adhere strictly to sales desk quotation policy.",
                target_entity_id=target.id if target else None,
                options_or_chips=["Request Official Quote", "Contact Sales Desk", "View Product Page"],
                next_step="Official tax invoices and volume discounts are provided directly by our sales desk at sales@keplertech.ae or +971 4 323 1008.",
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
        return PolicyDecision(
            action=PolicyAction.CLARIFY,
            reason="Ambiguous input; clarify customer needs with structured chips.",
            clarification_topic=current_topic,
            clarification_question="How can I best assist you with Kepler Tech printing equipment?",
            options_or_chips=["CAD Technical Plotters", "Professional Photo", "Dye-Sublimation", "Office Printers"],
            next_step="Please select a category or ask a specific model question.",
        )
