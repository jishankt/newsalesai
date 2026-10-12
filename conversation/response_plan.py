"""
Structured Response Plan, Renderer, and Grounded Validator for Kepler Tech SalesAI.
Phase 5: Structured response plan, diverse human openers (3-turn no-repeat),
and strict pre-transmission validators (evidence grounding, intent relevance,
focus consistency, no-pricing-in-chat compliance).
"""

import os
import re
import random
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from conversation.understanding import DialogueAct, Intent
from conversation.dialogue_state import DialogueState, ResolvedTurn, SalientEntity
from conversation.policy import PolicyDecision, PolicyAction
from catalog.evidence import EvidenceEngine, EvidenceRecord, CompatibilityStatus, knowledge_graph

logger = logging.getLogger("conversation.response_plan")


# ── Response Plan Schema ──────────────────────────────────────────────────────

class ResponsePlan(BaseModel):
    direct_answer: str
    assumption: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    product_cards: List[Dict[str, Any]] = Field(default_factory=list)
    consumable_cards: List[Dict[str, Any]] = Field(default_factory=list)
    chips: List[str] = Field(default_factory=list)
    confirm_buttons: List[Dict[str, str]] = Field(default_factory=list)
    next_step: str = ""
    formatted_reply: str = ""
    source: str = "unified_understanding"
    evidence_records: List[EvidenceRecord] = Field(default_factory=list)
    is_valid: bool = True
    validation_errors: List[str] = Field(default_factory=list)


# ── Human Openers Rotation (3-turn no-repeat) ─────────────────────────────────

OPENERS_POOL = [
    "Certainly!",
    "Yes, absolutely.",
    "Here are the verified details:",
    "Glad to assist with that.",
    "Understood.",
    "Good question!",
    "Here is the official confirmation:",
]


def _get_varied_opener(state: DialogueState) -> str:
    """Selects an opener avoiding the ones used in the last 3 turns."""
    recent_history = getattr(state, "recent_openers", []) or []
    available = [op for op in OPENERS_POOL if op not in recent_history[-3:]]
    if not available:
        available = OPENERS_POOL
    chosen = random.choice(available)
    if not hasattr(state, "recent_openers"):
        state.recent_openers = []
    state.recent_openers.append(chosen)
    return chosen


# ── Response Plan Builder ─────────────────────────────────────────────────────

class ResponsePlanBuilder:
    """Constructs a grounded, interactive response plan from policy decisions."""

    @classmethod
    def build(
        cls,
        decision: PolicyDecision,
        resolved: ResolvedTurn,
        state: DialogueState,
    ) -> ResponsePlan:
        und = resolved.understanding
        cards: List[Dict[str, Any]] = []
        c_cards: List[Dict[str, Any]] = []
        confirm_buttons: List[Dict[str, str]] = []
        chips = list(decision.options_or_chips)
        direct_answer = ""
        assumption = decision.assumption_text
        evidence_ids: List[str] = []

        # Gather evidence IDs
        for rec in decision.evidence_records:
            evidence_ids.extend(rec.entity_ids)

        # 1. Compatibility Answer Flow
        if decision.action in (PolicyAction.ANSWER, PolicyAction.ANSWER_WITH_STATED_ASSUMPTION) and und.intent == Intent.COMPATIBILITY_CHECK:
            rec = decision.evidence_records[0] if decision.evidence_records else None
            direct_answer = rec.claim if rec else "Compatibility could not be verified."

            # Attach Hardware Card for target printer
            if decision.target_entity_id:
                t_node = knowledge_graph.nodes.get(decision.target_entity_id.lower())
                if t_node:
                    cards.append({
                        "card_type": "hardware",
                        "id": t_node.id,
                        "model_family": t_node.attributes.get("model_family") or t_node.name,
                        "display_name": t_node.name,
                        "primary_category": t_node.attributes.get("category"),
                        "product_url": t_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{t_node.id}",
                        "image_url": t_node.attributes.get("image_url") or "/static/img/products/default.png",
                        "badges": ["Verified Official Model"],
                    })

            # Attach Consumable Card for active item
            if decision.active_item_id:
                c_node = knowledge_graph.nodes.get(decision.active_item_id.upper())
                if c_node:
                    c_cards.append({
                        "card_type": "consumable",
                        "sku": c_node.id,
                        "name": c_node.name,
                        "category": c_node.attributes.get("type", "consumable"),
                        "color": c_node.attributes.get("color"),
                        "product_url": c_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{c_node.id.lower()}",
                        "badges": ["Genuine Kepler Tech Consumable"],
                    })

            confirm_buttons = [
                {"label": "Yes, show full specs", "payload": f"specs_{decision.target_entity_id}"},
                {"label": "Show compatible inks", "payload": f"inks_{decision.target_entity_id}"},
            ]

        # 2. Clarification Flow
        elif decision.action == PolicyAction.CLARIFY:
            direct_answer = decision.clarification_question or "Could you clarify your requirements?"

        # 3. Handoff Flow
        elif decision.action == PolicyAction.NOT_VERIFIED_HANDOFF:
            direct_answer = decision.next_step

        # 4. Out of Scope Flow
        elif decision.action == PolicyAction.OUT_OF_SCOPE_REDIRECT:
            direct_answer = (
                "Kepler Tech is an authorized distributor specializing in official Epson large-format "
                "and Citizen photo/dye-sublimation systems. We do not supply 3D printers, laser copiers, or third-party brands."
            )

        # 5. Default Answer Flow
        else:
            rec = decision.evidence_records[0] if decision.evidence_records else None
            direct_answer = rec.claim if rec else (decision.next_step or "Here is the information from our verified catalogue.")

        # Ensure hardware cards are attached whenever target_entity_id is present
        # Ensure hardware cards are attached whenever target_entity_id or supporting_product_ids are present
        all_target_ids: List[str] = []
        if decision.target_entity_id:
            all_target_ids.append(decision.target_entity_id)
        if getattr(decision, "supporting_product_ids", None):
            for spid in decision.supporting_product_ids:
                if spid not in all_target_ids:
                    all_target_ids.append(spid)

        for pid in all_target_ids:
            if not any(c.get("id") == pid for c in cards):
                t_node = knowledge_graph.nodes.get(pid.lower())
                if t_node and t_node.node_type == "printer":
                    cards.append({
                        "card_type": "hardware",
                        "id": t_node.id,
                        "model_family": t_node.attributes.get("model_family") or t_node.name,
                        "display_name": t_node.name,
                        "primary_category": t_node.attributes.get("category"),
                        "product_url": t_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{t_node.id}",
                        "image_url": t_node.attributes.get("image_url") or "/static/img/products/default.png",
                        "badges": ["Verified Official Model"],
                    })

        # Ensure consumable cards are attached whenever active_item_id is present
        if decision.active_item_id and not c_cards:
            c_node = knowledge_graph.nodes.get(decision.active_item_id.upper())
            if c_node and c_node.node_type == "consumable":
                c_cards.append({
                    "card_type": "consumable",
                    "sku": c_node.id,
                    "name": c_node.name,
                    "category": c_node.attributes.get("type", "consumable"),
                    "color": c_node.attributes.get("color"),
                    "product_url": c_node.attributes.get("url") or f"https://www.keplertechllc.com/product/{c_node.id.lower()}",
                    "badges": ["Genuine Kepler Tech Consumable"],
                })

        # Assemble full formatted text
        parts = []
        if assumption:
            parts.append(f"*{assumption}*\n")
        parts.append(direct_answer)
        if decision.next_step and decision.next_step not in direct_answer:
            parts.append(f"\n\n{decision.next_step}")

        formatted_text = "".join(parts).strip()

        plan = ResponsePlan(
            direct_answer=direct_answer,
            assumption=assumption,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            product_cards=cards,
            consumable_cards=c_cards,
            chips=chips,
            confirm_buttons=confirm_buttons,
            next_step=decision.next_step,
            formatted_reply=formatted_text,
            evidence_records=decision.evidence_records,
            source=f"unified:{decision.action.value.lower()}",
        )

        # Run strict grounding and policy validators
        validated_plan = ResponsePlanValidator.validate(plan, resolved, state)
        return validated_plan


# ── Response Plan Pre-Transmission Validators ─────────────────────────────────

class ResponsePlanValidator:
    """
    Enforces 4 strict pre-flight invariant gates before emitting any reply:
    1. Grounding check: Every SKU/model in text exists in evidence
    2. Answers the question check: Reply addresses customer's intent
    3. Focus consistency: Focus model is not silently swapped
    4. Commercial policy check: No chat pricing or volume discount promises
    """

    PRICE_NUMERIC_PATTERN = re.compile(r"\b(?:aed\s*\d+|price\s*is\s*\d+|\$\s*\d+)\b", re.I)

    @classmethod
    def validate(
        cls,
        plan: ResponsePlan,
        resolved: ResolvedTurn,
        state: DialogueState,
    ) -> ResponsePlan:
        errors: List[str] = []
        text = plan.formatted_reply

        # 1. Commercial Policy Guardrail: No chat pricing or volume discount promises
        # Official quotations must strictly route to sales desk
        if cls.PRICE_NUMERIC_PATTERN.search(text) and "official request" not in text.lower():
            errors.append("Commercial policy violation: unverified price numeric claim in text.")

        # 2. Grounding Check: If text mentions a SKU, verify it exists in evidence records
        sku_mentions = re.findall(r"\b(c1[123][a-z0-9]{5,9}|cy-ms\w+|cz-ms\w+|cx2\w+)\b", text.lower())
        for sm in sku_mentions:
            if not any(sm.upper() in eid.upper() for eid in plan.evidence_ids):
                # Allow if it's the known active item
                if not (resolved.resolved_active_item and sm.upper() in resolved.resolved_active_item.id.upper()):
                    errors.append(f"Grounding violation: SKU '{sm}' in text without supporting evidence.")

        # 3. Intent Relevance Check
        if resolved.understanding.intent == Intent.COMPATIBILITY_CHECK:
            if not any(w in text.lower() for w in ["yes", "no", "compatible", "not compatible", "suitable"]):
                errors.append("Relevance violation: compatibility check did not contain a yes/no verification.")

        # 4. Silent Focus Switch Check
        if resolved.resolved_target_product and state.get_current_focus("printer"):
            current_f = state.get_current_focus("printer")
            new_f = resolved.resolved_target_product
            # If changed without explicit mention in user text or entities
            is_explicitly_mentioned = (
                new_f.id in resolved.understanding.raw_text.lower()
                or any(e.normalised_id == new_f.id for e in resolved.understanding.entities)
                or any(r.resolved_entity and r.resolved_entity.id == new_f.id for r in resolved.resolved_referents)
            )
            if current_f.id != new_f.id and not is_explicitly_mentioned:
                errors.append(f"Focus violation: switched focus from {current_f.id} to {new_f.id} without user mention.")

        if errors:
            logger.warning(f"Response plan validation errors: {errors}. Falling back to deterministic template.")
            plan.is_valid = False
            plan.validation_errors = errors
            # Fallback to deterministic template: use exact claim from evidence record
            if plan.evidence_records:
                plan.formatted_reply = plan.evidence_records[0].claim
                if plan.next_step:
                    plan.formatted_reply += f"\n\n{plan.next_step}"
            else:
                plan.formatted_reply = "I can only confirm specifications verified in our official catalogue. How can I assist you with your equipment requirements?"

        return plan
