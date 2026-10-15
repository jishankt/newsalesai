"""
Catalogue-Generated Alias Resolver.
Builds an automated alias index for every product in the catalogue from product code,
model name, and SKU, auto-generating variants with/without hyphens, spaces, and suffixes.

Resolves text to exact(product), candidates([products]), or none.
Also provides a consumables vocabulary matcher (edit distance <= 2).
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

from catalog.catalogue_loader import catalogue_loader


def _levenshtein(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
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


@dataclass
class AliasMatch:
    match_type: str  # "exact", "candidates", "none"
    product: Optional[Dict[str, Any]] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    alias_matched: str = ""

    @property
    def is_exact(self) -> bool:
        return self.match_type == "exact" and self.product is not None

    @property
    def is_candidates(self) -> bool:
        return self.match_type == "candidates" and len(self.candidates) > 0


class AliasIndex:
    def __init__(self):
        self.exact_alias_to_product: Dict[str, Dict[str, Any]] = {}
        self.short_aliases: Set[str] = set()
        self.consumables_vocab = {
            "consumables": ["consumable", "consumables", "consubales", "consumbales", "consumble", "consumbles"],
            "ink": ["ink", "inks", "inlk"],
            "maintenance box": ["maintenance box", "maintainence box", "maintenance", "maintainence", "maint box"],
            "ribbon": ["ribbon", "ribbons", "ribon", "riben"],
            "media": ["media", "medias", "paper roll", "paper rolls"],
        }
        self.build_index()

    def _generate_variants(self, raw_str: str) -> Set[str]:
        """Generates morphological and punctuation variants of a model identifier."""
        if not raw_str:
            return set()

        text = raw_str.lower().strip()
        variants = set()

        # Base cleanups
        clean = re.sub(r"[^a-z0-9\s\-_/]", "", text)
        variants.add(clean)

        # Remove brand prefixes
        no_brand = re.sub(r"\b(epson|citizen|surecolor|workforce|pro|enterprise)\b", "", clean).strip()
        if no_brand:
            variants.add(no_brand)

        # Strip suffixes like DWF, RDW, D4TW, D, M, II, WN, BB, BY
        no_suffix = re.sub(r"\b(dwf|rdw|d4tw|wn|ii|bb|by)\b", "", no_brand).strip()
        if no_suffix:
            variants.add(no_suffix)

        # Expand hyphens, underscores, spaces
        expanded = set(list(variants))
        for v in expanded:
            # Without hyphens / underscores / spaces
            compact = re.sub(r"[\s\-_/]", "", v)
            if compact:
                variants.add(compact)

            # Space separated
            spaced = re.sub(r"[\-_/]", " ", v)
            spaced = re.sub(r"\s+", " ", spaced).strip()
            if spaced:
                variants.add(spaced)

            # Hyphen separated
            hyphened = re.sub(r"[\s_/]", "-", v)
            hyphened = re.sub(r"-+", "-", hyphened).strip("-")
            if hyphened:
                variants.add(hyphened)

            # Core model number (e.g. c878r, c878, f100, t3100, p900, cz01, cx02)
            # Remove "sc-", "wf-", "am-", "ds-", "es-", "cy-", "cz-", "cx-"
            core = re.sub(r"\b(sc|wf|am|ds|es|cy|cz|cx)[\s\-_]?", "", compact)
            if core and len(core) >= 3 and not core.isdigit():
                variants.add(core)

            # For workforce models: "c878r", "c878", "c5890", "c21000", "c4000", "c5000", "c6000", "c800"
            wf_core_match = re.search(r"c\d{3,5}[a-z]?", compact)
            if wf_core_match:
                wf_core = wf_core_match.group(0)
                variants.add(wf_core)
                if wf_core.endswith("r"):
                    variants.add(wf_core[:-1])  # e.g. c878 from c878r

            # For SureColor models: "f100", "f500", "t3100", "t5100", "t5405", "p700", "p900", "p5300", "p7500", "p9500"
            sc_core_match = re.search(r"[ftp]\d{3,5}[a-z]?", compact)
            if sc_core_match:
                variants.add(sc_core_match.group(0))

            # Citizen models: "cz01", "cx02", "cy02", "cx02w", "cz-01", "cx-02", "cy-02", "cx-02w"
            cit_match = re.search(r"c[xyz]\d{2}[a-z]?", compact)
            if cit_match:
                variants.add(cit_match.group(0))

        # Add brand prefixed versions for core aliases (e.g. "epson c878", "epson c878r", "citizen cz01")
        brand_name = "epson" if "epson" in clean or "wf" in clean or "sc" in clean or "am" in clean else "citizen"
        final_set = set()
        for v in variants:
            if v and len(v) >= 2:
                final_set.add(v)
                if not v.startswith(brand_name) and len(v) >= 3:
                    final_set.add(f"{brand_name} {v}")
                    final_set.add(f"{brand_name}{v}")

        return final_set

    def build_index(self):
        """Indexes every catalogue product with auto-generated variants."""
        self.exact_alias_to_product.clear()
        self.short_aliases.clear()

        products = catalogue_loader.get_all()
        for p in products:
            p_id = p.get("id", "")
            p_model = p.get("model", "")
            p_name = p.get("name", "")
            p_sku = p.get("sku", "")

            # Combine all descriptive identifier strings
            candidates = [p_id, p_model, p_name]
            if p_sku:
                candidates.append(p_sku)

            all_variants = set()
            for cand in candidates:
                all_variants.update(self._generate_variants(cand))

            for alias in all_variants:
                # Do not let overly generic words be exact aliases (e.g. "printer", "epson")
                if alias in ("printer", "printers", "epson", "citizen", "scanner", "scanners", "plotter", "plotters", "pro", "dwf", "rdw"):
                    continue
                # Store alias
                self.exact_alias_to_product[alias] = p
                if len(alias) <= 8 and not " " in alias:
                    self.short_aliases.add(alias)

    def resolve(self, text: str) -> AliasMatch:
        """
        Resolves input text to an exact product match, candidate options, or none.
        Uses exact substring match, token boundaries, and Levenshtein distance <= 2 for typos.
        """
        if not text:
            return AliasMatch(match_type="none")

        cleaned = re.sub(r"[^a-z0-9\s\-_/]", "", text.lower()).strip()
        tokens = cleaned.split()

        # 1. Exact match on whole cleaned string
        if cleaned in self.exact_alias_to_product:
            return AliasMatch(
                match_type="exact",
                product=self.exact_alias_to_product[cleaned],
                alias_matched=cleaned,
            )

        compact_all = re.sub(r"[\s\-_/]", "", cleaned)
        if compact_all in self.exact_alias_to_product:
            return AliasMatch(
                match_type="exact",
                product=self.exact_alias_to_product[compact_all],
                alias_matched=compact_all,
            )

        # 2. Exact match on multi-token phrases or single tokens (longest first)
        for n in range(min(4, len(tokens)), 0, -1):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i+n])
                if phrase in self.exact_alias_to_product:
                    return AliasMatch(
                        match_type="exact",
                        product=self.exact_alias_to_product[phrase],
                        alias_matched=phrase,
                    )
                compact_phrase = re.sub(r"[\s\-_/]", "", phrase)
                if compact_phrase in self.exact_alias_to_product:
                    return AliasMatch(
                        match_type="exact",
                        product=self.exact_alias_to_product[compact_phrase],
                        alias_matched=compact_phrase,
                    )

        # 3. Fuzzy candidate search for model-like tokens (length >= 4, contains digits or citizen/surecolor prefixes)
        # Check tokens like "cz02", "c878", "f100", etc.
        for token in tokens:
            compact_t = re.sub(r"[\s\-_/]", "", token)
            # Only test candidate typo matching on model-shaped strings (letters + digits)
            if len(compact_t) >= 4 and any(c.isdigit() for c in compact_t) and any(c.isalpha() for c in compact_t):
                # Search across short aliases with edit distance <= 2
                scored_candidates = []
                for alias, prod in self.exact_alias_to_product.items():
                    # Only check compact aliases of comparable length
                    if abs(len(alias) - len(compact_t)) <= 2 and any(c.isdigit() for c in alias):
                        dist = _levenshtein(compact_t, alias)
                        if dist <= 2:
                            # Calculate affix overlap
                            p_len = 0
                            while p_len < min(len(compact_t), len(alias)) and compact_t[p_len] == alias[p_len]:
                                p_len += 1
                            s_len = 0
                            while s_len < min(len(compact_t), len(alias)) and compact_t[-1-s_len] == alias[-1-s_len]:
                                s_len += 1
                            scored_candidates.append((dist, -(p_len + s_len), prod))

                if scored_candidates:
                    # Sort by distance first, then highest overlap
                    scored_candidates.sort(key=lambda x: (x[0], x[1]))
                    min_dist = scored_candidates[0][0]
                    best_prods = {}
                    for d, _, p in scored_candidates:
                        if d <= min_dist + 1 and p["id"] not in best_prods:
                            best_prods[p["id"]] = p

                    if len(best_prods) == 1 and min_dist <= 1:
                        # Close unique match
                        p = list(best_prods.values())[0]
                        return AliasMatch(match_type="exact", product=p, alias_matched=token)
                    elif len(best_prods) > 1:
                        top_candidates = list(best_prods.values())[:2]
                        return AliasMatch(
                            match_type="candidates",
                            candidates=top_candidates,
                            alias_matched=token,
                        )

        return AliasMatch(match_type="none")

    def match_consumables_vocab(self, word: str) -> Optional[str]:
        """
        Matches a single word or short phrase against consumables vocabulary with edit distance <= 2.
        Returns canonical category (e.g. 'consumables', 'ink', 'maintenance box', 'ribbon', 'media') or None.
        """
        w = word.lower().strip()
        if not w:
            return None

        # Exact check
        for canonical, variants in self.consumables_vocab.items():
            if w in variants:
                return canonical

        # Distance <= 2 check for strings of length >= 5
        if len(w) >= 5:
            for canonical, variants in self.consumables_vocab.items():
                for var in variants:
                    if abs(len(w) - len(var)) <= 2:
                        if _levenshtein(w, var) <= 2:
                            return canonical

        return None


# Global singleton instance
alias_index = AliasIndex()
match_consumables_vocab = alias_index.match_consumables_vocab
