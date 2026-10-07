"""
Authoritative Customer Goal Manager for Kepler Tech SalesAI.

Tracks customer goals across conversational stages and enforces clean topic-switching
isolation to prevent requirement leakage across unrelated categories.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import uuid


class GoalType(str, Enum):
    FIND_PRINTER = "find_printer"
    FIND_MEDIA = "find_media"
    FIND_CONSUMABLE = "find_consumable"
    VERIFY_PRODUCT = "verify_product"
    COMPARE_PRODUCTS = "compare_products"
    UNDERSTAND_SPECIFICATION = "understand_specification"
    CHECK_COMPATIBILITY = "check_compatibility"
    CHECK_PRICE_POLICY = "check_price_policy"
    BUY_PRODUCT = "buy_product"
    REQUEST_QUOTE = "request_quote"
    SPEAK_TO_HUMAN = "speak_to_human"
    CLOSE_CONVERSATION = "close_conversation"
    EXPLORE = "explore"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    SUPERSEDED = "superseded"


# Category-specific requirement keys to purge when topic switching
CATEGORY_SPECIFIC_KEYS = {
    "technical_large_format": {"print_width", "scanner_required", "cad_linework", "line_drawings"},
    "office_printer": {"document_feeder", "duplex", "fax", "monthly_volume", "ppm"},
    "photography_large_format": {"color_count", "roll_adapter", "fine_art", "baryta", "gallery_wrap"},
    "citizen_photo": {"print_size", "photo_form_factor", "rewind_mode", "booth_integration", "roll_feed"},
    "dye_sublimation": {"sublimation_target", "apparel", "heat_press", "fluorescent"},
    "scanners": {"scan_sensor", "dpi", "feeder_capacity", "flatbed"},
}


@dataclass
class CustomerGoal:
    id: str
    goal_type: GoalType
    description: str = ""
    target_category: Optional[str] = None
    target_products: List[str] = field(default_factory=list)
    status: GoalStatus = GoalStatus.ACTIVE
    started_turn: int = 1
    completed_turn: Optional[int] = None
    requirements: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal_type": self.goal_type.value if hasattr(self.goal_type, "value") else str(self.goal_type),
            "description": self.description,
            "target_category": self.target_category,
            "target_products": list(self.target_products),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "started_turn": self.started_turn,
            "completed_turn": self.completed_turn,
            "requirements": dict(self.requirements),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomerGoal":
        gt_val = data.get("goal_type", "explore")
        try:
            gt = GoalType(gt_val)
        except ValueError:
            gt = GoalType.EXPLORE
        st_val = data.get("status", "active")
        try:
            st = GoalStatus(st_val)
        except ValueError:
            st = GoalStatus.ACTIVE
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            goal_type=gt,
            description=data.get("description", ""),
            target_category=data.get("target_category"),
            target_products=list(data.get("target_products") or []),
            status=st,
            started_turn=int(data.get("started_turn", 1)),
            completed_turn=data.get("completed_turn"),
            requirements=dict(data.get("requirements") or {}),
        )


class GoalManager:
    """Manages active customer goal and topic-switch state cleansing."""

    def __init__(
        self,
        current_goal: Optional[CustomerGoal] = None,
        goal_history: Optional[List[CustomerGoal]] = None
    ):
        self.current_goal: CustomerGoal = current_goal or CustomerGoal(
            id=str(uuid.uuid4())[:8],
            goal_type=GoalType.EXPLORE,
            description="Initial exploration",
            status=GoalStatus.ACTIVE,
            started_turn=1,
        )
        self.goal_history: List[CustomerGoal] = goal_history or []

    def set_or_update_goal(
        self,
        goal_type: GoalType,
        category: Optional[str] = None,
        products: Optional[List[str]] = None,
        description: str = "",
        turn_index: int = 1
    ) -> CustomerGoal:
        """Updates active goal or starts new goal if type changed significantly."""
        if self.current_goal.status == GoalStatus.ACTIVE and self.current_goal.goal_type == goal_type:
            if category:
                self.current_goal.target_category = category
            if products:
                self.current_goal.target_products = list(set(self.current_goal.target_products + products))
            if description:
                self.current_goal.description = description
            return self.current_goal

        # Close previous goal
        self.archive_current_goal(status=GoalStatus.SUPERSEDED, turn_index=turn_index)

        # Start new goal
        new_goal = CustomerGoal(
            id=str(uuid.uuid4())[:8],
            goal_type=goal_type,
            description=description or f"Goal: {goal_type.value}",
            target_category=category,
            target_products=products or [],
            status=GoalStatus.ACTIVE,
            started_turn=turn_index,
        )
        self.current_goal = new_goal
        return new_goal

    def handle_topic_switch(
        self,
        new_category: Optional[str] = None,
        new_goal_type: Optional[GoalType] = None,
        existing_requirements: Optional[Dict[str, Any]] = None,
        turn_index: int = 1,
        state: Optional[Any] = None,
        new_goal: Optional[Any] = None,
        new_requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes strict topic-switch protocol:
        1. Archives old goal.
        2. Clears incompatible requirements from previous category.
        3. Starts new goal cleanly.
        Returns sanitized requirements dictionary.
        """
        if new_goal and not new_goal_type:
            try:
                new_goal_type = GoalType(new_goal)
            except ValueError:
                new_goal_type = GoalType.FIND_PRINTER
        if not new_goal_type:
            new_goal_type = GoalType.FIND_PRINTER

        if new_requirements and not new_category:
            new_category = new_requirements.get("category")

        if state:
            if existing_requirements is None:
                existing_requirements = getattr(state, "requirements", {})
            if turn_index == 1 and hasattr(state, "turn_count"):
                turn_index = state.turn_count

        old_cat = self.current_goal.target_category or (getattr(state, "category", None) if state else None)
        self.archive_current_goal(status=GoalStatus.SUPERSEDED, turn_index=turn_index)

        sanitized_reqs = dict(existing_requirements or {})
        if old_cat and old_cat != new_category:
            # Purge old category specific slots
            purge_keys = CATEGORY_SPECIFIC_KEYS.get(old_cat, set())
            for k in purge_keys:
                sanitized_reqs.pop(k, None)
            sanitized_reqs.pop("category", None)
            sanitized_reqs.pop("subcategory", None)

        if new_requirements:
            sanitized_reqs.update(new_requirements)

        if state:
            state.category = new_category
            state.requirements = sanitized_reqs

        new_goal_obj = CustomerGoal(
            id=str(uuid.uuid4())[:8],
            goal_type=new_goal_type,
            description=f"Switched topic to {new_category or new_goal_type.value}",
            target_category=new_category,
            status=GoalStatus.ACTIVE,
            started_turn=turn_index,
            requirements=sanitized_reqs,
        )
        self.current_goal = new_goal_obj
        return sanitized_reqs

    def archive_current_goal(self, status: GoalStatus = GoalStatus.COMPLETED, turn_index: int = 1) -> None:
        """Archives current goal into history."""
        if self.current_goal.status == GoalStatus.ACTIVE:
            self.current_goal.status = status
            self.current_goal.completed_turn = turn_index
            self.goal_history.append(self.current_goal)

    def mark_completed(self, turn_index: int = 1) -> None:
        """Marks current goal as completed."""
        self.archive_current_goal(status=GoalStatus.COMPLETED, turn_index=turn_index)

    def is_closing(self) -> bool:
        """Checks if current goal is closing the conversation."""
        return self.current_goal.goal_type == GoalType.CLOSE_CONVERSATION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_goal": self.current_goal.to_dict(),
            "goal_history": [g.to_dict() for g in self.goal_history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalManager":
        curr = CustomerGoal.from_dict(data.get("current_goal") or {})
        hist = [CustomerGoal.from_dict(g) for g in (data.get("goal_history") or []) if isinstance(g, dict)]
        return cls(current_goal=curr, goal_history=hist)
