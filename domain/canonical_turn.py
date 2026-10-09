"""
Canonical Turn Understanding Domain Model for Kepler Tech SalesAI.

Defines the single authoritative semantic representation of a customer turn,
preventing independent reinterpretations across disparate modules.
Downstream components consume this object exclusively.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal
import re
import uuid

CustomerBehavior = Literal[
    "EXPLORING",
    "RESEARCHING",
    "EVALUATING",
    "COMPARING",
    "PRICE_SENSITIVE",
    "HIGH_INTENT",
    "READY_TO_BUY",
    "FRUSTRATED",
    "UNCERTAIN",
    "CLOSING",
]


class CIStr(str):
    """Case-insensitive string that equals both lowercase and uppercase variations."""
    def __eq__(self, other):
        if isinstance(other, str):
            return self.lower() == other.lower()
        return super().__eq__(other)
    def __hash__(self):
        return hash(self.lower())



@dataclass
class CanonicalQuestion:
    """Explicit customer question identified within a turn."""
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
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalQuestion":
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            text=data.get("text", ""),
            semantic_key=data.get("semantic_key", "general_inquiry"),
            target_product=data.get("target_product"),
            target_attribute=data.get("target_attribute"),
        )


@dataclass
class CanonicalTurnUnderstanding:
    """Single canonical interpretation object for a conversational turn."""
    raw_message: str
    normalized_message: str

    primary_goal: str = "explore"
    secondary_goals: List[str] = field(default_factory=list)

    explicit_questions: List[CanonicalQuestion] = field(default_factory=list)
    requested_information: List[str] = field(default_factory=list)

    mentioned_products: List[str] = field(default_factory=list)
    mentioned_categories: List[str] = field(default_factory=list)

    changed_requirements: Dict[str, Any] = field(default_factory=dict)
    corrections: Dict[str, Any] = field(default_factory=dict)

    references: List[str] = field(default_factory=list)
    comparison_target: Optional[str] = None

    customer_behavior: str = "EXPLORING"
    urgency: Optional[str] = "LOW"
    confidence: float = 1.0

    # Backwards-compatible fields with TurnUnderstanding
    dialogue_act: str = "informing"
    customer_stage: str = "discovery"
    sentiment: str = "neutral"
    purchase_readiness: str = "low"
    topic_switch: bool = False
    needs_clarification: bool = False

    @property
    def questions(self) -> List[CanonicalQuestion]:
        """Compatibility property for legacy code expecting .questions."""
        return self.explicit_questions

    @property
    def requested_attributes(self) -> List[str]:
        """Compatibility property for legacy code expecting .requested_attributes."""
        return self.requested_information

    @property
    def primary_intent(self) -> str:
        """Compatibility property for legacy code expecting .primary_intent."""
        return self.primary_goal

    @property
    def requirements(self) -> Dict[str, Any]:
        """Compatibility property for legacy code expecting .requirements."""
        return self.changed_requirements

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_message": self.raw_message,
            "normalized_message": self.normalized_message,
            "primary_goal": self.primary_goal,
            "primary_intent": self.primary_goal,
            "secondary_goals": list(self.secondary_goals),
            "explicit_questions": [q.to_dict() for q in self.explicit_questions],
            "questions": [q.to_dict() for q in self.explicit_questions],
            "requested_information": list(self.requested_information),
            "requested_attributes": list(self.requested_information),
            "mentioned_products": list(self.mentioned_products),
            "mentioned_categories": list(self.mentioned_categories),
            "changed_requirements": dict(self.changed_requirements),
            "requirements": dict(self.changed_requirements),
            "corrections": dict(self.corrections),
            "references": list(self.references),
            "comparison_target": self.comparison_target,
            "customer_behavior": self.customer_behavior,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "dialogue_act": self.dialogue_act,
            "customer_stage": self.customer_stage,
            "sentiment": self.sentiment,
            "purchase_readiness": self.purchase_readiness,
            "topic_switch": self.topic_switch,
            "needs_clarification": self.needs_clarification,
        }


def extract_canonical_turn(
    raw_message: str,
    normalized_message: str,
    state: Optional[Any] = None,
) -> CanonicalTurnUnderstanding:
    """
    Extracts the canonical interpretation of the customer's latest turn.
    Guarantees:
    1. Latest customer message has highest priority.
    2. Explicit multi-question extraction with target product resolution.
    3. Explicit correction extraction (product, category, application, format).
    4. Accurate customer behavior mapping.
    """
    from catalog.catalogue_resolver import find_mentioned_catalogue_products

    norm_msg = (normalized_message or raw_message).strip()
    msg_l = norm_msg.lower()

    # 1. Mentioned Products
    mentioned_prods = find_mentioned_catalogue_products(norm_msg)
    mentioned_ids = [p["id"] for p in mentioned_prods]

    target_product = mentioned_ids[0] if mentioned_ids else None
    if not target_product and state and hasattr(state, "get_canonical_focus_id"):
        target_product = state.get_canonical_focus_id()

    # 2. Extract Explicit Corrections
    corrections: Dict[str, Any] = {}
    
    # Product correction: "no, I meant CX-02W", "actually cx-02w", "not cx-02, cx-02w"
    # Product correction: "no, I meant CX-02W", "actually cx-02w", "not cz-01, i meant cy-02", "actually not p900, i meant sc-p700"
    if re.search(r"\b(?:no|actually|not|instead\s+of|meant)\b", msg_l):
        after_meant = re.search(r"\b(?:i\s+meant|meant|actually\s+i\s+meant|i\s+need|need|i\s+was\s+looking\s+for|i\s+was\s+asking\s+about)\s+(?:the\s+)?([a-zA-Z0-9\s_-]+)", msg_l)
        cand_text = after_meant.group(1).strip() if after_meant else None
        if not cand_text:
            prod_corr_match = re.search(r"\b(?:no[,\s]+(?:i\s+meant|actually)?|actually[,\s]+(?:i\s+meant)?)\s+([a-zA-Z0-9\s_-]+)", msg_l)
            cand_text = prod_corr_match.group(1).strip() if prod_corr_match else None
        if cand_text:
            matched_corr = find_mentioned_catalogue_products(cand_text)
            if matched_corr:
                new_prod_id = matched_corr[0]["id"]
                old_prod_id = target_product if target_product != new_prod_id else None
                corrections["product"] = {
                    "old": old_prod_id,
                    "new": new_prod_id,
                }
                target_product = new_prod_id
                if new_prod_id in mentioned_ids:
                    mentioned_ids.remove(new_prod_id)
                mentioned_ids.insert(0, new_prod_id)

    # Category / Application correction & Topic Switching
    has_switch_cue = any(w in msg_l for w in ["actually", "forget", "never mind", "need", "want", "switch", "looking for", "instead", "show me", "look a", "look for", "look at", "explore", "now i want", "now i need"])
    sw_clause = re.search(r"\b(?:forget|never\s*mind|instead\s*of)\s+[^,.]+[,\s]+(.*)", msg_l)
    target_text = sw_clause.group(1).strip() if sw_clause else msg_l

    if re.search(r"\b(?:cad|blueprints?|architectural|engineering|drawing\s*plotter|large\s*format\s*technical|wide\s*format\s*cad|plotter|plan\s*printing)\b", target_text) and has_switch_cue:
        corrections["category"] = "technical_large_format"
        corrections["application"] = "cad_drawings"
        if state and getattr(state, "category", None) and state.category not in ("technical_large_format", "technical_cad"):
            corrections["reset_requirements"] = True
    elif re.search(r"\b(?:photo|events?|weddings?|photo\s*booth|party\s*booth|studio\s*photo|portable\s*printer)\b", target_text) and has_switch_cue:
        corrections["category"] = "citizen_photo"
        corrections["application"] = "wedding"
        if state and getattr(state, "category", None) and state.category != "citizen_photo":
            corrections["reset_requirements"] = True
    elif re.search(r"\b(?:dye[-\s]*sublimation|sublimation|mugs|t[-\s]*shirts?)\b", target_text) and has_switch_cue:
        corrections["category"] = "dye_sublimation"
        if state and getattr(state, "category", None) and state.category != "dye_sublimation":
            corrections["reset_requirements"] = True
    elif re.search(r"\b(?:office\s*(?:printer|multifunction|mfp)|office\s*use)\b", target_text) and has_switch_cue:
        corrections["category"] = "office_printer"
        if state and getattr(state, "category", None) and state.category != "office_printer":
            corrections["reset_requirements"] = True
    elif re.search(r"\b(?:scanners?|document\s*scanners?|flatbed\s*scanners?)\b", target_text) and has_switch_cue:
        corrections["category"] = "scanner"
        if state and getattr(state, "category", None) and state.category != "scanner":
            corrections["reset_requirements"] = True
    elif re.search(r"\b(?:labels?|label\s*printers?|stickers?|printer\s*sticker|sticker\s*printer|barcode\s*labels?|colour\s*labels?|color\s*labels?|colorworks)\b", target_text):
        corrections["category"] = "label_printer"
        if state and getattr(state, "category", None) and state.category != "label_printer":
            corrections["reset_requirements"] = True

    # Size/Format correction: "actually i need a1", "no, 24 inch"
    if re.search(r"\b(?:actually\s+(?:i\s+need\s+)?a1|no[,\s]+a1)\b", msg_l):
        corrections["format"] = "A1"
    elif re.search(r"\b(?:actually\s+(?:i\s+need\s+)?24|no[,\s]+24\s*(?:inch|in|\"))\b", msg_l):
        corrections["format"] = "24_inch"

    # Reset requirement correction: "forget the previous requirement", "never mind that"
    if re.search(r"\b(?:forget\s+(?:the\s+)?previous\s+requirement|never\s*mind\s+that|start\s+over)\b", msg_l):
        corrections["reset_requirements"] = True

    # 3. Extract Explicit Questions
    explicit_questions: List[CanonicalQuestion] = []
    requested_information: List[str] = []

    # Map of pattern -> (semantic_key, label, attribute)
    QUESTION_PATTERNS = [
        (
            r"\b(?:speed|ppm|how\s*fast|seconds?\s*per\s*print|printing\s*speed)\b",
            "print_speed",
            "printing speed",
            "print_speed"
        ),
        (
            r"\b(?:wifi|wi-fi|wireless|airprint|ethernet|network|lan|connect(?:ivity)?)\b",
            "wifi_support",
            "wi-fi and connectivity support",
            "wifi_support"
        ),
        (
            r"\b(?:prints?\s*per\s*roll|yield|rolls?\s*per\s*box|capacity\s*per\s*roll|how\s*many\s*prints|roll\s*yield)\b",
            "media_yield",
            "prints per roll / media yield",
            "media_yield"
        ),
        (
            r"\b(?:weight|how\s*heavy|mass|dimensions?|footprint|size\s*of\s*printer)\b",
            "physical_specs",
            "dimensions and weight",
            "physical_specs"
        ),
        (
            r"\b(?:(?:max|maximum|print|what)\s*widths?|(?:paper|print|roll|format|supported\s+print)\s*sizes?|what\s*sizes?|what\s*widths?|(?:what|which)\s*formats?|24[\",\s]*36|a4\s*or\s*a3|roll\s*sizes?|format\s*sizes?)\b",
            "print_width",
            "print width and format size",
            "print_width"
        ),
        (
            r"\b(?:resolution|dpi|print\s*resolution)\b",
            "resolution",
            "print resolution and dpi",
            "resolution"
        ),
        (
            r"\b(?:(?:can|does|has|is)\s+(?:it|this|the\s+second(?:\s+one)?|[a-z0-9\-]+).*?\b(?:scanner|scan)|can\s+it\s+scan|does\s+it\s+scan|is\s+there\s+(?:a\s+)?scanner|scanner\s*\?|(?:have|with)\s+a?\s*scanner\?)\b",
            "scanner_support",
            "scanner capability",
            "scanner"
        ),
        (
            r"\b(?:warranty|guarantee|warranty\s*duration|warranty\s*period|warranty\s*coverage)\b",
            "warranty",
            "warranty coverage",
            "warranty"
        ),
        (
            r"\b(?:(?:which|what).*?\b(?:inks?|media|ribbon|consumables?)|ink\b|inks\b|cartridges?|tanks?|refill(?:able)?|bottles?|ribbon|inks?\s*included|consumables?|how\s*many\s*inks?|ink\s*col(?:ou)?rs?|number\s*of\s*col(?:ou)?rs?)\b",
            "ink_compatibility",
            "ink and consumable compatibility",
            "ink_compatibility"
        ),
        (
            r"\b(?:solar\s*panels?|coffee\s*maker|3d\s*(?:plastic|objects?)|bluetooth\s*audio|speakers?|video\s*projection)\b",
            "unsupported_feature",
            "unsupported feature",
            "unsupported_feature"
        ),
        (
            r"\b(?:stand|floor\s*stand|legs?|included\s*stand)\b",
            "physical_specs",
            "stand and mounting configuration",
            "physical_specs"
        ),
    ]

    has_media_loss = bool(re.search(r"\b(?:without|with\s+out|no|zero)\s+media\s*loss\b", msg_l))

    for pat, sem_key, label, attr in QUESTION_PATTERNS:
        if sem_key == "ink_compatibility" and has_media_loss:
            continue
        if re.search(pat, msg_l):
            explicit_questions.append(CanonicalQuestion(
                id=str(uuid.uuid4())[:8],
                text=label,
                semantic_key=sem_key,
                target_product=target_product,
                target_attribute=attr,
            ))
            requested_information.append(attr)

    # Price inquiry (exclude price objections, comparisons, and weight queries)
    is_price_comp = bool(re.search(r"\bwhich\s+(?:one\s+)?(?:is\s+)?(?:better|cheaper|lower|best|option)\b", msg_l))
    is_weight_query = bool(re.search(r"\bhow\s*much\s*does\s*.*weigh\b", msg_l))
    is_objection = bool(re.search(r"\b(?:too\s*(?:expensive|costly|much|high)|for\s*our\s*budget|high\s*price|cheaper)\b", msg_l))
    if (
        re.search(r"\b(?:price|cost|how\s*much|rate|rates|quote|quotation|investment|pricing|cpp|cost\s*per\s*print)\b", msg_l)
        and not is_objection
        and not is_price_comp
        and not is_weight_query
    ):
        explicit_questions.append(CanonicalQuestion(
            id=str(uuid.uuid4())[:8],
            text="pricing and investment cost",
            semantic_key="price",
            target_product=target_product,
            target_attribute="price",
        ))
        requested_information.append("price")

    if target_product and not explicit_questions:
        prev_sem_key = None
        prev_attr = None
        prev_label = None
        if state and getattr(state, "question_ledger", None) and getattr(state.question_ledger, "items", None):
            last_cust_item = next((it for it in reversed(state.question_ledger.items) if getattr(it, "origin", "") == "customer"), None)
            if last_cust_item:
                prev_sem_key = last_cust_item.semantic_key
                prev_attr = last_cust_item.target_attribute
                prev_label = last_cust_item.text if hasattr(last_cust_item, "text") else last_cust_item.original_text

        if prev_sem_key and re.search(r"\b(?:what\s+about|and\s+(?:what\s+about|for)|how\s+about)\b", msg_l):
            explicit_questions.append(CanonicalQuestion(
                id=str(uuid.uuid4())[:8],
                text=prev_label or f"{prev_sem_key} for {target_product}",
                semantic_key=prev_sem_key,
                target_product=target_product,
                target_attribute=prev_attr or prev_sem_key,
            ))
            requested_information.append(prev_attr or prev_sem_key)
        elif len(mentioned_ids) == 1 and (
            re.search(r"\b(?:tell\s+me\s+about|details?\s+(?:on|about)|info\s+(?:on|about)|information\s+(?:on|about)|specs?\s+(?:for|of|on)|specifications?\s+(?:for|of|on)|what\s+about|features?\s+of)\b", msg_l)
            or msg_l.strip() in (target_product, f"epson {target_product}", f"citizen {target_product}")
        ):
            explicit_questions.append(CanonicalQuestion(
                id=str(uuid.uuid4())[:8],
                text=f"product specifications for {target_product}",
                semantic_key="product_specs",
                target_product=target_product,
                target_attribute="specifications",
            ))
            requested_information.append("specifications")

    # 4. Context References
    references: List[str] = []
    for ref_term in ["it", "this", "that", "this one", "that model", "the first one", "the second one", "second one", "second printer", "second model", "the other one", "these two", "both", "same printer"]:
        if re.search(rf"\b{re.escape(ref_term)}\b", msg_l):
            references.append(ref_term)

    # 5. Customer Behavior & Goal Classification
    customer_behavior = "EXPLORING"
    primary_goal = "find_printer"
    dialogue_act = "informing"
    customer_stage = "discovery"
    urgency = "LOW"
    purchase_readiness = "low"
    secondary_goals: List[str] = []

    # Conversational Acknowledgment (e.g. "okey", "okay", "alright", "got it", "fine", "cool", "noted")
    if msg_l.strip() in ["ok", "okey", "okay", "alright", "all right", "got it", "fine", "cool", "noted", "sure", "k"] and not explicit_questions:
        customer_behavior = "ENGAGED"
        primary_goal = "acknowledgment"
        dialogue_act = "social"
        customer_stage = "in_consultation"

    # Check Closing first
    elif any(w in msg_l for w in ["thanks", "thank you", "that's all", "thats all", "done", "bye", "goodbye"]) and not any(w in msg_l for w in ["but", "what about", "how about", "can you", "and what", "and how", "and does", "and is"]):
        customer_behavior = "CLOSING"
        primary_goal = "closing"
        dialogue_act = "closing"
        customer_stage = "closing"

    # Frustration: "You are not answering my question", "wrong answer", "answer what I asked"
    elif any(w in msg_l for w in [
        "what i asked what you answering", "you didn't answer", "you did not answer",
        "answer me", "answer my question", "ignored my question", "wrong answer",
        "not what i asked", "stop repeating", "you're not answering", "what i asked was"
    ]):
        customer_behavior = "FRUSTRATED"
        primary_goal = "frustration"
        dialogue_act = "objection"
        customer_stage = "evaluation"
        urgency = "HIGH"

    # Price Sensitive / Objection: "too expensive", "thats expensive", "high price", "too high"
    elif any(w in msg_l for w in [
        "that's expensive", "thats expensive", "too expensive", "too much", "high price",
        "costly", "expensive", "cheaper", "too high", "for our budget", "affordable",
        "pricey", "cannot afford", "beyond what we planned", "high for a desktop", "high for us"
    ]):
        customer_behavior = "PRICE_SENSITIVE"
        primary_goal = "price_objection"
        dialogue_act = "objection"
        customer_stage = "objection"

    # High Intent / Ready to buy: "order this", "buy this", "how to buy", "i want to buy"
    elif re.search(r"\b(?:place\s*(?:an\s*)?order|order\s+(?:one|two|\d+|this|a|the)|want\s+to\s+order|like\s+to\s+order|buy\s+(?:this|two|\d+|a|the)|want\s+to\s+buy|how\s+to\s+buy|how\s+can\s+we\s+buy|ready\s+to\s+buy|ready\s+to\s+checkout|purchase|checkout|send\s+(?:the\s+)?invoice|send\s+invoice)\b", msg_l):
        customer_behavior = "READY_TO_BUY"
        primary_goal = "purchase_intent"
        dialogue_act = "request"
        customer_stage = "purchase_intent"
        purchase_readiness = "high"
        urgency = "MEDIUM"

    # Investment cost comparison
    elif re.search(r"\b(?:which\s+(?:one\s+)?(?:is\s+)?(?:better|cheaper|lower|best)\s+(?:for\s+)?(?:the\s+)?(?:investment|upfront|initial|running|budget|cost|price)|better\s+for\s+(?:the\s+)?investment\s+cost|which\s+option\s+would\s+be\s+better)\b", msg_l):
        customer_behavior = "PRICE_SENSITIVE"
        primary_goal = "investment_cost_comparison"
        dialogue_act = "compare"
        customer_stage = "comparison"

    # Comparing: "compare", "campare", "vs", "versus", "difference between", "which is faster", "which is better"
    elif any(w in msg_l for w in ["compare", "campare", "comapare", "compair", "conpare", "vs", "versus", "difference between", "which option would be better", "which one is better", "which is faster", "which is cheaper"]):
        customer_behavior = "COMPARING"
        primary_goal = "product_comparison"
        dialogue_act = "compare"
        customer_stage = "comparison"

    # Technical Direct Inquiries:
    elif explicit_questions:
        customer_behavior = "RESEARCHING" if requested_information != ["price"] else "PRICE_SENSITIVE"
        primary_goal = "technical_inquiry" if requested_information != ["price"] else "pricing_inquiry"
        dialogue_act = "question"
        customer_stage = "evaluation"

    # Confusion: "what?", "huh?", "pardon?"
    elif msg_l.strip() in ["what", "what?", "what ?", "huh", "huh?", "pardon", "pardon?", "excuse me?", "i don't understand", "i didnt understand"]:
        customer_behavior = "UNCERTAIN"
        primary_goal = "confusion"
        dialogue_act = "clarification"
        customer_stage = "evaluation"

    # Greeting
    elif bool(re.search(r"^(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", msg_l.strip())) and len(msg_l.split()) <= 3:
        customer_behavior = "EXPLORING"
        primary_goal = "greeting"
        dialogue_act = "social"
        customer_stage = "opening"

    # General Product Discovery
    elif any(w in msg_l for w in ["printer", "photo printer", "cad", "plotter", "scanner", "sublimation", "recommend", "looking for", "need a"]):
        customer_behavior = "EXPLORING"
        primary_goal = "product_discovery"
        dialogue_act = "request"
        customer_stage = "discovery"

    # 6. Extract Requirements & Categories
    changed_requirements: Dict[str, Any] = {}
    mentioned_categories: List[str] = []

    if corrections.get("category"):
        corr_cat = corrections["category"]
        changed_requirements["category"] = corr_cat
        mentioned_categories.append(corr_cat)
        if corrections.get("application"):
            changed_requirements["application"] = corrections["application"]
    elif (
        re.search(r"\b(?:scanners?|document\s*scanners?|flatbed\s*scanners?|photo\s*scanners?|film\s*scanners?|hybrid\s*scanners?)\b", msg_l)
        and not re.search(r"\b(?:with\s+a?\s*scanner|scanner\s+built\s*in|integrated\s*scanner|has\s+a?\s*scanner|can\s+it\s+scan|printer\s+with\s+scanner)\b", msg_l)
    ) or (
        state and getattr(state, "category", "") in ("scanner", "scanners")
        and not re.search(r"\b(?:printers?|plotters?|citizen|cx-02|f100|f500|am-c|c5000)\b", msg_l)
    ):
        changed_requirements["category"] = "scanner"
        mentioned_categories.append("scanner")
    elif re.search(r"\b(?:photo(?:\s*booth)?|event|wedding|studio|portrait|kiosk|citizen)\b", msg_l) or (state and getattr(state, "category", "") == "citizen_photo" and re.search(r"\b(?:on[\s-]*site|onsite|studio|portraits?|portable|events?|wedding|weddings?|photo\s*booth|photobooth|kiosk)\b", msg_l)):
        changed_requirements["category"] = "citizen_photo"
        mentioned_categories.append("citizen_photo")
        if re.search(r"\b(?:on[\s-]*site|onsite|studio|portraits?|photo\s*studio)\b", msg_l):
            changed_requirements["application"] = "studio"
        elif re.search(r"\b(?:photo\s*booth|photobooth)\b", msg_l):
            changed_requirements["application"] = "photo_booth"
        elif re.search(r"\b(?:portable|event|events|wedding|weddings|kiosk)\b", msg_l):
            changed_requirements["application"] = "wedding"
    elif re.search(r"\b(?:cad|gis|aec|blueprint|blueprints|engineering|technical\s*drawings?)\b", msg_l):
        changed_requirements["category"] = "technical_large_format"
        mentioned_categories.append("technical_large_format")
        changed_requirements["application"] = "cad_drawings"
    elif re.search(r"\b(?:office|business\s*documents?|workforce|copier)\b", msg_l):
        changed_requirements["category"] = "office_printer"
        mentioned_categories.append("office_printer")
        changed_requirements["application"] = "office_documents"
    elif re.search(r"\b(?:dy[\s-]*sublimation|dye[\s-]*sublimation|sublimation|t-shirts?|mugs?|merchandise)\b", msg_l):
        changed_requirements["category"] = "dye_sublimation"
        mentioned_categories.append("dye_sublimation")
        changed_requirements["application"] = "apparel"

    # Sizes (checked in descending order: 44/B0 > 36/A0 > 24/A1 > 17/A2 > 13/A3)
    size_target_text = target_text if sw_clause else msg_l
    if re.search(r"\b(?:44[\s-]*(?:inch|in|\")|44|b0)\b", size_target_text):
        changed_requirements["print_size"] = CIStr("B0")
        changed_requirements["paper_size"] = CIStr("B0")
        changed_requirements["print_width"] = 44
    elif re.search(r"\b(?:36[\s-]*(?:inch|in|\")|36|a0)\b", size_target_text):
        changed_requirements["print_size"] = CIStr("A0")
        changed_requirements["paper_size"] = CIStr("A0")
        changed_requirements["print_width"] = 36
    elif re.search(r"\b(?:24[\s-]*(?:inch|in|\")|24|a1)\b", size_target_text):
        changed_requirements["print_size"] = CIStr("A1")
        changed_requirements["paper_size"] = CIStr("A1")
        changed_requirements["print_width"] = 24
    elif re.search(r"\b(?:17[\s-]*(?:inch|in|\")|17|a2)\b", size_target_text):
        changed_requirements["print_size"] = CIStr("A2")
        changed_requirements["paper_size"] = CIStr("A2")
        changed_requirements["print_width"] = 17
    elif re.search(r"\b(?:13[\s-]*(?:inch|in|\")|13|a3\+?)\b", size_target_text):
        changed_requirements["print_size"] = CIStr("A3")
        changed_requirements["paper_size"] = CIStr("A3")
        changed_requirements["print_width"] = 13
    elif re.search(r"\b6x8\b", size_target_text):
        changed_requirements["print_size"] = "6x8"
        changed_requirements["size"] = "6x8"
    elif re.search(r"\b4x6\b", size_target_text):
        changed_requirements["print_size"] = "4x6"
        changed_requirements["size"] = "4x6"

    # Speed requirement
    if re.search(r"\b(?:very\s*fast|high\s*speed|fast\s*turnaround)\b", msg_l):
        changed_requirements["speed_priority"] = "high"

    # Merge deterministic requirements (scanner, volumes, slot resolution)
    try:
        from conversation.normalizer import extract_deterministic_requirements
        det_reqs, det_corrs = extract_deterministic_requirements(
            text=norm_msg,
            category=state.category if state else changed_requirements.get("category"),
            awaiting_field=state.awaiting_field if state else None,
        )
        if det_reqs:
            for k, v in det_reqs.items():
                if k not in corrections:
                    changed_requirements[k] = v
        if det_corrs:
            for k, v in det_corrs.items():
                corrections[k] = v
    except Exception:
        pass

    # 7. Topic Switch Detection
    topic_switch = False
    if state and getattr(state, "category", None):
        existing_cat = state.category
        new_cat = changed_requirements.get("category")
        if new_cat and new_cat != existing_cat:
            topic_switch = True
        elif any(w in msg_l for w in ["forget this", "never mind", "switch to", "different printer", "instead i need"]):
            topic_switch = True

    # Comparison target
    comparison_target = None
    if len(mentioned_ids) >= 2:
        comparison_target = mentioned_ids[1]

    return CanonicalTurnUnderstanding(
        raw_message=raw_message,
        normalized_message=norm_msg,
        primary_goal=primary_goal,
        secondary_goals=secondary_goals,
        explicit_questions=explicit_questions,
        requested_information=requested_information,
        mentioned_products=mentioned_ids,
        mentioned_categories=mentioned_categories,
        changed_requirements=changed_requirements,
        corrections=corrections,
        references=references,
        comparison_target=comparison_target,
        customer_behavior=customer_behavior,
        urgency=urgency,
        confidence=1.0,
        dialogue_act=dialogue_act,
        customer_stage=customer_stage,
        topic_switch=topic_switch,
    )
