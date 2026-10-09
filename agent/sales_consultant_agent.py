"""
Single Canonical Sales Consultant Agent for Kepler Tech SalesAI.

The sole authoritative decision maker across all conversational turns.
Eliminates competing decision brains (decision_engine.py, workflow conflicts,
and scattered orchestrator regexes).

Consumes:
- CanonicalTurnUnderstanding
- ConversationState
- QuestionLedger
- CustomerBehavior
- InformationSufficiency
- ActionBudget

Produces:
- AgentDecision
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
import logging
import re

from domain.canonical_turn import CanonicalTurnUnderstanding, CanonicalQuestion
from domain.conversation_state import ConversationState
from conversation.question_ledger import QuestionStatus
from agent.information_sufficiency import InformationSufficiency, SufficiencyStatus
from agent.stop_policy import ActionBudget, StopPolicy

logger = logging.getLogger("sales_consultant_agent")


class AgentAction(str, Enum):
    ANSWER = "ANSWER"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    RETRIEVE = "RETRIEVE"
    COMPARE = "COMPARE"
    RECOMMEND = "RECOMMEND"
    HANDLE_OBJECTION = "HANDLE_OBJECTION"
    CONFIRM = "CONFIRM"
    HANDOFF = "HANDOFF"
    CLOSE = "CLOSE"


@dataclass
class AgentDecision:
    """The canonical decision determining the agent's turn execution."""
    action: AgentAction
    reason: str
    target_product: Optional[str] = None
    target_question_ids: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    response_mode: str = "direct_answer"
    stop_after_response: bool = False
    clarification_field: Optional[str] = None
    clarification_question: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "target_product": self.target_product,
            "target_question_ids": list(self.target_question_ids),
            "required_tools": list(self.required_tools),
            "required_evidence": list(self.required_evidence),
            "response_mode": self.response_mode,
            "stop_after_response": self.stop_after_response,
            "clarification_field": self.clarification_field,
            "clarification_question": self.clarification_question,
        }


class SalesConsultantAgent:
    """Single canonical brain governing conversation flow and tool execution."""

    def __init__(self):
        pass

    def plan(
        self,
        understanding: CanonicalTurnUnderstanding,
        state: ConversationState,
        evidence_bundle: Optional[Any] = None,
        budget: Optional[ActionBudget] = None,
    ) -> AgentDecision:
        """
        Determines the single authoritative action for the current turn.
        Strict Priority:
        1. Human handoff
        2. Closing
        3. Frustration handling (answer exact question, zero sales pitch, stop)
        4. High-intent purchase (official purchasing link / invoice)
        5. Price objection handling
        6. Explicit Customer Questions (HIGHEST FACTUAL PRIORITY)
        7. Product Comparison
        8. Information Sufficiency / Warranted Clarification
        9. Product Recommendation
        """
        budget = budget or ActionBudget()
        behavior = understanding.customer_behavior
        active_prod = state.get_canonical_focus_id() if hasattr(state, "get_canonical_focus_id") else None

        # ── 1. Human Specialist Handoff ──────────────────────────────────────
        if understanding.dialogue_act == "human_handover" or "agent" in understanding.primary_goal or "human" in understanding.primary_goal:
            return AgentDecision(
                action=AgentAction.HANDOFF,
                reason="Customer explicitly requested a human specialist.",
                response_mode="handoff",
                stop_after_response=True,
            )

        # ── 2. Polite Closing ────────────────────────────────────────────────
        if behavior == "CLOSING" or understanding.primary_goal in ("closing", "close_conversation"):
            return AgentDecision(
                action=AgentAction.CLOSE,
                reason="Customer indicated conversation closing.",
                response_mode="closing",
                stop_after_response=True,
            )

        # ── 3. Frustrated Customer Recovery ──────────────────────────────────
        if behavior == "FRUSTRATED":
            # Priority: Acknowledge and directly answer any pending questions, strictly no pitch
            unanswered = []
            if state.question_ledger:
                unanswered = state.question_ledger.get_unanswered_customer_questions()
            q_ids = [q.id for q in unanswered]
            return AgentDecision(
                action=AgentAction.ANSWER,
                reason="Customer is frustrated. Directly answering question with zero pitch or questionnaires.",
                target_product=active_prod,
                target_question_ids=q_ids,
                required_tools=["spec_lookup"] if active_prod else [],
                response_mode="frustration_recovery",
                stop_after_response=True,
            )

        # ── 4. High-Intent Buying / Order ────────────────────────────────────
        if behavior in ("READY_TO_BUY", "HIGH_INTENT") or understanding.primary_goal == "purchase_intent":
            return AgentDecision(
                action=AgentAction.CONFIRM,
                reason="Customer showed ready-to-buy intent; guiding directly to purchase / invoice.",
                target_product=active_prod,
                required_tools=["product_lookup", "price_lookup"],
                response_mode="purchase_intent",
                stop_after_response=True,
            )

        # ── 5. Price Objection ───────────────────────────────────────────────
        if behavior == "PRICE_SENSITIVE" and understanding.primary_goal == "price_objection":
            return AgentDecision(
                action=AgentAction.HANDLE_OBJECTION,
                reason="Customer expressed price sensitivity; providing consultative TCO and alternative.",
                target_product=active_prod,
                required_tools=["price_lookup", "catalog_search"],
                response_mode="price_objection",
                stop_after_response=False,
            )

        # ── 6. Product Comparison (Two or More Models) ───────────────────────
        has_compared_pair = len(getattr(state, "compared_product_ids", [])) >= 2 or len(getattr(state, "comparison_product_ids", [])) >= 2
        is_pair_followup = has_compared_pair and (
            any(w in understanding.normalized_message.lower() for w in ["which of", "those two", "these two", "which one", "second one", "2nd one", "first one", "second printer", "second model", "both"])
            or bool(re.search(r"\bwhich\s+(?:of\s+(?:those|these|the)(?:\s+two)?\s+|one\s+|model\s+)?", understanding.normalized_message.lower()))
        )
        is_comparing = behavior == "COMPARING" or understanding.primary_goal in ("product_comparison", "investment_cost_comparison") or len(understanding.mentioned_products) >= 2 or is_pair_followup
        if is_comparing and (len(understanding.mentioned_products) >= 2 or has_compared_pair):
            prods = understanding.mentioned_products or getattr(state, "compared_product_ids", []) or getattr(state, "comparison_product_ids", [])
            return AgentDecision(
                action=AgentAction.COMPARE,
                reason="Customer requested comparison between options.",
                target_product=prods[0] if prods else active_prod,
                required_tools=["comparison_tool", "spec_lookup"],
                response_mode="comparison",
                stop_after_response=False,
            )

        # ── 6.5. Direct SKU / Consumable Lookup & Unique Capability Match ───
        norm_l = understanding.normalized_message.lower()
        has_sku = bool(re.search(r"\b(c1[123][a-z0-9]{5,9}|c13s\d+|c12c\d+|ifa\s*\d+|olm\s*\d+|cx2\.(?:4x6|6x8)|cy-ms[a-z0-9.\-]*|cz-ms[a-z0-9.\-]*|cx2w\s*812)\b", norm_l))
        if has_sku or understanding.primary_goal == "consumables_lookup":
            return AgentDecision(
                action=AgentAction.ANSWER,
                reason="Direct SKU / consumable lookup requested.",
                target_product=active_prod,
                required_tools=["product_lookup"],
                response_mode="direct_answer",
                stop_after_response=True,
            )

        reqs = state.requirements or {}
        if reqs.get("ribbon_rewind") or any(k in norm_l for k in ["single paper roll", "single roll", "with out media loss", "without media loss", "8x12", "8×12"]):
            target_cx = "citizen-cx-02w" if ("8x12" in norm_l or "8×12" in norm_l) else "citizen-cx-02"
            return AgentDecision(
                action=AgentAction.RECOMMEND,
                reason="Explicit unique capability or format specified.",
                target_product=target_cx,
                required_tools=["catalog_search"],
                response_mode="recommendation",
                stop_after_response=False,
            )

        # ── 7. Explicit Customer Question(s) (HIGHEST PRIORITY) ──────────────
        # Every explicit customer question must be answered BEFORE any sales qualification
        unanswered_qs = []
        if state.question_ledger:
            unanswered_qs = state.question_ledger.get_unanswered_customer_questions()

        if unanswered_qs or understanding.explicit_questions:
            # Questions take precedence over all qualification questionnaires!
            target_p = None
            if understanding.explicit_questions:
                target_p = understanding.explicit_questions[0].target_product
            if not target_p and unanswered_qs:
                target_p = unanswered_qs[0].target_product
            if not target_p:
                target_p = active_prod

            q_ids = [q.id for q in (understanding.explicit_questions or unanswered_qs)]
            tools = []
            # Select only necessary tools based on requested attributes
            attrs = understanding.requested_information
            if any(a in ("price", "cost") for a in attrs):
                tools.append("price_lookup")
            if any(a in ("media_yield", "ink_compatibility") for a in attrs):
                tools.append("media_lookup")
            if any(a in ("print_speed", "physical_specs", "wifi_support", "warranty", "print_width") for a in attrs) or not tools:
                tools.append("spec_lookup")

            # Check if evidence is already available or needs retrieval
            if evidence_bundle and budget.executed_tools:
                action_type = AgentAction.ANSWER
            else:
                action_type = AgentAction.RETRIEVE

            return AgentDecision(
                action=action_type,
                reason="Customer asked explicit technical/factual questions. Prioritizing direct answers.",
                target_product=target_p,
                target_question_ids=q_ids,
                required_tools=tools,
                required_evidence=attrs,
                response_mode="direct_answer",
                stop_after_response=True,  # Default to stopping after answering technical queries unless followup warranted
            )

        # ── 8. Single-product comparison fallback ────────────────────────────
        if is_comparing:
            prods = understanding.mentioned_products or getattr(state, "comparison_product_ids", [])
            return AgentDecision(
                action=AgentAction.COMPARE,
                reason="Customer requested comparison between options.",
                target_product=prods[0] if prods else active_prod,
                required_tools=["comparison_tool", "spec_lookup"],
                response_mode="comparison",
                stop_after_response=False,
            )

        # ── 8. Warranted Clarification (Information Sufficiency Check) ───────
        warranted = InformationSufficiency.get_next_warranted_question(
            state=state,
            current_goal=understanding.primary_goal
        )
        if warranted:
            field_key, question_text = warranted
            return AgentDecision(
                action=AgentAction.ASK_CLARIFICATION,
                reason=f"Mandatory requirement '{field_key}' is missing to proceed with recommendation.",
                clarification_field=field_key,
                clarification_question=question_text,
                response_mode="qualification",
                stop_after_response=True,
            )

        # ── 9. Product Recommendation ────────────────────────────────────────
        return AgentDecision(
            action=AgentAction.RECOMMEND,
            reason="Customer is exploring solutions; presenting top eligible recommendations.",
            target_product=active_prod,
            required_tools=["catalog_search"],
            response_mode="recommendation",
            stop_after_response=False,
        )
