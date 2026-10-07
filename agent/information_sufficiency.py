"""
Information Sufficiency Engine for Kepler Tech SalesAI.

Determines whether information is genuinely required before the agent is permitted
to ask the customer any question. Enforces:
- REQUIRED_MISSING
- OPTIONAL_MISSING
- SUFFICIENT
- NOT_APPLICABLE

Guarantees that when a customer asks a direct factual/price inquiry or has fixed
constraints (e.g., portable 4x6 photo printer), irrelevant qualification questionnaires
are strictly prohibited.
"""

from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
import logging

from domain.conversation_state import ConversationState
from conversation.question_ledger import QuestionStatus

logger = logging.getLogger("information_sufficiency")


class SufficiencyStatus(str, Enum):
    REQUIRED_MISSING = "required_missing"
    OPTIONAL_MISSING = "optional_missing"
    SUFFICIENT = "sufficient"
    NOT_APPLICABLE = "not_applicable"


class InformationSufficiency:
    """Evaluates field necessity and guards against irrelevant sales qualification."""

    @classmethod
    def evaluate_field(
        cls,
        field_name: str,
        state: ConversationState,
        current_goal: str = "explore",
        target_product: Optional[str] = None
    ) -> SufficiencyStatus:
        """
        Determines the sufficiency status of a given field.
        Returns NOT_APPLICABLE if the field is irrelevant to the customer's current focus.
        """
        # 1. Non-qualification goals never require qualification fields
        non_qual_goals = {
            "technical_inquiry", "pricing_inquiry", "spec_inquiry",
            "understand_specification", "direct_answer", "compare",
            "compare_products", "purchase_intent", "buy_product",
            "closing", "close_conversation", "frustration", "confusion"
        }
        if current_goal in non_qual_goals:
            return SufficiencyStatus.NOT_APPLICABLE

        # 2. If a specific product is already active/selected
        if target_product or state.get_canonical_focus_id():
            # For a known hardware unit, generic format or tech questions are NOT_APPLICABLE
            if field_name in ("category", "print_size", "ink_type", "print_width"):
                return SufficiencyStatus.NOT_APPLICABLE

        reqs = state.requirements or {}
        cat = state.category or reqs.get("category")

        # 3. Category-Specific NOT_APPLICABLE Rules
        if cat == "citizen_photo":
            # Citizen photo printers are 4x6 / 6x8 / 8x12 dye-sub rolls.
            # A4/A3 format or CAD blueprint inquiries are NOT_APPLICABLE.
            if field_name in ("format", "a4_or_a3", "cad_width", "adf", "scanner", "ink_technology"):
                return SufficiencyStatus.NOT_APPLICABLE

        if cat == "technical_large_format":
            # Technical CAD plotters (T-Series) are roll/sheet CAD. Photo booth size is NOT_APPLICABLE.
            if field_name in ("photo_finish", "dye_sublimation", "photo_booth_portable"):
                return SufficiencyStatus.NOT_APPLICABLE

        if cat == "office_printer":
            if field_name in ("roll_feed", "canvas_media", "photo_speed_seconds"):
                return SufficiencyStatus.NOT_APPLICABLE

        # 4. Check if already satisfied
        if field_name in reqs and reqs[field_name]:
            return SufficiencyStatus.SUFFICIENT

        # 5. Check if already in state.missing_fields as mandatory
        mandatory_fields = cls._get_mandatory_fields_for_category(cat)
        if field_name in mandatory_fields:
            return SufficiencyStatus.REQUIRED_MISSING

        return SufficiencyStatus.OPTIONAL_MISSING

    @classmethod
    def get_next_warranted_question(
        cls,
        state: ConversationState,
        current_goal: str = "explore",
    ) -> Optional[Tuple[str, str]]:
        """
        Returns (field_key, question_text) ONLY if information is REQUIRED_MISSING.
        Returns None if information is already sufficient, not applicable, or already asked.
        """
        # If goal is factual, pricing, comparison, buying or closing -> NEVER ask qualification
        non_qual_goals = {
            "technical_inquiry", "pricing_inquiry", "spec_inquiry",
            "understand_specification", "direct_answer", "compare",
            "compare_products", "purchase_intent", "buy_product",
            "closing", "close_conversation", "frustration", "confusion"
        }
        if current_goal in non_qual_goals:
            return None

        # If customer explicitly asked questions that are unanswered in ledger, answer those first!
        if state.question_ledger and state.question_ledger.get_unanswered_customer_questions():
            return None

        cat = state.category or state.requirements.get("category")
        if not cat:
            # Need high-level category if exploring without any context
            if state.question_ledger and not state.question_ledger.can_ask_agent_question("category"):
                return None
            return ("category", "What type of printing solution are you looking for (e.g. Photo & Event, Technical CAD, or Office)?")

        mandatory = cls._get_mandatory_fields_for_category(cat)
        for fld in mandatory:
            status = cls.evaluate_field(fld, state, current_goal)
            if status == SufficiencyStatus.REQUIRED_MISSING:
                # Check question ledger to ensure we never ask the same semantic question twice
                if state.question_ledger and not state.question_ledger.can_ask_agent_question(fld):
                    continue
                q_text = cls._get_question_for_field(fld, cat)
                if q_text:
                    return (fld, q_text)

        return None

    @classmethod
    def _get_mandatory_fields_for_category(cls, category: Optional[str]) -> List[str]:
        """Returns minimal essential fields for product resolution."""
        if category == "technical_large_format":
            return ["print_width"]
        if category == "office_printer":
            return ["print_volume"]
        if category == "citizen_photo":
            return ["application"]
        return []

    @classmethod
    def _get_question_for_field(cls, field_name: str, category: Optional[str]) -> Optional[str]:
        """Provides natural, non-pushy phrasing for a missing mandatory field."""
        if field_name == "print_width":
            return "What maximum print width do you require for your technical plans (e.g., 24-inch A1 or 36-inch A0)?"
        if field_name == "print_volume":
            return "What is your estimated monthly print volume (pages per month)?"
        if field_name == "application":
            return "Is this for portable event / photo booth printing or on-site studio portraits?"
        return None
