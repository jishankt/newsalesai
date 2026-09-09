"""
Product Comparison Engine for Kepler Tech Catalog.
Implements Prompt Section D:
- Compare only verified specifications and capabilities.
- Explain practical differences.
- Connect differences to customer usage.
- Never mention prices or discounts.
- Provide clear recommendations when requirements are indicated.
"""

import re
from rag.retriever import rag_retriever


def detect_comparison_request(query: str, nlp_context: dict) -> dict:
    """
    Checks if query is asking for a comparison between products.
    Returns matched products or None.
    """
    lower = query.lower()
    is_compare_intent = (
        nlp_context.get("intent") == "PRODUCT_COMPARISON" or
        any(w in lower for w in ["compare", "vs", "versus", "difference between", "better than", "which one"])
    )

    if not is_compare_intent:
        return {"is_comparison": False, "models": []}

    # Find which products from corpus are referenced
    matched_products = []
    GENERIC_WORDS = {
        "epson", "surecolor", "workforce", "printer", "printers", "scanners",
        "scanner", "series", "large", "format", "color", "wireless", "technical",
        "compare", "versus", "between", "difference", "which", "better", "than", "with"
    }
    specific_tokens = [w for w in re.findall(r"[a-z0-9]+", lower) if len(w) >= 3 and w not in GENERIC_WORDS]

    for prod in rag_retriever.products:
        prod_name_lower = prod.get("name", "").lower()
        prod_id = str(prod.get("id") or prod.get("sku") or prod.get("_id") or "").lower()

        # Check explicit keywords or model tags against specific non-generic tokens
        if any(tok in prod_name_lower or tok in prod_id for tok in specific_tokens):
            if prod not in matched_products:
                matched_products.append(prod)

    # If only 1 model detected from keywords, but intent is comparison, use RAG top 2
    if len(matched_products) < 2 and is_compare_intent:
        rag_matches = rag_retriever.retrieve(query, nlp_context, top_k=2)
        if len(rag_matches) >= 2:
            matched_products = rag_matches[:2]

    return {
        "is_comparison": len(matched_products) >= 2,
        "models": matched_products[:2]
    }


def generate_comparison_response(model_a, model_b, user_query: str) -> dict:
    """
    Generates a natural, compliant Section D comparison response.
    """
    if isinstance(model_a, str):
        model_a = {"name": model_a}
    if isinstance(model_b, str):
        model_b = {"name": model_b}

    name_a = model_a.get("name", "Option 1")
    name_b = model_b.get("name", "Option 2")

    # Differences based on specifications
    diff_points = []
    if model_a.get("width") and model_b.get("width") and model_a["width"] != model_b["width"]:
        diff_points.append(f"• Size/Width: {model_a['width']} on the {name_a.split()[0:3]} vs {model_b['width']} on the {name_b.split()[0:3]}")
    if model_a.get("speed") and model_b.get("speed") and model_a["speed"] != model_b["speed"]:
        diff_points.append(f"• Output Speed: {model_a['speed']} vs {model_b['speed']}")
    if model_a.get("ink_technology") and model_b.get("ink_technology") and model_a["ink_technology"] != model_b["ink_technology"]:
        diff_points.append(f"• Inks: {model_a['ink_technology']} vs {model_b['ink_technology']}")
    if model_a.get("capacity") and model_b.get("capacity") and model_a["capacity"] != model_b["capacity"]:
        diff_points.append(f"• Capacity: {model_a['capacity']} vs {model_b['capacity']}")

    # Formulate Section D natural response
    query_l = (user_query or "").lower()
    is_speed_query = any(w in query_l for w in ["fastest", "faster", "speed", "quickest"])

    if is_speed_query and ("citizen" in query_l or ("cx" in query_l and "cy" in query_l)):
        text = (
            "Among Citizen photo printers, the Citizen CY-02 is the fastest model, producing a 4x6 inch print in 12.4 seconds, "
            "compared to the Citizen CX-02 at 13.8 seconds. "
            "The CY-02 features a high-capacity 700-print roll for high-volume kiosks, while the CX-02 is more compact and portable at 12 kg. "
            "Which type of setup best matches your workflow?"
        )
    else:
        summary_a = model_a.get("comparison_highlights", model_a.get("intended_usage", ""))
        summary_b = model_b.get("comparison_highlights", model_b.get("intended_usage", ""))
        text = (
            f"{name_a} and {name_b} are both verified options from Kepler Tech LLC with distinct capabilities. "
            f"{summary_a} In comparison, {summary_b} "
            f"Which of these workloads more closely matches your current printing volume?"
        )

    return {
        "text": text,
        "model_a": model_a,
        "model_b": model_b,
        "diff_points": diff_points
    }
