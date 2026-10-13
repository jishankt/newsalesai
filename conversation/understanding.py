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
            "cx02": "citizen-cx-02",
            "cx-02": "citizen-cx-02",
            "cx 02": "citizen-cx-02",
            "citizen cx02": "citizen-cx-02",
            "cx02w": "citizen-cx-02w",
            "cx-02w": "citizen-cx-02w",
            "citizen cx02w": "citizen-cx-02w",
            "cy02": "citizen-cy-02",
            "cy-02": "citizen-cy-02",
            "citizen cy02": "citizen-cy-02",
            "cz01": "citizen-cz-01",
            "cz-01": "citizen-cz-01",
            "citizen cz01": "citizen-cz-01",
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
            "12000xl": "epson-expression-12000xl",
        }
        for k, v in high_frequency.items():
            alias_map[k] = v
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
        re.compile(r"^\s*(?:yes|yep|yeah|sure|ok|okay|correct|that'?s\s+right|affirmative|absolutely|indeed|proceed|agree)\b", re.I),
        re.compile(r"^\s*(?:1|first|option\s*1)\s*$", re.I),
    ]

    REJECTION_PATTERNS = [
        re.compile(r"^\s*(?:no|nope|not\s+really|neither|none|incorrect|disagree|don'?t\s+want\s+this|not\s+this)\b", re.I),
    ]

    CORRECTION_PATTERNS = [
        re.compile(r"\b(?:no[,\s]+i\s+meant|actually\s+i\s+mean|i\s+said|correction|not\s+[a-z0-9\-]+[,\s]+(?:i\s+mean\s+)?[a-z0-9\-]+)\b", re.I),
    ]

    HANDOFF_PATTERNS = [
        re.compile(r"\b(?:speak\s+to\s+(?:a\s+)?(?:human|sales\s*rep|person|specialist)|talk\s+to\s+(?:a\s+)?human|agent|customer\s+support|call\s+me|phone\s+number)\b", re.I),
    ]

    OUT_OF_SCOPE_PATTERNS = [
        re.compile(r"\b(?:3d\s*printer|resin|laser\s*jet|toner|canon|hp\s+designjet|food\s*printer|edible\s*ink)\b", re.I),
    ]

    COMPATIBILITY_PATTERNS = [
        re.compile(r"\b(?:suitable\s+for|compatible\s+with|works?\s+with|fits?\s+(?:on|in|with)?|can\s+i\s+use\s+(?:this|it)\s+(?:on|in|with)|is\s+(?:this|it)\s+for)\b", re.I),
        re.compile(r"\b(?:is\s+[a-z0-9\-]+\s+(?:suitable|compatible|fit|work)\s+(?:for|with|on)\s+[a-z0-9\-]+)\b", re.I),
    ]

    CONSUMABLES_PATTERNS = [
        re.compile(r"\b(?:what\s+inks?|which\s+inks?|consumables?|cartridges?|ribbons?|maintenance\s*box(?:es)?|supplies(?:\s+for)?|sublimation\s+inks?|print\s+supplies)\b", re.I),
        re.compile(r"\b(?:(?:what|which|need|want|buy|order|get|looking\s+for)\s+(?:an?\s+)?(?:ink|inks|cartridge|cartridges|ribbon|ribbons|toner|supplies)|(?:ink|inks|cartridge|cartridges|supplies)\s+for)\b", re.I),
    ]

    COMPARE_PATTERNS = [
        re.compile(r"\b(?:compare|comparison|difference\s+between|which\s+is\s+better|versus|\bvs\b)\b", re.I),
    ]

    ALTERNATIVES_PATTERNS = [
        re.compile(r"\b(?:alternatives?|similar\s+(?:models?|printers?)|other\s+options?|other\s+models?)\b", re.I),
    ]

    PRICE_POLICY_PATTERNS = [
        re.compile(r"\b(?:price|cost|how\s+much|quote|quotation|pricing|discount|rates?|in\s+stock|available\s+in\s+stock)\b", re.I),
    ]

    SHOWROOM_PATTERNS = [
        re.compile(
            r"\b(?:showroom|store\s*location|physical\s*store|office\s*location|office\s*address|"
            r"where\s+(?:is\s+your|are\s+you|can\s+i\s+visit)|visit\s+(?:your\s+)?(?:showroom|store|office)|"
            r"head\s*office|khalid\s+bin\s+waleed|directions\s+to\s+your|"
            r"working\s*hours|business\s*hours|opening\s*hours|when\s+are\s+you\s+open|open\s+today)\b",
            re.I
        ),
    ]

    DELIVERY_PATTERNS = [
        re.compile(
            r"\b(?:delivery|deliver|shipping|ship|dispatch|courier|do you deliver|can you deliver|"
            r"delivery service|deliver to|delivering|pickup|pick up|store pickup|return policy|returns?\b|"
            r"refunds?\b|cancel(?:lation)?|cancel order|customs duty|import tax|import duty|tracking|track my order|track order)\b",
            re.I
        ),
    ]

    CONFUSION_PATTERNS = [
        re.compile(r"\b(?:what (?:are )?you asking|what do you mean|i don'?t understand|previous chat|priviace chat|check (?:the )?chat|check (?:the )?history|what did i say|answer after checking)\b", re.I),
    ]

    FRUSTRATION_PATTERNS = [
        re.compile(
            r"\b(?:this is useless|useless|stupid\b|terrible|waste of time|"
            r"i already said|already said|i told you|already told you|listen to me|you are not listening|"
            r"not helpful|awful|talk to a human|human please|agent please)\b",
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
        sorted_aliases = sorted(alias_map.keys(), key=lambda a: len(a), reverse=True)
        for alias in sorted_aliases:
            if len(alias) < 2:
                continue
            # Use word boundaries for aliases to prevent substring collisions
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, text_l):
                norm_pid = alias_map[alias]
                if norm_pid not in seen_keys:
                    entities.append(EntityMention(
                        surface_text=alias,
                        normalised_id=norm_pid,
                        entity_type="model",
                        match_type="alias",
                        confidence=0.98,
                        metadata={"canonical_id": norm_pid},
                    ))
                    seen_keys.add(norm_pid)

        # 3. Model Matching: Exact alias matches only!
        # Near/fuzzy matches never answer as that model; flag as unlisted_model
        if not any(e.entity_type == "model" for e in entities):
            words = [w for w in re.findall(r"[a-z0-9\-]+", text_l) if len(w) >= 3]
            for word in words:
                best_alias = None
                best_score = 0.0
                for alias, pid in alias_map.items():
                    if len(alias) >= 3 and abs(len(alias) - len(word)) <= 2:
                        ratio = SequenceMatcher(None, word, alias).ratio()
                        if ratio > best_score:
                            best_score = ratio
                            best_alias = alias

                if best_alias and best_score >= FUZZY_MATCH_THRESHOLD:
                    # Near matches NEVER answer as that model! Mark as unlisted_model
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
                    if clean_code in alias_map:
                        norm_pid = alias_map[clean_code]
                        entities.append(EntityMention(
                            surface_text=raw_code,
                            normalised_id=norm_pid,
                            entity_type="model",
                            match_type="alias",
                            confidence=1.0,
                            metadata={"canonical_id": norm_pid},
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
        categories = {
            "office_workforce": [
                "office printer", "workforce", "business printer", "printer for my office",
                "printer for office", "for my office", "for our office", "office use",
                "office printing", "office copier", "enterprise mfp", "am-c", "wf-c",
                "office multifunction", "office enterprise", "enterprise", "enterprise printer",
                "line-head", "line head", "line-head enterprise", "office mfp", "office mfps", "business mfp"
            ],
            "technical_cad": [
                "cad", "technical", "engineering", "blueprints", "line drawings", "architectural",
                "architect", "archtect", "architecture", "drawing", "drawings", "architect drawings",
                "gis", "cad plotter", "blueprint", "plotter", "plotters", "large format plotter"
            ],
            "photo_fine_art": [
                "fine art", "photo printer", "gallery", "photography", "photo printing", "photo studio",
                "master studio", "spectro", "pro10", "pro12", "fine art gallery"
            ],
            "citizen_photo": [
                "photo booth", "event photography", "instant prints", "passport photos", "citizen", "citizon", "citzen",
                "citizen printer", "citizon printer", "instant photo", "photo booth printer", "dye-sub photo", "cz-01", "cx-02", "cy-02", "cx-02w"
            ],
            "dye_sublimation": [
                "dye sublimation", "sublimation", "sublimation printer", "apparel printing",
                "t-shirt printing", "textile printing", "mug printing", "sportswear printing",
                "apparel", "t-shirt", "mug"
            ],
            "scanners": [
                "scanner", "scanners", "document scanner", "sheetfed", "flatbed scanner",
                "film scanner", "large format scanner", "book scanner", "scanning solutions",
                "expression 12000xl", "workforce ds"
            ],
        }
        for cat_id, cat_keywords in categories.items():
            for kw in cat_keywords:
                if re.search(rf"\b{re.escape(kw)}\b", text_l):
                    entities.append(EntityMention(
                        surface_text=kw,
                        normalised_id=f"category:{cat_id}",
                        entity_type="category",
                        match_type="exact",
                        confidence=0.95,
                    ))
                    break

        return entities

    @classmethod
    def extract_slots(cls, text: str, entities: List[EntityMention]) -> Dict[str, SlotValue]:
        slots: Dict[str, SlotValue] = {}
        text_l = text.lower()

        # Category slot
        cats = [e.normalised_id.replace("category:", "") for e in entities if e.entity_type == "category"]
        if cats:
            slots["target_category"] = SlotValue(
                slot_name="target_category",
                value=cats[0],
                confidence=0.95,
                source="said_now"
            )

        # Target model slot
        models = [e.normalised_id for e in entities if e.entity_type == "model"]
        if models:
            slots["target_model"] = SlotValue(
                slot_name="target_model",
                value=models[0],
                confidence=0.95,
                source="said_now"
            )
            if len(models) > 1:
                slots["comparison_models"] = SlotValue(
                    slot_name="comparison_models",
                    value=models,
                    confidence=0.95,
                    source="said_now"
                )

        # Target SKU slot
        skus = [e.normalised_id for e in entities if e.entity_type == "sku"]
        if skus:
            slots["target_sku"] = SlotValue(
                slot_name="target_sku",
                value=skus[0],
                confidence=1.0,
                source="said_now"
            )

        # Size slot (e.g. 24 inch, 36 inch, 4x6, 6x8, A4)
        size_match = re.search(r"\b(24\s*inch|36\s*inch|44\s*inch|a4|a3\+?|4x6|5x7|6x8|8x10)\b", text_l)
        if size_match:
            slots["media_size"] = SlotValue(
                slot_name="media_size",
                value=size_match.group(1).replace(" ", ""),
                confidence=0.90,
                source="said_now"
            )

        # Target attribute slot (for specific spec inquiries)
        target_attr = None
        if any(k in text_l for k in ["stand", "legs", "floor stand", "with a stand"]):
            target_attr = "stand"
        elif any(k in text_l for k in ["speed", "ppm", "fast", "how long to print"]):
            target_attr = "print_speed"
        elif any(k in text_l for k in ["dpi", "resolution", "clarity"]):
            target_attr = "dpi"
        elif any(k in text_l for k in ["width", "max width", "print width", "paper size"]):
            target_attr = "print_width"
        elif any(k in text_l for k in ["connectivity", "wifi", "wi-fi", "ethernet", "usb", "network"]):
            target_attr = "connectivity"
        elif any(k in text_l for k in ["dimension", "dimensions", "size", "height"]):
            target_attr = "dimensions"
        elif any(k in text_l for k in ["weight", "heavy", "kg"]):
            target_attr = "weight"
        elif any(k in text_l for k in ["scanner", "scan", "copy", "mfp"]):
            target_attr = "scanner_integrated"
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

        return slots

    @classmethod
    def classify_dialogue_act_and_intent(
        cls, text: str, entities: List[EntityMention], refs: List[ReferenceExpression]
    ) -> Tuple[DialogueAct, Intent, float, List[str]]:
        text_l = text.lower().strip()
        ambiguities: List[str] = []

        # 1. Handoff request
        if any(p.search(text_l) for p in cls.HANDOFF_PATTERNS):
            return DialogueAct.HANDOFF_REQUEST, Intent.CONTACT_SHOWROOM, 0.99, ambiguities

        # 2. Out of scope
        if any(p.search(text_l) for p in cls.OUT_OF_SCOPE_PATTERNS):
            return DialogueAct.OUT_OF_SCOPE, Intent.OTHER, 0.95, ambiguities

        # 2b. Confusion or complaint / frustration about conversation
        if any(p.search(text_l) for p in cls.FRUSTRATION_PATTERNS) or any(p.search(text_l) for p in cls.CONFUSION_PATTERNS):
            return DialogueAct.COMPLAINT, Intent.OTHER, 0.98, ambiguities

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

        # 4. Confirmation
        if any(p.search(text_l) for p in cls.CONFIRMATION_PATTERNS):
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
        if any(p.search(text_l) for p in cls.CONSUMABLES_PATTERNS):
            act = DialogueAct.REFERENCE_FOLLOW_UP if refs else DialogueAct.QUESTION
            return act, Intent.CONSUMABLES_LOOKUP, 0.95, ambiguities

        # 8. Models and SKUs
        models = [e for e in entities if e.entity_type == "model"]
        skus = [e for e in entities if e.entity_type == "sku"]

        # Compare (requires explicit comparison wording)
        if any(p.search(text_l) for p in cls.COMPARE_PATTERNS):
            return DialogueAct.QUESTION, Intent.COMPARE, 0.92, ambiguities

        # 9. Alternatives
        if any(p.search(text_l) for p in cls.ALTERNATIVES_PATTERNS):
            act = DialogueAct.REFERENCE_FOLLOW_UP if refs else DialogueAct.QUESTION
            return act, Intent.ALTERNATIVES, 0.92, ambiguities

        # 10. Delivery & Shipping policy inquiry (check before general availability)
        has_explicit_price = any(k in text_l for k in ["price", "cost", "how much", "quote", "quotation", "pricing", "rate", "discount"])
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
    def parse(cls, text: str) -> TurnUnderstanding:
        """Runs the deterministic extractor pipeline."""
        t_start = time.time()
        entities = cls.extract_entities(text)
        refs = cls.extract_reference_expressions(text)
        slots = cls.extract_slots(text, entities)
        dialogue_act, intent, confidence, ambiguities = cls.classify_dialogue_act_and_intent(text, entities, refs)
        compound_intents = cls.extract_compound_intents(text, intent)
        duration_ms = int((time.time() - t_start) * 1000)

        return TurnUnderstanding(
            raw_text=text,
            dialogue_act=dialogue_act,
            intent=intent,
            secondary_intents=compound_intents,
            entities=entities,
            reference_expressions=refs,
            slots=slots,
            overall_confidence=confidence,
            ambiguities=ambiguities,
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
                "You are an accurate dialogue understanding parser for Kepler Tech printer sales. "
                "Classify the customer's message into the specified dialogue_act and intent. "
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
    except Exception as e:
        logger.warning(f"Ollama structured understanding error: {e}. Falling back to deterministic result.")

    det_understanding.latency_ms = int((time.time() - t_start) * 1000)
    return det_understanding
