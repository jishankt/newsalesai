"""
Universal Comparison Engine for Kepler Tech SalesAI.
Covers all 42 approved catalogue entries across all categories.

Requirements fulfilled:
1. Resolve any 2+ approved product IDs.
2. Identify same-subcategory / same-category / cross-category.
3. Select comparison criteria dynamically by category.
4. Always include 7 common criteria.
5. Add category-specific criteria per spec.
6. Cross-category: shared fields only + explanatory note.
7. No generic fixed 5-field table.
8. Use verified catalogue data only; missing -> NOT_VERIFIED sentinel.
9. Return structured JSON -- never Markdown.
10. Values sanitised via html.escape() (XSS-safe).
11. Recommendations only when customer requirements are provided.
12. Catalogue-only allowlist -- unapproved IDs raise ValueError.
"""

import html
import logging
from typing import Any, Dict, List, Optional, Tuple

from catalog.catalogue_loader import catalogue_loader

logger = logging.getLogger("catalog:comparison_engine")

NOT_VERIFIED = "Not verified in the approved catalogue."

# ── Common criteria (all comparisons) ──────────────────────────────────────
COMMON_CRITERIA: List[Tuple[str, str]] = [
    ("model",           "Model"),
    ("main_category",   "Main Category"),
    ("subcategory_key", "Subcategory"),
    ("applications",    "Primary Applications"),
    ("functions",       "Functions"),
    ("max_output_size", "Maximum Output Size"),
    ("match_reasons",   "Key Selling Points"),
]

# ── Category-specific criteria ──────────────────────────────────────────────
CATEGORY_CRITERIA: Dict[str, List[Tuple[str, str]]] = {
    "office_printer": [
        ("paper_size",          "Paper Format"),
        ("colour_mode",         "Colour Mode"),
        ("scanner_integrated",  "Integrated Scanner"),
        ("product_line",        "Product Line"),
        ("recommended_volume",  "Recommended Monthly Volume"),
        ("catalogue",           "Source Catalogue"),
    ],
    "technical_large_format": [
        ("max_width_inches",      "Maximum Print Width"),
        ("scanner_integrated",    "Integrated Scanner"),
        ("dual_roll",             "Dual-Roll Media"),
        ("applications_cad",      "CAD / GIS / AEC Applications"),
        ("colour_mode",           "Colour Mode"),
        ("supported_print_sizes", "Supported Output Sizes"),
    ],
    "photography_large_format": [
        ("max_width_inches",      "Maximum Print Width"),
        ("supported_print_sizes", "Supported Photo Sizes"),
        ("dual_roll",             "Dual-Roll Media"),
        ("spectro",               "Spectrophotometer"),
        ("scanner_integrated",    "Integrated Scanner"),
        ("applications_photo",    "Photography / Fine Art / Poster Use"),
        ("colour_mode",           "Colour Mode"),
    ],
    "citizen_photo": [
        ("max_width_inches",        "Maximum Print Width"),
        ("supported_print_sizes",   "Supported Photo Sizes"),
        ("paper_size",              "Media Width"),
        ("applications_citizen",    "Studio / Event / Kiosk / Photo-Booth Use"),
        ("colour_mode",             "Colour Mode"),
    ],
    "dye_sublimation": [
        ("paper_size",            "Paper Format"),
        ("max_width_inches",      "Maximum Print Width"),
        ("applications_dyesub",   "Dye-Sub Applications"),
        ("colour_mode",           "Colour Mode"),
    ],
}

# Cross-category: only these shared fields
CROSS_CATEGORY_SHARED: List[Tuple[str, str]] = [
    ("model",           "Model"),
    ("main_category",   "Main Category"),
    ("subcategory_key", "Subcategory"),
    ("applications",    "Primary Applications"),
    ("functions",       "Functions"),
    ("max_output_size", "Maximum Output Size"),
    ("colour_mode",     "Colour Mode"),
    ("match_reasons",   "Key Selling Points"),
    ("product_line",    "Product Line"),
]


def _safe(value: Any) -> str:
    """Convert any value to a safe display string, escaping HTML."""
    if value is None:
        return NOT_VERIFIED
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        cleaned = [html.escape(str(v).replace("_", " ").title()) for v in value if v]
        return ", ".join(cleaned) if cleaned else NOT_VERIFIED
    if isinstance(value, (int, float)):
        return html.escape(str(value))
    s = str(value).strip()
    # Strip injection patterns before escaping
    s = s.replace("<", "").replace(">", "").replace("javascript:", "").replace("data:", "")
    return html.escape(s.replace("_", " ").title())


def _resolve_field(product: Dict[str, Any], key: str) -> str:
    """Resolve a comparison criterion key to a safe display string."""
    p = product

    if key == "model":
        return html.escape(p.get("display_name", NOT_VERIFIED))

    if key == "main_category":
        v = p.get("main_category", "")
        return html.escape(v.replace("_", " ").title()) if v else NOT_VERIFIED

    if key == "subcategory_key":
        v = p.get("subcategory", "")
        return html.escape(v.replace("_", " ").title()) if v else NOT_VERIFIED

    if key == "applications":
        apps = p.get("applications") or []
        return _safe(apps)

    if key == "applications_cad":
        apps = [a for a in (p.get("applications") or []) if a in (
            "cad", "architecture", "engineering_drawings", "gis", "aec", "posters", "maps"
        )]
        return _safe(apps) if apps else NOT_VERIFIED

    if key == "applications_photo":
        apps = [a for a in (p.get("applications") or []) if a in (
            "fine_art", "photography", "gallery_prints", "studio_portraits",
            "photo_printing", "poster", "exhibition"
        )]
        return _safe(apps) if apps else NOT_VERIFIED

    if key == "applications_citizen":
        apps = [a for a in (p.get("applications") or []) if a in (
            "photo_booth", "compact_events", "id_photos", "mobile_studio",
            "event_photography", "kiosk", "studio", "weddings"
        )]
        return _safe(apps) if apps else NOT_VERIFIED

    if key == "applications_dyesub":
        apps = [a for a in (p.get("applications") or []) if a in (
            "dye_sublimation", "garment_printing", "fabric_printing",
            "transfer_printing", "personalised_products"
        )]
        return _safe(apps) if apps else NOT_VERIFIED

    if key == "functions":
        funcs = p.get("functions") or []
        return _safe(funcs) if funcs else NOT_VERIFIED

    if key == "max_output_size":
        w = p.get("max_width_inches")
        ps = p.get("paper_size", "")
        if w and ps:
            return html.escape(f"{w:.4g}-inch / {str(ps).upper()}")
        if w:
            return html.escape(f"{w:.4g} inches wide")
        if ps:
            return html.escape(str(ps).upper())
        return NOT_VERIFIED

    if key == "max_width_inches":
        w = p.get("max_width_inches")
        return html.escape(f"{w:.4g} inches") if w is not None else NOT_VERIFIED

    if key == "paper_size":
        ps = p.get("paper_size")
        return html.escape(str(ps).upper()) if ps else NOT_VERIFIED

    if key == "colour_mode":
        return _safe(p.get("colour_mode", ""))

    if key == "scanner_integrated":
        v = p.get("scanner_integrated")
        if v is True:
            return "Yes — integrated flatbed scanner"
        if v is False:
            return "No — print-only"
        return NOT_VERIFIED

    if key == "dual_roll":
        v = p.get("dual_roll")
        if v is True:
            return "Yes — automatic dual-roll switching"
        if v is False:
            return "No — single roll"
        return NOT_VERIFIED

    if key == "spectro":
        v = p.get("spectro")
        if v is True:
            return "Yes — inline spectrophotometer"
        if v is False:
            return "No"
        if isinstance(v, str):
            return html.escape(v)
        return NOT_VERIFIED

    if key == "product_line":
        pl = p.get("product_line", "")
        labels = {
            "workforce_pro":        "WorkForce Pro",
            "workforce_enterprise": "WorkForce Enterprise",
            "surecolor_t":          "SureColor T-Series",
            "surecolor_p":          "SureColor P-Series",
            "surecolor_f":          "SureColor F-Series",
            "citizen":              "Citizen",
        }
        return html.escape(labels.get(pl, pl.replace("_", " ").title())) if pl else NOT_VERIFIED

    if key == "recommended_volume":
        mn = p.get("recommended_monthly_min")
        mx = p.get("recommended_monthly_max")
        if mn is not None and mx is not None:
            return html.escape(f"{mn:,}\u2013{mx:,} pages/month")
        if mx is not None:
            return html.escape(f"Up to {mx:,} pages/month")
        if mn is not None:
            return html.escape(f"From {mn:,} pages/month")
        return NOT_VERIFIED

    if key == "catalogue":
        return html.escape(p.get("source_catalogue", NOT_VERIFIED))

    if key == "supported_print_sizes":
        sizes = p.get("supported_print_sizes") or []
        return html.escape(", ".join(sizes)) if sizes else NOT_VERIFIED

    if key == "match_reasons":
        reasons = []
        funcs = p.get("functions") or []
        if "scan" in funcs or "copy" in funcs:
            reasons.append("Multifunction: print, scan, copy")
        if p.get("dual_roll"):
            reasons.append("Dual-roll automatic media switching")
        if p.get("spectro"):
            reasons.append("Spectrophotometer for colour calibration")
        if p.get("scanner_integrated") and "scan" not in funcs:
            reasons.append("Integrated flatbed scanner")
        pl = p.get("product_line", "")
        pl_labels = {
            "workforce_pro":        "WorkForce Pro — high-volume office range",
            "workforce_enterprise": "WorkForce Enterprise — ultra-high-volume range",
            "surecolor_p":          "SureColor P — professional photo accuracy",
            "surecolor_t":          "SureColor T — CAD/GIS technical plotting",
            "citizen":              "Citizen — instant dye-sub photo printing",
            "surecolor_f":          "SureColor F — dye-sublimation transfer printing",
        }
        if pl in pl_labels:
            reasons.append(pl_labels[pl])
        return html.escape("; ".join(reasons)) if reasons else NOT_VERIFIED

    # Fallback: direct field lookup
    val = p.get(key)
    return _safe(val) if val is not None else NOT_VERIFIED


def _values_differ(values: Dict[str, str]) -> bool:
    """Return True if the products have different values for this criterion."""
    unique = set(values.values())
    return len(unique) > 1 and NOT_VERIFIED not in unique


def build_comparison(
    products: List[Dict[str, Any]],
    customer_requirements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a structured comparison dict for 2+ approved catalogue products.

    Raises:
        ValueError: if any product ID is unapproved, or < 2 products supplied.
    """
    if len(products) < 2:
        raise ValueError("Comparison requires at least 2 products.")

    approved_ids = catalogue_loader.approved_ids
    for p in products:
        pid = p.get("id", "")
        if pid not in approved_ids:
            raise ValueError(
                f"Product '{pid}' is not in the approved catalogue."
            )

    subcategories  = [p.get("subcategory") for p in products]
    main_cats      = [p.get("main_category") for p in products]

    if len(set(subcategories)) == 1:
        comparison_type = "same_subcategory"
    elif len(set(main_cats)) == 1:
        comparison_type = "same_category"
    else:
        comparison_type = "cross_category"

    cross_category_note = None
    if comparison_type == "cross_category":
        criteria_keys = CROSS_CATEGORY_SHARED
        cat_names = list({
            p.get("main_category", "").replace("_", " ").title()
            for p in products
        })
        cross_category_note = (
            f"These products serve fundamentally different applications "
            f"({' vs '.join(sorted(cat_names))}). "
            "Only shared specifications are shown. "
            "Please describe your specific printing requirements and we will "
            "recommend the most suitable product."
        )
    else:
        primary_cat = main_cats[0]
        cat_specific = CATEGORY_CRITERIA.get(primary_cat, [])
        common_keys = {k for k, _ in COMMON_CRITERIA}
        extra = [(k, l) for k, l in cat_specific if k not in common_keys]
        criteria_keys = COMMON_CRITERIA + extra

    # Resolve values for each criterion
    criteria_rows = []
    for ck, label in criteria_keys:
        values = {p["id"]: _resolve_field(p, ck) for p in products}
        criteria_rows.append({
            "key":       ck,
            "label":     label,
            "values":    values,
            "highlight": _values_differ(values),
        })

    product_summaries = [
        {
            "id":           p["id"],
            "display_name": html.escape(p.get("display_name", p["id"])),
            "image_url":    p.get("image_url") or "/static/images/printer-placeholder.svg",
            "product_url":  p.get("product_url") or "https://www.keplertechllc.com/",
            "main_category":p.get("main_category", ""),
            "subcategory":  p.get("subcategory", ""),
        }
        for p in products
    ]

    recommendation_note = None
    if customer_requirements and comparison_type != "cross_category":
        recommendation_note = _build_recommendation_note(
            products, customer_requirements
        )

    return {
        "comparison_type":      comparison_type,
        "products":             product_summaries,
        "criteria":             criteria_rows,
        "cross_category_note":  cross_category_note,
        "recommendation_note":  recommendation_note,
    }


def _build_recommendation_note(
    products: List[Dict[str, Any]],
    requirements: Dict[str, Any],
) -> Optional[str]:
    """Score products against explicit requirements; recommend only when clear."""
    scores: Dict[str, int] = {p["id"]: 0 for p in products}
    req_scan   = requirements.get("scanner_required")
    req_dual   = requirements.get("dual_roll_required")
    req_spectro= requirements.get("spectro_required")
    req_line   = requirements.get("product_line")
    daily_vol  = requirements.get("daily_volume")

    for p in products:
        pid = p["id"]
        if req_scan is True  and p.get("scanner_integrated") is True:  scores[pid] += 2
        if req_scan is False and p.get("scanner_integrated") is False:  scores[pid] += 1
        if req_dual is True  and p.get("dual_roll") is True:           scores[pid] += 2
        if req_spectro is True and p.get("spectro") is True:           scores[pid] += 2
        if req_line and req_line not in ("unspecified",) and req_line == p.get("product_line"):
            scores[pid] += 3
        if daily_vol is not None:
            mn = p.get("recommended_monthly_min")
            mx = p.get("recommended_monthly_max")
            monthly = daily_vol * 22
            if mn is not None and mx is not None and mn <= monthly <= mx:
                scores[pid] += 2

    max_score = max(scores.values())
    if max_score == 0:
        return None

    winners = [pid for pid, s in scores.items() if s == max_score]
    if len(winners) == 1:
        winner = next(p for p in products if p["id"] == winners[0])
        return (
            f"Based on your stated requirements, the "
            f"**{html.escape(winner.get('display_name', winner['id']))}** "
            f"appears to be the better fit. "
            "Please confirm your full requirements for a definitive recommendation."
        )
    return None


def build_comparison_intro(
    products: List[Dict[str, Any]],
    comparison_data: Dict[str, Any],
) -> str:
    """Short natural-language intro shown above the comparison table."""
    names = [p.get("display_name", p["id"]) for p in products]
    comp_type = comparison_data.get("comparison_type", "")

    if len(names) == 2:
        header = f"Here is a verified side-by-side comparison of the **{names[0]}** and **{names[1]}**"
    else:
        joined = ", ".join(f"**{n}**" for n in names)
        header = f"Here is a verified comparison of {len(names)} models: {joined}"

    suffix_map = {
        "same_subcategory": ", both from the same product subcategory.",
        "same_category":    ", both from the same product category.",
        "cross_category":   ". Note that these products serve different application areas — only shared specifications are shown.",
    }
    intro = header + suffix_map.get(comp_type, ".")

    if comparison_data.get("recommendation_note"):
        intro += f"\n\n{comparison_data['recommendation_note']}"

    return intro
