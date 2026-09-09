"""
Consumables Route for Kepler Tech Conversational AI.
Handles consumable/ink queries with full-word exact matching,
color-specific filtering, and color clarification prompts when ink color is unspecified.
"""

import logging
import re
from domain.conversation_types import LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState
from agent.tool_executor import catalog_tool_executor

logger = logging.getLogger("route:consumables")

# Known ink colors in Epson / professional printing
KNOWN_COLORS = [
    "black", "photo black", "matte black", "cyan", "magenta", "yellow", 
    "light cyan", "light magenta", "gray", "grey", "light gray", "light grey",
    "violet", "orange", "green", "red", "vivid magenta", "vivid light magenta"
]


def handle(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteResult:
    """Handle consumable queries — find inks/cartridges/ribbons with color specificity."""
    entities = understanding.entities
    model_code = entities.get("model_code")
    raw_lower = (raw_message or "").lower().strip()

    # 1. Direct Consumable SKU Match (e.g., customer asks for "C13T40D140" or "C13S210057")
    direct_sku_match = re.search(r"\b(c1[23][a-z0-9]{5,8}|c13s\d+|c12c\d+|ifa\s*\d+|olm\s*\d+)\b", raw_lower)
    if direct_sku_match:
        sku = direct_sku_match.group(1).upper()
        res_sku = catalog_tool_executor.execute_tool("get_product_specs", {"product_identifier": sku})
        if res_sku.get("success"):
            item = res_sku.get("product", {})
            card = catalog_tool_executor.format_card(item, card_type="consumable")
            p_name = item.get("name", sku)
            state.active_printer_for_consumables = None
            return RouteResult(
                reply=f"Here is the verified genuine consumable for **{p_name}** (SKU: {sku}):",
                consumable_cards=[card],
                source="tool:get_direct_consumable_sku",
            )

    # 2. Extract Color if customer mentioned one
    extracted_color = None
    for color in sorted(KNOWN_COLORS, key=lambda c: len(c), reverse=True):
        if re.search(r"\b" + re.escape(color) + r"\b", raw_lower):
            extracted_color = color
            break

    # 3. Determine target printer / hardware model with exact full-word matching
    target = None
    # If the user explicitly provided a model code in this turn
    if model_code:
        target = model_code
    elif raw_message:
        m = re.search(
            r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3,5}[a-z]?|cx-?\d{2}|cy-?\d{2}|cz-?\d{2}|am-?c\d{3,4}|wf-?c\d{3,4}[a-z]?|12000xl)\b",
            raw_lower
        )
        if m:
            target = m.group(0).upper()

    # If no explicit model code in query, rely on active printer context from previous turn
    if not target and state.active_printer_for_consumables:
        target = state.active_printer_for_consumables
    if not target and state.active_product:
        p_cat = state.active_product.get("category", "").lower()
        # Only use active_product if it is hardware or has consumables
        if any(hw_kw in p_cat for hw_kw in ["printer", "scanner", "large format", "business"]) or state.active_product.get("consumables"):
            target = state.active_product.get("name") or state.active_product.get("sku")

    # Fallback to identifying printer key if still unresolved
    if not target and raw_message:
        from rag.consumables_engine import consumables_engine
        target = consumables_engine.identify_printer_key(raw_message)

    # If no printer identified, ask user for the exact model
    if not target:
        state.category = "consumable"
        state.awaiting_field = "printer_model"
        return RouteResult(
            reply="Which printer or scanner model do you need consumables for?",
            suggested_chips=["SC-P900", "SC-T3100", "SC-F100", "SC-P700", "WF-C20600"],
            source="route:consumables",
        )

    # Cache active printer for follow-up questions
    state.active_printer_for_consumables = target

    # 4. Fetch compatible consumables via tool executor
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": target, "limit": 12}
    )
    all_consumables = res.get("consumable_cards", [])
    product_cards = res.get("product_cards", [])
    printer_name = res.get("printer_name") or target

    if not all_consumables:
        return RouteResult(
            reply=f"I could not locate verified consumables for '{target}' in our catalog. Please contact sales@keplertech.ae for specialty sourcing.",
            source="tool:get_compatible_consumables",
        )

    # 5. Check if user asked specifically for ink without specifying a color
    is_ink_query = any(k in raw_lower for k in ["ink", "cartridge", "inks", "cartridges"])
    
    # Filter by color if color was specified
    if extracted_color:
        matched_color_cards = [
            c for c in all_consumables 
            if extracted_color in c.get("name", "").lower() or extracted_color in c.get("description", "").lower()
        ]
        if matched_color_cards:
            item_names = ", ".join([c["name"] for c in matched_color_cards])
            return RouteResult(
                reply=f"Here is the genuine **{extracted_color.title()}** ink for {printer_name}:",
                product_cards=product_cards,
                consumable_cards=matched_color_cards,
                source="tool:get_compatible_consumables_by_color",
            )

    # If asking for ink generally and there are multiple colors, prompt for color with chips
    available_ink_colors = []
    for c in all_consumables:
        c_name = c.get("name", "").lower()
        for clr in ["Photo Black", "Matte Black", "Cyan", "Magenta", "Yellow", "Grey", "Violet"]:
            if clr.lower() in c_name and clr not in available_ink_colors:
                available_ink_colors.append(clr)

    if is_ink_query and len(available_ink_colors) >= 2 and not extracted_color:
        state.awaiting_field = "ink_color"
        ink_tech = ""
        p_lower = printer_name.lower()
        if "f100" in p_lower or "f500" in p_lower:
            ink_tech = "UltraChrome DS (T49N) sublimation inks and maintenance box"
        elif any(k in p_lower for k in ["t3100", "t5100", "t3400", "t5400"]):
            ink_tech = "UltraChrome XD2 pigment inks and maintenance box"
        elif "p700" in p_lower or "p900" in p_lower:
            ink_tech = "UltraChrome PRO10 inks and maintenance box"
        elif "p7500" in p_lower or "p9500" in p_lower:
            ink_tech = "UltraChrome PRO12 inks and maintenance box"

        prefix = f"The **{printer_name}** uses genuine {ink_tech}. " if ink_tech else ""
        return RouteResult(
            reply=f"{prefix}Which ink color do you need for the **{printer_name}**? (Black, Cyan, Magenta, Yellow, etc.)",
            suggested_chips=available_ink_colors[:5] + ["All Colors"],
            product_cards=product_cards,
            consumable_cards=all_consumables[:6],
            source="route:consumables:ask_color",
        )

    # Default: Return verified compatible consumables
    items = ", ".join([c["name"] for c in all_consumables[:3]])
    reply = f"Here are the genuine compatible consumables for {printer_name} (including {items}):"

    return RouteResult(
        reply=reply,
        product_cards=product_cards,
        consumable_cards=all_consumables[:6],
        source="tool:get_compatible_consumables",
    )

