"""
NLP Intent Extractor and Entity Recognition Engine.
Classifies user messages according to Section B of the system prompt
and extracts domain-specific entities.
"""

import re
from nlp.normalizer import normalize_text

INTENT_PRICE = "PRICE_INQUIRY"
INTENT_DISCOUNT = "DISCOUNT_INQUIRY"
INTENT_GREETING = "GREETING"
INTENT_DISCOVERY = "PRODUCT_DISCOVERY"
INTENT_COMPARISON = "PRODUCT_COMPARISON"
INTENT_CHECK_SPECS = "CHECK_SPECS"
INTENT_TROUBLESHOOTING = "TROUBLESHOOTING"
INTENT_BUSINESS_INFO = "BUSINESS_INFORMATION"
INTENT_SERVICE_INFO = "SERVICE_INFORMATION"
INTENT_CONSUMABLES = "CONSUMABLES_QUERY"
INTENT_ENDING = "CONVERSATION_ENDING"
INTENT_UNCLEAR = "UNCLEAR_REQUEST"

# Intent regex rules
INTENT_RULES = [
    (INTENT_CONSUMABLES, [
        r"\b(?:consumable|consumables|ink|inks|cartridge|cartridges|toner|ribbon|paper roll|photo paper|maintenance box|maintenance tank|compatible with)\b"
    ]),
    (INTENT_CHECK_SPECS, [
        r"\b(?:wi-?fi|wifi|wireless|scanner|integrated scanner|print speed|ppm|resolution|dpi|print width|max width|specifications?|specs?)\b",
        r"\b(?:can (?:it|the [a-z0-9\-_]+) print|does (?:it|the [a-z0-9\-_]+) have|is (?:it|the [a-z0-9\-_]+) able to|able to print)\b",
    ]),
    (INTENT_DISCOUNT, [
        r"\b(?:discount|discounts|offer|offers|bargain|promo|coupon|deal|cheaper rate|best price)\b"
    ]),
    (INTENT_PRICE, [
        r"\b(?:how much|price|pricing|cost|costs|rate|quotation|quote|charge|charges|fee|fees|expensive|cheap|affordable)\b",
        r"[$₹€£]\s*\d+",
        r"\b\d+\s*(?:aed|dirhams|dollars|usd|inr|eur)\b"
    ]),
    (INTENT_BUSINESS_INFO, [
        r"\b(?:hours?|timings?|schedule|opening|open|closed?)\b",
        r"\b(?:where|location|address|office|dubai|khalid bin waleed|direction)\b",
        r"\b(?:phone|call|contact|telephone|mobile|email|whatsapp)\b"
    ]),
    (INTENT_TROUBLESHOOTING, [
        r"\b(?:error|issue|problem|broken|jam|jammed|paper jam|streak|line|faint|blurry|clog|clogged|nozzle|not working|failed)\b"
    ]),
    (INTENT_COMPARISON, [
        r"\b(?:compare|comparison|difference|differences|difference between|versus|vs|better than|which one is better|which is better|how do they compare|how does .* compare)\b"
    ]),
    (INTENT_SERVICE_INFO, [
        r"\b(?:warranty|installation|maintenance|amc|contract|training|repair|service)\b"
    ]),
    (INTENT_ENDING, [
        r"\b(?:thank you|thanks|bye|goodbye|that's all|thats all|have a good day)\b"
    ]),
    (INTENT_GREETING, [
        r"^(?:hi|hello|hey|good morning|good afternoon|good evening|howdy)\b"
    ])
]

# Entity Matchers
BRAND_PATTERNS = {
    "Epson": r"\b(?:epson|surecolor|workforce|precisioncore|ultrachrome)\b",
    "Citizen": r"\b(?:citizen|cx-?02|cy-?02|op900)\b",
    "Innova Art": r"\b(?:innova|ifa\s*\d+|cotton rag)\b",
    "Olmec": r"\b(?:olmec|olm\s*\d+|photo pearl|photo lustre)\b",
    "Mirage (DINAX)": r"\b(?:mirage|dinax|rip software)\b",
    "AirCastPro": r"\b(?:aircast|aircastpro)\b",
    "Adobe": r"\b(?:adobe)\b"
}

CATEGORY_PATTERNS = {
    "cad_plotter": r"\b(?:cad|gis|plotter|blueprint|architect|engineering|technical drawing|plan)\b",
    "photo_fine_art": r"\b(?:photo|fine art|gallery|portrait|exhibition|giclee|photographer)\b",
    "photo_booth_dyesub": r"\b(?:photo booth|booth|dye-?sub|event print|instant photo|passport)\b",
    "office_enterprise": r"\b(?:office|enterprise|copier|multifunction|mfp|workforce|40\s*ppm|55\s*ppm)\b",
    "paper_media": r"\b(?:paper|media|cotton rag|canvas|lustre|pearl|roll paper|cut sheet)\b",
    "consumables": r"\b(?:ink|cartridge|maintenance box|printhead|ribbon)\b",
    "software": r"\b(?:software|rip|aircast|driver)\b"
}

MODEL_PATTERNS = {
    "Epson SureColor T3100": r"\b(?:(?:sc-?)?t3100m?|t-3100)\b",
    "Epson SureColor T5100": r"\b(?:(?:sc-?)?t5100m?|t-5100)\b",
    "Epson SureColor T5400": r"\b(?:(?:sc-?)?t5400m?|t-5400)\b",
    "Epson SureColor P700": r"\b(?:(?:sc-?)?p700|p-700)\b",
    "Epson SureColor P900": r"\b(?:(?:sc-?)?p900|p-900)\b",
    "Epson SureColor P7500": r"\b(?:(?:sc-?)?p7500|p-7500)\b",
    "Epson SureColor P9500": r"\b(?:(?:sc-?)?p9500|p-9500)\b",
    "Epson WorkForce AM-C4000": r"\b(?:am-?c4000|c4000)\b",
    "Epson WorkForce AM-C550": r"\b(?:am-?c550|c550)\b",
    "Epson WorkForce WF-C879R": r"\b(?:c879r|wf-c879r)\b",
    "Epson SureColor SC-F100": r"\b(?:f100|sc-?f100)\b",
    "Epson SureColor SC-F500": r"\b(?:f500|sc-?f500)\b",
    "Citizen CX-02": r"\b(?:cx-?02|cx02)\b",
    "Citizen CY-02": r"\b(?:cy-?02|cy02)\b",
}


def analyze_input(text: str) -> dict:
    """
    Runs text normalization, intent classification, and entity extraction.
    """
    norm_result = normalize_text(text)
    normalized_text = norm_result["normalized_text"]
    lower_text = normalized_text.lower()

    # 1. Intent Detection
    detected_intent = INTENT_DISCOVERY  # default intent
    from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer
    if CanonicalEntityNormalizer.is_capability_query(lower_text):
        detected_intent = INTENT_CHECK_SPECS
    else:
        for intent_name, patterns in INTENT_RULES:
            if any(re.search(p, lower_text) for p in patterns):
                detected_intent = intent_name
                break

    # 2. Entity Extraction
    extracted_brands = [b for b, p in BRAND_PATTERNS.items() if re.search(p, lower_text)]
    extracted_categories = [c for c, p in CATEGORY_PATTERNS.items() if re.search(p, lower_text)]
    extracted_models = [m for m, p in MODEL_PATTERNS.items() if re.search(p, lower_text)]

    # 3. Interactive suggestion chips generation
    suggested_chips = []
    if detected_intent == INTENT_PRICE:
        suggested_chips = ["Explore CAD Plotters", "Explore Photo Printers", "Request Official Quote via Email"]
    elif detected_intent == INTENT_DISCOUNT:
        suggested_chips = ["Compare Suitable Models", "Technical Specifications", "Contact Sales Representative"]
    elif "cad_plotter" in extracted_categories:
        if not norm_result["canonical_sizes"]:
            suggested_chips = ["24-inch (A1) Size", "36-inch (A0) Size", "Desktop Stand Details"]
        else:
            suggested_chips = ["Print Only", "Integrated Scanner Option", "Roll Paper Details"]
    elif "photo_fine_art" in extracted_categories:
        suggested_chips = ["Desktop (P700/P900)", "Production (P7500/P9500)", "Innova Cotton Rag Media"]
    elif "photo_booth_dyesub" in extracted_categories:
        suggested_chips = ["Citizen CX-02 (Compact)", "Citizen CY-02 (High Capacity)", "AirCastPro Wireless Setup"]
    elif "office_enterprise" in extracted_categories:
        suggested_chips = ["AM-C4000 (40 ppm)", "AM-C550 (55 ppm)", "Finisher / Stapler Options"]
    elif detected_intent == INTENT_BUSINESS_INFO:
        suggested_chips = ["Office Location (Dubai)", "Working Hours", "Sales Contact Details"]
    elif detected_intent == INTENT_TROUBLESHOOTING:
        suggested_chips = ["Nozzle Check Instructions", "Paper Feed Issues", "Printhead Cleaning"]
    else:
        suggested_chips = ["Printers", "Scanners", "Consumables"]

    return {
        "raw_text": norm_result["raw_text"],
        "clean_text": norm_result["clean_text"],
        "normalized_text": normalized_text,
        "corrections": norm_result["corrections_applied"],
        "intent": detected_intent,
        "brands": extracted_brands,
        "categories": extracted_categories,
        "models": extracted_models,
        "sizes": norm_result["canonical_sizes"],
        "suggested_chips": suggested_chips
    }
