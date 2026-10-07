"""
Bounded Agent Planner for Kepler Tech SalesAI.

Determines the optimal next action for the sales consultant using an explicit
hierarchy (ANSWER > RETRIEVE > RECOMMEND > ASK), enforces a strict limit of 4
internal iterations per turn, and prevents tool or question loops.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Tuple
import logging

from domain.turn_understanding import TurnUnderstanding, TurnQuestion
from domain.conversation_state import ConversationState
from conversation.requirement_coverage import RequirementCoverageModel
from conversation.question_ledger import QuestionLedger
from conversation.goal_manager import GoalType

logger = logging.getLogger("agent_planner")


class PlannerAction(str, Enum):
    ANSWER = "answer"
    RETRIEVE = "retrieve"
    SEARCH = "search"
    RECOMMEND = "recommend"
    COMPARE = "compare"
    ASK = "ask"
    HANDOFF = "handoff"
    FINISH = "finish"


@dataclass
class PlanStep:
    action: PlannerAction
    target_tool: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    response_mode: Optional[str] = None
    target_question_key: Optional[str] = None


class AgentPlanner:
    """Bounded, goal-aware action planner for customer conversations."""

    MAX_ACTIONS_PER_TURN = 4

    def __init__(self):
        self.executed_tools: List[Tuple[str, str]] = []  # List of (tool_name, args_repr)
        self.tool_results_history: List[Dict[str, Any]] = []

    def reset_turn(self):
        """Resets action tracking at the start of a turn."""
        self.executed_tools.clear()
        self.tool_results_history.clear()

    def plan_next_step(
        self,
        understanding: TurnUnderstanding,
        state: ConversationState,
        evidence_available: bool = False,
        iteration_count: int = 1
    ) -> PlanStep:
        """
        Determines the next bounded action.
        Follows priority contract:
        1. Human handoff / Escalate
        2. Customer closing -> FINISH
        3. Frustration recovery -> ANSWER
        4. Explicit customer questions -> RETRIEVE (if needed) then ANSWER
        5. Comparison query -> COMPARE
        6. Recommendation request -> RECOMMEND (if sufficient info) else ASK (max 1)
        7. Discovery / Qualification -> ASK (only genuinely unknown essential fields)
        """
        if iteration_count > self.MAX_ACTIONS_PER_TURN:
            logger.warning("Reached maximum allowed actions per turn (4). Forcing ANSWER/FINISH.")
            return PlanStep(
                action=PlannerAction.ANSWER,
                reason="Hard limit of 4 actions reached; concluding turn.",
                response_mode="direct_answer"
            )

        # 1. Human Handoff
        if understanding.dialogue_act == "human_handover" or "agent" in understanding.primary_intent:
            return PlanStep(
                action=PlannerAction.HANDOFF,
                reason="Customer explicitly requested human specialist.",
                response_mode="handoff"
            )

        # 2. Closing / Ending
        if understanding.primary_intent in ("conversation_ending", "closing") or any(
            w in understanding.normalized_message.lower() for w in [
                "thanks", "thank you", "that's all", "done", "okay thanks", "perfect thanks"
            ]
        ):
            # Check if there are unresolved questions
            if not understanding.questions:
                return PlanStep(
                    action=PlannerAction.FINISH,
                    reason="Customer indicated conclusion of conversation.",
                    response_mode="closing"
                )

        # 3. Frustration Recovery
        if understanding.primary_intent == "frustration" or understanding.customer_behavior == "frustrated":
            return PlanStep(
                action=PlannerAction.ANSWER,
                reason="Frustration detected; prioritize direct answer to customer's core query.",
                response_mode="objection_handling"
            )

        # 4. Direct Customer Questions Priority (Never ask qualification if customer asked a question!)
        if understanding.questions:
            unresolved = understanding.questions
            # Determine target product
            target_prod_id = state.get_canonical_focus_id()
            if understanding.mentioned_products:
                target_prod_id = understanding.mentioned_products[0]

            if not evidence_available:
                # Check if we already called retrieval for this exact product & attributes
                sig = ("get_product_specs", f"{target_prod_id}:{understanding.requested_attributes}")
                if sig in self.executed_tools:
                    # Already retrieved, answer now
                    return PlanStep(
                        action=PlannerAction.ANSWER,
                        reason="Evidence already retrieved; compose direct answers.",
                        response_mode="direct_answer"
                    )
                return PlanStep(
                    action=PlannerAction.RETRIEVE,
                    target_tool="get_product_specs",
                    tool_args={
                        "product_identifier": target_prod_id or "active",
                        "attributes": understanding.requested_attributes
                    },
                    reason="Retrieve verified specs to answer explicit customer questions.",
                    response_mode="direct_answer"
                )
            else:
                return PlanStep(
                    action=PlannerAction.ANSWER,
                    reason="Verified evidence is ready to answer explicit questions.",
                    response_mode="direct_answer"
                )

        # 5. Comparison Request
        if understanding.primary_intent == "product_comparison" or "compare" in understanding.dialogue_act:
            if not evidence_available:
                return PlanStep(
                    action=PlannerAction.RETRIEVE,
                    target_tool="compare_products",
                    tool_args={"products": state.compared_product_ids or state.displayed_product_ids[:2]},
                    reason="Retrieve comparison matrix.",
                    response_mode="comparison"
                )
            return PlanStep(
                action=PlannerAction.COMPARE,
                reason="Comparison evidence ready.",
                response_mode="comparison"
            )

        # 6. Recommendation & Discovery
        # Check requirement coverage model
        active_cat = state.category or understanding.requirements.get("category")
        missing_essential = RequirementCoverageModel.get_genuinely_missing_fields(
            category=active_cat,
            requirements=state.requirements,
            goal_type=state.customer_goal or "find_printer"
        )

        # Check QuestionLedger to avoid repeated questions
        ledger: Optional[QuestionLedger] = getattr(state, "question_ledger", None)
        valid_missing = []
        if ledger:
            for f in missing_essential:
                if ledger.can_ask_agent_question(f):
                    valid_missing.append(f)
        else:
            valid_missing = missing_essential

        # If customer requested recommendation or has enough information
        if len(state.requirements) >= 2 or not valid_missing or state.results_loaded:
            return PlanStep(
                action=PlannerAction.RECOMMEND,
                target_tool="search_catalogue",
                tool_args={"category": active_cat, "requirements": state.requirements},
                reason="Sufficient information available for targeted recommendation.",
                response_mode="recommendation"
            )

        # If essential qualification is missing and not already asked
        if valid_missing:
            next_q = valid_missing[0]
            return PlanStep(
                action=PlannerAction.ASK,
                target_question_key=next_q,
                reason=f"Prompt for essential unknown field: {next_q}.",
                response_mode="qualification"
            )

        # Default fallback: Answer concisely
        return PlanStep(
            action=PlannerAction.ANSWER,
            reason="Default response.",
            response_mode="direct_answer"
        )

    def record_tool_call(self, tool_name: str, args: Dict[str, Any], result: Any) -> bool:
        """
        Records a tool call and detects infinite tool loops.
        Returns False if identical tool and arguments were executed previously.
        """
        args_repr = str(sorted(args.items()))
        sig = (tool_name, args_repr)
        if sig in self.executed_tools:
            logger.warning(f"Detected duplicate tool call {tool_name} with same args. Breaking tool loop.")
            return False
        self.executed_tools.append(sig)
        return True
