"""
Universal Fuzzy Normalizer & Typo Tolerance Engine for Kepler Tech SalesAI.

Provides vocabulary-aware typo correction and entity normalization across:
1. Consumable and ink colors (e.g. maenta -> magenta, cyn -> cyan)
2. Hardware categories and terms (e.g. pritner -> printer, scannr -> scanner)
3. Media types (e.g. canvs -> canvas, sublimtion rool -> sublimation roll)
4. Brands and approved models (e.g. citizon -> Citizen, epson workfoce -> Epson WorkForce)
"""

import re
from typing import Dict, List, Optional, Tuple, Set

# Canonical Color Palette for Kepler Tech Hardware & Consumables
CANONICAL_COLORS = {
    "magenta": ["maenta", "megenta", "mgenta", "magenda", "magents", "magnta", "magente"],
    "cyan": ["cyn", "cayan", "cayn", "cyen", "ciyan", "syan"],
    "yellow": ["yelow", "yeloow", "yellw", "yello", "yelw"],
    "black": ["blak", "blck", "blac", "bak"],
    "photo black": ["photo blak", "pbk", "photo-black", "photoblack"],
    "matte black": ["matte blak", "mbk", "matte-black", "mat black", "mate black"],
    "light cyan": ["light cyn", "lc"],
    "light magenta": ["light maenta", "light megenta", "lm"],
    "gray": ["grey", "gry", "graay"],
    "light gray": ["light grey", "light gry", "lgray", "lgrey"],
    "violet": ["voilet", "violt", "violte"],
}

# Common domain keywords and typo mappings
DOMAIN_TYPOS = {
    # Printer types & components
    "printer": ["pritner", "prnter", "prntr", "pirnter", "priter", "pinter"],
    "plotter": ["ploter", "plottr", "poltter", "plter"],
    "scanner": ["scaner", "scannr", "scnr", "skanner", "skaner"],
    "cartridge": ["catridge", "cartrige", "cartidge", "catridg", "cartrdige"],
    "ribbon": ["ribon", "ribbn", "riben", "riboon"],
    "consumable": ["consumble", "consumables", "consumbles", "consumabels"],
    
    # Sublimation & Apparel
    "sublimation": ["sublimtion", "sublimaton", "sublimashun", "sublimatn", "sublim"],
    "t-shirt": ["tshirt", "t shirt", "t-shirts", "tshirts", "t shirts", "tee shirt"],
    
    # Media & Paper
    "canvas": ["canvs", "cnvas", "kanvas", "canvass"],
    "paper": ["papr", "ppar", "papper", "pape"],
    "glossy": ["glosy", "glosssy", "glos"],
    "matte": ["mate", "matt"],
    "roll": ["rool", "rol", "roole"],
    "rolls": ["rools", "rols", "rooles"],
    "media": ["medias", "meda", "meedia", "meedias", "mdeia"],
    "all": ["aall", "al", "alll"],
    
    # Attributes & Performance
    "fast": ["fst", "faast", "fsat", "fatest"],
    "speed": ["sped", "speeed", "spead"],

    # Brands & Series
    "citizen": ["citizon", "citiizen", "citzen", "cittizen", "citizn"],
    "epson": ["epsn", "epzon", "epsom"],
    "workforce": ["workfoce", "workforc", "work-force", "wrkforce", "workfocre"],
    "surecolor": ["sure-color", "sure color", "surecolr", "surcolor"],
}


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


class UniversalFuzzyNormalizer:
    """Universal Typo Normalizer for SalesAI."""

    def __init__(self):
        # Build reverse lookup for direct common typos
        self.direct_color_map: Dict[str, str] = {}
        for canonical, typo_list in CANONICAL_COLORS.items():
            for t in typo_list:
                self.direct_color_map[t] = canonical
            self.direct_color_map[canonical] = canonical

        self.direct_domain_map: Dict[str, str] = {}
        for canonical, typo_list in DOMAIN_TYPOS.items():
            for t in typo_list:
                self.direct_domain_map[t] = canonical
            self.direct_domain_map[canonical] = canonical

    COMMON_WORDS: Set[str] = {
        "can", "place", "plan", "back", "pack", "man", "fan", "pan", "tan", "van", "ran",
        "block", "blank", "play", "plate", "pace", "peace", "please", "clean", "clan",
        "scan", "span", "price", "print", "one", "two", "an", "the", "for", "to", "in",
        "on", "at", "by", "from", "with", "about", "what", "which", "where", "who", "how",
        "when", "why", "is", "are", "was", "were", "be", "been", "have", "has", "had",
        "do", "does", "did", "will", "would", "shall", "should", "may", "might", "must",
        "want", "need", "like", "order", "buy", "sell", "use", "make", "get", "give", "take",
        "fine", "line", "page", "pages", "paper", "fast", "speed", "box", "case", "cost"
    }

    def normalize_color(self, token: str) -> Optional[str]:
        """
        Normalizes a color token to canonical color if match/fuzzy distance is close.
        Returns canonical color name or None.
        """
        t = token.lower().strip()
        if not t or t in self.COMMON_WORDS:
            return None

        # 1. Exact or direct dictionary lookup
        if t in self.direct_color_map:
            return self.direct_color_map[t]

        # 2. Fuzzy Levenshtein match across canonical colors
        best_match = None
        min_dist = 999
        for canonical in CANONICAL_COLORS.keys():
            dist = _levenshtein_distance(t, canonical)
            # Allow distance <= 2 for words with length >= 4
            max_allowed = 1 if len(canonical) <= 4 else 2
            if dist <= max_allowed and dist < min_dist:
                min_dist = dist
                best_match = canonical

        return best_match

    def normalize_text_tokens(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Scans text and normalizes common domain typos and colors while preserving structure.
        Returns (normalized_text, list_of_corrections_applied).
        """
        if not text:
            return text, []

        corrections = []
        words = re.findall(r"\b[\w\-]+\b|[^\w\s]|\s+", text)
        new_words = []

        for word in words:
            w_lower = word.lower()
            replacement = None

            # Skip punctuation or whitespace
            if not re.match(r"^[\w\-]+$", word):
                new_words.append(word)
                continue

            # Check direct domain typos
            if w_lower in self.direct_domain_map and self.direct_domain_map[w_lower] != w_lower:
                replacement = self.direct_domain_map[w_lower]
            # Check direct color typos
            elif w_lower in self.direct_color_map and self.direct_color_map[w_lower] != w_lower:
                replacement = self.direct_color_map[w_lower]
            else:
                # Check fuzzy color
                color_cand = self.normalize_color(w_lower)
                if color_cand and color_cand != w_lower:
                    replacement = color_cand

            if replacement:
                corrections.append({"original": word, "normalized": replacement})
                # Preserve capitalization if original had title case
                if word.istitle():
                    replacement = replacement.title()
                new_words.append(replacement)
            else:
                new_words.append(word)

        normalized_text = "".join(new_words)
        return normalized_text, corrections


fuzzy_normalizer = UniversalFuzzyNormalizer()
