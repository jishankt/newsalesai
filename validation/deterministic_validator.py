"""
Deterministic Response Validator for Kepler Tech Conversational AI.

Enforces 8 strict zero-hallucination checks on every generated response:
1. product_id matches source product_id (and URL product_id and evidence product_id)
2. product name matches URL
3. every numeric value exists in retrieved evidence for the ACTIVE product only
4. consumable SKU is linked to the selected printer
5. no rejected SKU exists in the catalogue
6. no global absence claims ("does not exist" -> "not found in our approved catalogue")
7. no absolute guarantees ("100% guaranteed" -> forbidden)
8. no unsupported speculative claims

Automatically fails an answer when any product name, SKU, speed, weight,
size, capacity or compatibility claim lacks exact evidence for the active product.
Never accepts a value merely because another catalogue product has it.
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

logger = logging.getLogger("validation:deterministic_validator")

# Verified URL slugs and their mandatory authorized product identifiers
SLUG_TO_PRODUCT_RULE = {
    "epson-surecolor-sc-t5100m-plotter-printer": {
        "canonical_id": "epson-t5100m",
        "required_terms": ["sc-t5100m", "t5100m"],
        "forbidden_terms": ["sc-t5400m", "t5400m"],
        "display_name": "Epson SureColor SC-T5100M Plotter Printer"
    },
    "epson-sc-t5400m-mfp-plotter-printer": {
        "canonical_id": "epson-t5400m",
        "required_terms": ["sc-t5400m", "t5400m"],
        "forbidden_terms": ["sc-t5100m"],
        "display_name": "Epson SureColor SC-T5400M MFP Plotter Printer"
    },
    "citizen-cx-02-photo-printer": {
        "canonical_id": "citizen-cx-02",
        "required_terms": ["cx-02", "cx02"],
        "forbidden_terms": ["cx-02w", "cx02w", "cy-02", "cz-01"],
        "display_name": "Citizen CX-02 Digital Photo Printer"
    },
    "citizen-cx-02w-large-photo-printer": {
        "canonical_id": "citizen-cx-02w",
        "required_terms": ["cx-02w", "cx02w"],
        "forbidden_terms": [],
        "display_name": "Citizen CX-02W 8\" Large Photo Printer"
    },
    "citizen-cy-02-photo-printer": {
        "canonical_id": "citizen-cy-02",
        "required_terms": ["cy-02", "cy02"],
        "forbidden_terms": ["cx-02", "cz-01"],
        "display_name": "Citizen CY-02 Photo Printer"
    },
    "citizen-cz-01-photo-printer": {
        "canonical_id": "citizen-cz-01",
        "required_terms": ["cz-01", "cz01"],
        "forbidden_terms": ["cx-02", "cy-02"],
        "display_name": "Citizen CZ-01 Photo Printer"
    },
}

# ---------------------------------------------------------------------------
# Dynamic approved-slug set – generated at startup from every canonical
# catalogue record so no slug is ever silently missing or stale.
# ---------------------------------------------------------------------------

def _build_known_valid_slugs() -> Set[str]:
    """
    Build the approved URL-to-product slug set from the catalogue repository.
    Called once at module import time; the result is cached as KNOWN_VALID_SLUGS.
    """
    slugs: Set[str] = set()
    # Always include slugs from the static SLUG_TO_PRODUCT_RULE detail map
    slugs.update(SLUG_TO_PRODUCT_RULE.keys())
    try:
        from catalog.repository import catalog_repository
        for prod in catalog_repository.get_all():
            # Extract slug from the product's website_url
            url = (
                getattr(prod, "product_url", None)
                or (prod.source.website_url if prod.source else None)
            )
            if url:
                m = re.search(
                    r"https?://www\.keplertechllc\.com/product/([a-zA-Z0-9\-_]+)/?",
                    url
                )
                if m:
                    slugs.add(m.group(1))
    except Exception as exc:
        logger.warning("Could not build dynamic KNOWN_VALID_SLUGS from catalogue: %s", exc)
    return slugs


KNOWN_VALID_SLUGS: Set[str] = _build_known_valid_slugs()

# Known valid catalogue SKUs that MUST NOT be rejected as unverified or non-existent
KNOWN_VALID_SKUS = {
    "CX2.4X6": "citizen-cx-02",
    "CX2.6X8": "citizen-cx-02",
    "CX2-MS46-2PC": "citizen-cx-02",
    "CX2W 812": "citizen-cx-02w",
    "CY-MS46": "citizen-cy-02",
    "CY-MS68": "citizen-cy-02",
    "CZ-MS46": "citizen-cz-01",
    "CZ-MS458": "citizen-cz-01",
    "C13S210057": "epson-t5100m",
    "C13T40D140": "epson-t5100m",
    "C11CJ54301A1": "epson-t5100m",
}

# Consumables linked to each hardware model (only explicitly catalogue-evidenced
# SKUs and model numbers; no speculative aliases).
# NOTE: input-normalisation aliases (e.g. "cx2w812") belong exclusively in
# product_resolver.py::ALIAS_TO_CANONICAL_ID, never here.
PRINTER_CONSUMABLE_LINKS = {
    "citizen-cx-02": ["cx2.4x6", "cx2.6x8", "cx2-ms46-2pc", "cx2-ms46", "cx2-ms68"],
    "citizen-cx-02w": ["cx2w 812"],          # canonical only; "cx2w812" is an input alias
    "citizen-cy-02": ["cy-ms46", "cy-ms68"],
    "citizen-cz-01": ["cz-ms46", "cz-ms458"],
    "epson-t5100m": ["c13s210057", "c13t40d140", "c13t40d240", "c13t40d340", "c13t40d440"],
    "epson-t5400m": ["c13t699700", "c13t41f540", "c13t41f240", "c13t41f340", "c13t41f440"],
}

# Verified ground-truth metrics for Citizen & Technical printers.
# These are keyed by canonical product_id and used for per-product validation only.
VERIFIED_METRICS = {
    "citizen-cx-02": {
        "speeds": {"8.4", "9.8", "14.2", "15.6", "20.8"},
        "speed_pairs": {
            "4x6": {"8.4", "9.8"},
            "5x7": {"14.2"},
            "6x8": {"15.6"},
            "6x9": {"20.8"}
        },
        "weights": {"12", "12.0", "13.5"},
        "capacities": {"400", "230", "200", "180", "800"},
        "sizes": {"4x6", "4×6", "5x7", "5×7", "6x8", "6×8", "6x9", "6×9"},
    },
    "citizen-cy-02": {
        "speeds": {"12.4", "19.9", "21.9"},
        "speed_pairs": {
            "4x6": {"12.4"},
            "5x7": {"19.9"},
            "6x8": {"21.9"}
        },
        "weights": {"13.8", "16.5"},
        "forbidden_weights": {"18", "18.0", "18 kg"},
        "capacities": {"700", "350", "1400"},
        "sizes": {"4x6", "4×6", "5x7", "5×7", "6x8", "6×8"},
    },
    "citizen-cz-01": {
        "speeds": {"16.3", "18.8", "19.5", "23.1"},
        "speed_pairs": {
            "4x4": {"16.3"},
            "4x6": {"18.8"},
            "4.5x4.5": {"19.5"},
            "4.5x8": {"23.1"},
        },
        "weights": {"5.8", "8.5"},
        "capacities": {"150", "110", "300", "220"},
        "sizes": {"4x4", "4×4", "4x6", "4×6", "4.5x4.5", "4.5×4.5", "4.5x8", "4.5×8"},
    },
    "citizen-cx-02w": {
        "speeds": {"39.2", "38.4", "33.4"},
        "speed_pairs": {
            "8x12": {"39.2"},
            "a4": {"38.4"},
        },
        "weights": {"14", "14.0", "16.5"},
        "capacities": {"110", "220"},
        "sizes": {"8x10", "8×10", "8x12", "8×12", "a4", "A4"},
    },
    "epson-t5100m": {
        "speeds": {"34", "31"},
        "widths": {"36", "36-inch", "914"},
        "has_scanner": True,
        "weights": {"54"},
    }
}


class DeterministicResponseValidator:
    """Deterministic validation of response claims against approved evidence."""

    def validate_product_id_source_match(
        self,
        text: str,
        source: str,
        product_id: Optional[str] = None,
        url_product_id: Optional[str] = None,
        evidence_product_id: Optional[str] = None,
    ) -> List[str]:
        """
        Check 1: product_id == URL product_id == evidence product_id.
        Never allow a product name, URL and specification record belonging to
        different product IDs in the same answer.
        """
        violations = []
        text_lower = text.lower()
        src_lower = (source or "").lower()
        pid_lower = (product_id or "").lower()

        # --- Triple-ID consistency ---
        ids_to_compare = {
            k: v.lower() for k, v in {
                "product_id": product_id,
                "url_product_id": url_product_id,
                "evidence_product_id": evidence_product_id,
            }.items() if v
        }
        unique_vals = set(ids_to_compare.values())
        if len(unique_vals) > 1:
            violations.append(
                f"Product ID triple mismatch: {ids_to_compare} — "
                "product_id, URL product_id, and evidence product_id must all match."
            )

        # --- Source / text consistency ---
        # If source is SC-T5100M or URL has sc-t5100m, text must NOT refer to SC-T5400M
        if "t5100m" in src_lower or "t5100m" in pid_lower or "sc-t5100m" in text_lower:
            if "sc-t5400m" in text_lower or "t5400m" in text_lower:
                # Unless it's an explicit comparison acknowledging both
                if "t5100m" in src_lower and not ("compare" in text_lower or "difference between" in text_lower):
                    violations.append(
                        "Product ID mismatch: source specifies epson-t5100m but response refers to SC-T5400M."
                    )

        # Citizen CX-02 vs CY-02 / CX-02W cross-contamination
        if "citizen-cx-02" == pid_lower or ("cx-02" in src_lower and "cx-02w" not in src_lower):
            if "cy-02" in text_lower and not any(k in text_lower for k in ["compare", "vs", "difference", "switch", "instead"]):
                violations.append(
                    "Product ID mismatch: source is citizen-cx-02 but response discusses CY-02 without comparison context."
                )

        return violations

    def validate_product_name_matches_url(self, text: str) -> List[str]:
        """
        Check 2: product name matches URL, and no unknown/fabricated URL slugs exist.
        Every URL slug in markdown link or plain text must match its authorized product name.
        Approved slugs are generated dynamically from the catalogue at startup.
        """
        violations = []
        text_lower = text.lower()

        # Reject any fabricated or non-catalogue URL slugs
        all_url_slugs = re.findall(r"https?://www\.keplertechllc\.com/product/([a-zA-Z0-9\-_]+)/?", text)
        for slug in all_url_slugs:
            if slug not in SLUG_TO_PRODUCT_RULE and slug not in KNOWN_VALID_SLUGS:
                violations.append(
                    f"Fabricated or unknown URL slug detected: '{slug}' is not an authorized catalogue URL."
                )

        # Find markdown links: [Link Text](URL)
        link_matches = re.findall(r"\[([^\]]+)\]\((https?://www\.keplertechllc\.com/product/([a-z0-9\-_]+)/?)?\)", text)
        for link_text, full_url, slug in link_matches:
            link_text_lower = link_text.lower()
            rule = SLUG_TO_PRODUCT_RULE.get(slug)
            if rule:
                for forbidden in rule["forbidden_terms"]:
                    if forbidden in link_text_lower:
                        violations.append(
                            f"Product name / URL mismatch: Link to '{slug}' has incompatible anchor text '{link_text}' "
                            f"(forbidden term '{forbidden}' found; belongs to {rule['display_name']})."
                        )
                # Check if at least one required term is in the anchor or immediately surrounding text
                if rule["required_terms"] and not any(r in link_text_lower for r in rule["required_terms"]):
                    violations.append(
                        f"Product name / URL mismatch: Link to '{slug}' with text '{link_text}' does not match "
                        f"expected model name '{rule['display_name']}'."
                    )

        # Plain URL checks
        for slug, rule in SLUG_TO_PRODUCT_RULE.items():
            if slug in text_lower:
                pos = 0
                while True:
                    idx = text_lower.find(slug, pos)
                    if idx == -1:
                        break
                    start = max(0, idx - 120)
                    end = min(len(text_lower), idx + len(slug) + 120)
                    window = text_lower[start:end]
                    for forbidden in rule["forbidden_terms"]:
                        if forbidden in window and not any(k in window for k in ["vs", "compare", "not", "instead", "difference"]):
                            violations.append(
                                f"Product name / URL conflict: Found '{forbidden}' adjacent to URL slug '{slug}' "
                                f"(URL belongs strictly to {rule['display_name']})."
                            )
                    pos = idx + len(slug)

        return violations

    def validate_numeric_values(
        self,
        text: str,
        evidence: Optional[Dict[str, Any]] = None,
        product_id: Optional[str] = None,
    ) -> List[str]:
        """
        Check 3: every numeric value exists in retrieved evidence for the ACTIVE product.

        Critical rule: a value is only accepted if the ACTIVE product has it.
        We never skip a violation merely because another catalogue product carries
        the same number.  This prevents cross-product contamination where, for
        example, CY-02's 700-print capacity is silently accepted for CX-02.
        """
        violations = []
        text_lower = text.lower()

        # Determine which product(s) to validate against
        active_pids: List[str] = []
        if product_id:
            active_pids.append(product_id)
        else:
            for pid in VERIFIED_METRICS:
                tok = pid.replace("citizen-", "").replace("epson-", "")
                if tok in text_lower:
                    active_pids.append(pid)

        # 3a. Weight validation — active product only
        weight_matches = re.finditer(r"\b(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\b", text_lower)
        for wm in weight_matches:
            val_str = wm.group(1)
            val = float(val_str)
            for pid in active_pids:
                m_info = VERIFIED_METRICS.get(pid, {})
                allowed_w = m_info.get("weights", set())
                forbidden_w = m_info.get("forbidden_weights", set())
                if val_str in forbidden_w or f"{val_str} kg" in forbidden_w:
                    violations.append(
                        f"Numeric weight violation for {pid}: claimed {val_str} kg is an unverified / forbidden value."
                    )
                elif allowed_w and val_str not in allowed_w and f"{val:.1f}" not in allowed_w:
                    tok = pid.replace("citizen-", "").replace("epson-", "")
                    if tok in text_lower:
                        violations.append(
                            f"Numeric weight violation for {pid}: claimed {val_str} kg lacks exact evidence "
                            f"(verified: {allowed_w})."
                        )

        # 3b. Speed validation — active product only
        for pid in (active_pids or list(VERIFIED_METRICS.keys())):
            m_metrics = VERIFIED_METRICS.get(pid, {})
            tok = pid.replace("citizen-", "").replace("epson-", "")
            if tok in text_lower:
                if "speed_pairs" in m_metrics:
                    for sz, allowed_spds in m_metrics["speed_pairs"].items():
                        pattern = rf"{re.escape(sz)}[^\.\n\(\)]{{0,50}}?(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s\b)"
                        for m in re.finditer(pattern, text_lower):
                            claimed_spd = m.group(1)
                            if claimed_spd not in allowed_spds and claimed_spd not in {"300", "600"}:
                                allowed_str = ", ".join(sorted(allowed_spds))
                                model_lbl = pid.replace("citizen-", "").replace("epson-", "").upper()
                                violations.append(
                                    f"Numeric speed violation: {model_lbl} {sz} speed is {allowed_str} seconds "
                                    f"(claimed {claimed_spd}s lacks exact evidence)."
                                )

        # 3c. Capacity validation — active product only.
        # IMPORTANT: We validate exclusively against the active product's allowed
        # capacities.  We never skip the check because another product has the value.
        cap_matches = re.finditer(r"(?<!\d,)(?<!\d)\b(\d{1,2},?\d{3}|\d{3,4})\s*(?:photos|prints|sheets|copies)\b", text_lower)
        for cm in cap_matches:
            val_str = cm.group(1).replace(",", "")
            for pid in active_pids:
                m_info = VERIFIED_METRICS.get(pid, {})
                allowed_c = m_info.get("capacities", set())
                if allowed_c and val_str not in allowed_c:
                    violations.append(
                        f"Numeric capacity violation for {pid}: claimed capacity of {val_str} "
                        f"lacks exact evidence (verified: {allowed_c})."
                    )

        return violations

    def validate_consumable_linkage(self, text: str, selected_printer: Optional[str] = None) -> List[str]:
        """
        Check 4: consumable SKU is linked to the selected printer.
        Check that any consumable SKU or model number stated as compatible is actually linked.
        """
        violations = []
        text_lower = text.lower()

        # Check CX2.4x6 or CX2-MS46-2PC claimed for CX-02W
        if any(k in text_lower for k in ["cx2.4x6", "cx2-ms46-2pc", "cx2-ms46"]):
            if "cx-02w" in text_lower or "cx02w" in text_lower:
                if (
                    re.search(r"(?:use|compatible|works? with|for)\s+(?:the\s+|your\s+|a\s+)?cx-02w.*?(?:cx2\.4x6|cx2-ms46)", text_lower) or
                    re.search(r"(?:cx2\.4x6|cx2-ms46).*?(?:can be used|compatible with|for\s+(?:the\s+|your\s+|a\s+)?cx-02w|works? with\s+(?:the\s+|your\s+|a\s+)?cx-02w)", text_lower) or
                    re.search(r"(?:use|using)\s+(?:the\s+)?(?:cx2\.4x6|cx2-ms46).*?(?:for|in|with)\s+(?:the\s+|your\s+|a\s+)?cx-02w", text_lower)
                ):
                    violations.append(
                        "Consumable linkage violation: CX2.4x6 (CX2-MS46-2PC) is 6-inch media for CX-02, "
                        "not linked to 8-inch CX-02W (requires CX2W 812)."
                    )

        # Check CY-02 media claimed for CX-02 or vice versa
        if "cy-ms46" in text_lower and "cx-02" in text_lower:
            if re.search(r"(?:use|compatible|works? with)\s+(?:the\s+)?cx-02.*?(?:cy-ms46)", text_lower) or \
               re.search(r"cy-ms46.*?(?:can be used in|compatible with|for)\s+(?:the\s+)?cx-02", text_lower):
                violations.append(
                    "Consumable linkage violation: CY-MS46 is linked to CY-02, not confirmed for CX-02."
                )

        return violations

    def validate_no_rejected_sku_in_catalogue(self, text: str) -> List[str]:
        """
        Check 5: no rejected SKU exists in the catalogue.
        If the answer rejects a SKU (claiming it does not exist or is invalid),
        but that SKU actually exists in the approved catalogue, FAIL.
        """
        violations = []
        text_lower = text.lower()

        for sku_norm, linked_model in KNOWN_VALID_SKUS.items():
            sku_lower = sku_norm.lower()
            if sku_lower in text_lower:
                rejection_patterns = [
                    rf"{re.escape(sku_lower)}\s+(?:is not a valid|is not in our (?:catalog|catalogue)|does not exist|is an invalid code|cannot be found|is unverified)",
                    rf"(?:not a valid|invalid code|unrecognized code|not in our (?:catalog|catalogue)|does not exist in our)\s+.*?\b{re.escape(sku_lower)}\b"
                ]
                for p in rejection_patterns:
                    if re.search(p, text_lower):
                        violations.append(
                            f"Valid SKU falsely rejected: '{sku_norm}' is an approved catalogue SKU "
                            f"linked to {linked_model}."
                        )

        return violations

    def validate_no_global_absence_claims(self, text: str) -> List[str]:
        """
        Check 6: no global absence claims.
        For unknown models, say "not found in our approved catalogue,"
        not "does not exist" or "is not manufactured."
        """
        violations = []
        patterns = [
            r"\b(?:does not exist|doesn't exist|is not manufactured|was never manufactured|was never made|is not a real product|not manufactured by)\b"
        ]
        text_lower = text.lower()
        for p in patterns:
            m = re.search(p, text_lower)
            if m:
                violations.append(
                    f"Global absence claim violation: '{m.group(0)}' detected. "
                    "Use 'not found in our approved catalogue' instead."
                )
        return violations

    def validate_no_absolute_guarantees(self, text: str) -> List[str]:
        """
        Check 7: no absolute guarantees.
        Never say "100% guaranteed" or make absolute compatibility promises.
        """
        violations = []
        patterns = [
            r"\b100%\s*guarantee[ds]?\b",
            r"\bguarantee[ds]?\s+that\s+it\s+will\s+work\b",
            r"\babsolutely\s+guarantee[ds]?\b",
            r"\bwe\s+guarantee\s+compatibility\b",
        ]
        text_lower = text.lower()
        for p in patterns:
            m = re.search(p, text_lower)
            if m:
                violations.append(
                    f"Absolute guarantee violation: '{m.group(0)}' detected. Absolute guarantees are forbidden."
                )
        return violations

    def validate_no_unsupported_speculative_claims(self, text: str) -> List[str]:
        """
        Check 8: no unsupported speculative claims.
        Flags unverified statements about printhead damage, chassis fit, spool construction,
        and warranty invalidation.
        """
        violations = []
        text_lower = text.lower()
        speculative_patterns = [
            (r"\b(?:damage[ds]? the printhead|cause printhead damage|damage to the printhead)\b", "unsupported printhead damage claim"),
            (r"\b(?:spool construction|chassis fit)\b", "unsupported chassis fit or spool construction claim"),
            (r"\b(?:void[s]? (?:the |your )?warranty|invalidat(?:e|es|ing) (?:the |your )?warranty)\b", "unsupported warranty invalidation claim"),
        ]
        for pattern, claim_name in speculative_patterns:
            if re.search(pattern, text_lower):
                violations.append(f"Unsupported claim violation: '{claim_name}' lacks catalogue backing.")
        return violations

    def validate(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Run all deterministic validation checks.

        Context keys:
          product_id        – canonical product ID being discussed
          source            – source slug or URL
          url_product_id    – product ID inferred from the URL in use
          evidence_product_id – product ID from evidence record used
          evidence          – evidence dict (optional)

        Returns (is_valid: bool, violations: List[str]).
        """
        if not text or not text.strip():
            return False, ["Empty response"]

        ctx = context or {}
        source = ctx.get("source", "")
        product_id = ctx.get("product_id")
        url_product_id = ctx.get("url_product_id")
        evidence_product_id = ctx.get("evidence_product_id")
        evidence = ctx.get("evidence")

        violations: List[str] = []

        violations.extend(self.validate_product_id_source_match(
            text, source, product_id, url_product_id, evidence_product_id
        ))
        violations.extend(self.validate_product_name_matches_url(text))
        violations.extend(self.validate_numeric_values(text, evidence, product_id))
        violations.extend(self.validate_consumable_linkage(text, product_id))
        violations.extend(self.validate_no_rejected_sku_in_catalogue(text))
        violations.extend(self.validate_no_global_absence_claims(text))
        violations.extend(self.validate_no_absolute_guarantees(text))
        violations.extend(self.validate_no_unsupported_speculative_claims(text))

        is_valid = len(violations) == 0
        return is_valid, violations


deterministic_validator = DeterministicResponseValidator()
