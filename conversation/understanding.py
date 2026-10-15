"""
Structured Conversational Turn Understanding for Kepler Tech SalesAI.
Phase 1: Deterministic extractors first, then constrained small LLM,
merged with deterministic priority into a single typed Pydantic object.
"""

import os
import re
import time
import logging
from enum import Enum
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field

from config import (
    OLLAMA_CLASSIFIER_MODEL,
    FUZZY_MATCH_THRESHOLD,
    THINKING_ENABLED,
)
from ollama_client import ollama_client

logger = logging.getLogger("conversation.understanding")


# ── Dialogue Acts & Closed Intents Taxonomy ───────────────────────────────────

class DialogueAct(str, Enum):
    QUESTION = "question"
    ANSWER_TO_MY_QUESTION = "answer_to_my_question"
    CONFIRMATION = "confirmation"
    REJECTION = "rejection"
    CORRECTION = "correction"
    REFINEMENT = "refinement"
    REFERENCE_FOLLOW_UP = "reference_follow_up"
    CHITCHAT = "chitchat"
    COMPLAINT = "complaint"
    HANDOFF_REQUEST = "handoff_request"
    OUT_OF_SCOPE = "out_of_scope"


class Intent(str, Enum):
    PRODUCT_INFO = "product_info"
    COMPATIBILITY_CHECK = "compatibility_check"
    CONSUMABLES_LOOKUP = "consumables_lookup"
    COMPARE = "compare"
    RECOMMEND = "recommend"
    ALTERNATIVES = "alternatives"
    AVAILABILITY_OR_PRICE_POLICY = "availability_or_price_policy"
    DISCOUNT_REQUEST = "discount_request"
    QUOTE_REQUEST = "quote_request"
    CUSTOM_CONFIG_REQUEST = "custom_config_request"
    COMPETITOR_MENTION = "competitor_mention"
    CONTACT_SHOWROOM = "contact_showroom"
    SHIPPING_OR_DELIVERY = "shipping_or_delivery"
    OTHER = "other"


# ── Typed Turn Understanding Schema ───────────────────────────────────────────

class EntityMention(BaseModel):
    surface_text: str
    normalised_id: str
    entity_type: str  # "model", "sku", "category", "size", "attribute", "brand"
    match_type: str   # "exact", "fuzzy", "alias"
    confidence: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReferenceExpression(BaseModel):
    text: str
    reference_type: str  # "demonstrative", "pronoun", "ordinal", "attribute_ref", "color_ref", "ellipsis", "comparative"
    target_type_hint: Optional[str] = None  # "consumable", "printer", "media", "unknown"
    start_idx: int = 0
    end_idx: int = 0


class SlotValue(BaseModel):
    slot_name: str
    value: Any
    confidence: float = 1.0
    source: str = "said_now"  # "said_now", "inherited", "assumed"


class TurnUnderstanding(BaseModel):
    raw_text: str
    dialogue_act: DialogueAct
    intent: Intent
    secondary_intents: List[Intent] = Field(default_factory=list)
    entities: List[EntityMention] = Field(default_factory=list)
    reference_expressions: List[ReferenceExpression] = Field(default_factory=list)
    slots: Dict[str, SlotValue] = Field(default_factory=dict)
    overall_confidence: float = 1.0
    ambiguities: List[str] = Field(default_factory=list)
    buyer_pace: str = "standard"  # "concise" | "standard" | "technical"
    is_deterministic: bool = True
    used_llm: bool = False
    latency_ms: int = 0


# ── Catalogue Aliases & Knowledge Cache ──────────────────────────────────────

_CATALOGUE_ALIASES_CACHE: Optional[Dict[str, str]] = None
_KNOWN_SKUS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _get_catalogue_aliases() -> Dict[str, str]:
    """Builds and caches lowercase alias -> canonical_product_id mapping."""
    global _CATALOGUE_ALIASES_CACHE
    if _CATALOGUE_ALIASES_CACHE is not None:
        return _CATALOGUE_ALIASES_CACHE

    alias_map: Dict[str, str] = {}
    try:
        from catalog.catalogue_loader import catalogue_loader
        products = catalogue_loader.load_and_validate()
        for p in products:
            pid = p.get("id", "").lower()
            name = p.get("name", "").lower()
            disp = p.get("display_name", "").lower()
            fam = p.get("model_family", "").lower()

            # Canonical ID itself
            alias_map[pid] = pid

            # Shorthands and common aliases
            for s in [name, disp, fam]:
                if s:
                    alias_map[s] = pid

            # Specific family shorthands: epson-sc-f500 -> f500, sc f500, sc-f500, surecolor f500
            for prefix in ["epson-sc-", "epson-wf-", "epson-am-", "epson-em-", "citizen-"]:
                if pid.startswith(prefix):
                    short = pid[len(prefix):]
                    alias_map[short] = pid
                    alias_map[short.replace("-", " ")] = pid
                    alias_map[short.replace("-", "")] = pid
                    alias_map[f"sc {short}"] = pid
                    alias_map[f"sc-{short}"] = pid
                    alias_map[f"surecolor {short}"] = pid
                    alias_map[f"citizen {short}"] = pid
                    alias_map[f"epson {short}"] = pid

        # Handcrafted high-frequency shortcuts and variants
        high_frequency = {
            "f500": "epson-sc-f500",
            "f 500": "epson-sc-f500",
            "sc f500": "epson-sc-f500",
            "sc-f500": "epson-sc-f500",
            "f100": "epson-sc-f100",
            "f 100": "epson-sc-f100",
            "sc f100": "epson-sc-f100",
            "sc-f100": "epson-sc-f100",
            "t3100": "epson-sc-t3100",
            "sc t3100": "epson-sc-t3100",
            "t3700": "epson-sc-t3700d",
            "t3700d": "epson-sc-t3700d",
            "sc-t3700": "epson-sc-t3700d",
            "sc-t3700d": "epson-sc-t3700d",
            "t5100": "epson-sc-t5100",
            "t5405": "epson-sc-t5405",
            "t5700": "epson-sc-t5700d",
            "t7700": "epson-sc-t7700d",
            # Citizen Photo Booth Printers
            "cx02": "citizen-cx-02",
            "cx-02": "citizen-cx-02",
            "cx 02": "citizen-cx-02",
            "cx2": "citizen-cx-02",
            "cx-2": "citizen-cx-02",
            "cx 2": "citizen-cx-02",
            "citizen cx02": "citizen-cx-02",
            "cx02w": "citizen-cx-02w",
            "cx-02w": "citizen-cx-02w",
            "cx 02w": "citizen-cx-02w",
            "cx2w": "citizen-cx-02w",
            "cx-2w": "citizen-cx-02w",
            "cx 2w": "citizen-cx-02w",
            "citizen cx02w": "citizen-cx-02w",
            "cy02": "citizen-cy-02",
            "cy-02": "citizen-cy-02",
            "cy 02": "citizen-cy-02",
            "cy2": "citizen-cy-02",
            "cy-2": "citizen-cy-02",
            "cy 2": "citizen-cy-02",
            "citizen cy02": "citizen-cy-02",
            "cz01": "citizen-cz-01",
            "cz-01": "citizen-cz-01",
            "cz 01": "citizen-cz-01",
            "cz1": "citizen-cz-01",
            "cz-1": "citizen-cz-01",
            "cz 1": "citizen-cz-01",
            "citizen cz01": "citizen-cz-01",
            "citizen cz-01": "citizen-cz-01",
            "citizen cz 01": "citizen-cz-01",
            # Epson SureColor Photo & Fine Art
            "p700": "epson-sc-p700",
            "sc-p700": "epson-sc-p700",
            "p900": "epson-sc-p900",
            "sc-p900": "epson-sc-p900",
            "p5300": "epson-sc-p5300",
            "sc-p5300": "epson-sc-p5300",
            "p6500": "epson-sc-p6500d",
            "p7500": "epson-sc-p7500",
            "p8500": "epson-sc-p8500d",
            "p9500": "epson-sc-p9500",
            "p20500": "epson-sc-p20500",
            # Epson WorkForce Enterprise & Scanners
            "em-c800": "epson-em-c800",
            "em c800": "epson-em-c800",
            "em800": "epson-em-c800",
            "c800": "epson-em-c800",
            "am-c4000": "epson-am-c4000",
            "am c4000": "epson-am-c4000",
            "am-c5000": "epson-am-c5000",
            "am c5000": "epson-am-c5000",
            "am-c6000": "epson-am-c6000",
            "am c6000": "epson-am-c6000",
            "ds-1630": "epson-workforce-ds-1630",
            "ds 1630": "epson-workforce-ds-1630",
            "ds1630": "epson-workforce-ds-1630",
            "ds-6500": "epson-workforce-ds-6500",
            "ds 6500": "epson-workforce-ds-6500",
            "ds6500": "epson-workforce-ds-6500",
            "ds-60000": "epson-workforce-ds-60000",
            "ds 60000": "epson-workforce-ds-60000",
            "ds60000": "epson-workforce-ds-60000",
            "12000xl": "epson-expression-12000xl",
        }
        for k, v in high_frequency.items():
            alias_map[k] = v

        # Add letter-digit spaced variants (e.g. "p 7500", "p-7500", "cx 02", "t 3100")
        spaced_variants: Dict[str, str] = {}
        for alias, pid in list(alias_map.items()):
            m_code = re.match(r"^([a-z]{1,4})[-_]?(\d{2,5}[a-z]*)$", alias)
            if m_code:
                spaced_variants[f"{m_code.group(1)} {m_code.group(2)}"] = pid
                spaced_variants[f"{m_code.group(1)}-{m_code.group(2)}"] = pid
            m_sc = re.match(r"^(sc|surecolor)[-\s]+([a-z]{1,3})[-_]?(\d{2,5}[a-z]*)$", alias)
            if m_sc:
                spaced_variants[f"{m_sc.group(1)} {m_sc.group(2)} {m_sc.group(3)}"] = pid
                spaced_variants[f"{m_sc.group(1)}-{m_sc.group(2)} {m_sc.group(3)}"] = pid
        alias_map.update(spaced_variants)
    except Exception as e:
        logger.warning(f"Error initializing catalogue aliases: {e}")

    _CATALOGUE_ALIASES_CACHE = alias_map
    return alias_map


def _get_known_skus() -> Dict[str, Dict[str, Any]]:
    """Caches known SKUs from catalogue and consumable registries."""
    global _KNOWN_SKUS_CACHE
    if _KNOWN_SKUS_CACHE is not None:
        return _KNOWN_SKUS_CACHE

    sku_map: Dict[str, Dict[str, Any]] = {}
    try:
        from catalog.consumable_registry import consumable_registry
        for sku, item in consumable_registry.consumables.items():
            sku_clean = sku.upper().strip()
            sku_map[sku_clean] = {
                "sku": sku_clean,
                "name": item.name,
                "category": item.consumable_type,
                "color": item.color,
                "printers": item.compatible_printers,
            }
    except Exception as e:
        logger.warning(f"Error loading consumable SKUs: {e}")

    _KNOWN_SKUS_CACHE = sku_map
    return sku_map


# ── Negation and Polarity Detection ──────────────────────────────────────────

NEGATION_TOKENS = {
    "not", "no", "dont", "don't", "without", "except", "forget", "skip",
    "never", "cancel", "neither", "nor", "nahi", "nahin", "mat", "nhi",
    "la", "mush", "mish", "venda", "alla", "allathe",
    "لا", "مش", "غير", "بدون", "بلا", "ويند", "വേണ്ട", "അല്ല"
}

NEGATION_PHRASES = [
    "do not", "don't need", "dont need", "don't want", "dont want",
    "not interested", "not needed", "no need", "instead of", "never mind",
    "change of mind", "ما نريد", "ما نحتاج", "don't print", "dont print",
    "we don't", "we dont", "don't include", "dont include"
]


def is_negated_match(text_l: str, start_idx: int, end_idx: Optional[int] = None) -> bool:
    """
    Checks if a slot keyword or entity mention starting at start_idx in text_l
    is preceded by a negation token or phrase within a 4-token window,
    or followed by a post-position negation token.
    """
    if start_idx > 0:
        window = text_l[max(0, start_idx - 50):start_idx].strip()
        if window:
            for p in NEGATION_PHRASES:
                if p in window:
                    return True
            tokens = re.findall(r"[\w']+", window)
            check_tokens = tokens[-4:] if len(tokens) >= 4 else tokens
            for t in check_tokens:
                if t in NEGATION_TOKENS:
                    return True
    if end_idx is not None and end_idx < len(text_l):
        window_after = text_l[end_idx:min(len(text_l), end_idx + 25)].strip()
        after_tokens = re.findall(r"[\w']+", window_after)[:2]
        for t in after_tokens:
            if t in {"nahi", "nahin", "mat", "venda", "alla", "allathe", "no", "not"}:
                return True
    return False


# ── Deterministic Turn Understanding Extractor ──────────────────────────────

class TurnUnderstandingExtractor:
    """
    Deterministic first-pass parser for customer messages.
    Extracts Dialogue Act, Intent, Entities (with alias/fuzzy matching),
    Reference Expressions, and Structured Slots.
    """

    SKU_PATTERN = re.compile(
        r"\b(c1[123][a-z0-9]{5,9}|c13s\d+|c12c\d+|t49n\d?|t49[a-z0-9]*|"
        r"ifa\s*\d+|olm\s*\d+|cx2\.(?:4x6|6x8)|cy-ms[a-z0-9.\-]*|"
        r"cz-ms[a-z0-9.\-]*|cx2w\s*812)\b",
        re.I
    )

    REFERENCE_RULES = [
        # Demonstratives
        (re.compile(r"\b(this\s+one|this\s+ink|this\s+cartridge|this\s+model|this\s+printer|this|these\s+ones|these)\b", re.I), "demonstrative"),
        (re.compile(r"\b(that\s+one|that\s+ink|that\s+model|that\s+printer|that|those)\b", re.I), "demonstrative"),
        # Pronouns
        (re.compile(r"\b(it|they|them)\b", re.I), "pronoun"),
        # Ordinals
        (re.compile(r"\b(the\s+first\s+one|the\s+first|the\s+1st\s+one|the\s+1st)\b", re.I), "ordinal"),
        (re.compile(r"\b(the\s+second\s+one|the\s+second|the\s+2nd\s+one|the\s+2nd)\b", re.I), "ordinal"),
        (re.compile(r"\b(the\s+third\s+one|the\s+third|the\s+3rd\s+one|the\s+3rd)\b", re.I), "ordinal"),
        (re.compile(r"\b(the\s+last\s+one|the\s+last)\b", re.I), "ordinal"),
        # Comparatives
        (re.compile(r"\b(the\s+cheaper\s+one|the\s+cheaper\s+printer|the\s+cheapest\s+one|the\s+cheaper)\b", re.I), "comparative"),
        (re.compile(r"\b(the\s+faster\s+one|the\s+wider\s+one|the\s+smaller\s+one|the\s+larger\s+one)\b", re.I), "comparative"),
        # Color / Consumable specific references
        (re.compile(r"\b(same\s+ink|same\s+cartridge|same\s+paper|same\s+media)\b", re.I), "attribute_ref"),
        (re.compile(r"\b(the\s+yellow\s+one|the\s+yellow\s+ink|the\s+black\s+one|the\s+cyan\s+one|the\s+magenta\s+one)\b", re.I), "color_ref"),
        # Ellipsis ("for the f100?", "and for f500?", "what about cx-02?")
        (re.compile(r"(?:^|[,;]|\band\b)\s*(?:for\s+(?:the\s+)?|what\s+about\s+(?:the\s+)?|how\s+about\s+(?:the\s+)?)([a-z0-9\-]+)(?:\s*\?)?\s*$", re.I), "ellipsis"),
    ]

    CONFIRMATION_PATTERNS = [
        re.compile(
            r"^\s*(?:yes|yep|yeah|sure|ok|okay|correct|that'?s\s+right|affirmative|absolutely|indeed|proceed|agree|"
            r"that'?s\s+(?:fine|good|ok|okay|great|cool|clear)|fine|sounds\s+good|alright|all\s+right|okey|noted)\b",
            re.I
        ),
        re.compile(r"^\s*(?:1|first|option\s*1)\s*$", re.I),
    ]

    REJECTION_PATTERNS = [
        re.compile(
            r"\b(?:"
            r"^\s*(?:no|nope|not\s+really|neither|none|incorrect|disagree|nah)|"
            r"(?:don'?t|do\s+not)\s+(?:need|want|print|include)|"
            r"not\s+(?:for|interested|needed|a3|a4|laser|citizen|dye\s+sublimation)|"
            r"forget\s+(?:the|this)|skip\s+the|never\s+mind|cancel\s+(?:the|previous)|"
            r"without\s+(?:a\s+)?(?:stand|scanner)|no\s+scanner\s+needed"
            r")\b",
            re.I
        ),
    ]

    CORRECTION_PATTERNS = [
        re.compile(
            r"\b(?:"
            r"no[,\s]+(?:i\s+)?(?:meant|said)|actually|instead\s+of|correction\b|"
            r"change\s+(?:it\s+)?to|change\s+of\s+mind|"
            r"not\s+[a-z0-9\-]+[,\s]+(?:the\s+|i\s+mean\s+|we\s+need\s+|make\s+it\s+)?[a-z0-9\-]+|"
            r"never\s+mind\s+the\s+[a-z0-9\-]+[,\s]+just\s+the|"
            r"not\s+[a-z0-9\-]+[,\s]+it'?s\s+for|no\s+not\s+[a-z0-9\-]+[,\s]+[a-z0-9\-]+\s+only"
            r")\b",
            re.I
        ),
    ]

    HANDOFF_PATTERNS = [
        re.compile(r"\b(?:speak\s+to\s+(?:a\s+)?(?:human|sales\s*rep|person|specialist)|talk\s+to\s+(?:a\s+)?human|agent|customer\s+support|call\s+me|phone\s+number)\b", re.I),
    ]

    OUT_OF_SCOPE_PATTERNS = [
        # Non-catalogue hardware categories
        re.compile(
            r"\b(?:label\s*printers?|barcode\s*printers?|thermal\s*labels?|pos\s*printers?|receipt\s*printers?|"
            r"3d\s*printers?|resin|laser\s*jets?|toner\b|"
            r"food\s*printers?|edible\s*inks?)\b",
            re.I
        ),
        # Food, cooking, recipes, dining (e.g. "do you know about biriyani", "recipe for pizza")
        re.compile(
            r"\b(?:biriyani|biryani|food|cooking|cook|recipe|recipes|pizza|burger|sandwich|curry|pasta|"
            r"restaurant|cafe|coffee|tea|dinner|lunch|breakfast|eat|eating|meal|snack|kitchen)\b",
            re.I
        ),
        # Non-business / general trivia / personal chitchat
        re.compile(
            r"\b(?:weather\s+today|temperature\s+outside|football|cricket|fifa|movie|movies|cinema|"
            r"song|music|actor|actress|politics|election|president|prime\s+minister|horoscope|joke|tell\s+me\s+a\s+joke)\b",
            re.I
        ),
    ]

    COMPANY_CAPABILITY_PATTERNS = [
        re.compile(
            r"\b(?:"
            r"do\s+you\s+(?:supplay|supply|sell|carry|provide|deal\s+in|have|stock|distribute)\s+(?:printers?|scanners?|plotters?|hardware|equipment|machines?)|"
            r"are\s+you\s+(?:an?\s+)?(?:authorized|official)?\s*(?:dealer|distributor|reseller|supplier|partner)|"
            r"what\s+(?:printers?|scanners?|equipment|hardware)\s+do\s+you\s+(?:have|sell|supply|deal\s+in)|"
            r"what\s+do\s+you\s+(?:sell|supply|distribute)|"
            r"do\s+you\s+(?:have|sell)\s+epson|"
            r"do\s+you\s+(?:have|sell)\s+citizen|"
            r"give\s+all\s+(?:the\s+)?product\s+list|"
            r"all\s+(?:the\s+)?products?\s+list|"
            r"list\s+all\s+(?:the\s+)?(?:products?|printers?|scanners?)|"
            r"show\s+all\s+(?:products?|printers?|scanners?)"
            r")\b",
            re.I
        ),
    ]

    COMPATIBILITY_PATTERNS = [
        re.compile(r"\b(?:suitable\s+for|compatible\s+with|works?\s+with|fits?\s+(?:on|in|with)?|can\s+i\s+use\s+(?:this|it)\s+(?:on|in|with)|is\s+(?:this|it)\s+for)\b", re.I),
        re.compile(r"\b(?:is\s+[a-z0-9\-]+\s+(?:suitable|compatible|fit|work)\s+(?:for|with|on)\s+[a-z0-9\-]+)\b", re.I),
    ]

    CONSUMABLES_PATTERNS = [
        re.compile(r"\b(?:what\s+inks?|which\s+inks?|consumables?|consubles?|consumbales?|cartridges?|ribbons?|maintenance\s*box(?:es)?|supplies(?:\s+for)?|sublimation\s+inks?|print\s+supplies)\b", re.I),
        re.compile(r"\b(?:(?:what|which|need|want|buy|order|get|looking\s+for|list|show|all|give)\s+(?:all\s+)?(?:some|more|replacement|extra|new|compatible|original|the|these)?\s*(?:350ml|700ml|roll|paper)?\s*(?:ink|inks|cartridge|cartridges|ribbon|ribbons|maintenance\s*box|supplies|paper|media|consumables?|consubles?|consumbales?))\b", re.I),
        re.compile(r"\b(?!(?:our|the|my|this|that|their|its|more|less|high|low|zero|no)\s+)(?:[a-z0-9\-]+\s+(?:ink|inks|cartridge|cartridges|ribbon|ribbons|paper|media|supplies|consumables?|consubles?|consumbales?))\b", re.I),
        re.compile(r"\b(?:ink|inks|cartridge|cartridges|ribbon|ribbons|supplies|paper|media|consumables?|consubles?|consumbales?)\s+(?:for|of)\s+[a-z0-9\-]+\b", re.I),
    ]

    COMPARE_PATTERNS = [
        re.compile(
            r"\b(?:"
            r"compare|campare|compair|comapre|comparison|differences?|difference\s+between|"
            r"which\s+(?:one\s+)?(?:is\s+)?(?:better|best|recommended)|"
            r"which\s+(?:one\s+)?to\s+(?:choose|pick|get|buy)|"
            r"which\s+(?:one\s+)?should\s+i\s+(?:choose|pick|get|buy)|"
            r"what\s+is\s+the\s+difference|"
            r"how\s+do\s+they\s+compare|"
            r"better\s+(?:choice|option)|"
            r"versus|\bvs\b|compare\s+(?:these|them|both|all)|campare\s+these"
            r")\b",
            re.I
        ),
    ]

    ALTERNATIVES_PATTERNS = [
        re.compile(r"\b(?:alternatives?|similar\s+(?:models?|printers?)|other\s+options?|other\s+models?)\b", re.I),
    ]

    PRICE_POLICY_PATTERNS = [
        re.compile(r"\b(?:price|cost|how\s+much|quote|quotation|pricing|discount|rates?|in\s+stock|available\s+in\s+stock|print\s+cost|cost\s+per\s+print|running\s+cost|media\s+cost|investment|intial\s+investment|initial\s+investment|budget)\b", re.I),
    ]

    DISCOUNT_PATTERNS = [
        re.compile(r"\b(?:discounts?|bargain|bargaining|negotiat\w*|best\s*price|price\s*cut|lower\s*(?:the\s*)?price|reduce\s*(?:the\s*)?price|less\s*price|special\s*rate)\b", re.I),
        re.compile(r"\b\d+%\s*(?:off|discount)\b", re.I),
    ]

    CUSTOM_CONFIG_PATTERNS = [
        re.compile(r"\b(?:custom\s*(?:setup|config\w*|installation|solution|spec\w*)|configured\s*with)\b", re.I),
    ]

    QUOTE_PATTERNS = [
        re.compile(r"\b(?:quotation|formal\s*quote|request\s*(?:a\s*)?quote|send\s*(?:me\s*)?(?:a\s*)?quote|need\s*(?:a\s*)?quote|official\s*quote|tax\s*invoice\s*quote)\b", re.I),
    ]

    COMPETITOR_PATTERNS = [
        re.compile(
            r"\b(?:canon|hp\s+designjet|designjet|brother|dnp|dnp\s*rx1|rx1\b|mitsubishi|fujifilm|noritsu|ricoh|xerox|konica|lexmark)\b|"
            r"\b(?:epson\s+(?:vs|versus|over|or)\s+[a-z0-9\-]+|[a-z0-9\-]+\s+(?:vs|versus|over|or)\s+epson)\b|"
            r"\b(?:citizen\s+(?:vs|versus|over|or)\s+[a-z0-9\-]+|[a-z0-9\-]+\s+(?:vs|versus|over|or)\s+citizen)\b",
            re.I
        ),
    ]

    # Attribute-level spec query keywords — triggers PRODUCT_INFO
    SPEC_ATTRIBUTE_PATTERNS = [
        re.compile(
            r"\b(?:specs?|technical\s+specs?|technical\s+specifications?|specifications?|specification|"
            r"details?|features?|functions?|capabilities|print\s+speed|resolution|dpi|dimension|dimensions|"
            r"measurement|measurements|size|how\s+big|weight|how\s+heavy|memory|ram|datasheet|brochure|"
            r"spec\s+sheet|data\s+sheet|pdf|view\s+specs|full\s+specs|product\s*cards?|show\s*(?:the\s*)?card|show\s+product\s+card|"
            r"prints?\s*(?:per|a|\/)\s*day|pages?\s*(?:per|a|\/)\s*day|daily\s*(?:volume|prints?|pages?|capacity)|"
            r"monthly\s*(?:volume|prints?|pages?|capacity|duty)|duty\s*cycle|how\s*many\s*(?:prints?|pages?)|"
            r"consum\w*|ink\s*consum\w*|how\s*much\s*ink|ink\s*usage|cartridge\s*sizes?|cartridge\s*capacit\w*|"
            r"yield|page\s*yield|print\s*yield)\b",
            re.I
        ),
    ]

    SHOWROOM_PATTERNS = [
        re.compile(
            r"\b(?:showroom|store\s*location|physical\s*store|office\s*location|office\s*address|"
            r"where\s+(?:is\s+your|are\s+you|can\s+i\s+visit)|visit\s+(?:your\s+)?(?:showroom|store|office)|"
            r"head\s*office|khalid\s+bin\s+waleed|directions\s+to\s+your|"
            r"working\s*hours|business\s*hours|opening\s*hours|when\s+are\s+you\s+open|open\s+today)\b",
            re.I
        ),
        re.compile(r"\bwhere\b.*?\b(?:licat\w*|locat\w*|compani\w*|company|office|store|shop|showroom|situat\w*|based|address)\b", re.I),
        re.compile(r"\b(?:where\s+is\s+(?:your|the)\s+(?:company|office|store|shop|showroom))\b", re.I),
    ]

    DELIVERY_PATTERNS = [
        re.compile(
            r"\b(?:delivery|deliver|shipping|ship|dispatch|courier|do you deliver|can you deliver|"
            r"delivery service|deliver to|delivering|pickup|pick up|store pickup|return policy|returns?\b|"
            r"refunds?\b|cancel(?:lation)?|cancel order|customs duty|import tax|import duty|tracking|track my order|track order|"
            r"dubai|abu\s*dhabi|sharjah|ajman|al\s*ain|ras\s*al\s*khaimah|fujairah|uae|oman|saudi|qatar|kuwait|bahrain|gcc)\b",
            re.I
        ),
    ]

    CONFUSION_PATTERNS = [
        re.compile(r"\b(?:what (?:are )?you asking|what do you mean|i don'?t understand|previous chat|priviace chat|check (?:the )?chat|check (?:the )?history|what did i say|answer after checking)\b", re.I),
    ]

    FRUSTRATION_PATTERNS = [
        re.compile(
            r"\b(?:"
            r"this is useless|useless|stupid\b|terrible|waste of time|"
            r"i already said|already said|i told you|already told you|listen to me|you are not listening|"
            r"not helpful|awful|talk to a human|human please|agent please|"
            r"what\s+(?:did\s+)?i\s+ask(?:ed)?\s+what\s+(?:are\s+)?you\s+giving|"
            r"what\s+i\s+asked\s+what\s+you\s+giving|"
            r"not\s+what\s+i\s+asked|"
            r"not\s+what\s+i\s+want(?:ed)?|"
            r"why\s+(?:are\s+)?you\s+(?:giving|showing|sending)\s+this|"
            r"wrong\s+answer|wrong\s+information|wrong\s+product|"
            r"you\s+didn'?t\s+answer|didn'?t\s+answer\s+my\s+question|"
            r"what\s+are\s+you\s+talking\s+about|"
            r"did\s+you\s+(?:even\s+)?(?:read|listen|hear)"
            r")\b",
            re.I
        ),
    ]

    OBJECTION_PATTERNS = [
        re.compile(r"\b(?:too expensive|too high|expensive|cannot afford|out of my budget|cheaper|lower cost|less expensive)\b", re.I),
    ]

    HESITATION_PATTERNS = [
        re.compile(r"\b(?:think about it|i'?ll think about it|need to think|not sure yet|maybe later)\b", re.I),
    ]

    GRATITUDE_PATTERNS = [
        re.compile(r"\b(?:shukran|thank you|thanks|thank u|thx|much appreciated|appreciate it)\b", re.I),
    ]

    LEAD_INFO_PATTERNS = [
        re.compile(r"\b(?:my name is|number is|phone is|call me at|reach me at|contact me at)\b", re.I),
        re.compile(r"(?:\+971|00971|0)(?:5[0124568]|4|2|3|6|7|9)\d{7}\b"),
    ]

    @classmethod
    def extract_reference_expressions(cls, text: str) -> List[ReferenceExpression]:
        refs: List[ReferenceExpression] = []
        text_l = text.lower()

        for pat, rtype in cls.REFERENCE_RULES:
            for m in pat.finditer(text):
                matched_str = m.group(0).strip()
                # Determine target type hint
                hint = "unknown"
                if any(k in matched_str.lower() for k in ["ink", "cartridge", "yellow", "cyan", "magenta", "black"]):
                    hint = "consumable"
                elif any(k in matched_str.lower() for k in ["printer", "model"]):
                    hint = "printer"
                elif any(k in matched_str.lower() for k in ["paper", "media", "roll"]):
                    hint = "media"
                elif rtype == "demonstrative" and any(k in text_l for k in ["suitable for", "compatible with", "fit in", "use in"]):
                    # "this is suitable for f500" -> "this" is referencing consumable
                    hint = "consumable"

                refs.append(ReferenceExpression(
                    text=matched_str,
                    reference_type=rtype,
                    target_type_hint=hint,
                    start_idx=m.start(),
                    end_idx=m.end(),
                ))
        return refs

    @classmethod
    def extract_entities(cls, text: str) -> List[EntityMention]:
        entities: List[EntityMention] = []
        seen_keys: Set[str] = set()
        text_l = text.lower()

        alias_map = _get_catalogue_aliases()
        sku_map = _get_known_skus()

        # 1. Exact SKU extraction
        for m in cls.SKU_PATTERN.finditer(text):
            raw_sku = m.group(0).upper().strip()
            sku_info = sku_map.get(raw_sku) or sku_map.get(raw_sku.replace(" ", ""))
            norm_id = sku_info["sku"] if sku_info else raw_sku
            if norm_id not in seen_keys:
                entities.append(EntityMention(
                    surface_text=m.group(0),
                    normalised_id=norm_id,
                    entity_type="sku",
                    match_type="exact",
                    confidence=1.0,
                    metadata=sku_info or {},
                ))
                seen_keys.add(norm_id)

        # 2. Catalogue Model Alias matching (longest matches first)
        # Check against both original text and space-collapsed text (e.g. "p 7500" -> "p7500")
        collapsed_text = re.sub(r"\b([a-z]{1,4})\s+(\d{2,5}[a-z]*)\b", r"\1\2", text_l)
        sorted_aliases = sorted(alias_map.keys(), key=lambda a: len(a), reverse=True)
        for alias in sorted_aliases:
            if len(alias) < 2:
                continue
            # Use word boundaries for aliases to prevent substring collisions
            pattern = rf"\b{re.escape(alias)}\b"
            m = re.search(pattern, text_l) or re.search(pattern, collapsed_text)
            if m:
                norm_pid = alias_map[alias]
                if norm_pid not in seen_keys:
                    is_neg = is_negated_match(text_l, m.start(), m.end())
                    entities.append(EntityMention(
                        surface_text=alias,
                        normalised_id=norm_pid,
                        entity_type="model",
                        match_type="alias",
                        confidence=0.98,
                        metadata={"canonical_id": norm_pid, "is_negated": is_neg},
                    ))
                    seen_keys.add(norm_pid)

        # 3. Model Matching: Exact alias matches only!
        # Near/fuzzy matches never answer as that model; flag as unlisted_model or ambiguous_candidate
        if not any(e.entity_type == "model" for e in entities):
            words = [w for w in re.findall(r"[a-z0-9\-]+", text_l) if len(w) >= 3]
            for word in words:
                if word.isdigit():
                    continue
                candidate_matches = []
                for alias, pid in alias_map.items():
                    if len(alias) >= 3 and abs(len(alias) - len(word)) <= 2:
                        ratio = SequenceMatcher(None, word, alias).ratio()
                        if ratio >= FUZZY_MATCH_THRESHOLD - 0.05:
                            candidate_matches.append((ratio, alias, pid))

                if candidate_matches:
                    candidate_matches.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_alias, best_pid = candidate_matches[0]
                    runner_ups = [c for c in candidate_matches[1:] if c[2] != best_pid and abs(best_score - c[0]) <= 0.15]
                    if runner_ups:
                        all_pids = sorted(list(set([best_pid] + [r[2] for r in runner_ups])))
                        if word.lower() not in seen_keys:
                            entities.append(EntityMention(
                                surface_text=word,
                                normalised_id=word.lower(),
                                entity_type="unlisted_model",
                                match_type="ambiguous_candidate",
                                confidence=0.60,
                                metadata={"ambiguous_candidates": all_pids, "similarity": best_score},
                            ))
                            seen_keys.add(word.lower())
                    elif best_score >= FUZZY_MATCH_THRESHOLD:
                        norm_pid = alias_map[best_alias]
                        if word.lower() not in seen_keys:
                            entities.append(EntityMention(
                                surface_text=word,
                                normalised_id=word.lower(),
                                entity_type="unlisted_model",
                                match_type="near_match",
                                confidence=round(best_score, 3),
                                metadata={"matched_alias": best_alias, "candidate_id": norm_pid, "similarity": best_score},
                            ))
                            seen_keys.add(word.lower())

        # 3b. Detect any unlisted model-code patterns (e.g. wf-c20600, t5200) not in approved catalogue
        if not any(e.entity_type in ("model", "unlisted_model") for e in entities):
            STOP_PREFIXES = {"is", "my", "no", "at", "in", "on", "to", "by", "or", "am", "pm", "if", "do", "so", "up", "me", "us", "we", "he", "it", "and", "the", "for"}
            phone_scrubbed = re.sub(r"(?:\+971|00971|0)(?:5[0124568]|4|2|3|6|7|9)\d{7}\b", " ", text_l)

            for mc in re.finditer(r"\b([a-z]{1,4}[-_]?[a-z]?\d{2,5}[a-z0-9\-_]*)\b", phone_scrubbed):
                raw_code = mc.group(1).strip()
                clean_code = raw_code.lower()
                prefix_word = re.split(r"[-_0-9]", clean_code)[0]
                if prefix_word in STOP_PREFIXES:
                    continue
                if clean_code not in seen_keys and len(clean_code) >= 3 and clean_code not in ["page", "pages", "day", "days"]:
                    is_neg = is_negated_match(text_l, mc.start(), mc.end())
                    if clean_code in alias_map:
                        norm_pid = alias_map[clean_code]
                        entities.append(EntityMention(
                            surface_text=raw_code,
                            normalised_id=norm_pid,
                            entity_type="model",
                            match_type="alias",
                            confidence=1.0,
                            metadata={"canonical_id": norm_pid, "is_negated": is_neg},
                        ))
                        seen_keys.add(norm_pid)
                    else:
                        entities.append(EntityMention(
                            surface_text=raw_code,
                            normalised_id=clean_code,
                            entity_type="unlisted_model",
                            match_type="unlisted",
                            confidence=0.9,
                            metadata={"raw_query": raw_code},
                        ))
                        seen_keys.add(clean_code)

        # 4. Category Mentions (Matching Page 1 Flowchart Overview)
        # Specific application domains are evaluated first so specific requirements take precedence
        categories = {
            "technical_cad": [
                "cad", "technical cad", "technical drawing", "technical drawings", "engineering", "blueprints", "line drawings", "architectural",
                "architect", "archtect", "architecture", "drawing", "drawings", "architect drawings",
                "gis", "cad plotter", "cad plotters", "blueprint", "plotter", "plotters", "large format plotter",
                "large format plotters", "technical plotter", "technical plotters", "technical printer", "technical printers",
                "مخططات", "طابعة مخططات", "طابعة كاد", "طابعة هندسية", "بلوتر", "بلاتر", "رسومات هندسية", "naksha"
            ],
            "photo_fine_art": [
                "fine art", "photo printer", "photo printers", "gallery", "photography", "photo printing", "photo studio",
                "photo machine", "photo machines", "master studio", "spectro", "pro10", "pro12", "fine art gallery",
                "photography printer", "photography printers", "fine art printer", "fine art printers",
                "فوتوغرافية", "طابعة فوتوغرافية", "طابعة صور", "طباعة فوتوغرافية", "طباعة صور", "طابعات صور", "طابعات فوتوغرافية", "صور احترافية", "tasveer"
            ],
            "citizen_photo": [
                "photo booth", "photo booth printer", "photo booth printers", "event photography", "event photo", "event photos",
                "event photo printer", "event photo printers", "instant prints", "passport photos",
                "citizen", "citizon", "citzen", "ciyizon", "ctizen", "citizn",
                "citizen printer", "citizen printers", "citizon printer", "ciyizon printer", "instant photo", "instant photo printer", "instant photo printers", "dye-sub photo", "cz-01", "cx-02", "cy-02", "cx-02w",
                "طابعة كشك صور", "طابعة كشك", "طابعة مناسبات", "سيتيزن", "طابعة حفلات"
            ],
            "dye_sublimation": [
                "dye sublimation", "sublimation", "sublimation printer", "sublimation printers", "apparel printing",
                "t-shirt printing", "textile printing", "mug printing", "sportswear printing",
                "apparel", "t-shirt", "mug",
                "طابعة تسامي", "سبلميشن", "طباعة أقمشة", "طباعة تيشرتات"
            ],
            "scanners": [
                "scanner", "scanners", "document scanner", "document scanners", "sheetfed", "flatbed scanner", "flatbed scanners",
                "film scanner", "large format scanner", "book scanner", "scanning solutions",
                "expression 12000xl", "workforce ds",
                "ماسح ضوئي", "سكانر", "ماسحات ضوئية"
            ],
            "office_workforce": [
                "office printer", "office printers", "workforce", "business printer", "business printers", "printer for my office",
                "printer for office", "printers for office", "for my office", "for our office", "office use",
                "office printing", "office copier", "office copiers", "enterprise mfp", "enterprise mfps", "am-c", "wf-c",
                "office multifunction", "office enterprise", "enterprise", "enterprise printer", "enterprise printers",
                "line-head", "line head", "line-head enterprise", "office mfp", "office mfps", "business mfp",
                "pages daily", "pages per day", "pages/day", "pages a day",
                "طابعة مكتبية", "طابعات مكتبية", "طابعة للمكتب", "مكتبية", "daftar"
            ],
        }
        has_specific_app_match = any(e.entity_type == "category" and e.normalised_id != "category:office_workforce" for e in entities)
        for cat_id, cat_keywords in categories.items():
            if cat_id == "scanners":
                if re.search(r"\b(?:no|without|dont\s+need|don't\s+need|not\s+needed)\s+(?:a\s+)?(?:scanner|scan|scanning)\b", text_l):
                    continue
                if any(w in text_l for w in ["print only", "print-only"]):
                    continue
            elif cat_id == "photo_fine_art":
                if any(w in text_l for w in ["scanner", "scanners", "scanning"]) and not any(p in text_l for p in ["printer", "printers", "plotter"]):
                    continue
            elif cat_id == "office_workforce":
                # Prepositional location phrases (e.g. "for my office") should not trigger office_workforce
                # when a specific printer type is already mentioned, but explicit product needs like
                # "office printer", "office copiers", "office use", "workforce" MUST be preserved!
                if has_specific_app_match or any(k in text_l for k in ["photo", "fine art", "cad", "blueprint", "plotter", "sublimation", "citizen"]):
                    prepositional_exclusions = {
                        "printer for my office", "printer for office", "printers for office",
                        "for my office", "for our office", "for the office", "in the office", "for office"
                    }
                    cat_keywords = [k for k in cat_keywords if k not in prepositional_exclusions]
            for kw in cat_keywords:
                m = re.search(rf"(?:^|\b){re.escape(kw)}(?:\b|$)", text_l)
                if m:
                    is_neg = is_negated_match(text_l, m.start())
                    entities.append(EntityMention(
                        surface_text=kw,
                        normalised_id=f"category:{cat_id}",
                        entity_type="category",
                        match_type="exact",
                        confidence=0.95,
                        metadata={"is_negated": is_neg},
                    ))
                    break

        return entities

    @classmethod
    def extract_slots(cls, text: str, entities: List[EntityMention]) -> Dict[str, SlotValue]:
        slots: Dict[str, SlotValue] = {}
        text_l = text.lower()
        excluded: Dict[str, Any] = {}

        # Category slot
        CATEGORY_PRIORITY = {
            "photo_fine_art": 1,
            "citizen_photo": 2,
            "technical_cad": 3,
            "dye_sublimation": 4,
            "scanners": 5,
            "office_workforce": 6,
        }
        cats_pos = [e.normalised_id.replace("category:", "") for e in entities if e.entity_type == "category" and not (e.metadata and e.metadata.get("is_negated"))]
        cats_neg = [e.normalised_id.replace("category:", "") for e in entities if e.entity_type == "category" and (e.metadata and e.metadata.get("is_negated"))]
        if cats_neg:
            excluded["target_category"] = cats_neg[0] if len(cats_neg) == 1 else cats_neg
        if cats_pos:
            cats_sorted = sorted(cats_pos, key=lambda c: CATEGORY_PRIORITY.get(c, 99))
            slots["target_category"] = SlotValue(
                slot_name="target_category",
                value=cats_sorted[0],
                confidence=0.95,
                source="said_now"
            )

        # Target model slot
        models_pos = [e.normalised_id for e in entities if e.entity_type == "model" and not (e.metadata and e.metadata.get("is_negated"))]
        models_neg = [e.normalised_id for e in entities if e.entity_type == "model" and (e.metadata and e.metadata.get("is_negated"))]
        if models_neg:
            excluded["target_model"] = models_neg[0] if len(models_neg) == 1 else models_neg
        if models_pos:
            slots["target_model"] = SlotValue(
                slot_name="target_model",
                value=models_pos[0],
                confidence=0.95,
                source="said_now"
            )
            if len(models_pos) > 1:
                slots["comparison_models"] = SlotValue(
                    slot_name="comparison_models",
                    value=models_pos,
                    confidence=0.95,
                    source="said_now"
                )

        # Target SKU slot
        skus_pos = [e.normalised_id for e in entities if e.entity_type == "sku" and not (e.metadata and e.metadata.get("is_negated"))]
        skus_neg = [e.normalised_id for e in entities if e.entity_type == "sku" and (e.metadata and e.metadata.get("is_negated"))]
        if skus_neg:
            excluded["target_sku"] = skus_neg[0] if len(skus_neg) == 1 else skus_neg
        if skus_pos:
            slots["target_sku"] = SlotValue(
                slot_name="target_sku",
                value=skus_pos[0],
                confidence=1.0,
                source="said_now"
            )

        # Size slot (e.g. 24 inch, 36 inch, 44 inch, a4, a3, 4x6, 5x7, 6x8, 8x10)
        size_matches = list(re.finditer(r"\b(24\s*inch|36\s*inch|44\s*inch|a4|a3\+?|4x6|5x7|6x8|8x10)\b", text_l))
        pos_sizes = []
        for sm in size_matches:
            val = sm.group(1).replace(" ", "")
            if is_negated_match(text_l, sm.start(), sm.end()):
                excluded["media_size"] = val
            else:
                pos_sizes.append(val)
        if pos_sizes:
            slots["media_size"] = SlotValue(
                slot_name="media_size",
                value=pos_sizes[0],
                confidence=0.90,
                source="said_now"
            )

        # Target attribute slot (for specific spec inquiries)
        target_attr = None
        has_volume = bool(re.search(r"\b(?:prints?\s*(?:per|a|\/)\s*day|pages?\s*(?:per|a|\/)\s*day|daily\s*(?:volume|prints?|pages?|capacity)|duty\s*cycle|how\s*many\s*(?:prints?|pages?)|monthly\s*(?:volume|duty))\b", text_l))
        has_consume = bool(re.search(r"\b(?:consum\w*|ink\s*consum\w*|how\s*much\s*ink|ink\s*usage|cartridge\s*capacit\w*|yield)\b", text_l))
        if has_volume and has_consume:
            target_attr = "volume_and_ink_consumption"
        elif has_volume:
            target_attr = "duty_cycle"
        elif has_consume:
            target_attr = "ink_consumption"
        elif any(k in text_l for k in ["stand", "legs", "floor stand", "with a stand", "without stand"]):
            target_attr = "stand"
            m_stand = re.search(r"\b(?:stand|legs)\b", text_l)
            if m_stand and is_negated_match(text_l, m_stand.start(), m_stand.end()):
                excluded["stand"] = True
                excluded["target_attribute"] = "stand"
        elif any(k in text_l for k in ["speed", "ppm", "fast", "how long to print"]):
            target_attr = "print_speed"
        elif any(k in text_l for k in ["dpi", "resolution", "clarity"]):
            target_attr = "dpi"
        elif any(k in text_l for k in ["width", "max width", "print width", "paper size"]):
            target_attr = "print_width"
        elif any(k in text_l for k in ["connectivity", "wifi", "wi-fi", "ethernet", "usb", "network", "wireless"]):
            target_attr = "connectivity"
            m_conn = re.search(r"\b(?:connectivity|wifi|wi-fi|ethernet|usb|network|wireless)\b", text_l)
            if m_conn and is_negated_match(text_l, m_conn.start(), m_conn.end()):
                excluded["connectivity"] = True
                excluded["target_attribute"] = "connectivity"
        elif any(k in text_l for k in ["dimension", "dimensions", "size", "height"]):
            target_attr = "dimensions"
        elif any(k in text_l for k in ["weight", "heavy", "kg"]):
            target_attr = "weight"
        elif any(k in text_l for k in ["scanner", "scan", "copy", "mfp"]):
            target_attr = "scanner_integrated"
            m_scan = re.search(r"\b(?:scanner|scan)\b", text_l)
            if m_scan and is_negated_match(text_l, m_scan.start(), m_scan.end()):
                excluded["scanner"] = True
                excluded["target_attribute"] = "scanner_integrated"
        elif any(k in text_l for k in ["dual roll", "dual-roll"]):
            target_attr = "dual_roll"
        elif any(k in text_l for k in ["warranty", "guarantee"]):
            target_attr = "warranty"
        elif any(k in text_l for k in ["memory", "ram", "storage", "ssd"]):
            target_attr = "memory"
        elif any(k in text_l for k in ["ink", "inks", "colours", "colors", "cartridge"]):
            target_attr = "total_colours"

        if target_attr:
            slots["target_attribute"] = SlotValue(
                slot_name="target_attribute",
                value=target_attr,
                confidence=0.95,
                source="said_now"
            )

        # Quote quantity slot (e.g. 5 units, 10 pcs, 2 printers)
        qty_match = re.search(r"\b(\d+)\s*(?:units?|pcs?|pieces?|printers?|machines?|scanners?|items?|qty)\b", text_l) or re.search(r"\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b", text_l)
        if qty_match:
            qty_val = int(qty_match.group(1) or qty_match.group(2))
            slots["quote_quantity"] = SlotValue(
                slot_name="quote_quantity",
                value=qty_val,
                confidence=0.95,
                source="said_now"
            )

        # Quote product slot
        if models_pos:
            slots["quote_product"] = SlotValue(
                slot_name="quote_product",
                value=models_pos[0],
                confidence=0.95,
                source="said_now"
            )
        elif cats_pos:
            cats_sorted = sorted(cats_pos, key=lambda c: CATEGORY_PRIORITY.get(c, 99))
            slots["quote_product"] = SlotValue(
                slot_name="quote_product",
                value=cats_sorted[0],
                confidence=0.90,
                source="said_now"
            )

        # Primary concern slot (problem discovery: running_cost, print_speed, colour_quality, reliability, paper_size, portability, ease_of_use)
        concern = None
        if re.search(r"\b(?:(?:ink|toner|cartridge|running|consumable|print)\s*costs?|costs?\s*(?:are|is)?\s*(?:killing\s*us|too\s*high)|costing\s*a\s*fortune|expensive\s*ink|cheaper\s*prints?|per\s*print\s*cost|cost\s*per\s*print|cost\s*per\s*page|running\s*costs?|operational\s*costs?)\b", text_l):
            concern = "running_cost"
        elif re.search(r"\b(?:print\s*speed|speed|fast|faster|slow|too\s*slow|ppm|quick\s*turnaround)\b", text_l):
            concern = "print_speed"
        elif re.search(r"\b(?:colour\s*quality|color\s*quality|print\s*quality|fine\s*art|accurate\s*colou?r|pantone|resolution|clarity|vibrant)\b", text_l):
            concern = "colour_quality"
        elif re.search(r"\b(?:reliab\w*|break\s*down|jam|jamming|downtime|maintenance|heavy\s*duty|duty\s*cycle)\b", text_l):
            concern = "reliability"
        elif re.search(r"\b(?:paper\s*size|media\s*size|large\s*format|wide\s*format|wide|24\s*inch|36\s*inch|44\s*inch|a3\b|a0\b|a1\b)\b", text_l):
            concern = "paper_size"
        elif re.search(r"\b(?:portable|portability|compact|lightweight|light|mobile|booth|kiosk|transport)\b", text_l):
            concern = "portability"
        elif re.search(r"\b(?:easy\s*to\s*use|ease\s*of\s*use|simple|touchscreen|user\s*friendly|plug\s*and\s*play)\b", text_l):
            concern = "ease_of_use"

        if concern:
            slots["primary_concern"] = SlotValue(
                slot_name="primary_concern",
                value=concern,
                confidence=0.95,
                source="said_now"
            )

        # Budget extraction (budget_ceiling, budget_floor, budget_scope)
        from conversation.numeric_parse import extract_budget
        b_res = extract_budget(text)
        if b_res:
            if b_res.budget_ceiling is not None:
                slots["budget_ceiling"] = SlotValue(
                    slot_name="budget_ceiling",
                    value=b_res.budget_ceiling,
                    confidence=0.95,
                    source="said_now"
                )
            if b_res.budget_floor is not None:
                slots["budget_floor"] = SlotValue(
                    slot_name="budget_floor",
                    value=b_res.budget_floor,
                    confidence=0.95,
                    source="said_now"
                )
            if b_res.budget_scope is not None:
                slots["budget_scope"] = SlotValue(
                    slot_name="budget_scope",
                    value=b_res.budget_scope,
                    confidence=0.90,
                    source="said_now"
                )

        if excluded:
            slots["excluded"] = SlotValue(
                slot_name="excluded",
                value=excluded,
                confidence=0.95,
                source="said_now"
            )
            for k, v in excluded.items():
                slots[f"excluded.{k}"] = SlotValue(
                    slot_name=f"excluded.{k}",
                    value=v,
                    confidence=0.95,
                    source="said_now"
                )

        return slots

    @classmethod
    def classify_dialogue_act_and_intent(
        cls, text: str, entities: List[EntityMention], refs: List[ReferenceExpression]
    ) -> Tuple[DialogueAct, Intent, float, List[str]]:
        text_l = text.lower().strip()
        ambiguities: List[str] = []

        # Degenerate: Empty, whitespace-only, or emoji-only
        if not text_l or not re.search(r"[\w\d]", text_l):
            return DialogueAct.CHITCHAT, Intent.OTHER, 0.20, ["empty_or_emoji_input"]

        # Degenerate bare numbers (e.g. "24", "12", "5") with no units or context
        text_clean = text_l.replace("”", '"').replace("“", '"').replace("″", '"').replace("’", "'").replace("‘", "'")
        if re.match(r"^\s*\d+\s*$", text_clean):
            return DialogueAct.ANSWER_TO_MY_QUESTION, Intent.OTHER, 0.40, ["bare_number_no_context"]

        # Check for model ambiguities from entities
        for e in entities:
            if e.match_type == "ambiguous_candidate" and e.metadata and "ambiguous_candidates" in e.metadata:
                cand_str = "|".join(e.metadata["ambiguous_candidates"])
                ambiguities.append(f"model:{cand_str}")

        # Multiple categories ambiguity
        cat_entities = [e for e in entities if e.entity_type == "category" and not (e.metadata and e.metadata.get("is_negated"))]
        if len(set(e.normalised_id for e in cat_entities)) > 1:
            ambiguities.append("multiple_categories")

        # 0. Numeric, dimension, or flowchart answer (e.g. "40 ppm", "44\"", "44”", "44” wider", "44” wide production printer", "looking for fine art printer", "< 100", "300+")
        flow_patterns = [
            r"^\s*(?:i\s*(?:need|want)\s*(?:to\s*print\s*)?)?[<>]?\s*\d+(?:[–\-]\d+)?\s*(?:[\"”″'’]|inch|in|ppm|pages?|prints?|docs?|sheets?|mm|cm|wide|wider|width|production|mfp|roll|sheet|desktop|kiosk|daily|\/day|per\s*day|\+)(?:\s+(?:wider|wide|production|printer|plotter|scanner|mfp|roll|sheets?))*\s*$",
            r"^\s*(?:fine\s*art|photo\s*printer|photo\s*production|production\s*printer|large\s*format|cad\s*plotter|technical\s*cad|dye[\s-]*sub|photo\s*booth|office\s*printer)\s*$",
            r"^\s*(?:looking\s+for|i\s+need|i\s+want)\s+(?:a\s+)?(?:fine\s*art|photo|cad|office|large\s*format|production)\s*(?:printer|plotter)?\s*$",
        ]
        if any(re.search(pat, text_clean) for pat in flow_patterns):
            return DialogueAct.QUESTION, Intent.RECOMMEND, 0.96, ambiguities

        # 1. Handoff request
        if any(p.search(text_l) for p in cls.HANDOFF_PATTERNS):
            return DialogueAct.HANDOFF_REQUEST, Intent.CONTACT_SHOWROOM, 0.99, ambiguities

        # 2. Out of scope (food, general trivia, personal chat, unapproved brands)
        if any(p.search(text_l) for p in cls.OUT_OF_SCOPE_PATTERNS):
            return DialogueAct.OUT_OF_SCOPE, Intent.OTHER, 0.99, ambiguities

        # 2b. Confusion or complaint / frustration about conversation
        if any(p.search(text_l) for p in cls.FRUSTRATION_PATTERNS) or any(p.search(text_l) for p in cls.CONFUSION_PATTERNS):
            return DialogueAct.COMPLAINT, Intent.OTHER, 0.99, ambiguities

        # 2bb. Company capability / authorized dealership / catalogue overview
        has_models_or_skus = any(e.entity_type in ("model", "sku") for e in entities)
        if any(p.search(text_l) for p in cls.COMPANY_CAPABILITY_PATTERNS) and not has_models_or_skus:
            return DialogueAct.QUESTION, Intent.OTHER, 0.98, ["company_capability"]

        # 2c. Price objection
        if any(p.search(text_l) for p in cls.OBJECTION_PATTERNS):
            return DialogueAct.CORRECTION, Intent.AVAILABILITY_OR_PRICE_POLICY, 0.95, ambiguities

        # 2d. Hesitation / thinking about it
        if any(p.search(text_l) for p in cls.HESITATION_PATTERNS):
            return DialogueAct.REJECTION, Intent.OTHER, 0.95, ambiguities

        # 2e. Gratitude
        if any(p.search(text_l) for p in cls.GRATITUDE_PATTERNS) and len(text_l.split()) <= 3:
            return DialogueAct.CHITCHAT, Intent.OTHER, 0.98, ambiguities

        # 2f. Lead info capture
        if any(p.search(text_l) for p in cls.LEAD_INFO_PATTERNS):
            return DialogueAct.ANSWER_TO_MY_QUESTION, Intent.CONTACT_SHOWROOM, 0.98, ambiguities

        # 3. Corrections
        if any(p.search(text_l) for p in cls.CORRECTION_PATTERNS):
            return DialogueAct.CORRECTION, Intent.OTHER, 0.90, ambiguities

        # 4. Confirmation (only if not accompanied by a price query, spec question, or model mention)
        has_substantive_query = (
            any(p.search(text_l) for p in cls.PRICE_POLICY_PATTERNS)
            or any(p.search(text_l) for p in cls.SPEC_ATTRIBUTE_PATTERNS)
            or any(p.search(text_l) for p in cls.COMPATIBILITY_PATTERNS)
            or any(p.search(text_l) for p in cls.CONSUMABLES_PATTERNS)
            or any(p.search(text_l) for p in cls.COMPARE_PATTERNS)
            or any(e.entity_type in ("model", "sku") for e in entities)
        )
        if any(p.search(text_l) for p in cls.CONFIRMATION_PATTERNS) and not has_substantive_query:
            return DialogueAct.CONFIRMATION, Intent.OTHER, 0.95, ambiguities

        # 5. Rejection
        if any(p.search(text_l) for p in cls.REJECTION_PATTERNS):
            return DialogueAct.REJECTION, Intent.OTHER, 0.95, ambiguities

        # 6. Compatibility check (e.g. "this is suitable for f500", "is c13t49n400 suitable for f500")
        is_compatibility = any(p.search(text_l) for p in cls.COMPATIBILITY_PATTERNS)
        if is_compatibility:
            act = DialogueAct.REFERENCE_FOLLOW_UP if refs else DialogueAct.QUESTION
            return act, Intent.COMPATIBILITY_CHECK, 0.96, ambiguities

        # 7. Consumables lookup ("what inks does f500 use", "cartridges for sc-t3100")
        is_hardware_req = any(
            re.search(p, text_l) for p in [
                r"\b(?:need|want|looking for|buy|recommend|suggest)\s+(?:an?\s+)?(?:office\s+)?(?:printer|plotter|scanner|copier|mfp)\b",
                r"\b(?:printer|plotter|scanner)\s+for\b",
            ]
        )
        is_volume_or_consumption_query = bool(re.search(
            r"\b(?:"
            r"consum\w*|usage|yield|prints?\s*(?:per|a|\/)\s*day|pages?\s*(?:per|a|\/)\s*day|"
            r"daily\s*(?:prints?|pages?|volume|capacity)|monthly\s*(?:prints?|pages?|volume|capacity|duty)|"
            r"duty\s*cycle|how\s*many\s*(?:prints?|pages?)|how\s*much\s*ink"
            r")\b",
            text_l
        ))
        if any(p.search(text_l) for p in cls.CONSUMABLES_PATTERNS) and not is_hardware_req and not is_volume_or_consumption_query:
            act = DialogueAct.REFERENCE_FOLLOW_UP if refs else DialogueAct.QUESTION
            return act, Intent.CONSUMABLES_LOOKUP, 0.95, ambiguities

        # 8. Models and SKUs
        models = [e for e in entities if e.entity_type == "model"]
        skus = [e for e in entities if e.entity_type == "sku"]

        # Compare (requires explicit comparison wording)
        if any(p.search(text_l) for p in cls.COMPARE_PATTERNS):
            return DialogueAct.QUESTION, Intent.COMPARE, 0.92, ambiguities

        # Custom config / setup inquiry (e.g. "Send me a quotation for 5 units with custom setup")
        if any(p.search(text_l) for p in cls.CUSTOM_CONFIG_PATTERNS):
            return DialogueAct.QUESTION, Intent.CUSTOM_CONFIG_REQUEST, 0.96, ambiguities

        # Discount inquiry (e.g. "Can you give me 20% discount?", "any discounts?")
        if any(p.search(text_l) for p in cls.DISCOUNT_PATTERNS):
            return DialogueAct.QUESTION, Intent.DISCOUNT_REQUEST, 0.96, ambiguities

        # Formal Quotation request (e.g. "send me a quotation", "request official quote")
        if any(p.search(text_l) for p in cls.QUOTE_PATTERNS):
            return DialogueAct.QUESTION, Intent.QUOTE_REQUEST, 0.96, ambiguities

        # Competitor Mention (e.g. "Why choose Epson over Canon?", "Epson vs HP DesignJet", "DNP RX1")
        if any(p.search(text_l) for p in cls.COMPETITOR_PATTERNS):
            return DialogueAct.QUESTION, Intent.COMPETITOR_MENTION, 0.95, ambiguities

        # 8a. Specific model + price/print-cost query → direct AVAILABILITY_OR_PRICE_POLICY
        #     Prevents flowchart routing when customer asks "what is the price of Citizen CZ-01?"
        has_explicit_price = any(k in text_l for k in [
            "price", "cost", "how much", "quote", "quotation", "pricing", "rate", "discount",
            "print cost", "cost per print", "running cost", "media cost"
        ])
        if (models or skus) and has_explicit_price:
            return DialogueAct.QUESTION, Intent.AVAILABILITY_OR_PRICE_POLICY, 0.95, ambiguities

        # 8b. Spec/datasheet attribute query → direct PRODUCT_INFO
        #     Applies both with explicit model or implicitly referring to active focus
        has_spec_query = any(p.search(text_l) for p in cls.SPEC_ATTRIBUTE_PATTERNS)
        if has_spec_query:
            return DialogueAct.QUESTION, Intent.PRODUCT_INFO, 0.96, ambiguities

        # 8c. Consumable/ink pack chip clicks and inquiries
        if any(k in text_l for k in ["replaceable ink packs", "rips high yield", "ink packs", "consumable cards", "view compatible printers"]):
            return DialogueAct.QUESTION, Intent.CONSUMABLES_LOOKUP, 0.96, ambiguities

        # 8d. Quotation chip clicks
        if any(k in text_l for k in ["official quotation", "request official quote", "request quotation"]):
            return DialogueAct.QUESTION, Intent.AVAILABILITY_OR_PRICE_POLICY, 0.96, ambiguities

        # 9. Alternatives
        if any(p.search(text_l) for p in cls.ALTERNATIVES_PATTERNS):
            act = DialogueAct.REFERENCE_FOLLOW_UP if refs else DialogueAct.QUESTION
            return act, Intent.ALTERNATIVES, 0.92, ambiguities

        # 10. Delivery & Shipping policy inquiry (check before general availability)
        if any(p.search(text_l) for p in cls.DELIVERY_PATTERNS) and not has_explicit_price:
            return DialogueAct.QUESTION, Intent.SHIPPING_OR_DELIVERY, 0.96, ambiguities

        # 10b. Availability or Pricing Policy
        if any(p.search(text_l) for p in cls.PRICE_POLICY_PATTERNS):
            return DialogueAct.QUESTION, Intent.AVAILABILITY_OR_PRICE_POLICY, 0.90, ambiguities

        # 11. Contact showroom (only if not an equipment or category inquiry)
        is_equipment_query = any(k in text_l for k in [
            "printer", "scanner", "plotter", "copier", "equipment", "machine", "device",
            "ink", "cartridge", "consumable", "media", "paper", "roll", "toner"
        ])
        if not is_equipment_query and any(p.search(text_l) for p in cls.SHOWROOM_PATTERNS):
            return DialogueAct.QUESTION, Intent.CONTACT_SHOWROOM, 0.95, ambiguities

        # 12. Category Mentions without specific model -> RECOMMEND intent
        category_entities = [e for e in entities if e.entity_type == "category"]
        if category_entities and not models and not skus:
            return DialogueAct.QUESTION, Intent.RECOMMEND, 0.92, ambiguities

        # 13. Ellipsis or Reference Follow-up
        if any(r.reference_type == "ellipsis" for r in refs):
            return DialogueAct.REFERENCE_FOLLOW_UP, Intent.PRODUCT_INFO, 0.88, ambiguities

        if refs and not entities:
            return DialogueAct.REFERENCE_FOLLOW_UP, Intent.PRODUCT_INFO, 0.85, ambiguities

        # 13b. Flowchart specification responses (e.g. 'A4 Output', 'Under 100 pages/day', '24-inch (A1)')
        is_explicit_info_query = any(k in text_l for k in ["spec", "datasheet", "details", "feature", "tell me about", "what is", "overview of"])
        if not is_explicit_info_query:
            from conversation.product_flows import extract_flowchart_requirements
            flow_reqs = extract_flowchart_requirements(text_l)
            if flow_reqs:
                return DialogueAct.QUESTION, Intent.RECOMMEND, 0.95, ambiguities

        # 14. Product Info if SKU or model is mentioned
        skus = [e for e in entities if e.entity_type == "sku"]
        if skus:
            return DialogueAct.QUESTION, Intent.PRODUCT_INFO, 0.95, ambiguities

        if models:
            return DialogueAct.QUESTION, Intent.PRODUCT_INFO, 0.90, ambiguities

        # 15. Recommendation query
        if any(w in text_l for w in ["need", "want", "looking for", "recommend", "best", "which"]):
            return DialogueAct.QUESTION, Intent.RECOMMEND, 0.80, ambiguities

        # 16. Short inquiry or clarification prompts ("what", "what?", "tell me", "show me", "explain")
        if text_l in ("what", "what?", "tell me", "show me", "what is it", "what's that", "whats that", "explain"):
            return DialogueAct.QUESTION, Intent.PRODUCT_INFO, 0.90, ambiguities

        # Fallback chitchat / greetings
        if re.search(r"\b(?:hello|hi|hey|good\s*morning|good\s*afternoon|good\s*evening)\b", text_l):
            if len(text_l.split()) <= 3:
                return DialogueAct.CHITCHAT, Intent.OTHER, 0.95, ambiguities

        return DialogueAct.QUESTION, Intent.OTHER, 0.60, ["Ambiguous intent, deterministic confidence below 0.70"]

    @classmethod
    def extract_compound_intents(cls, text: str, primary_intent: Intent) -> List[Intent]:
        """Detects compound ordered intents in complex multi-intent inquiries."""
        text_l = text.lower().strip()
        matched: List[Tuple[int, Intent]] = []

        # Check Price Policy
        for p in cls.PRICE_POLICY_PATTERNS:
            m = p.search(text_l)
            if m:
                matched.append((m.start(), Intent.AVAILABILITY_OR_PRICE_POLICY))
                break

        # Check Delivery
        for p in cls.DELIVERY_PATTERNS:
            m = p.search(text_l)
            if m:
                matched.append((m.start(), Intent.SHIPPING_OR_DELIVERY))
                break

        # Check Specs / Speed
        m_spec = re.search(r"\b(?:how fast|speed|ppm|resolution|dpi|print width|specs?|features?|stand)\b", text_l)
        if m_spec:
            matched.append((m_spec.start(), Intent.PRODUCT_INFO))

        # Check Compatibility
        for p in cls.COMPATIBILITY_PATTERNS:
            m = p.search(text_l)
            if m:
                matched.append((m.start(), Intent.COMPATIBILITY_CHECK))
                break

        # Check Consumables
        for p in cls.CONSUMABLES_PATTERNS:
            m = p.search(text_l)
            if m:
                matched.append((m.start(), Intent.CONSUMABLES_LOOKUP))
                break

        if len(matched) > 1:
            # Sort by order of appearance in customer text
            matched.sort(key=lambda x: x[0])
            ordered_intents: List[Intent] = []
            for _, i in matched:
                if i not in ordered_intents:
                    ordered_intents.append(i)
            return ordered_intents

        return []

    @classmethod
    def extract_buyer_pace(cls, text: str) -> str:
        """
        Determines buyer pace: 'concise' | 'standard' | 'technical'
        based on message length, impatience words (quick, fast, urgent, asap),
        and technical tokens (dpi, duty cycle, ISO, picoliter, interface).
        """
        text_l = text.lower().strip()
        words = text_l.split()

        # 1. Technical tokens
        tech_pattern = re.compile(
            r"\b(?:dpi|dots\s+per\s+inch|duty\s*cycle|iso\b|iso/iec|picoliter|picolitre|picoliters|pl\b|interface|interfaces|ethernet|usb\s*3|postscript|esc/p|precisioncore|printhead|nozzle|nozzles|gm/m2|gsm)\b",
            re.I
        )
        if tech_pattern.search(text_l):
            return "technical"

        # 2. Impatience tokens / short query
        impatience_pattern = re.compile(
            r"\b(?:quick|quickly|fast|urgent|urgently|asap|brief|briefly|short|no fluff|straight to the point|one word)\b",
            re.I
        )
        if impatience_pattern.search(text_l) or (len(words) <= 3 and any(w in text_l for w in ["price?", "cost?", "how much?", "specs?"])):
            return "concise"

        return "standard"

    @classmethod
    def parse(cls, text: str) -> TurnUnderstanding:
        """Runs the deterministic extractor pipeline."""
        t_start = time.time()
        entities = cls.extract_entities(text)
        refs = cls.extract_reference_expressions(text)
        slots = cls.extract_slots(text, entities)
        dialogue_act, intent, confidence, ambiguities = cls.classify_dialogue_act_and_intent(text, entities, refs)
        compound_intents = cls.extract_compound_intents(text, intent)
        buyer_pace = cls.extract_buyer_pace(text)
        slots["buyer_pace"] = SlotValue(
            slot_name="buyer_pace",
            value=buyer_pace,
            confidence=0.95,
            source="said_now"
        )
        duration_ms = int((time.time() - t_start) * 1000)

        # Fix 3: Evidence-based confidence calibration & penalties
        penalties = 0.0
        if len(ambiguities) > 0:
            penalties += 0.20
        if len(compound_intents) > 1:
            penalties += 0.15
        if re.search(r"\b(?:not|dont|don't|never|forget|no)\b", text.lower()):
            penalties += 0.10
        if text.count("?") >= 2 or " and " in text.lower():
            penalties += 0.10

        calibrated_confidence = max(0.10, round(confidence - penalties, 2))

        return TurnUnderstanding(
            raw_text=text,
            dialogue_act=dialogue_act,
            intent=intent,
            secondary_intents=compound_intents,
            entities=entities,
            reference_expressions=refs,
            slots=slots,
            overall_confidence=calibrated_confidence,
            ambiguities=ambiguities,
            buyer_pace=buyer_pace,
            is_deterministic=True,
            used_llm=False,
            latency_ms=duration_ms,
        )


# ── Constrained Small LLM Fallback (Ollama JSON Schema) ───────────────────────

CLASSIFIER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "dialogue_act": {
            "type": "string",
            "enum": [act.value for act in DialogueAct]
        },
        "intent": {
            "type": "string",
            "enum": [i.value for i in Intent]
        },
        "overall_confidence": {"type": "number"},
        "ambiguities": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["dialogue_act", "intent"]
}


def understand_turn(
    text: str,
    allow_llm: bool = True,
    model: Optional[str] = None,
) -> TurnUnderstanding:
    """
    Primary entry point for structured turn understanding.
    1. Runs deterministic parser first (< 5 ms).
    2. If confidence >= 0.75, returns deterministic result immediately (0 LLM calls).
    3. If confidence < 0.75 and allow_llm is True, calls small classifier model via
       Ollama JSON schema with temperature 0.
    4. Merges with deterministic priority: deterministic entities, SKUs, and slots are ALWAYS preserved.
    """
    t_start = time.time()
    det_understanding = TurnUnderstandingExtractor.parse(text)

    # Fast path: deterministic confidence is high -> return immediately
    if det_understanding.overall_confidence >= 0.75 or not allow_llm:
        det_understanding.latency_ms = int((time.time() - t_start) * 1000)
        return det_understanding

    # LLM disambiguation path
    target_model = model or OLLAMA_CLASSIFIER_MODEL
    messages = [
        {
            "role": "system",
            "content": (
                "You are an accurate dialogue understanding parser for Kepler Tech printer sales.\n"
                "Classify the customer's message into the specified dialogue_act and intent.\n"
                "Guidelines:\n"
                "- If the customer asks off-topic questions (food, cooking, recipes, personal queries, weather, sports, general knowledge): dialogue_act='out_of_scope', intent='other'.\n"
                "- If the customer replies with numbers, page counts, dimensions, paper sizes (A4, A3, 24\", 44\"), formats, or printer types: dialogue_act='question', intent='recommend'. NEVER classify numbers or equipment requests as out_of_scope.\n"
                "- If the customer expresses frustration, says 'not what I asked', 'what I asked what you giving': dialogue_act='complaint', intent='other'.\n"
                "- If the customer acknowledges or says 'thats fine', 'sounds good', 'okay', 'alright': dialogue_act='confirmation', intent='other'.\n"
                "- If the customer asks what you supply or sell: dialogue_act='question', intent='other'.\n"
                "Output strictly JSON matching the required schema."
            )
        },
        {
            "role": "user",
            "content": f"Customer message: \"{text}\""
        }
    ]

    try:
        resp = ollama_client.classify(
            messages=messages,
            schema=CLASSIFIER_JSON_SCHEMA,
            model=target_model,
            temperature=0.0,
            max_retries=0,  # Never retry in a loop on parse failure
        )
        if resp.get("success") and resp.get("result"):
            res = resp["result"]
            act_str = res.get("dialogue_act")
            intent_str = res.get("intent")
            conf = float(res.get("overall_confidence", 0.85))

            # Merge: update act/intent, keeping all deterministic entities & slots
            if act_str in [a.value for a in DialogueAct]:
                det_understanding.dialogue_act = DialogueAct(act_str)
            if intent_str in [i.value for i in Intent]:
                det_understanding.intent = Intent(intent_str)

            det_understanding.overall_confidence = max(det_understanding.overall_confidence, conf)
            det_understanding.is_deterministic = False
            det_understanding.used_llm = True
            det_understanding.ambiguities = res.get("ambiguities", [])

            # Guard against LLM false-positive OUT_OF_SCOPE
            if det_understanding.dialogue_act == DialogueAct.OUT_OF_SCOPE:
                t_lower = text.lower()
                is_valid_topic = any(
                    k in t_lower for k in [
                        "dubai", "abu dhabi", "sharjah", "uae", "oman", "saudi", "gcc",
                        "delivery", "ship", "pickup", "order", "price", "quote",
                        "ink", "inks", "consumable", "consuble", "consumbales", "cartridge", "ribbon",
                        "printer", "scanner", "plotter", "epson", "citizen", "f100", "c878", "cz01", "cx02"
                    ]
                )
                if is_valid_topic:
                    det_understanding.dialogue_act = DialogueAct.QUESTION
                    if any(k in t_lower for k in ["dubai", "abu dhabi", "sharjah", "uae", "oman", "delivery", "ship"]):
                        det_understanding.intent = Intent.SHIPPING_OR_DELIVERY
                    elif any(k in t_lower for k in ["ink", "inks", "consumable", "consuble", "consumbales", "cartridge", "ribbon"]):
                        det_understanding.intent = Intent.CONSUMABLES_LOOKUP
                    else:
                        det_understanding.intent = Intent.PRODUCT_INFO
    except Exception as e:
        logger.warning(f"Ollama structured understanding error: {e}. Falling back to deterministic result.")

    det_understanding.latency_ms = int((time.time() - t_start) * 1000)
    return det_understanding
