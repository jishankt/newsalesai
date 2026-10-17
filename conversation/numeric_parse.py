"""
Numeric and budget parser for customer messages.
Single source of truth used by both conversation/understanding.py and conversation/product_flows.py.
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass

# Mapping for Arabic-Indic and Eastern Arabic-Indic (Persian) digits
ARABIC_INDIC_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

CURRENCY_PATTERN = r"(?:aed|dhs?|dh|dirhams?|د\.إ|درهم|دراهم)"
BUDGET_KEYWORD_PATTERN = (
    r"(?:budget|under|below|max|maximum|up\s*to|within|not\s*more\s*than|"
    r"less\s*than|around|about|upto|ميزانية|ميزانيتي|ميزانيتنا|حد\s*أقصى|اقصى|أقصى|اقل\s*من|أقل\s*من|تحت)"
)

# Units that disqualify a number from being a budget
NON_BUDGET_UNITS_PATTERN = (
    r"(?:pages?|prints?|sheets?|daily|day|week|month|inch|inches|in|\"|"
    r"cm|mm|dpi|ppm|kg|hz|watts?|rolls?|units?|pcs?|pieces?|printers?|"
    r"machines?|scanners?|items?|cartridges?)"
)


@dataclass
class BudgetParseResult:
    budget_ceiling: Optional[float] = None
    budget_floor: Optional[float] = None
    budget_scope: Optional[str] = None  # "total", "per_unit", "unspecified"
    currency: str = "AED"
    raw_match: str = ""


def normalize_digits(text: str) -> str:
    """Converts Arabic-Indic and Persian digits to standard ASCII digits."""
    if not text:
        return ""
    return text.translate(ARABIC_INDIC_TRANS)


def parse_number_with_suffix(val_str: str) -> Optional[float]:
    """
    Parses a numeric string that may contain 'k', 'K', 'lakh', or 'lac'.
    Examples:
      '10k' -> 10000.0
      '2.5k' -> 2500.0
      '10' -> 10.0
    """
    if not val_str:
        return None
    val_str = val_str.strip().lower()
    val_str = val_str.replace(",", "")

    # Lakh / Lac
    lakh_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:lakhs?|lacs?)$", val_str)
    if lakh_match:
        return float(lakh_match.group(1)) * 100000.0

    # K suffix
    k_match = re.match(r"^(\d+(?:\.\d+)?)\s*k$", val_str)
    if k_match:
        return float(k_match.group(1)) * 1000.0

    try:
        return float(val_str)
    except ValueError:
        return None


def extract_budget(text: str) -> Optional[BudgetParseResult]:
    """
    Extracts budget constraints from user text.
    Enforces rules:
    - Normalises Arabic-Indic and Persian digits, strips commas.
    - Requires either an explicit budget keyword OR adjacent currency token.
    - Ranges ("10,000-15,000", "10 to 15k", "between 6000 and 9000 AED") extract floor & ceiling.
    - Disqualifies non-budget numbers ("200 pages daily", "36 inch", "A3", "20 units").
    - If quantity is also present ("under 1800 AED for 5 units"), sets budget_scope="unspecified".
    """
    if not text:
        return None

    # Step 1: Normalise digits and lower-case
    norm = normalize_digits(text).lower()

    # Step 2: Strip thousands separator commas (e.g. 10,000 -> 10000)
    norm = re.sub(r"(?<=\d),(?=\d)", "", norm)

    # Check for quantity presence
    has_quantity = bool(
        re.search(r"\b(\d+)\s*(?:units?|pcs?|pieces?|printers?|machines?|scanners?|items?)\b", norm)
        or re.search(r"\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b", norm)
    )

    if has_quantity:
        detected_scope = "unspecified"
    elif bool(re.search(r"\b(?:cartridges?|inks?|toners?|ribbons?|rolls?|papers?|medias?|consumables?)\b", norm)):
        detected_scope = "consumable"
    else:
        detected_scope = "hardware"

    # Helper regex for a number with optional 'k'
    num_k = r"(\d+(?:\.\d+)?\s*(?:k|lakhs?|lacs?)?)"

    # Disqualification check for non-budget units immediately after the number
    def is_disqualified(after_text: str) -> bool:
        after_strip = after_text.strip()
        return bool(re.match(r"^" + NON_BUDGET_UNITS_PATTERN + r"\b", after_strip))

    # Pattern A: Range expressions
    # e.g., "10,000-15,000", "10 to 15k", "between 6000 and 9000 AED", "budget between 6000 and 9000"
    range_match = re.search(
        r"(?:(?:budget|within|between)\s*)?"
        r"(?:between\s+)?"
        rf"{num_k}\s*(?:-|–|to|and)\s*{num_k}\s*"
        rf"(?:{CURRENCY_PATTERN})?",
        norm
    )
    if range_match:
        # Check if disqualified by non-budget units
        end_idx = range_match.end()
        after = norm[end_idx:]
        if not is_disqualified(after):
            val1 = parse_number_with_suffix(range_match.group(1))
            val2 = parse_number_with_suffix(range_match.group(2))
            if val1 is not None and val2 is not None:
                # Ensure it's not a dimension range like 4x6 or 24-36 inch
                if not re.search(r"\b(?:inch|inches|cm|mm|pages?)\b", after[:15]):
                    # Valid range if keyword present, currency present, or values > 100
                    has_kw = bool(re.search(BUDGET_KEYWORD_PATTERN, norm[:range_match.start()] + " " + range_match.group(0)))
                    has_curr = bool(re.search(CURRENCY_PATTERN, range_match.group(0) + " " + after[:15]))
                    if has_kw or has_curr or (val1 >= 500 and val2 >= 500):
                        lower = min(val1, val2)
                        upper = max(val1, val2)
                        return BudgetParseResult(
                            budget_ceiling=upper,
                            budget_floor=lower,
                            budget_scope=detected_scope,
                            raw_match=range_match.group(0),
                        )

    # Pattern B: Budget Keyword + Number + optional currency/k
    # e.g. "budget is 10k AED", "under 1800 AED", "max 25k aed", "not more than 2000", "within 12000"
    kw_pattern = re.search(
        rf"\b({BUDGET_KEYWORD_PATTERN})\s*(?:is|of|[:=])?\s*(?:{CURRENCY_PATTERN}\s*)?{num_k}\s*(?:{CURRENCY_PATTERN})?",
        norm
    )
    if kw_pattern:
        end_idx = kw_pattern.end()
        after = norm[end_idx:]
        if not is_disqualified(after):
            val = parse_number_with_suffix(kw_pattern.group(2))
            if val is not None:
                return BudgetParseResult(
                    budget_ceiling=val,
                    budget_scope=detected_scope,
                    raw_match=kw_pattern.group(0),
                )

    # Pattern C: Number + Budget Keyword
    # e.g. "5000 AED max", "10k budget", "2000 max"
    num_kw_pattern = re.search(
        rf"{num_k}\s*(?:{CURRENCY_PATTERN}\s*)?({BUDGET_KEYWORD_PATTERN})\b",
        norm
    )
    if num_kw_pattern:
        val = parse_number_with_suffix(num_kw_pattern.group(1))
        end_idx = num_kw_pattern.end()
        after = norm[end_idx:]
        if val is not None and not is_disqualified(after):
            return BudgetParseResult(
                budget_ceiling=val,
                budget_scope=detected_scope,
                raw_match=num_kw_pattern.group(0),
            )

    # Pattern D: Adjacent Currency token (Prefix or Suffix)
    # e.g. "AED 1,800", "1800 AED", "around 5000 dirhams", "8000 dhs"
    curr_prefix = re.search(
        rf"\b({CURRENCY_PATTERN})\s*{num_k}\b",
        norm
    )
    if curr_prefix:
        end_idx = curr_prefix.end()
        after = norm[end_idx:]
        if not is_disqualified(after):
            val = parse_number_with_suffix(curr_prefix.group(2))
            if val is not None:
                return BudgetParseResult(
                    budget_ceiling=val,
                    budget_scope=detected_scope,
                    raw_match=curr_prefix.group(0),
                )

    curr_suffix = re.search(
        rf"\b{num_k}\s*({CURRENCY_PATTERN})\b",
        norm
    )
    if curr_suffix:
        val = parse_number_with_suffix(curr_suffix.group(1))
        if val is not None:
            return BudgetParseResult(
                budget_ceiling=val,
                budget_scope=detected_scope,
                raw_match=curr_suffix.group(0),
            )

    # Pattern E: Bare '10k' shorthand (k suffix directly)
    k_bare = re.search(r"\b(\d+(?:\.\d+)?)\s*k\b", norm)
    if k_bare:
        end_idx = k_bare.end()
        after = norm[end_idx:]
        if not is_disqualified(after):
            val = float(k_bare.group(1)) * 1000.0
            return BudgetParseResult(
                budget_ceiling=val,
                budget_scope=detected_scope,
                raw_match=k_bare.group(0),
            )

    return None
