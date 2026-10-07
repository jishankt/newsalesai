"""
Requirement Coverage Model for Kepler Tech SalesAI.

Defines the 5-state requirement model:
KNOWN, UNKNOWN, NOT_REQUIRED, CONFLICTING, CORRECTED.

Ensures the agent only prompts for an unknown field if it is genuinely necessary
for the customer's current goal, preventing unnecessary interrogation.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from conversation.qualification_schema import get_mandatory_fields


class CoverageStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"
    CONFLICTING = "conflicting"
    CORRECTED = "corrected"


@dataclass
class RequirementSlot:
    name: str
    status: CoverageStatus
    value: Any = None
    is_essential_for_goal: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "value": self.value,
            "is_essential_for_goal": self.is_essential_for_goal,
        }


class RequirementCoverageModel:
    """Evaluates qualification requirements against goal relevance."""

    @classmethod
    def evaluate(
        cls,
        category: Optional[str],
        requirements: Dict[str, Any],
        goal_type: str = "find_printer",
        corrections: Optional[Dict[str, Any]] = None
    ) -> Dict[str, RequirementSlot]:
        """
        Builds requirement coverage mapping for the current state and goal.
        """
        slots: Dict[str, RequirementSlot] = {}
        corrections = corrections or {}

        if not category:
            return slots

        mandatory_fields = get_mandatory_fields(category)

        # Goal-aware essential field filtering:
        # If user goal is verification or comparison or direct specification check,
        # hardware discovery qualification is NOT_REQUIRED.
        is_direct_query_goal = goal_type in (
            "verify_product",
            "understand_specification",
            "check_compatibility",
            "check_price_policy",
            "compare_products",
            "close_conversation"
        )

        for field_name in mandatory_fields:
            val = requirements.get(field_name)
            is_corrected = field_name in corrections

            if is_direct_query_goal:
                slots[field_name] = RequirementSlot(
                    name=field_name,
                    status=CoverageStatus.NOT_REQUIRED if val is None else CoverageStatus.KNOWN,
                    value=val,
                    is_essential_for_goal=False
                )
                continue

            # Context-specific exemptions:
            # Citizen Photo: If application is wedding/photo booth, 4x6 roll is standard.
            # Don't ask A4/A3.
            if category == "citizen_photo":
                if field_name == "print_format" and ("wedding" in str(requirements.get("application", "")).lower() or "booth" in str(requirements.get("application", "")).lower()):
                    slots[field_name] = RequirementSlot(
                        name=field_name,
                        status=CoverageStatus.KNOWN,
                        value="4x6",
                        is_essential_for_goal=False
                    )
                    continue

            # Technical CAD: If print_width is known (e.g. 24 or 36 or 44), don't ask size again.
            if category == "technical_large_format":
                if field_name == "print_width" and requirements.get("print_width"):
                    slots[field_name] = RequirementSlot(
                        name=field_name,
                        status=CoverageStatus.KNOWN,
                        value=requirements["print_width"],
                        is_essential_for_goal=True
                    )
                    continue

            if val is not None and str(val).strip() != "":
                status = CoverageStatus.CORRECTED if is_corrected else CoverageStatus.KNOWN
                slots[field_name] = RequirementSlot(
                    name=field_name,
                    status=status,
                    value=val,
                    is_essential_for_goal=True
                )
            else:
                slots[field_name] = RequirementSlot(
                    name=field_name,
                    status=CoverageStatus.UNKNOWN,
                    value=None,
                    is_essential_for_goal=True
                )

        return slots

    @classmethod
    def get_genuinely_missing_fields(
        cls,
        category: Optional[str],
        requirements: Dict[str, Any],
        goal_type: str = "find_printer",
        corrections: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Returns only fields that are genuinely UNKNOWN and essential for the active goal.
        """
        eval_slots = cls.evaluate(category, requirements, goal_type, corrections)
        return [
            slot.name for slot in eval_slots.values()
            if slot.status == CoverageStatus.UNKNOWN and slot.is_essential_for_goal
        ]
