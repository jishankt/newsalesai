"""
Multilingual and Dialect Normalization Module for Kepler Tech SalesAI.
Specialized in Malayalam-English (Manglish) conversational phrases, transliterations,
and colloquial regional idioms.
"""

import re
from typing import Dict, List, Tuple

# Structured Manglish mappings to English canonical conversational intents / phrases
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


def normalize_multilingual(text: str) -> Tuple[str, List[str]]:
    """
    Translates colloquial Manglish and regional expressions to standard English.
    Returns (normalized_text, list_of_applied_translations).
    """
    applied = []
    normalized = text
    for pattern, replacement in MANGLISH_PATTERNS:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            matched_str = match.group(0)
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            applied.append(f"{matched_str} -> {replacement}")
    return normalized, applied
