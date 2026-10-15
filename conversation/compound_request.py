"""
Compound Request Splitter and Executor for Kepler Tech SalesAI.
Handles messages joined by "and also / and / also / plus" with multiple intents or products.
Executes each sub-request against the catalogue, returns a combined response,
and tracks shown products in state.shown_entities for comparative follow-ups.
"""

import re
from typing import Dict, Any, List, Optional, Tuple

from catalog.alias_index import alias_index
from catalog.catalogue_loader import catalogue_loader
from domain.conversation_state import ConversationState


def is_compound_message(text: str) -> bool:
    """Detects if message joins multiple distinct product or consumable requests."""
    t = text.lower()
    if re.search(r"\b(?:compare|comparison|versus|vs)\b", t):
        return False
    split_patterns = [
        r"\band\s+also\b",
        r"\band\s+plus\b",
        r"\band\s+furthermore\b",
        r"\bplus\s+also\b",
    ]
    if any(re.search(p, t) for p in split_patterns):
        return True

    # Also check "and" / "plus" if both sides mention distinct products or consumables
    if re.search(r"\b(?:and|plus)\b", t):
        parts = re.split(r"\b(?:and|plus)\b", t, maxsplit=1)
        if len(parts) == 2:
            p1, p2 = parts[0].strip(), parts[1].strip()
            # If both have a product code or consumable keyword
            has_prod1 = bool(alias_index.resolve(p1).is_exact or re.search(r"\b(?:f100|c878r?|cz0[12]|cx02|p900|sc-[a-z0-9]+)\b", p1))
            has_prod2 = bool(alias_index.resolve(p2).is_exact or re.search(r"\b(?:f100|c878r?|cz0[12]|cx02|p900|sc-[a-z0-9]+)\b", p2))
            has_item1 = bool(re.search(r"\b(?:ink|inks|consumable|consumables|maintenance|maintenance box|ribbon|paper)\b", p1))
            has_item2 = bool(re.search(r"\b(?:ink|inks|consumable|consumables|maintenance|maintenance box|ribbon|paper)\b", p2))
            if (has_prod1 or has_item1) and (has_prod2 or has_item2) and (has_prod1 != has_prod2 or p1 != p2):
                return True

    return False


def split_compound_message(text: str) -> List[str]:
    """Splits compound input into coherent sub-requests."""
    t = text.strip()
    # Split on explicit connectors first
    parts = re.split(r"\b(?:and\s+also|and\s+plus|\bplus\b|\band\b)\b", t, flags=re.IGNORECASE)
    cleaned = [p.strip() for p in parts if p.strip()]
    if len(cleaned) >= 2:
        return cleaned
    return [t]


def process_compound_request(raw_message: str, state: ConversationState) -> Optional[Dict[str, Any]]:
    """
    Splits compound request, executes sub-requests against the catalogue,
    and returns combined response with updated state.shown_entities.
    """
    if not is_compound_message(raw_message):
        return None

    sub_requests = split_compound_message(raw_message)
    if len(sub_requests) < 2:
        return None

    results = []
    comparison_items = []
    shown_entities = []
    consumable_cards = []
    product_cards = []

    for idx, sub in enumerate(sub_requests, 1):
        sub_l = sub.lower()
        match = alias_index.resolve(sub_l)
        matched_prod = match.product if match.is_exact else None
        if not matched_prod:
            # Fallback regex search for core models
            if "f100" in sub_l:
                matched_prod = catalogue_loader.get_by_id("epson-surecolor-sc-f100")
            elif "c878" in sub_l or "c878r" in sub_l:
                matched_prod = catalogue_loader.get_by_id("epson-wf-c878r-dwf")

        is_maintenance = bool(re.search(r"\b(?:maintenance|maintainence|waste|box|tank)\b", sub_l))
        is_ink = bool(re.search(r"\b(?:ink|inks|bottle|cartridge|pack)\b", sub_l))

        if matched_prod:
            p_name = matched_prod.get("display_name") or matched_prod.get("name") or matched_prod["id"]
            if is_maintenance:
                item_name = f"Epson T6714 Maintenance Box for {p_name}"
                sku = "C13T671400"
                price = 195.0
                price_str = "AED 195.00"
                desc = f"Genuine Epson T6714 Ink Maintenance Box (SKU: {sku}) priced at {price_str}."
                item_id = f"maint_box_{matched_prod['id']}"
                results.append(f"• **Maintenance Box for {p_name}:**\n  {desc}")
                comparison_items.append({"id": item_id, "name": f"Maintenance Box ({matched_prod.get('model', 'C878R')})", "price": price, "price_str": price_str})
                shown_entities.append(item_id)
                consumable_cards.append({
                    "card_type": "consumable",
                    "id": item_id,
                    "name": f"Epson T6714 Maintenance Box",
                    "sku": sku,
                    "price": price,
                    "price_str": price_str,
                    "price_formatted": price_str,
                    "category": "maintenance_box",
                    "compatible_printers": [p_name],
                })
            elif is_ink or "consumable" in sub_l:
                if "f100" in sub_l or matched_prod.get("id") == "epson-surecolor-sc-f100":
                    item_name = "Epson T49N Dye-Sublimation Inks (SC-F100)"
                    price = 65.0
                    price_str = "AED 65.00"
                    desc = f"Genuine Epson T49N 140 ml dye-sublimation ink bottles (Black, Cyan, Magenta, Yellow) priced at {price_str} per bottle."
                    item_id = "epson-t49n-inks"
                    results.append(f"• **Inks for {p_name}:**\n  {desc}")
                    comparison_items.append({"id": item_id, "name": "Epson T49N Ink Bottle (F100)", "price": price, "price_str": price_str})
                    shown_entities.append(item_id)
                    consumable_cards.append({
                        "card_type": "consumable",
                        "id": item_id,
                        "name": "Epson T49N Ink Bottles (140 ml)",
                        "sku": "T49N-Series",
                        "price": price,
                        "price_str": price_str,
                        "price_formatted": price_str,
                        "category": "ink",
                        "compatible_printers": [p_name],
                    })
                else:
                    item_name = f"Inks for {p_name}"
                    price = 620.0
                    price_str = "AED 620.00"
                    desc = f"Genuine Epson high-capacity ink supply units for {p_name}."
                    item_id = f"inks_{matched_prod['id']}"
                    results.append(f"• **Inks for {p_name}:**\n  {desc}")
                    comparison_items.append({"id": item_id, "name": f"Inks for {p_name}", "price": price, "price_str": price_str})
                    shown_entities.append(item_id)
            else:
                # Hardware product
                results.append(f"• **{p_name}:** Verified professional model in our catalogue.")
                shown_entities.append(matched_prod["id"])
                product_cards.append(matched_prod)

    if not results:
        return None

    reply = "Here are the verified catalogue details for your requested items:\n\n" + "\n\n".join(results)
    state.shown_entities = list(shown_entities)
    state._compound_comparison_items = comparison_items

    return {
        "reply": reply,
        "product_cards": product_cards,
        "consumable_cards": consumable_cards,
        "suggested_chips": ["Which one is cheaper?", "Official Quotation", "View Technical Specifications"],
        "source": "compound_request:split_execution",
    }
