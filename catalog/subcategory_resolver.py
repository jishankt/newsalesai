"""
Deterministic Subcategory Resolver.
Selects the leaf subcategory using normalized requirements without any LLM involvement.
"""
from typing import Dict, Any, Optional, List


def resolve_subcategory(category: str, requirements: Dict[str, Any]) -> Optional[str]:
    """
    Deterministically resolves the final subcategory from normalized requirements.
    """
    if not category:
        return None

    # ── 1. Office Printers ───────────────────────────────────────────────
    if category == "office_printer":
        paper_size = str(requirements.get("paper_size", "")).lower()
        daily_vol = requirements.get("daily_volume")
        vol_num = int(daily_vol) if isinstance(daily_vol, (int, float)) else 0

        # A4 office printers
        if paper_size in ("a4", "letter", "legal") or "a4" in paper_size:
            return "a4_colour_multifunction"

        # A3 office printers
        if paper_size in ("a3", "a3+", "tabloid", "ledger") or "a3" in paper_size:
            prod_line = requirements.get("product_line")

            # 1. Explicit product line ALWAYS takes precedence over volume
            if prod_line == "workforce_pro":
                return "a3_workforce_pro_multifunction"
            elif prod_line == "workforce_enterprise":
                return "a3_enterprise_multifunction"

            # 2. Explicitly unspecified product line: do not restrict subcategory
            if prod_line == "unspecified":
                return None

            # 3. If product_line was not specified by customer, route based on daily volume
            if vol_num >= 200 or requirements.get("enterprise_required"):
                return "a3_enterprise_multifunction"
            elif 0 < vol_num < 200:
                return "a3_workforce_pro_multifunction"

            # When volume is also not specified, do not assume Pro or Enterprise
            return None

        return None

    # ── 2. Technical Large-Format ────────────────────────────────────────
    if category == "technical_large_format":
        width = requirements.get("print_width")
        scanner_req = requirements.get("scanner_required")

        # 24-inch (All 24-inch CAD entries in catalogue are print-only)
        if width == 24:
            if scanner_req is True:
                return "technical_24_multifunction"
            return "technical_24_print_only"

        # 36-inch
        if width == 36:
            if scanner_req is True:
                return "technical_36_multifunction"
            elif scanner_req is False:
                return "technical_36_print_only"
            # When scanner requirement is unanswered, return None so qualification asks
            return None

        # 44-inch
        if width == 44:
            if scanner_req is True:
                return "technical_44_multifunction"
            elif scanner_req is False:
                return "technical_44_print_only"
            # When scanner requirement is unanswered, return None so qualification asks
            return None

        return None

    # ── 3. Photography and Fine-Art ──────────────────────────────────────
    if category == "photography_large_format":
        width = requirements.get("print_width")

        if width == 13:
            return "photo_13_desktop"
        elif width == 17:
            return "photo_17_desktop"
        elif width == 24:
            return "photo_24_professional"
        elif width == 44:
            return "photo_44_professional"
        elif width == 64:
            return "photo_64_production"

        return None

    # ── 4. Citizen Photo Printers ────────────────────────────────────────
    if category == "citizen_photo":
        sizes = requirements.get("print_sizes", [])
        if isinstance(sizes, str):
            sizes = [sizes]
        sizes_str = " ".join(sizes).lower()

        if any(s in sizes_str for s in ["8x10", "8x12", "8-inch", "8 inch"]):
            return "citizen_8_inch"
        elif any(s in sizes_str for s in ["4x4", "4.5x4.5", "4.5x8", "4-inch", "4 inch"]):
            return "citizen_4_inch"
        elif any(s in sizes_str for s in ["4x6", "5x7", "6x8", "6-inch", "6 inch"]):
            return "citizen_6_inch"

        # Unknown Citizen print size must not default to 6-inch
        return None

    return None


class SubcategoryResolver:
    @staticmethod
    def resolve_subcategory(category: str, requirements: Dict[str, Any]) -> Optional[str]:
        return resolve_subcategory(category, requirements)

    @staticmethod
    def resolve(category: str, requirements: Dict[str, Any]) -> Optional[str]:
        return resolve_subcategory(category, requirements)


subcategory_resolver = SubcategoryResolver()
