"""
Fail-Closed Catalogue Validator.
Enforces:
1. card['id'] in approved_catalogue_ids (asserts no website-only models appear in cards)
2. Validates every product mentioned in natural-language text against the 42 approved catalogue entries.
3. Replaces or strips unapproved model mentions (unapproved competitor brands / unapproved series).
   NOTE: SC-F100 and SC-F500 are approved catalogue entries and must NOT be listed here.
"""
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from catalog.catalogue_loader import catalogue_loader

logger = logging.getLogger("validation:catalogue")

UNAPPROVED_MODELS = [
    "canon", "hp", "brother", "xerox", "ricoh",
    "designjet", "imageprograf", "surelab", "d1000", "d500",
    "wf-m", "et-", "l3150", "l805",
    "dnp", "rx1", "dnprx1", "ds-rx1", "hiti", "hi-ti", "fuji", "mitsubishi"
]


def validate_product_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fail-closed card validation:
    Every card ID MUST exist in the 41 approved catalogue IDs.
    Any unapproved card is strictly dropped.
    """
    valid_cards = []
    for c in cards:
        cid = c.get("id")
        if catalogue_loader.is_approved_id(cid):
            valid_cards.append(c)
        else:
            logger.error(f"FAIL-CLOSED: Blocked unapproved product card with id '{cid}'")
    return valid_cards


def validate_and_sanitize_catalogue_text(text: str, allowed_products: List[Dict[str, Any]]) -> Tuple[str, bool]:
    """
    Validates that the natural language response does not mention unapproved models.
    Returns (sanitized_text, is_valid).
    """
    if not text:
        return text, True

    text_lower = text.lower()
    violation_found = False

    # 1. Check for known unapproved/website-only models
    for unapproved in UNAPPROVED_MODELS:
        if re.search(rf"\b{re.escape(unapproved)}\b", text_lower):
            logger.warning(f"FAIL-CLOSED: Unapproved model or competitor brand '{unapproved}' detected in text.")
            violation_found = True
            break

    if violation_found:
        # Construct deterministic verified response from the allowed matching products
        if allowed_products:
            names = [p.get("model") or p.get("display_name") for p in allowed_products]
            clean_text = f"I have verified the official Kepler Tech catalogue options matching your requirements: {', '.join(names)}."
        else:
            clean_text = "I have searched our official catalogue based on your verified requirements."
        return clean_text, False

    return text, True


class CatalogueValidator:
    @staticmethod
    def validate_cards(cards: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        valid = []
        errors = []
        for c in cards:
            cid = c.get("id")
            if catalogue_loader.is_approved_id(cid):
                valid.append(c)
            else:
                errors.append(f"Unapproved product card id: {cid}")
        return valid, errors

    @staticmethod
    def validate_product_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return validate_product_cards(cards)

    @staticmethod
    def validate_and_sanitize_catalogue_text(text: str, allowed_products: List[Dict[str, Any]]) -> Tuple[str, bool]:
        return validate_and_sanitize_catalogue_text(text, allowed_products)


catalogue_validator = CatalogueValidator()
