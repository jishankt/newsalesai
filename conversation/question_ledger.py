"""
Authoritative Question Ledger for Kepler Tech SalesAI.

Tracks all customer inquiries and agent qualification questions across turns.
Enforces semantic equivalence, prevents repetitive question loops, and guarantees
that every customer question is tracked until answered.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
import re
import uuid


class QuestionStatus(str, Enum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    DEFERRED = "deferred"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


# Canonical Semantic Mapping Patterns
SEMANTIC_EQUIVALENCE_RULES = [
    # Speed
    (r"\b(?:speed|ppm|fast|seconds?\s*per\s*print|how\s*fast|printing\s*speed)\b", "print_speed"),
    # WiFi / Networking
    (r"\b(?:wifi|wi-fi|wireless|airprint|ethernet|network|lan|connect(?:ivity)?)\b", "wifi_support"),
    # Media Roll Yield / Capacity
    (r"\b(?:prints?\s*per\s*roll|yield|rolls?\s*per\s*box|capacity\s*per\s*roll|how\s*many\s*prints|roll\s*yield)\b", "media_yield"),
    # Weight & Dimensions
    (r"\b(?:weight|how\s*heavy|mass|portable|dimensions?|footprint|size\s*of\s*printer)\b", "physical_specs"),
    # Print Width / Paper Size / Format
    (r"\b(?:print\s*width|paper\s*size|what\s*size|what\s*width|which\s*format|24[\",\s]*36|a4\s*or\s*a3|roll\s*size|format\s*size)\b", "print_width"),
    # Media & Paper Compatibility
    (r"\b(?:matte|glossy?|canvas|luster|lustre|fine\s*art|cotton\s*rag|baryta|what\s*media|paper\s*type|media\s*compatibility)\b", "media_compatibility"),
    # Inks & Consumables
    (r"\b(?:which\s*inks?|ink\s*type|cartridges?|tank|ribbon|inks?\s*included|consumables?)\b", "ink_compatibility"),
    # Price / Investment
    (r"\b(?:price|cost|how\s*much|rate|rates|quote|quotation|investment|pricing|cpp|cost\s*per\s*print)\b", "price"),
    # Warranty & Service
    (r"\b(?:warranty|guarantee|coverplus|amc|maintenance\s*contract|repair|service)\b", "warranty"),
    # Application / Use Case
    (r"\b(?:photo\s*booth|wedding|cad|blueprints?|studio|event|office\s*documents?|sublimation|mugs|t-shirts?)\b", "application"),
]


def canonicalize_semantic_key(text: str, default_key: Optional[str] = None) -> str:
    """Maps freeform question text to a canonical semantic key."""
    t_clean = (text or "").lower()
    for pattern, key in SEMANTIC_EQUIVALENCE_RULES:
        if re.search(pattern, t_clean):
            return key
    if default_key:
        return default_key
    # Clean text to alphanumeric slug
    slug = re.sub(r"[^\w\s]", "", t_clean).strip().replace(" ", "_")
    return slug[:32] if slug else "general_inquiry"


@dataclass
class QuestionItem:
    id: str
    semantic_key: str
    original_text: str
    normalized_text: str
    target_product: Optional[str] = None
    target_attribute: Optional[str] = None
    status: QuestionStatus = QuestionStatus.UNANSWERED
    origin: str = "customer"  # "customer" | "agent"
    asked_count: int = 1
    asked_turn: int = 1
    answered_turn: Optional[int] = None
    answer_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "semantic_key": self.semantic_key,
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
            "target_product": self.target_product,
            "target_attribute": self.target_attribute,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "origin": self.origin,
            "asked_count": self.asked_count,
            "asked_turn": self.asked_turn,
            "answered_turn": self.answered_turn,
            "answer_summary": self.answer_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestionItem":
        status_val = data.get("status", "unanswered")
        try:
            status = QuestionStatus(status_val)
        except ValueError:
            status = QuestionStatus.UNANSWERED
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            semantic_key=data.get("semantic_key", "general_inquiry"),
            original_text=data.get("original_text", ""),
            normalized_text=data.get("normalized_text", ""),
            target_product=data.get("target_product"),
            target_attribute=data.get("target_attribute"),
            status=status,
            origin=data.get("origin", "customer"),
            asked_count=int(data.get("asked_count", 1)),
            asked_turn=int(data.get("asked_turn", 1)),
            answered_turn=data.get("answered_turn"),
            answer_summary=data.get("answer_summary"),
        )


class QuestionLedger:
    """Manages session-level question lifecycle and enforces loop prevention."""

    def __init__(self, items: Optional[List[QuestionItem]] = None):
        self.items: List[QuestionItem] = items or []

    def register_customer_question(
        self,
        text: str,
        turn_index: int,
        target_product: Optional[str] = None,
        target_attribute: Optional[str] = None,
        explicit_semantic_key: Optional[str] = None
    ) -> QuestionItem:
        """Registers an explicit question from customer."""
        sem_key = explicit_semantic_key or canonicalize_semantic_key(text, target_attribute)
        target_attr = target_attribute or sem_key

        # Check existing matching question
        for item in self.items:
            if item.origin == "customer" and item.semantic_key == sem_key:
                if target_product and item.target_product and target_product != item.target_product:
                    continue  # Different target product question
                item.asked_count += 1
                item.original_text = text
                if item.status == QuestionStatus.ANSWERED:
                    # Re-opened explicitly by customer
                    item.status = QuestionStatus.UNANSWERED
                    item.answered_turn = None
                return item

        new_item = QuestionItem(
            id=str(uuid.uuid4())[:8],
            semantic_key=sem_key,
            original_text=text,
            normalized_text=text.lower().strip(),
            target_product=target_product,
            target_attribute=target_attr,
            status=QuestionStatus.UNANSWERED,
            origin="customer",
            asked_count=1,
            asked_turn=turn_index,
        )
        self.items.append(new_item)
        return new_item

    def register_agent_question(
        self,
        semantic_key: str,
        question_text: str,
        turn_index: int
    ) -> QuestionItem:
        """Registers a qualification question posed by the agent to the customer."""
        sem_key = canonicalize_semantic_key(question_text, semantic_key)
        for item in self.items:
            if item.origin == "agent" and item.semantic_key == sem_key:
                item.asked_count += 1
                return item

        new_item = QuestionItem(
            id=str(uuid.uuid4())[:8],
            semantic_key=sem_key,
            original_text=question_text,
            normalized_text=question_text.lower().strip(),
            status=QuestionStatus.UNANSWERED,
            origin="agent",
            asked_count=1,
            asked_turn=turn_index,
        )
        self.items.append(new_item)
        return new_item

    def mark_answered(
        self,
        semantic_key: str,
        turn_index: int,
        answer_summary: str = "",
        target_product: Optional[str] = None
    ) -> None:
        """Marks questions matching the semantic key as answered."""
        for item in self.items:
            if item.semantic_key == semantic_key:
                if target_product and item.target_product and target_product != item.target_product:
                    continue
                item.status = QuestionStatus.ANSWERED
                item.answered_turn = turn_index
                item.answer_summary = answer_summary

    def is_already_answered(self, semantic_key: str, target_product: Optional[str] = None) -> bool:
        """Checks if a semantic question has already been answered."""
        for item in self.items:
            if item.semantic_key == semantic_key and item.status == QuestionStatus.ANSWERED:
                if target_product and item.target_product and target_product != item.target_product:
                    continue
                return True
        return False

    def can_ask_agent_question(self, semantic_key: str) -> bool:
        """
        Guards against question loops.
        Returns False if:
        1. semantic_key is already answered.
        2. Agent already asked this semantic_key once and customer did not answer it.
        """
        for item in self.items:
            if item.origin == "agent" and item.semantic_key == semantic_key:
                if item.status == QuestionStatus.ANSWERED:
                    return False
                if item.asked_count >= 1:
                    return False
        return True

    def get_unanswered_customer_questions(self) -> List[QuestionItem]:
        """Returns customer questions awaiting answers."""
        return [
            item for item in self.items
            if item.origin == "customer" and item.status == QuestionStatus.UNANSWERED
        ]

    def get_latest_unanswered_customer_question(self) -> Optional[QuestionItem]:
        """Returns the most recent customer question awaiting an answer."""
        unans = self.get_unanswered_customer_questions()
        return unans[-1] if unans else None

    def supersede_pending_agent_questions(self) -> None:
        """Marks pending agent qualification questions as superseded (e.g. when user asks a direct spec question)."""
        for item in self.items:
            if item.origin == "agent" and item.status == QuestionStatus.UNANSWERED:
                item.status = QuestionStatus.SUPERSEDED

    def to_list(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.items]

    @classmethod
    def from_list(cls, data: List[Dict[str, Any]]) -> "QuestionLedger":
        items = [QuestionItem.from_dict(d) for d in data if isinstance(d, dict)]
        return cls(items)
