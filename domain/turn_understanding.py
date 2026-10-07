"""
Canonical Turn Understanding Domain Model for Kepler Tech SalesAI.

Defines the single authoritative semantic representation of a customer turn,
preventing independent reinterpretations across disparate modules.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import uuid


@dataclass
class TurnQuestion:
    """Explicit question identified within a turn."""
    id: str
    text: str
    semantic_key: str
    target_product: Optional[str] = None
    target_attribute: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "semantic_key": self.semantic_key,
            "target_product": self.target_product,
            "target_attribute": self.target_attribute,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnQuestion":
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            text=data.get("text", ""),
            semantic_key=data.get("semantic_key", "general_inquiry"),
            target_product=data.get("target_product"),
            target_attribute=data.get("target_attribute"),
        )


@dataclass
class TurnUnderstanding:
    """Canonical representation of customer input for the current turn."""
    primary_intent: str = "unclear"
    dialogue_act: str = "informing"
    customer_goal: str = "explore"
    customer_stage: str = "discovery"      # opening, discovery, qualification, recommendation, evaluation, comparison, objection, purchase_intent, handoff, closing
    customer_behavior: str = "exploring"   # exploring, researching, comparing, evaluating, technical, price_sensitive, high_intent, ready_to_buy, uncertain, frustrated, urgent, returning_customer, closing, casual
    sentiment: str = "neutral"             # positive, neutral, negative
    urgency: str = "low"                   # low, medium, high
    purchase_readiness: str = "low"        # low, medium, high
    questions: List[TurnQuestion] = field(default_factory=list)
    requested_attributes: List[str] = field(default_factory=list)
    mentioned_products: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list) # "it", "the first one", "the other one"
    requirements: Dict[str, Any] = field(default_factory=dict)
    corrections: Dict[str, Any] = field(default_factory=dict)
    topic_switch: bool = False
    explicit_answer_to_previous_question: Optional[str] = None
    needs_clarification: bool = False
    confidence: float = 1.0
    raw_message: str = ""
    normalized_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_intent": self.primary_intent,
            "dialogue_act": self.dialogue_act,
            "customer_goal": self.customer_goal,
            "customer_stage": self.customer_stage,
            "customer_behavior": self.customer_behavior,
            "sentiment": self.sentiment,
            "urgency": self.urgency,
            "purchase_readiness": self.purchase_readiness,
            "questions": [q.to_dict() for q in self.questions],
            "requested_attributes": list(self.requested_attributes),
            "mentioned_products": list(self.mentioned_products),
            "references": list(self.references),
            "requirements": dict(self.requirements),
            "corrections": dict(self.corrections),
            "topic_switch": self.topic_switch,
            "explicit_answer_to_previous_question": self.explicit_answer_to_previous_question,
            "needs_clarification": self.needs_clarification,
            "confidence": self.confidence,
            "raw_message": self.raw_message,
            "normalized_message": self.normalized_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnUnderstanding":
        qs = [
            TurnQuestion.from_dict(q) if isinstance(q, dict) else q
            for q in (data.get("questions") or [])
        ]
        return cls(
            primary_intent=data.get("primary_intent", "unclear"),
            dialogue_act=data.get("dialogue_act", "informing"),
            customer_goal=data.get("customer_goal", "explore"),
            customer_stage=data.get("customer_stage", "discovery"),
            customer_behavior=data.get("customer_behavior", "exploring"),
            sentiment=data.get("sentiment", "neutral"),
            urgency=data.get("urgency", "low"),
            purchase_readiness=data.get("purchase_readiness", "low"),
            questions=qs,
            requested_attributes=list(data.get("requested_attributes") or []),
            mentioned_products=list(data.get("mentioned_products") or []),
            references=list(data.get("references") or []),
            requirements=dict(data.get("requirements") or {}),
            corrections=dict(data.get("corrections") or {}),
            topic_switch=bool(data.get("topic_switch", False)),
            explicit_answer_to_previous_question=data.get("explicit_answer_to_previous_question"),
            needs_clarification=bool(data.get("needs_clarification", False)),
            confidence=float(data.get("confidence", 1.0)),
            raw_message=data.get("raw_message", ""),
            normalized_message=data.get("normalized_message", ""),
        )


def extract_turn_understanding(
    raw_message: str,
    normalized_message: str,
    state: Optional[Any] = None,
) -> TurnUnderstanding:
    """
    Extracts canonical turn understanding from customer message and conversation state.
    Produces unambiguous dialogue act, customer goals, explicit questions, and attributes.
    """
    import re
    from catalog.catalogue_resolver import find_mentioned_catalogue_products

    norm_msg = (normalized_message or raw_message).strip()
    msg_l = norm_msg.lower()

    # 1. Mentioned Products
    mentioned_prods = find_mentioned_catalogue_products(norm_msg)
    mentioned_ids = [p["id"] for p in mentioned_prods]

    # Target product context
    target_product = mentioned_ids[0] if mentioned_ids else None
    if not target_product and state and hasattr(state, "get_canonical_focus_id"):
        target_product = state.get_canonical_focus_id()

    # 2. Extract Explicit Questions
    questions: List[TurnQuestion] = []
    requested_attributes: List[str] = []

    # Speed
    if re.search(r"\b(?:speed|ppm|how\s*fast|seconds?\s*per\s*print|printing\s*speed)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="printing speed",
            semantic_key="print_speed",
            target_product=target_product,
            target_attribute="print_speed"
        ))
        requested_attributes.append("print_speed")

    # Wi-Fi / Connectivity
    if re.search(r"\b(?:wifi|wi-fi|wireless|airprint|ethernet|network|lan|connect(?:ivity)?)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="wi-fi and connectivity support",
            semantic_key="wifi_support",
            target_product=target_product,
            target_attribute="wifi_support"
        ))
        requested_attributes.append("wifi_support")

    # Media Yield / Roll Capacity
    if re.search(r"\b(?:prints?\s*per\s*roll|yield|rolls?\s*per\s*box|capacity\s*per\s*roll|how\s*many\s*prints|roll\s*yield)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="prints per roll / media yield",
            semantic_key="media_yield",
            target_product=target_product,
            target_attribute="media_yield"
        ))
        requested_attributes.append("media_yield")

    # Price / Cost / Investment
    if re.search(r"\b(?:price|cost|how\s*much|rate|rates|quote|quotation|investment|pricing|cpp|cost\s*per\s*print)\b", msg_l) and not re.search(r"\b(?:too|thats|that's)\s*(?:expensive|costly|much)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="pricing and investment cost",
            semantic_key="price",
            target_product=target_product,
            target_attribute="price"
        ))
        requested_attributes.append("price")

    # Physical Specs / Weight / Dimensions
    if re.search(r"\b(?:weight|how\s*heavy|mass|portable|dimensions?|footprint|size\s*of\s*printer)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="dimensions and weight",
            semantic_key="physical_specs",
            target_product=target_product,
            target_attribute="physical_specs"
        ))
        requested_attributes.append("physical_specs")

    # Print Width / Media Size
    if re.search(r"\b(?:print\s*width|paper\s*size|what\s*size|what\s*width|which\s*format|24[\",\s]*36|a4\s*or\s*a3|roll\s*size|format\s*size)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="print width and format size",
            semantic_key="print_width",
            target_product=target_product,
            target_attribute="print_width"
        ))
        requested_attributes.append("print_width")

    # Inks / Consumables
    if re.search(r"\b(?:which\s*inks?|ink\s*type|cartridges?|tank|ribbon|inks?\s*included|consumables?)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="ink and consumable compatibility",
            semantic_key="ink_compatibility",
            target_product=target_product,
            target_attribute="ink_compatibility"
        ))
        requested_attributes.append("ink_compatibility")

    # Warranty
    if re.search(r"\b(?:warranty|guarantee|coverplus|amc|maintenance\s*contract|repair|service)\b", msg_l):
        questions.append(TurnQuestion(
            id=str(uuid.uuid4())[:8],
            text="warranty coverage",
            semantic_key="warranty",
            target_product=target_product,
            target_attribute="warranty"
        ))
        requested_attributes.append("warranty")

    # 3. Anaphoric References
    references: List[str] = []
    for ref_term in ["it", "this", "that", "the first one", "the other one", "these two", "both"]:
        if re.search(rf"\b{re.escape(ref_term)}\b", msg_l):
            references.append(ref_term)

    # 4. Intent & Stage Classification
    primary_intent = "unclear"
    dialogue_act = "informing"
    customer_stage = "discovery"
    customer_behavior = "exploring"
    customer_goal = "find_printer"
    urgency = "low"
    purchase_readiness = "low"

    # Greeting
    if bool(re.search(r"^(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", msg_l.strip())) and len(msg_l.split()) <= 3:
        primary_intent = "greeting"
        dialogue_act = "social"
        customer_stage = "opening"
        customer_behavior = "exploring"
        customer_goal = "explore"

    # Confusion / "what?" case
    elif msg_l.strip() in ["what", "what?", "what ?", "huh", "huh?", "pardon", "pardon?", "excuse me?", "i don't understand", "i didnt understand"]:
        primary_intent = "confusion"
        dialogue_act = "clarification"
        customer_stage = "evaluation"
        customer_behavior = "confused"
        customer_goal = "clarify"

    # Investment Cost Comparison
    elif re.search(r"\b(?:which\s+(?:one\s+)?(?:is\s+)?(?:better|cheaper|lower|best)\s+(?:for\s+)?(?:the\s+)?(?:investment|upfront|initial|running|budget|cost|price)|better\s+for\s+(?:the\s+)?investment\s+cost|which\s+(?:one\s+)?(?:is\s+)?(?:cheaper|more\s+affordable|budget\s+friendly))\b", msg_l):
        primary_intent = "investment_cost_comparison"
        dialogue_act = "compare"
        customer_stage = "comparison"
        customer_behavior = "price_sensitive"
        customer_goal = "compare_products"

    # Closing
    elif any(w in msg_l for w in ["thanks", "thank you", "that's all", "thats all", "done", "bye", "goodbye"]) and not any(w in msg_l for w in ["but", "what about", "how about", "can you", "and"]):
        primary_intent = "closing"
        dialogue_act = "closing"
        customer_stage = "closing"
        customer_behavior = "closing"
        customer_goal = "close_conversation"

    # Price Objection
    elif any(w in msg_l for w in ["that's expensive", "thats expensive", "too expensive", "too much", "high price", "costly", "expensive", "cheaper"]):
        primary_intent = "price_objection"
        dialogue_act = "objection"
        customer_stage = "objection"
        customer_behavior = "price_sensitive"
        customer_goal = "evaluate_price"

    # Frustration
    elif any(w in msg_l for w in ["what i asked what you answering", "you didn't answer", "you did not answer", "answer me", "answer my question", "ignored my question", "wrong answer", "stupid bot", "not what i asked", "stop repeating"]):
        primary_intent = "frustration"
        dialogue_act = "objection"
        customer_stage = "evaluation"
        customer_behavior = "frustrated"

    # Purchase Intent / Order
    elif any(w in msg_l for w in ["order this", "buy this", "purchase", "i want to buy", "how to buy", "checkout"]):
        primary_intent = "purchase_intent"
        dialogue_act = "request"
        customer_stage = "purchase_intent"
        customer_behavior = "ready_to_buy"
        customer_goal = "buy_product"
        purchase_readiness = "high"

    # Product Comparison
    elif any(w in msg_l for w in ["compare", "vs", "versus", "difference between", "which option would be better", "which one is better"]):
        primary_intent = "product_comparison"
        dialogue_act = "compare"
        customer_stage = "comparison"
        customer_behavior = "comparing"
        customer_goal = "compare_products"

    # Direct Question(s)
    elif questions:
        primary_intent = "technical_inquiry" if requested_attributes != ["price"] else "pricing_inquiry"
        dialogue_act = "question"
        customer_stage = "evaluation"
        customer_behavior = "technical"
        customer_goal = "understand_specification"

    # Product Discovery
    elif any(w in msg_l for w in ["printer", "photo printer", "cad", "plotter", "scanner", "sublimation", "recommend", "looking for", "need a"]):
        primary_intent = "product_discovery"
        dialogue_act = "request"
        customer_stage = "discovery"
        customer_behavior = "exploring"
        customer_goal = "find_printer"

    # 5. Requirements Extraction
    requirements: Dict[str, Any] = {}
    if re.search(r"\b(?:photo(?:\s*booth)?|event|wedding|studio|portrait|kiosk)\b", msg_l):
        requirements["category"] = "citizen_photo"
        if re.search(r"\b(?:wedding|weddings)\b", msg_l):
            requirements["application"] = "wedding"
        if re.search(r"\b(?:photo\s*booth|photobooth)\b", msg_l):
            requirements["application"] = "photo_booth"
    elif re.search(r"\b(?:cad|gis|aec|blueprint|blueprints|engineering|technical\s*drawings?)\b", msg_l):
        requirements["category"] = "technical_large_format"
        requirements["application"] = "cad_drawings"
    elif re.search(r"\b(?:office|business\s*documents?|workforce|copier)\b", msg_l):
        requirements["category"] = "office_printer"
        requirements["application"] = "office_documents"
    elif re.search(r"\b(?:dy[\s-]*sublimation|dye[\s-]*sublimation|sublimation|t-shirts?|mugs?|merchandise)\b", msg_l):
        requirements["category"] = "dye_sublimation"
        requirements["application"] = "apparel"

    # Sizes
    if re.search(r"\b4x6\b", msg_l):
        requirements["print_size"] = "4x6"
        requirements["size"] = "4x6"
    elif re.search(r"\b6x8\b", msg_l):
        requirements["print_size"] = "6x8"
        requirements["size"] = "6x8"
    elif re.search(r"\b(?:24[\s-]*(?:inch|in|\")|24)\b", msg_l):
        requirements["print_width"] = 24
    elif re.search(r"\b(?:36[\s-]*(?:inch|in|\")|36)\b", msg_l):
        requirements["print_width"] = 36
    elif re.search(r"\b(?:44[\s-]*(?:inch|in|\")|44)\b", msg_l):
        requirements["print_width"] = 44

    # Speed requirement
    if re.search(r"\b(?:very\s*fast|high\s*speed|fast\s*turnaround)\b", msg_l):
        requirements["speed_priority"] = "high"

    # 6. Topic Switch Detection
    topic_switch = False
    if state and getattr(state, "category", None):
        existing_cat = state.category
        new_cat = requirements.get("category")
        if new_cat and new_cat != existing_cat:
            topic_switch = True
        elif any(w in msg_l for w in ["forget this", "never mind", "switch to", "different printer", "instead i need"]):
            topic_switch = True

    return TurnUnderstanding(
        primary_intent=primary_intent,
        dialogue_act=dialogue_act,
        customer_goal=customer_goal,
        customer_stage=customer_stage,
        customer_behavior=customer_behavior,
        sentiment="neutral",
        urgency=urgency,
        purchase_readiness=purchase_readiness,
        questions=questions,
        requested_attributes=requested_attributes,
        mentioned_products=mentioned_ids,
        references=references,
        requirements=requirements,
        topic_switch=topic_switch,
        raw_message=raw_message,
        normalized_message=norm_msg,
    )

