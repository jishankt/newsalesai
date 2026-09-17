"""
Text and Entity Normalization Module.
Corrects common typos, expands abbreviations, and canonicalizes technical units.
Protects model numbers and SKUs against accidental distortion.
"""

import re
import unicodedata
from typing import Dict, Any, List, Tuple
from nlp.multilingual import normalize_multilingual

# Common English typo dictionary mapping misspelled terms to standard vocabulary
TYPO_CORRECTIONS: Dict[str, str] = {
    # Common printer typos
    r"\bpribter\b": "printer",
    r"\bpriner\b": "printer",
    r"\bpriners\b": "printers",
    r"\bpritner\b": "printer",
    r"\bprinr\b": "printer",
    r"\bprintr\b": "printer",
    r"\bpeinter\b": "printer",
    r"\bprntr\b": "printer",
    r"\bprentr\b": "printer",
    r"\baprinter\b": "a printer",
    r"\bofice\b": "office",
    r"\bpltter\b": "plotter",
    r"\bploter\b": "plotter",
    r"\bpltr\b": "plotter",
    r"\bcadd\b": "CAD",
    r"\barchitct\b": "architect",
    r"\barchitcture\b": "architecture",
    r"\bblueprints?\b": "blueprint",
    r"\binova\b": "Innova",
    r"\bepsonn\b": "Epson",
    r"\beposn\b": "Epson",
    r"\bcitzen\b": "Citizen",
    r"\bcitizn\b": "Citizen",
    r"\bcitizon\b": "Citizen",
    r"\bcitizone\b": "Citizen",
    r"\bcitizens\b": "Citizen",
    r"\bcartrige\b": "cartridge",
    r"\bcatridge\b": "cartridge",
    r"\bcartidges?\b": "cartridge",
    r"\bmaintenence\b": "maintenance",
    r"\bmaintanance\b": "maintenance",
    r"\bphotoboth\b": "photo booth",
    r"\bphotobooth\b": "photo booth",
    r"\bdyesub\b": "dye-sublimation",
    r"\bdye sub\b": "dye-sublimation",
    r"\bsublimtion\b": "sublimation",
    r"\bcopire\b": "copier",
    r"\benterprize\b": "enterprise",
    r"\bscannr\b": "scanner",
    r"\bscaner\b": "scanner",
    r"\bsacnners?\b": "scanners",
    r"\bcxo2\b": "CX02",
    r"\bcxo-2\b": "CX-02",
    r"\bcx02w\b": "CX-02W",
    r"\bf1oo\b": "F100",
    r"\bsc-?f1oo\b": "SC-F100",
    r"\bf-100\b": "F100",
    r"\bf5oo\b": "F500",
    r"\bf-500\b": "F500",
    r"\bp9oo\b": "P900",
    r"\bp7oo\b": "P700",
    r"\bt31oo\b": "T3100",
    r"\bt51oo\b": "T5100",
    r"\bluster\b": "lustre",
    r"\bmirag\b": "Mirage",
    r"\baircast\b": "AirCastPro",
    r"\bdiscont\b": "discount",
    r"\bdiscout\b": "discount",
    r"\bprce\b": "price",
    r"\bpric\b": "price",
    r"\btiming\b": "hours",
    r"\btimings\b": "hours",
    r"\bbroucher\b": "brochure",
    r"\bbrousher\b": "brochure",
    r"\bbrouchure\b": "brochure",
    r"\bdatashet\b": "datasheet",
    r"\bspecfication\b": "specification",
    r"\bspecfications\b": "specifications",
    r"\brecomandation\b": "recommendation",
    r"\brecomended\b": "recommended",
    r"\brequirment\b": "requirement",
    r"\brequirments\b": "requirements",
    r"\bconsumbles\b": "consumables",
    r"\bconsumebles\b": "consumables",
    r"\bnegosition\b": "negotiation",
}

# Regex to detect and protect model codes / SKUs during typo passes
SKU_PROTECTION_PATTERN = re.compile(
    r"\b(?:SC-[A-Z0-9]+|AM-[A-Z0-9]+|WF-[A-Z0-9]+|CX-[0-9A-Z]+|CY-[0-9A-Z]+|CZ-[0-9A-Z]+|EM-[0-9A-Z]+|DS-[A-Z0-9]+)\b",
    re.IGNORECASE
)

# Canonical entity normalization mappings
SIZE_CANONICAL: List[Tuple[str, str]] = [
    (r"\b(?:24\s*(?:inch|in|\")|a[\s-]?1)\b", "24-inch (A1)"),
    (r"\b(?:36\s*(?:inch|in|\")|a[\s-]?0)\b", "36-inch (A0)"),
    (r"\b(?:44\s*(?:inch|in|\"))\b", "44-inch"),
    (r"\b(?:64\s*(?:inch|in|\"))\b", "64-inch"),
    (r"\b(?:a[\s-]?3\+?|13\s*(?:inch|in|\"))\b", "13-inch (A3+)"),
    (r"\b(?:a[\s-]?2\+?|17\s*(?:inch|in|\"))\b", "17-inch (A2+)"),
    (r"\b(?:a[\s-]?4)\b", "A4"),
    (r"\b(?:a[\s-]?3)(?!\+)\b", "A3"),
    (r"\b(?:2\s*(?:x|\*)\s*6|6\s*(?:x|\*)\s*2)\b", "2x6 inches"),
    (r"\b(?:4\s*(?:x|\*)\s*6|6\s*(?:x|\*)\s*4)\b", "4x6 inches"),
    (r"\b(?:5\s*(?:x|\*)\s*7|7\s*(?:x|\*)\s*5)\b", "5x7 inches"),
    (r"\b(?:6\s*(?:x|\*)\s*8|8\s*(?:x|\*)\s*6)\b", "6x8 inches"),
    (r"\b(?:8\s*(?:x|\*)\s*10|10\s*(?:x|\*)\s*8)\b", "8x10 inches"),
    (r"\b(?:8\s*(?:x|\*)\s*12|12\s*(?:x|\*)\s*8)\b", "8x12 inches"),
]


def normalize_text(text: str) -> Dict[str, Any]:
    """
    Cleans raw user input:
    1. Unicode NFKC normalization and character standardization
    2. Model code / SKU protection
    3. Multilingual / dialect normalization
    4. Typo correction
    5. SKU restoration
    6. Canonical entity identification
    Returns dict with 'raw_text', 'clean_text', 'normalized_text', 'corrections_applied', and 'canonical_sizes'.
    """
    if not text:
        return {
            "raw_text": "",
            "clean_text": "",
            "normalized_text": "",
            "corrections_applied": [],
            "canonical_sizes": []
        }

    # Normalize unicode characters
    clean = unicodedata.normalize("NFKC", text.strip())
    # Standardize special quotes and multiplication symbols
    clean = clean.replace("″", "\"").replace("“", "\"").replace("”", "\"")
    clean = clean.replace("’", "'").replace("‘", "'")
    clean = clean.replace("×", "x")
    # Replace multiple spaces/newlines
    clean = re.sub(r"\s+", " ", clean)

    applied_corrections: List[str] = []

    # 1. Protect SKUs and known model codes
    protected_skus: Dict[str, str] = {}
    def _protect_sku(match: re.Match) -> str:
        token = f"__PROTECTED_SKU_{len(protected_skus)}__"
        protected_skus[token] = match.group(0)
        return token

    normalized = SKU_PROTECTION_PATTERN.sub(_protect_sku, clean)

    # 2. Apply multilingual / Manglish normalization
    normalized, ml_corrections = normalize_multilingual(normalized)
    applied_corrections.extend(ml_corrections)

    # 3. Apply typo dictionary
    for pattern, replacement in TYPO_CORRECTIONS.items():
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            matched_str = match.group(0)
            if matched_str.lower() != replacement.lower():
                applied_corrections.append(f"{matched_str} -> {replacement}")
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    # 4. Restore protected SKUs
    for token, original_sku in protected_skus.items():
        normalized = normalized.replace(token, original_sku)

    # 5. Detect canonical sizes
    canonical_sizes: List[str] = []
    for pattern, canonical_val in SIZE_CANONICAL:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            if canonical_val not in canonical_sizes:
                canonical_sizes.append(canonical_val)

    return {
        "raw_text": text,
        "clean_text": clean,
        "normalized_text": normalized,
        "corrections_applied": applied_corrections,
        "canonical_sizes": canonical_sizes
    }
