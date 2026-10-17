"""
Multilingual and Dialect Normalization Module for Kepler Tech SalesAI.
Specialized in Arabic, Hindi, Malayalam (Script and Manglish), and regional dialects.
Provides inbound NLU normalization to English and outbound translation back to the user's native language.
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("nlp.multilingual")

# ── 1. Manglish (Malayalam in Latin Script) ──────────────────────────────────
MANGLISH_PATTERNS: List[Tuple[str, str]] = [
    # Complex composite phrases first
    (r"\boru\s+photo\s+(?:printer|peinter)\s+venam\b", "I need a photo printer"),
    (r"\bphoto\s+(?:printer|peinter)\s+venam\b", "I need a photo printer"),
    (r"\boru\s+(?:printer|peinter)\s+venam\b", "I need a printer"),
    (r"\bprinter\s+venam\b", "I need a printer"),
    (r"\bcheyyan\s*ulla\s+printer\b", "printer for"),
    (r"\bprint\s+cheyyan\b", "to print"),
    (r"\bcheyyan\b", "to do"),
    (r"\bnalla\s+photo\s+printer\s+eathaanu\b", "which is the best photo printer"),
    (r"\bnalla\s+printer\s+eathaanu\b", "which is the best printer"),
    (r"\beathaanu\s+nallath(?:u)?\b", "which is best"),
    (r"\bnallath(?:u)?\b", "good"),
    (r"\bnalla\b", "good"),

    # Greetings & Common Expressions
    (r"\bnamaskaram\b", "hello"),
    (r"\bsukhamano\b", "hello how are you"),
    (r"\bnanni\b", "thank you"),
    (r"\baavashyamund\b", "needed"),
    (r"\baavashyam\b", "need"),
    (r"\bvaangan\b", "to buy"),
    (r"\bedukkan\b", "to take"),

    # Price / Cost inquiries
    (r"\bethra\s+price(?: aakum)?\b", "what is the price"),
    (r"\bethraya(?:nu)?\s+vila\b", "what is the price"),
    (r"\bvila\s+ethrayanu\b", "what is the price"),
    (r"\bethra\s+cost\b", "what is the cost"),
    (r"\bethra\s+aakum\b", "how much will it cost"),

    # Discounts / Commercial negotiation
    (r"\bkurachu\s+tharumo\b", "can you give discount"),
    (r"\bkurakko\b", "reduce price"),
    (r"\bdiscount\s+kittumo\b", "can I get a discount"),
    (r"\bdiscount\s+undo\b", "is there a discount"),
    (r"\bkurakkan\s+pattumo\b", "can you reduce price"),
    (r"\bkurachu\b", "little less"),

    # Questions & Pronouns
    (r"\bparayan\s+pattumo\b", "can you explain"),
    (r"\bparanju\s+tharumo\b", "can you explain"),
    (r"\bparayamo\b", "can you tell me"),
    (r"\bparayu\b", "tell me"),
    (r"\bithu\s+nallathano\b", "is this good"),
    (r"\bith\s+nallathano\b", "is this good"),
    (r"\binkjet\s+aano(?:\s+ithu)?\b", "is this an inkjet"),
    (r"\bithinte\s+features\s+enthanu\b", "what are its features"),
    (r"\bfeatures\s+enthokke\s+und\b", "what features does it have"),
    (r"\benthokke\s+und\b", "what all are there"),
    (r"\benthanu\b", "what is"),
    (r"\bentha\b", "what is"),
    (r"\bithu\b", "this"),
    (r"\beathaanu\b", "which is"),
    (r"\bevideyanu\b", "where is"),
    (r"\bevidaya\b", "where is"),
    (r"\beppozhanu\s+open\b", "when is it open"),
    (r"\bonnude\s+parayamo\b", "can you repeat"),

    # Hardware & Consumables
    (r"\bpaper\s+kittumo\b", "is paper available"),
    (r"\bpaper\s+kitto\b", "is paper available"),
    (r"\bink\s+kittumo\b", "is ink available"),
    (r"\bcartridge\s+undo\b", "is cartridge available"),
    (r"\bscanner\s+(?:undo|inda)\b", "is scanner available"),
    (r"\b(?:valiya|vadiya)\s+printer\b", "large format printer"),
    (r"\bcheriya\s+printer\b", "compact small printer"),
]

# ── 2. Arabic Script Inbound Patterns ─────────────────────────────────────────
ARABIC_PATTERNS: List[Tuple[str, str]] = [
    (r"\bطابعة\s*مكتبية\b", "office printer"),
    (r"\bطابعات\s*مكتبية\b", "office printers"),
    (r"\bطابعة\s*صور\b", "photo printer"),
    (r"\bطابعة\s*ملصقات\b", "label printer"),
    (r"\bماسح\s*ضوئي\b", "scanner"),
    (r"\bمخططات\s*هندسية\b", "CAD blueprints"),
    (r"\bطابعة\s*مخططات\b", "CAD plotter printer"),
    (r"\bطابعة\b", "printer"),
    (r"\bطابعات\b", "printers"),
    (r"\bأحتاج\s*إلى\b", "I need"),
    (r"\احتاج\s*الى\b", "I need"),
    (r"\bأريد\b", "I want"),
    (r"\barid\b", "I want"),
    (r"\bسريعة\b", "fast"),
    (r"\bسريع\b", "fast"),
    (r"\bكم\s*السعر\b", "what is the price"),
    (r"\bكم\s*سعر\b", "what is the price"),
    (r"\bالسعر\b", "price"),
    (r"\bسعر\b", "price"),
    (r"\bتخفيض\b", "discount"),
    (r"\bخصم\b", "discount"),
    (r"\bعقد\s*صيانة\b", "maintenance contract AMC"),
    (r"\bصيانة\b", "maintenance service"),
    (r"\bضمان\b", "warranty"),
    (r"\bحبر\b", "ink"),
    (r"\bأحبار\b", "inks"),
    (r"\bأوراق\b", "paper"),
    (r"\bورق\b", "paper"),
    (r"\bمرحبا\b", "hello"),
    (r"\bأهلا\b", "hello"),
    (r"\bالسلام\s*عليكم\b", "hello"),
    (r"\bشكرا\b", "thank you"),
    (r"\bشكراً\b", "thank you"),
]

# ── 3. Hindi (Devanagari) Inbound Patterns ───────────────────────────────────
HINDI_PATTERNS: List[Tuple[str, str]] = [
    (r"ऑफिस\s*प्रिंटर", "office printer"),
    (r"कार्यालय\s*प्रिंटर", "office printer"),
    (r"फोटो\s*प्रिंटर", "photo printer"),
    (r"प्रिंटर\s*चाहिए", "need printer"),
    (r"प्रिंटर", "printer"),
    (r"ऑफिस", "office"),
    (r"स्कैनर", "scanner"),
    (r"मुझे\s*चाहिए", "I need"),
    (r"चाहिए", "need"),
    (r"अच्छा", "good"),
    (r"अच्छी", "good"),
    (r"तेज़", "fast"),
    (r"कीमत\s*क्या\s*है", "what is the price"),
    (r"कीमत", "price"),
    (r"दाम", "price"),
    (r"छूट", "discount"),
    (r"डिस्काउंट", "discount"),
    (r"वारंटी", "warranty"),
    (r"इंक", "ink"),
    (r"स्याही", "ink"),
    (r"नमस्ते", "hello"),
    (r"नमस्कार", "hello"),
    (r"धन्यवाद", "thank you"),
    (r"शुक्रिया", "thank you"),
]

# ── 4. Malayalam Script Inbound Patterns ─────────────────────────────────────
MALAYALAM_SCRIPT_PATTERNS: List[Tuple[str, str]] = [
    (r"ഓഫീസ്\s*പ്രിന്റർ", "office printer"),
    (r"ഫോട്ടോ\s*പ്രിന്റർ", "photo printer"),
    (r"പ്രിന്റർ\s*വേണം", "need a printer"),
    (r"പ്രിന്റർ", "printer"),
    (r"ഓഫീസ്", "office"),
    (r"സ്കാനർ", "scanner"),
    (r"എനിക്ക്\s*വേണം", "I need"),
    (r"വേണം", "need"),
    (r"നല്ല", "good"),
    (r"വില\s*എത്രയാണ്", "what is the price"),
    (r"വില", "price"),
    (r"ഡിസ്കൗണ്ട്", "discount"),
    (r"കുറച്ചു\s*തരുമോ", "can you give discount"),
    (r"വാറന്റി", "warranty"),
    (r"ഇങ്ക്", "ink"),
    (r"മഷി", "ink"),
    (r"നമസ്കാരം", "hello"),
    (r"നന്ദി", "thank you"),
]


def detect_language(text: str) -> str:
    """Detects whether text is in Arabic (ar), Hindi (hi), Malayalam (ml), or English (en)."""
    if not text:
        return "en"
    # Arabic script Unicode range
    if re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text):
        return "ar"
    # Devanagari script Unicode range (Hindi)
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    # Malayalam script Unicode range
    if re.search(r"[\u0D00-\u0D7F]", text):
        return "ml"
    # Manglish check
    t_lower = text.lower()
    for pat, _ in MANGLISH_PATTERNS[:15]:
        if re.search(pat, t_lower):
            return "ml"
    return "en"


def normalize_multilingual(text: str, return_lang: bool = False) -> Any:
    """
    Translates colloquial regional expressions and scripts to standard English for NLU.
    If return_lang=True, returns (normalized_text, applied_translations, detected_language).
    Otherwise returns (normalized_text, applied_translations) for backward compatibility.
    """
    applied: List[str] = []
    normalized = text or ""
    lang = detect_language(normalized)

    # 1. Apply script-based translations
    if lang == "ar":
        for pattern, replacement in ARABIC_PATTERNS:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                matched_str = match.group(0)
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
                applied.append(f"{matched_str} -> {replacement}")
    elif lang == "hi":
        for pattern, replacement in HINDI_PATTERNS:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                matched_str = match.group(0)
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
                applied.append(f"{matched_str} -> {replacement}")
    elif lang == "ml":
        for pattern, replacement in MALAYALAM_SCRIPT_PATTERNS:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                matched_str = match.group(0)
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
                applied.append(f"{matched_str} -> {replacement}")

    # 2. Apply Manglish translations
    for pattern, replacement in MANGLISH_PATTERNS:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            matched_str = match.group(0)
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            applied.append(f"{matched_str} -> {replacement}")

    if return_lang:
        return normalized, applied, lang
    return normalized, applied


# ── Curated High-Frequency Outbound Translations ──────────────────────────────
OUTBOUND_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ar": {
        "Welcome to Kepler Tech!": "مرحبًا بكم في كيبلر تك!",
        "Do you require standard A4 output or large-format A3 output for your office documents?": "هل تحتاجون إلى مخرجات قياسية بحجم A4 أو مخرجات بحجم A3 للوثائق المكتبية؟",
        "Approximately how many pages do you print per day in the office?": "كم صفحة تقريبًا تطبعون يوميًا في المكتب؟",
        "Approximately how many pages do you print per day for your A3 workgroup or department?": "كم صفحة تقريبًا تطبعون يوميًا لقسمكم أو مجموعة العمل بحجم A3؟",
        "Which printing application fits your requirements?": "ما هو نوع وتطبيق الطباعة الذي يناسب متطلباتكم؟",
        "Do you want a scanner, printer, or consumables?": "هل تبحثون عن ماسح ضوئي، أو طابعة، أو أحبار ومستهلكات؟",
        "Here are our recommended Office Printer models matching your updated specifications:": "إليكم طابعات المكاتب الموصى بها والتي تطابق مواصفاتكم المحدثة:",
        "Understood! Here are our recommended Office Printer models matching your updated specifications:": "مفهوم! إليكم طابعات المكاتب الموصى بها والتي تطابق مواصفاتكم المحدثة:",
        "Based on your requirements, here are our recommended options from our verified catalogue:": "بناءً على متطلباتكم، إليكم الخيارات الموصى بها من كتالوجنا المعتمد:",
        "Commercial Quote on Request": "عرض سعر تجاري رسمي عند الطلب",
        "Verified Official Model": "طراز معتمد رسميًا من الوكيل",
    },
    "hi": {
        "Welcome to Kepler Tech!": "केपलर टेक में आपका स्वागत है!",
        "Do you require standard A4 output or large-format A3 output for your office documents?": "क्या आपको अपने ऑफिस दस्तावेजों के लिए मानक A4 आउटपुट या बड़े A3 आउटपुट की आवश्यकता है?",
        "Approximately how many pages do you print per day in the office?": "आप ऑफिस में प्रतिदिन लगभग कितने पेज प्रिंट करते हैं?",
        "Approximately how many pages do you print per day for your A3 workgroup or department?": "आप अपने A3 वर्कग्रुप या विभाग के लिए प्रतिदिन लगभग कितने पेज प्रिंट करते हैं?",
        "Which printing application fits your requirements?": "आपकी आवश्यकताओं के अनुसार कौन सा प्रिंटिंग कार्य उपयुक्त है?",
        "Do you want a scanner, printer, or consumables?": "क्या आपको स्कैनर, प्रिंटर या उपभोग्य वस्तुएं (इंक/कार्ट्रिज) चाहिए?",
        "Here are our recommended Office Printer models matching your updated specifications:": "आपके अपडेट किए गए विनिर्देशों के अनुसार अनुशंसित ऑफिस प्रिंटर मॉडल यहाँ हैं:",
        "Understood! Here are our recommended Office Printer models matching your updated specifications:": "समझ गया! आपके विनिर्देशों के अनुसार अनुशंसित ऑफिस प्रिंटर मॉडल यहाँ हैं:",
        "Based on your requirements, here are our recommended options from our verified catalogue:": "आपकी आवश्यकताओं के आधार पर हमारे कैटलॉग से अनुशंसित विकल्प यहाँ हैं:",
        "Commercial Quote on Request": "अनुरोध पर आधिकारिक व्यावसायिक कोटेशन",
        "Verified Official Model": "आधिकारिक सत्यापित मॉडल",
    },
    "ml": {
        "Welcome to Kepler Tech!": "കെപ്ലർ ടെക്കിലേക്ക് സ്വാഗതം!",
        "Do you require standard A4 output or large-format A3 output for your office documents?": "നിങ്ങളുടെ ഓഫീസ് ഡോക്യുമെന്റുകൾക്കായി സ്റ്റാൻഡേർഡ് A4 ഔട്ട്പുട്ടാണോ അതോ വലിയ ഫോർമാറ്റ് A3 ഔട്ട്പുട്ടാണോ ആവശ്യമുള്ളത്?",
        "Approximately how many pages do you print per day in the office?": "ഓഫീസിൽ പ്രതിദിനം എത്ര പേജുകൾ നിങ്ങൾ പ്രിന്റ് ചെയ്യുന്നുണ്ട്?",
        "Approximately how many pages do you print per day for your A3 workgroup or department?": "നിങ്ങളുടെ A3 ഡിപ്പാർട്ട്മെന്റിനായി പ്രതിദിനം എത്ര പേജുകൾ പ്രിന്റ് ചെയ്യുന്നുണ്ട്?",
        "Which printing application fits your requirements?": "ഏത് തരത്തിലുള്ള പ്രിന്റിംഗ് ആവശ്യമാണ് നിങ്ങൾക്ക് ഉള്ളത്?",
        "Do you want a scanner, printer, or consumables?": "നിങ്ങൾക്ക് സ്കാനർ, പ്രിന്റർ, അല്ലെങ്കിൽ മഷി/പേപ്പർ എന്നിവയാണോ ആവശ്യം?",
        "Here are our recommended Office Printer models matching your updated specifications:": "നിങ്ങളുടെ ആവശ്യങ്ങൾക്ക് അനുയോജ്യമായ ഓഫീസ് പ്രിന്ററുകൾ ഇതാ:",
        "Understood! Here are our recommended Office Printer models matching your updated specifications:": "മനസ്സിലായി! നിങ്ങളുടെ ആവശ്യങ്ങൾക്ക് അനുയോജ്യമായ ഓഫീസ് പ്രിന്ററുകൾ ഇതാ:",
        "Based on your requirements, here are our recommended options from our verified catalogue:": "നിങ്ങളുടെ ആവശ്യങ്ങൾക്ക് അനുയോജ്യമായി ഞങ്ങൾ ശുപാർശ ചെയ്യുന്ന മോഡലുകൾ ഇതാ:",
        "Commercial Quote on Request": "ഔദ്യോഗിക കൊട്ടേഷൻ അഭ്യർത്ഥിക്കാം",
        "Verified Official Model": "അംഗീകൃത ഒഫീഷ്യൽ മോഡൽ",
    }
}


def translate_to_language(english_text: str, target_lang: str) -> str:
    """
    Translates an English sales response into the customer's native language (ar, hi, ml).
    Preserves model names (e.g. WF-C5890, AM-C4000), numbers, and technical specifications.
    """
    if not english_text or target_lang in ("en", "", None):
        return english_text

    target_lang = target_lang.lower().strip()
    if target_lang not in ("ar", "hi", "ml"):
        return english_text

    # 1. Check exact or substring dictionary matches first
    dict_map = OUTBOUND_TRANSLATIONS.get(target_lang, {})
    translated = english_text
    matched_phrase = False
    for en_phrase, native_phrase in dict_map.items():
        if en_phrase.lower() in translated.lower():
            translated = re.sub(re.escape(en_phrase), native_phrase, translated, flags=re.IGNORECASE)
            matched_phrase = True

    # If key phrases were matched and substituted, return the localized text
    if matched_phrase:
        return translated

    # 2. Try LLM translation via Ollama if available
    try:
        from llm.ollama_client import ollama_client
        prompt = (
            f"You are a professional Kepler Tech commercial translator. "
            f"Translate the following English equipment sales response into natural, fluent {target_lang.upper()} script. "
            f"Keep all model names (e.g. Epson, WF-C5890, AM-C550), numbers, and brand terms in English/Latin script.\n\n"
            f"English: {english_text}\n"
            f"Translation:"
        )
        res = ollama_client.generate(prompt=prompt, timeout=2.5)
        if res and res.strip():
            cleaned = res.strip().replace('"', '').replace("Translation:", "").strip()
            # Verify script presence
            if target_lang == "ar" and any('\u0600' <= c <= '\u06FF' for c in cleaned):
                return cleaned
            elif target_lang == "hi" and any('\u0900' <= c <= '\u097F' for c in cleaned):
                return cleaned
            elif target_lang == "ml" and any('\u0D00' <= c <= '\u0D7F' for c in cleaned):
                return cleaned
    except Exception as e:
        logger.debug("Ollama translation fallback: %s", e)

    # 3. Native fallback headers by language
    if target_lang == "ar":
        return f"مرحبًا بكم في كيبلر تك! {english_text}"
    elif target_lang == "hi":
        return f"केपलर टेक में आपका स्वागत है! {english_text}"
    elif target_lang == "ml":
        return f"കെപ്ലർ ടെക്കിലേക്ക് സ്വാഗതം! {english_text}"

    return english_text
