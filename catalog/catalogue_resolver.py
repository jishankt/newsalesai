"""
Catalogue Resolver for Kepler Tech SalesAI.
Resolves customer text to approved catalogue entries for:
- Exact model detail queries
- Approved model comparisons (universal engine, all 42 catalogue entries)
Enforces strict catalogue membership via comparison_engine.
"""
import re
from typing import Optional, List, Dict, Any, Tuple
from catalog.catalogue_loader import catalogue_loader


def find_mentioned_catalogue_products(text: str) -> List[Dict[str, Any]]:
    """
    Identifies which approved catalogue products are mentioned in the text.
    Returns matching catalogue products.
    """
    if not text:
        return []

    text_lower = text.lower()
    all_products = catalogue_loader.get_all()
    matched = []

    # Sort by id length desc so 'SC-T3700DE' matches before 'SC-T3700D'
    sorted_prods = sorted(all_products, key=lambda p: len(p["id"]), reverse=True)

    seen_ids = set()
    for p in sorted_prods:
        pid = p["id"]
        fam = p.get("model_family", "").lower()
        disp = p.get("display_name", "").lower()

        patterns = [
            re.escape(pid),
            re.escape(fam),
            re.escape(fam.replace("sc-", "").replace("wf-", "").replace("em-", "").replace("am-", "")),
        ]

        found = False
        for pat in patterns:
            if len(pat) >= 4 and re.search(rf"\b{pat}\b", text_lower):
                found = True
                break

        if not found:
            clean_words = [re.sub(r"[^a-z0-9]", "", w) for w in text_lower.split() if len(re.sub(r"[^a-z0-9]", "", w)) >= 4]
            clean_text = re.sub(r"[^a-z0-9]", "", text_lower)
            clean_fam = re.sub(r"[^a-z0-9]", "", fam.lower())
            clean_pid = re.sub(r"[^a-z0-9]", "", pid.replace("epson-", "").replace("citizen-", "").lower())
            clean_disp = re.sub(r"[^a-z0-9]", "", disp.lower()
                .replace("epson", "").replace("citizen", "")
                .replace("workforce", "").replace("pro", "")
                .replace("enterprise", "").replace("surecolor", ""))

            candidates = {c for c in [clean_fam, clean_pid, clean_disp] if len(c) >= 4}
            for cand in candidates:
                if cand in clean_words:
                    found = True
                    break
                if len(cand) >= 6 and cand in clean_text:
                    found = True
                    break

        if found and pid not in seen_ids:
            seen_ids.add(pid)
            matched.append(p)

    return matched


def build_model_detail_response(product: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Builds verified description, specs, and card for an exact model inquiry."""
    from catalog.catalogue_filter import catalogue_filter
    card = catalogue_filter._format_card(product, product.get("subcategory"), {})

    name = product.get("display_name")
    cat = product.get("catalogue", "").replace("_", " ").title()
    subcat = product.get("subcategory", "").replace("_", " ").title()
    width = product.get("max_width_inches")
    functions = "/".join([f.title() for f in (product.get("functions") or ["Print"])])
    scanner = "Includes integrated scanner" if product.get("scanner_integrated") else "Dedicated print-only"

    reply = (
        f"Here are the verified specifications for the **{name}** from our official {cat} catalogue:\n\n"
        f"• **Category:** {cat} ({subcat})\n"
        f"• **Functions:** {functions} ({scanner})\n"
    )
    if width:
        reply += f"• **Maximum Print Width:** {width:.0f} inches\n"
    if product.get("paper_size"):
        reply += f"• **Paper Formats:** {product['paper_size'].upper()}\n"
    if product.get("dual_roll"):
        reply += "• **Dual Roll:** Automatic dual-roll media switching supported\n"
    if product.get("spectro"):
        reply += "• **Spectrophotometer:** Integrated inline colour calibration\n"

    reply += f"\n*(Verified from official catalogue: {product.get('source_catalogue')})*"

    return reply, [card]


def build_approved_comparison_response(
    products: List[Dict[str, Any]],
    customer_requirements: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Universal comparison for 2+ approved catalogue products.

    Returns:
        (intro_text, product_cards, comparison_data_json)
        comparison_data_json is the structured dict for frontend rendering.
    """
    from catalog.catalogue_filter import catalogue_filter
    from catalog.comparison_engine import build_comparison, build_comparison_intro
    import logging
    _log = logging.getLogger("catalog:resolver")

    try:
        comparison_data = build_comparison(products[:3], customer_requirements)
    except ValueError as exc:
        _log.error(f"Comparison rejected: {exc}")
        return (
            "I can only compare products from our approved catalogue. "
            "Please specify verified Kepler Tech catalogue models.",
            [],
            {},
        )

    intro = build_comparison_intro(products[:3], comparison_data)
    cards = [
        catalogue_filter._format_card(p, p.get("subcategory"), {})
        for p in products[:3]
    ]

    return intro, cards, comparison_data
