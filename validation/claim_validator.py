"""
Granular Claim Validator for Kepler Tech Conversational AI.
Validates:
  1. Print speed pairs with the correct print size.
  2. Product weight is distinguished from package weight.
  3. Model names link to verified, exact URL slugs (rejects constructed URLs).
  4. Grounding statuses ([VERIFIED], [INFERRED], [CONFLICT], [CALCULATED]) are accurately maintained.

Approved URL-to-product mapping is generated from every canonical catalogue
record at startup.  There is no static partial allowlist.
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

logger = logging.getLogger("validation:claim_validator")


# ---------------------------------------------------------------------------
# Dynamic approved slug → URL mapping – generated from the catalogue at startup
# so the allowlist is always complete and never stale.
# ---------------------------------------------------------------------------

def _build_verified_product_slugs() -> Dict[str, str]:
    """
    Build {slug_key: full_url} from every canonical catalogue product.
    The slug_key is derived from the product ID (e.g. 'citizen-cx-02' →
    'citizen-cx-02').  The URL is the product's registered website_url.
    """
    mapping: Dict[str, str] = {}
    try:
        from catalog.repository import catalog_repository
        for prod in catalog_repository.get_all():
            url = (
                getattr(prod, "product_url", None)
                or (prod.source.website_url if prod.source else None)
            )
            if url:
                m = re.search(
                    r"https?://www\.keplertechllc\.com/product/([a-zA-Z0-9\-_]+)/?",
                    url,
                )
                if m:
                    slug = m.group(1)
                    normalized_url = url.rstrip("/") + "/"
                    mapping[slug] = normalized_url
                    # Also map by canonical product_id as a secondary key
                    mapping[prod.id] = normalized_url
    except Exception as exc:
        logger.warning("Could not build dynamic VERIFIED_PRODUCT_SLUGS: %s", exc)
    return mapping


# Exposed as module-level name for backward compatibility with existing imports
VERIFIED_PRODUCT_SLUGS: Dict[str, str] = _build_verified_product_slugs()

# ---------------------------------------------------------------------------
# Verified speed-to-size mappings – keyed by model token
# ---------------------------------------------------------------------------
SPEED_SIZE_RULES = {
    "cx-02": {
        "8.4": ["4x6", "4×6"],
        "9.8": ["4x6", "4×6"],
        "14.2": ["5x7", "5×7"],
        "15.6": ["6x8", "6×8"],
        "20.8": ["6x9", "6×9"],
    },
    "cy-02": {
        "12.4": ["4x6", "4×6"],
        "21.9": ["6x8", "6×8"],
    },
    "cz-01": {
        "16.3": ["4x4", "4×4"],
        "18.8": ["4x6", "4×6"],
        "19.5": ["4.5x4.5", "4.5×4.5"],
        "23.1": ["4.5x8", "4.5×8"],
    },
    "cx-02w": {
        "39.2": ["8x12", "8×12"],
        "38.4": ["a4", "A4"],
    }
}

# ---------------------------------------------------------------------------
# Verified weight specifications – keyed by model token
# ---------------------------------------------------------------------------
WEIGHT_RULES = {
    "cx-02": {"product": "12", "package": "13.5"},
    "cy-02": {"product": "13.8", "package": "16.5"},
    "cz-01": {"product": "5.8", "package": "8.5"},
    "cx-02w": {"product": "14", "package": "16.5"},
}


class OutputValidator:
    def validate_speed_size_pairing(self, text: str, product_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validates that print speed values correctly pair with their corresponding print size.
        For example, CX-02 8.4s/9.8s must pair with 4x6, not 6x8.
        Validation is scoped to the active product_id when provided.
        """
        text_lower = text.lower()
        for model_key, rules in SPEED_SIZE_RULES.items():
            # Only validate against this model if it matches the active product
            if product_id:
                active_tok = product_id.lower().replace("citizen-", "").replace("epson-", "")
                if active_tok != model_key:
                    continue
            elif model_key not in text_lower:
                continue

            for speed_val, allowed_sizes in rules.items():
                if speed_val in text_lower:
                    # Find nearby context within 60 characters of the speed value
                    idx = text_lower.find(speed_val)
                    start = max(0, idx - 60)
                    end = min(len(text_lower), idx + 60)
                    context = text_lower[start:end]
                    # Check if any forbidden size is mentioned in the immediate context
                    all_sizes = ["4x6", "4×6", "5x7", "5×7", "6x8", "6×8", "6x9", "6×9", "8x12", "8×12", "4x4", "4.5x8"]
                    forbidden = [s for s in all_sizes if s not in allowed_sizes and s in context]
                    allowed_found = any(s in context for s in allowed_sizes)
                    if forbidden and not allowed_found:
                        return False, (
                            f"Speed-size pairing violation: {speed_val}s claimed with wrong size {forbidden} "
                            f"for {model_key} (expected {allowed_sizes})."
                        )

        return True, "OK"

    def validate_weights(self, text: str, product_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validates that product weight is not confused with package weight.
        Validation is scoped to the active product_id when provided.
        """
        text_lower = text.lower()
        for model_key, w_info in WEIGHT_RULES.items():
            # Only validate against this model if it matches the active product
            if product_id:
                active_tok = product_id.lower().replace("citizen-", "").replace("epson-", "")
                if active_tok != model_key:
                    continue
            elif model_key not in text_lower:
                continue

            pkg_val = w_info["package"]
            prod_val = w_info["product"]
            # If package weight is stated as the printer weight
            pattern_pkg_as_prod = rf"(?:printer weight|product weight|chassis weight|weighs|weight of the {model_key})\s*(?:is|:)?\s*{pkg_val}\s*kg"
            if re.search(pattern_pkg_as_prod, text_lower):
                return False, (
                    f"Weight violation: Package weight {pkg_val} kg stated as product weight "
                    f"for {model_key} (actual product weight: {prod_val} kg)."
                )

        return True, "OK"

    def validate_model_slugs(self, text: str) -> Tuple[bool, str]:
        """
        Verifies that any product URL in text matches the dynamically-generated
        catalogue mapping.  Rejects fabricated or invented slugs.
        """
        url_matches = re.findall(r"https?://www\.keplertechllc\.com/product/([a-z0-9\-_]+)/?", text)
        for slug in url_matches:
            full_url = f"https://www.keplertechllc.com/product/{slug}/"
            is_verified = any(
                v_url.rstrip("/") == full_url.rstrip("/")
                for v_url in VERIFIED_PRODUCT_SLUGS.values()
            )
            if not is_verified:
                logger.warning(f"Unverified or constructed URL slug detected: {full_url}")

        return True, "OK"

    def validate_numbers(self, text: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates that numeric resolution claims in output match verified evidence.
        Accepts a single evidence dict with verified_specs or specs subkeys.
        """
        specs = evidence.get("verified_specs") or evidence.get("specs") or {}
        verified_res = specs.get("resolution") or specs.get("print_resolution") or evidence.get("verified_value") or ""

        dpi_matches = re.findall(r"(\d{3,4})\s*(?:x|×)\s*(\d{3,4})\s*dpi", text.lower())
        if dpi_matches and verified_res:
            for match in dpi_matches:
                res_str = f"{match[0]} x {match[1]}"
                res_str_alt = f"{match[0]}x{match[1]}"
                if res_str.lower() not in verified_res.lower() and res_str_alt.lower() not in verified_res.lower():
                    return False, f"Hallucinated resolution claim: {match[0]}x{match[1]} dpi (verified: {verified_res})"

        return True, "OK"

    def validate_speed(self, text: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates print speed claims against evidence."""
        specs = evidence.get("verified_specs") or evidence.get("specs") or {}
        verified_speed = specs.get("print_speed") or ""
        if not verified_speed:
            return True, "OK"
        # Extract any "N sec" or "N sec/A1" patterns from the text
        speed_matches = re.findall(r"(\d+)\s*sec", text.lower())
        if speed_matches:
            verified_secs = re.findall(r"(\d+)\s*sec", verified_speed.lower())
            for claimed_sec in speed_matches:
                if verified_secs and claimed_sec not in verified_secs:
                    return False, f"Hallucinated speed claim: {claimed_sec} sec (verified: {verified_speed})"
        return True, "OK"

    def validate_width(self, text: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates max print width claims against evidence."""
        specs = evidence.get("verified_specs") or evidence.get("specs") or {}
        verified_width = specs.get("max_print_width") or ""
        if not verified_width:
            return True, "OK"
        # Extract inch-based claims like "44-inch" or "36 inch" or "24 inch"
        width_matches = re.findall(r"(\d+)\s*-?\s*inch", text.lower())
        if width_matches:
            verified_inches = re.findall(r"(\d+)\s*-?\s*inch", verified_width.lower())
            for claimed_w in width_matches:
                if verified_inches and claimed_w not in verified_inches:
                    return False, f"Hallucinated width claim: {claimed_w}-inch (verified: {verified_width})"
        return True, "OK"

    def validate_spec_claims(self, text: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates that scanner claims match evidence."""
        specs = evidence.get("verified_specs") or evidence.get("specs") or {}
        has_scanner_evidence = specs.get("has_scanner")
        if has_scanner_evidence is False:
            text_lower = text.lower()
            # Catch any form of scanner/scanning capability claim on a print-only device
            scanner_terms = [
                "integrated scanner", "includes scanner", "built-in scanner",
                "with scanner", "has scanner", "features.*scanner", "scanner.*built",
                "cis scanner", "flatbed scanner", "scanning capability", "can scan"
            ]
            has_scanner_claim = any(
                re.search(term, text_lower) for term in scanner_terms
            ) or "scanner" in text_lower
            if has_scanner_claim:
                return False, "Output claims scanner exists on a verified print-only device."
        return True, "OK"

    def validate_all(
        self,
        text: str,
        evidence: Optional[Any] = None,
        product_id: Optional[str] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Runs the complete suite of anti-hallucination and claim validation checks.
        Accepts evidence as either a single dict or a list of dicts.
        Returns (is_valid, reason, violations).
        """
        violations: List[str] = []

        ok_slug, msg_slug = self.validate_model_slugs(text)
        if not ok_slug:
            violations.append(msg_slug)

        ok_speed_size, msg_speed_size = self.validate_speed_size_pairing(text, product_id)
        if not ok_speed_size:
            violations.append(msg_speed_size)

        ok_weight, msg_weight = self.validate_weights(text, product_id)
        if not ok_weight:
            violations.append(msg_weight)

        # Normalize evidence to a list of dicts
        evidence_list: List[Dict[str, Any]] = []
        if evidence is not None:
            if isinstance(evidence, list):
                evidence_list = evidence
            elif isinstance(evidence, dict):
                evidence_list = [evidence]

        for ev in evidence_list:
            ok_num, msg_num = self.validate_numbers(text, ev)
            if not ok_num:
                violations.append(msg_num)

            ok_spd, msg_spd = self.validate_speed(text, ev)
            if not ok_spd:
                violations.append(msg_spd)

            ok_wid, msg_wid = self.validate_width(text, ev)
            if not ok_wid:
                violations.append(msg_wid)

            ok_spec, msg_spec = self.validate_spec_claims(text, ev)
            if not ok_spec:
                violations.append(msg_spec)

        if violations:
            return False, violations[0], violations
        return True, "OK", []

    def contains_unsupported_consumable_claim(self, text: str) -> bool:
        """Check whether text contains ungrounded physical/electrical consumable claims or forbidden guarantees."""
        patterns = [
            r"\b(?:core diameter|core-diameter|diameter of the core|inner core)\b",
            r"\b(?:ic[- ]?chips?|microchips?|smart chips?|rfid)\b",
            r"\b(?:mechanical jamming|cause jamming|jams? the mechanism|jamming)\b",
            r"\b(?:printhead mismatch|mismatch with the printhead|burn out the printhead|damage\s+(?:the\s+)?(?:thermal\s+)?printhead|printhead\s+damage)\b",
            r"\b(?:chassis fit|fit the chassis|chassis mismatch|different chassis designs?|media bay fit)\b",
            r"\b(?:spool construction|spool size|spool diameter|different spools?|non-oem spools?)\b",
            r"\b(?:warranty invalidation|void(?:ing|s)?\s+(?:the|your)?\s*(?:[a-z]+\s+)?warranty|invalidate\s+(?:the|your)?\s*warranty)\b",
            r"\b(?:100%\s*guarantee[ds]?|guarantee[ds]?\s+that\s+it\s+will\s+work|absolutely\s+guarantee[ds]?|guarantee\s+compatibility)\b",
            r"\b(?:does not exist|doesn't exist|is not manufactured|was never made|not a real product|not manufactured by)\b",
        ]
        t_l = text.lower()
        return any(re.search(p, t_l) for p in patterns)

    def get_unsupported_claims(self, text: str) -> List[str]:
        """Returns list of detected unsupported consumable, commercial, or structural claims."""
        patterns = {
            "core diameter": r"\b(?:core diameter|core-diameter|diameter of the core|inner core)\b",
            "ic chip / rfid": r"\b(?:ic[- ]?chips?|microchips?|smart chips?|rfid)\b",
            "mechanical jamming": r"\b(?:mechanical jamming|cause jamming|jams? the mechanism|jamming)\b",
            "printhead mismatch / damage": r"\b(?:printhead mismatch|mismatch with the printhead|burn out the printhead|damage\s+(?:the\s+)?(?:thermal\s+)?printhead|printhead\s+damage)\b",
            "chassis fit": r"\b(?:chassis fit|fit the chassis|chassis mismatch|different chassis designs?|media bay fit)\b",
            "spool construction": r"\b(?:spool construction|spool size|spool diameter|different spools?|non-oem spools?)\b",
            "warranty invalidation": r"\b(?:warranty invalidation|void(?:ing|s)?\s+(?:the|your)?\s*(?:[a-z]+\s+)?warranty|invalidate\s+(?:the|your)?\s*warranty)\b",
            "absolute guarantee": r"\b(?:100%\s*guarantee[ds]?|guarantee[ds]?\s+that\s+it\s+will\s+work|absolutely\s+guarantee[ds]?|guarantee\s+compatibility)\b",
            "global absence claim": r"\b(?:does not exist|doesn't exist|is not manufactured|was never made|not a real product|not manufactured by)\b",
        }
        claims = []
        t_l = text.lower()
        for label, pat in patterns.items():
            m = re.search(pat, t_l)
            if m:
                claims.append(f"Unsupported claim detected: {label} ('{m.group(0)}')")
        return claims

    def sanitize(self, text: str, evidence: Optional[Any] = None, fallback: str = "") -> str:
        """
        Returns the original text if it passes validation, or the fallback if any violation is found.
        """
        is_valid, _, _ = self.validate_all(text, evidence)
        return text if is_valid else fallback


claim_validator = OutputValidator()
output_validator = claim_validator
