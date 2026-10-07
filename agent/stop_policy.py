"""
First-Class Stop Policy and Action Budget for Kepler Tech SalesAI.

Defines conversation outcomes and hard stop conditions to prevent conversational loops,
repetitive tool calls, and post-completion selling.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import logging

from domain.conversation_state import ConversationState

logger = logging.getLogger("stop_policy")


class ConversationOutcome(str, Enum):
    GOAL_PROGRESS = "goal_progress"
    GOAL_COMPLETE = "goal_complete"
    NEEDS_INFORMATION = "needs_information"
    NEEDS_CLARIFICATION = "needs_clarification"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    HANDOFF_REQUIRED = "handoff_required"
    CONVERSATION_CLOSED = "conversation_closed"


@dataclass
class ActionBudget:
    """Action safety limits per customer turn."""
    max_planning_steps: int = 1
    max_retrieval_steps: int = 2
    max_repeated_tool_calls: int = 1
    max_questions_per_response: int = 1

    current_planning_steps: int = 0
    current_retrieval_steps: int = 0
    executed_tools: List[Tuple[str, str]] = field(default_factory=list)
    questions_asked_in_response: int = 0

    def can_retrieve(self) -> bool:
        return self.current_retrieval_steps < self.max_retrieval_steps

    def record_tool_call(self, tool_name: str, args_repr: str) -> bool:
        """Records a tool call. Returns False if repeated tool call budget exceeded."""
        match_count = sum(1 for t, a in self.executed_tools if t == tool_name and a == args_repr)
        if match_count >= self.max_repeated_tool_calls:
            logger.warning("Repeated tool call budget reached for %s(%s)", tool_name, args_repr)
            return False
        self.executed_tools.append((tool_name, args_repr))
        self.current_retrieval_steps += 1
        return True


class StopPolicy:
    """Evaluates whether the agent must stop and wait for the customer."""

    @classmethod
    def evaluate_stop(
        cls,
        customer_behavior: str,
        customer_goal: str,
        unanswered_questions_remaining: int,
        has_new_evidence: bool,
        budget: ActionBudget,
        is_closing: bool = False,
        is_handoff: bool = False,
    ) -> Tuple[bool, ConversationOutcome, str]:
        """
        Determines whether the turn must stop immediately.
        Returns (should_stop, outcome, stop_reason).
        """
        # 1. Explicit Closing
        if is_closing or customer_behavior == "CLOSING" or customer_goal in ("closing", "close_conversation"):
            return True, ConversationOutcome.CONVERSATION_CLOSED, "Customer explicitly closed the conversation."

        # 2. Handoff Triggered
        if is_handoff or customer_goal == "handoff":
            return True, ConversationOutcome.HANDOFF_REQUIRED, "Human specialist handoff triggered."

        # 3. Frustrated Customer: answer and stop (no trailing questions/pitches)
        if customer_behavior == "FRUSTRATED":
            return True, ConversationOutcome.WAITING_FOR_CUSTOMER, "Customer is frustrated; answered directly and stopping without pitch."

        # 4. Budget Exceeded
        if budget.current_retrieval_steps >= budget.max_retrieval_steps:
            return True, ConversationOutcome.WAITING_FOR_CUSTOMER, "Action budget reached; presenting current findings and waiting."

        # 5. Direct Question Answered & No New Unanswered Inquiries
        if unanswered_questions_remaining == 0 and customer_goal in ("technical_inquiry", "pricing_inquiry", "spec_inquiry"):
            return True, ConversationOutcome.GOAL_COMPLETE, "All customer explicit questions answered."

        # 6. Default: Wait for customer input
        return False, ConversationOutcome.GOAL_PROGRESS, "Conversation progressing normally."
