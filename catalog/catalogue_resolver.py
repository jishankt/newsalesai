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
        cfg = p.get("configuration")

        # Guard variant matching: non-standard configurations (Roll Adapter, Spectro)
        # require explicit mention of the variant keyword in the text
        if cfg == "Roll Adapter" or "-roll" in pid:
            if not bool(re.search(r"\b(?:roll|panoramic)\b", text_lower)):
                continue
        elif cfg == "Spectro" or "-spectro" in pid:
            if not bool(re.search(r"\b(?:spectro|spectrophotometer)\b", text_lower)):
                continue
        elif cfg == "Standard":
            # If the user explicitly asked for the variant only (e.g. "p900 with roll adapter"),
            # skip the base standard model unless they also mentioned "standard" or "without"
            fam_short = fam.replace("sc-", "")
            fam_in_text = bool(re.search(rf"\b{re.escape(fam)}\b", text_lower)) or bool(re.search(rf"\b{re.escape(fam_short)}\b", text_lower))
            if fam_in_text:
                if fam == "sc-p900" and bool(re.search(r"\b(?:with\s+roll|roll\s+adapter|with\s+the\s+roll)\b", text_lower)) and not bool(re.search(r"\b(?:without|standard|sheet)\b", text_lower)):
                    continue
                if fam in ("sc-p7500", "sc-p9500") and bool(re.search(r"\b(?:spectro|spectrophotometer)\b", text_lower)) and not bool(re.search(r"\b(?:without|standard)\b", text_lower)):
                    continue

        # Guard Expression 12000XL base vs 12000XL Pro
        if pid == "epson-expression-12000xl":
            if bool(re.search(r"\b(?:pro|12000xl\s*pro)\b", text_lower)) and not bool(re.search(r"\b(?:without|standard|both|compare|versus|vs)\b", text_lower)):
                continue

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
                    # Mask already matched longer candidate models to avoid substring false positives
                    # (e.g. 'scp8500d' matching inside 'scp8500dm')
                    masked_text = clean_text
                    for m in matched:
                        m_fam = re.sub(r"[^a-z0-9]", "", m.get("model_family", "").lower())
                        m_pid = re.sub(r"[^a-z0-9]", "", m.get("id", "").replace("epson-", "").replace("citizen-", "").lower())
                        for mc in [m_fam, m_pid]:
                            if len(mc) > len(cand) and cand in mc:
                                masked_text = masked_text.replace(mc, " " * len(mc), 1)
                    if cand in masked_text:
                        found = True
                        break

        if found and pid not in seen_ids:
            seen_ids.add(pid)
            matched.append(p)

    if not matched:
        # Fuzzy fallback for model code typos (e.g. repeated digits c55890 -> c5890, p9900 -> p900)
        raw_words = text_lower.split()
        clean_words = [re.sub(r"[^a-z0-9]", "", w) for w in raw_words]
        tokens_to_check = set()
        for idx, w in enumerate(clean_words):
            if len(w) >= 4 and bool(re.search(r"[a-z]", w)) and bool(re.search(r"[0-9]", w)):
                if not w.endswith(("inch", "in", "gsm", "ml", "mm", "cm", "dpi")):
                    tokens_to_check.add(w)
            if idx > 0:
                bigram = clean_words[idx - 1] + w
                if len(bigram) >= 5 and bool(re.search(r"[a-z]", bigram)) and bool(re.search(r"[0-9]", bigram)):
                    if not bigram.endswith(("inch", "in", "gsm", "ml", "mm", "cm", "dpi")):
                        tokens_to_check.add(bigram)

        compressed_tokens = set()
        for t in tokens_to_check:
            compressed = re.sub(r"([a-z0-9])\1+", r"\1", t)
            if compressed != t and len(compressed) >= 4:
                compressed_tokens.add(compressed)
        tokens_to_check.update(compressed_tokens)

        if tokens_to_check:
            scored_candidates = []
            for p in sorted_prods:
                pid = p["id"]
                fam = p.get("model_family", "").lower().replace("sc-", "").replace("wf-", "").replace("am-", "").replace("em-", "")
                clean_fam = re.sub(r"[^a-z0-9]", "", fam)
                clean_pid = re.sub(r"[^a-z0-9]", "", pid.replace("epson-", "").replace("citizen-", ""))
                clean_full = re.sub(r"[^a-z0-9]", "", p.get("display_name", "").lower().replace("epson", "").replace("workforce", "").replace("surecolor", ""))

                cands = {c for c in [clean_fam, clean_pid, clean_full] if len(c) >= 4}
                for cand in cands:
                    for token in tokens_to_check:
                        if token == cand:
                            return [p]
                        d = _levenshtein(token, cand)
                        max_allowed = 1 if len(cand) <= 6 else 2
                        if d <= max_allowed:
                            scored_candidates.append((d, p))

            if scored_candidates:
                scored_candidates.sort(key=lambda x: x[0])
                best_d = scored_candidates[0][0]
                for d, prod in scored_candidates:
                    if d == best_d and prod["id"] not in seen_ids:
                        seen_ids.add(prod["id"])
                        matched.append(prod)

    return matched


def _levenshtein(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[-1]


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
        f"Here are the verified specifications and key features for the **{name}** ({cat} — {subcat}):\n\n"
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
    if product.get("yield_capacity"):
        reply += f"• **Yield & Capacity:** {product['yield_capacity']}\n"
    if product.get("pattern_and_finishing"):
        reply += f"• **Finishing & Pattern:** {product['pattern_and_finishing']}\n"

    reply += f"\n*(Verified from official catalogue: {product.get('source_catalogue')})*"

    return reply, [card]


def build_p900_family_detail_response() -> Tuple[str, List[Dict[str, Any]]]:
    """Builds verified description, specs, and cards for both Epson SC-P900 configurations (with and without roll adapter)."""
    from catalog.catalogue_filter import catalogue_filter
    from catalog.catalogue_loader import catalogue_loader

    p_std = catalogue_loader.get_by_id("epson-sc-p900")
    p_roll = catalogue_loader.get_by_id("epson-sc-p900-roll")

    cards = []
    if p_std:
        cards.append(catalogue_filter._format_card(p_std, p_std.get("subcategory"), {}))
    if p_roll:
        cards.append(catalogue_filter._format_card(p_roll, p_roll.get("subcategory"), {}))

    reply = (
        "Great choice! The **Epson SureColor SC-P900** is our premier 17-inch photo and fine-art desktop printer.\n\n"
        "It is available in two official configurations to match your workflow:\n"
        "• **Standard Configuration (without Roll Adapter)**: Dedicated desktop photo printer for cut-sheet media (A2+, A3+, A3, A4).\n"
        "• **With Roll Adapter Configuration**: Includes the continuous roll media unit for panoramic photography and banner printing up to 17 inches.\n\n"
        "• **Category:** Photography And Fine Art (Photo 17 Desktop)\n"
        "• **Functions:** Print (Dedicated print-only)\n"
        "• **Maximum Print Width:** 17 inches\n"
        "• **Paper Formats:** 17-INCH, A2+, A3+, A3, A4\n"
        "• **Configurations Available:** Standard (without roll adapter) and with Roll Adapter\n\n"
        "*(Verified from official catalogue: LARGE FORMAT PRINTERS FOR PHOTOGRAPHY_CATALOG.pdf)*"
    )

    return reply, cards



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
    from catalog.comparison_engine import (
        build_comparison,
        build_comparison_intro,
        format_comparison_markdown_table,
    )
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
    table_md = format_comparison_markdown_table(products[:3], comparison_data)
    reply_text = f"{intro}\n\n{table_md}" if table_md else intro

    cards = [
        catalogue_filter._format_card(p, p.get("subcategory"), {})
        for p in products[:3]
    ]

    return reply_text, cards, comparison_data

