"""
Domain Types for Kepler Tech Conversational AI.
Defines canonical enums, dataclasses, and type contracts used across the system.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Intent Taxonomy
# ---------------------------------------------------------------------------
class Intent(str, Enum):
    """All recognized customer intents. The LLM must return one of these."""
    GREETING = "greeting"
    CUSTOMER_INTRODUCTION = "customer_introduction"
    SMALL_TALK = "small_talk"
    POSITIVE_FEEDBACK = "positive_feedback"
    NEGATIVE_FEEDBACK = "negative_feedback"
    FRUSTRATION = "frustration"
    CORRECTION = "correction"
    CONFIRMATION = "confirmation"
    REJECTION = "rejection"
    CONVERSATION_ENDING = "conversation_ending"
    CONVERSATION_HELP = "conversation_help"
    LANGUAGE_CHANGE = "language_change"
    PRODUCT_DISCOVERY = "product_discovery"
    PRODUCT_QUESTION = "product_question"
    PRODUCT_COMPARISON = "product_comparison"
    CONSUMABLES_QUERY = "consumables_query"
    BUSINESS_INFORMATION = "business_information"
    TROUBLESHOOTING = "troubleshooting"
    UNCLEAR = "unclear"
    OUT_OF_SCOPE = "out_of_scope"


# Grouped intent sets for decision engine routing
SOCIAL_INTENTS = frozenset({
    Intent.GREETING,
    Intent.CUSTOMER_INTRODUCTION,
    Intent.SMALL_TALK,
    Intent.POSITIVE_FEEDBACK,
    Intent.NEGATIVE_FEEDBACK,
    Intent.FRUSTRATION,
    Intent.CONVERSATION_ENDING,
})

PRODUCT_INTENTS = frozenset({
    Intent.PRODUCT_DISCOVERY,
    Intent.PRODUCT_QUESTION,
    Intent.PRODUCT_COMPARISON,
    Intent.CONSUMABLES_QUERY,
})


# ---------------------------------------------------------------------------
# Dialogue Act (what the user is doing in the conversation)
# ---------------------------------------------------------------------------
class DialogueAct(str, Enum):
    # Core conversational acts
    GREETING = "greeting"
    THANKING = "thanking"
    COMPLAINING = "complaining"
    CONFIRMING = "confirming"
    REJECTING = "rejecting"
    UNCLEAR = "unclear"
    HUMAN_HANDOVER = "human_handover"

    # General / legacy acts
    INFORMING = "informing"
    REQUESTING = "requesting"
    QUESTIONING = "questioning"
    CORRECTING = "correcting"
    CLARIFYING = "clarifying"

    # Requirements & Discovery
    DISCOVERY_REQUEST = "discovery_request"
    REQUIREMENT_ANSWER = "requirement_answer"
    REQUIREMENT_UPDATE = "requirement_update"
    REQUIREMENT_CORRECTION = "requirement_correction"

    # Product Inquiries & Capabilities
    PRODUCT_LOOKUP = "product_lookup"
    PRODUCT_CAPABILITY_QUESTION = "product_capability_question"
    PRODUCT_SPECIFICATION_QUESTION = "product_specification_question"
    PRODUCT_SUITABILITY_QUESTION = "product_suitability_question"

    # Recommendations & Alternatives
    RECOMMENDATION_REQUEST = "recommendation_request"
    RECOMMENDATION_EXPLANATION = "recommendation_explanation"
    ALTERNATIVE_REQUEST = "alternative_request"

    # Comparisons
    COMPARISON_REQUEST = "comparison_request"
    COMPARISON_FOLLOWUP = "comparison_followup"
    CONFIGURATION_DIFFERENCE = "configuration_difference"

    # Consumables
    CONSUMABLE_REQUEST = "consumable_request"

    # References & Memory
    REFERENCE_FOLLOWUP = "reference_followup"
    MEMORY_RECALL = "memory_recall"
    MEDIA_REQUEST = "media_request"

    # Navigation & Flow
    TOPIC_SWITCH = "topic_switch"


# ---------------------------------------------------------------------------
# Conversation Stage
# ---------------------------------------------------------------------------
class ConversationStage(str, Enum):
    OPEN = "open"
    QUALIFYING = "qualifying"
    RECOMMENDING = "recommending"
    COMPARING = "comparing"
    CONSUMABLES = "consumables"
    SUPPORTING = "supporting"
    CLOSING = "closing"


# ---------------------------------------------------------------------------
# Route Names (used by decision engine)
# ---------------------------------------------------------------------------
class RouteName(str, Enum):
    SOCIAL = "social"
    CONVERSATION_HELP = "conversation_help"
    GUARDRAIL = "guardrail"
    QUALIFICATION = "qualification"
    PRODUCT = "product"
    COMPARISON = "comparison"
    CONSUMABLES = "consumables"
    SUPPORT = "support"
    BUSINESS_INFO = "business_info"
    CLARIFICATION = "clarification"


# ---------------------------------------------------------------------------
# Intercept Result (from deterministic interceptor)
# ---------------------------------------------------------------------------
@dataclass
class InterceptResult:
    """Result from the deterministic interceptor that runs before any LLM call."""
    matched: bool
    intent: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    response: Optional[str] = None
    should_continue: bool = True  # False = stop here, True = pass to LLM
    suggested_chips: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM Understanding Result
# ---------------------------------------------------------------------------
@dataclass
class LLMUnderstanding:
    """Structured output from the local LLM understanding module."""
    intent: Intent = Intent.UNCLEAR
    dialogue_act: DialogueAct = DialogueAct.INFORMING
    product_related: bool = False
    confidence: float = 0.0
    sentiment: str = "neutral"
    language: str = "en"
    entities: Dict[str, Any] = field(default_factory=dict)
    requirement_updates: Dict[str, Any] = field(default_factory=dict)
    requested_action: str = "ask_clarification"
    tool_request: Optional[Dict[str, Any]] = None

    # Enhanced structured semantic fields
    customer_goal: str = ""
    requirements: Dict[str, Any] = field(default_factory=dict)
    corrections: Dict[str, Any] = field(default_factory=dict)
    mentioned_products: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    requested_attributes: List[str] = field(default_factory=list)
    comparison_targets: List[str] = field(default_factory=list)
    topic_switch: bool = False
    confirmation: bool = False
    rejection: bool = False
    needs_clarification: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMUnderstanding":
        """Parse from LLM JSON output with fallback for invalid values."""
        try:
            intent = Intent(data.get("intent", "unclear"))
        except ValueError:
            intent = Intent.UNCLEAR

        raw_da = str(data.get("dialogue_act", "informing")).lower().strip()
        try:
            dialogue_act = DialogueAct(raw_da)
        except ValueError:
            dialogue_act = DialogueAct.INFORMING

        entities = dict(data.get("entities") or {})
        if entities.get("daily_volume") is not None:
            try:
                if int(entities["daily_volume"]) <= 0:
                    del entities["daily_volume"]
            except (ValueError, TypeError):
                del entities["daily_volume"]

        return cls(
            intent=intent,
            dialogue_act=dialogue_act,
            product_related=bool(data.get("product_related", False)),
            confidence=float(data.get("confidence", 0.0)),
            sentiment=str(data.get("sentiment", "neutral")),
            language=str(data.get("language", "en")),
            entities=entities,
            requirement_updates=data.get("requirement_updates") or {},
            requested_action=str(data.get("requested_action", "ask_clarification")),
            tool_request=data.get("tool_request"),
            customer_goal=str(data.get("customer_goal", "")),
            requirements=dict(data.get("requirements") or {}),
            corrections=dict(data.get("corrections") or {}),
            mentioned_products=list(data.get("mentioned_products") or []),
            references=list(data.get("references") or []),
            questions=list(data.get("questions") or []),
            requested_attributes=list(data.get("requested_attributes") or []),
            comparison_targets=list(data.get("comparison_targets") or []),
            topic_switch=bool(data.get("topic_switch", False)),
            confirmation=bool(data.get("confirmation", False)),
            rejection=bool(data.get("rejection", False)),
            needs_clarification=bool(data.get("needs_clarification", False)),
        )


# ---------------------------------------------------------------------------
# Route Decision (from decision engine)
# ---------------------------------------------------------------------------
@dataclass
class RouteDecision:
    """Decision made by the decision engine about which route to execute."""
    route: RouteName
    tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ---------------------------------------------------------------------------
# Route Result (returned by route handlers)
# ---------------------------------------------------------------------------
@dataclass
class RouteResult:
    """Result returned by a route handler after processing."""
    reply: str = ""
    product_cards: List[Dict[str, Any]] = field(default_factory=list)
    consumable_cards: List[Dict[str, Any]] = field(default_factory=list)
    suggested_chips: List[str] = field(default_factory=list)
    source: str = "ai_agent"
    needs_composition: bool = False  # True = send to LLM composer for natural language
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    instruction: str = ""  # Instruction for the response composer
    recommendation_audit: Optional[Dict[str, Any]] = None  # Internal audit object for recommendation traceability
    product_id: Optional[str] = None  # Canonical product ID if specific to a single product

    def __post_init__(self):
        if self.reply and isinstance(self.reply, str):
            import re
            self.reply = re.sub(r"\s*\[(?:VERIFIED|CONFLICT|INFERRED|CALCULATED)[^\]]*\]", "", self.reply).strip()

