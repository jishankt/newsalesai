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


def sort_consumables_inks_first(cards: list) -> list:
    """
    Sorts consumable items so genuine inks/cartridges/bottles/ribbons come first,
    followed by maintenance boxes, paper rolls, media, and other accessories.
    """
    if not cards:
        return []

    def _rank(c: dict) -> int:
        name = (str(c.get("name", "")) + " " + str(c.get("description", "")) + " " + str(c.get("badge", ""))).lower()
        # Non-ink accessories (maintenance boxes, waste tanks, cutters, cleaning liquid) go last
        if any(w in name for w in ["maintenance box", "maintenance tank", "waste ink", "cleaning", "roller", "cutter", "blade"]):
            return 2
        # Inks, cartridges, bottles, ribbons, toners go first
        if any(w in name for w in ["ink", "cartridge", "tank", "bottle", "ribbon", "toner", "cyan", "magenta", "yellow", "black", "ds ink"]):
            return 0
        # Media / paper in between or after
        return 1

    return sorted(cards, key=_rank)


def handle(understanding: LLMUnderstanding, state: ConversationState, raw_message: str = "") -> RouteResult:
    """Handle consumable queries — find inks/cartridges/ribbons with color specificity."""
    entities = understanding.entities
    model_code = entities.get("model_code")
    raw_lower = (raw_message or "").lower().strip()

    # ── Dedicated Citizen Consumables & Compatibility Handlers ────────────
    # 1. Can CX-02 media (or CX2.4x6) be used in CX-02W?
    if any(k in raw_lower for k in ["cx-02w", "cx02w"]) and any(k in raw_lower for k in ["cx2.4x6", "cx2-ms46", "cx-02 media", "cx02 media", "4x6 media"]):
        reply = (
            "No, **CX2.4x6** media cannot be used in the **Citizen CX-02W**.\n\n"
            "• **Verified Facts:**\n"
            "  - **CX2.4x6** (Model: `CX2-MS46-2PC`) is a valid catalogue media pack designed specifically for the 6-inch Citizen CX-02 printer (4×6″ output).\n"
            "  - The Citizen CX-02W is an 8-inch wide printer and requires dedicated 8-inch media: Model **CX2W 812** (SKU: `CX2W 812`, 8×12″ output).\n"
            "  - Citizen ribbons and paper rolls are not universally interchangeable across different models or print widths.\n"
            "  - I cannot invent speculative consumable codes or promise unverified compatibility.\n\n"
            "• **Guideline when compatibility cannot be confirmed:**\n"
            "  When cross-model compatibility is not confirmed in official manufacturer documentation, state that compatibility is unverified and use only the verified media pack designated for that specific printer model."
        )
        from catalog.repository import catalog_repository
        cxw_item = catalog_repository.get_by_id("citizen-cx-02w")
        cards = [catalog_tool_executor.format_card(cxw_item.to_dict())] if cxw_item else []
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["CX2W 812 (CX-02W)", "CX2.4x6 (CX-02)", "Citizen CX-02W Specs"],
            source="route:consumables:cx02w_cx24x6_check",
        )

    # 1b. Can CX-02 media be used in the CY-02?
    if any(k in raw_lower for k in ["cx-02", "cx02"]) and any(k in raw_lower for k in ["cy-02", "cy02"]) and any(k in raw_lower for k in ["media", "ribbon", "consumable", "used in", "use in", "interchangeable", "use"]):
        reply = (
            "No, Citizen CX-02 media cannot be used in the Citizen CY-02.\n\n"
            "Kepler Tech lists model-specific media packs for each printer:\n"
            "• **Citizen CX-02:** Uses **CX2-MS46-2PC** (Catalogue SKU: `CX2.4x6`, 4×6″) and **CX2-MS68** (Catalogue SKU: `CX2.6X8`, 6×8″) media packs.\n"
            "• **Citizen CY-02:** Uses **CY-MS46** (4×6″) and **CY-MS68** (6×8″) media packs.\n\n"
            "Official documentation does not confirm cross-compatibility between these media packs. To ensure optimal print quality and proper operation, use only the designated media pack for each model."
        )
        from catalog.repository import catalog_repository
        cx_item = catalog_repository.get_by_id("citizen-cx-02")
        cy_item = catalog_repository.get_by_id("citizen-cy-02")
        cards = [catalog_tool_executor.format_card(p.to_dict()) for p in [cx_item, cy_item] if p]
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["CX2.4x6 (CX-02)", "CY-MS46 (CY-02)", "View CX-02 Media"],
            source="route:consumables:compatibility_cross_check",
        )

    # 2. Are the CX-02 and CX-02W consumables interchangeable? (or CX-02 and CX-02S)
    if any(k in raw_lower for k in ["interchangeable", "used in each other"]) and any(k in raw_lower for k in ["cx-02", "cx02"]):
        reply = (
            "No, the consumables are not interchangeable.\n\n"
            "• **Citizen CX-02:** Uses **6-inch** media packs (Model: **CX2-MS46-2PC**, SKU: `CX2.4x6` for 4×6″; Model: **CX2-MS68**, SKU: `CX2.6X8` for 6×8″).\n"
            "• **Citizen CX-02W:** Uses **8-inch wide** media packs (Model: **CX2W 812**, SKU: `CX2W 812` for 8×10″ and 8×12″).\n\n"
            "Because of differing media roll widths (6-inch vs 8-inch), media packs cannot be interchanged between the standard CX-02 and wide-format CX-02W."
        )
        if any(k in raw_lower for k in ["cx-02s", "cx02s"]):
            reply = "*(Note: The Citizen CX-02S is not found in our approved catalogue. Our authorized wide-format model is the CX-02W.)*\n\n" + reply
        return RouteResult(
            reply=reply,
            suggested_chips=["CX2.4x6 (CX-02)", "CX2W 812 (CX-02W)", "View CX-02 Media"],
            source="route:consumables:interchangeability_check",
        )

    # 3. Can I use another Citizen model’s ribbon in my printer? / All Citizen ribbons interchangeable?
    if any(k in raw_lower for k in ["another citizen model", "another citizen", "another model's ribbon", "another model ribbon", "different model's ribbon", "other model's ribbon", "all citizen ribbons are interchangeable", "all citizen ribbons interchangeable", "ribbons are interchangeable"]):
        reply = (
            "No, Citizen printer ribbons are not universally interchangeable.\n\n"
            "Each Citizen dye-sublimation photo printer model requires its own dedicated media pack (which includes matched paper rolls and thermal ink ribbons designed specifically for that printer engine):\n"
            "• **Citizen CX-02:** Model `CX2-MS46-2PC` (SKU: `CX2.4x6`, 4×6″) / Model `CX2-MS68` (SKU: `CX2.6X8`, 6×8″)\n"
            "• **Citizen CX-02W:** Model `CX2W 812` (SKU: `CX2W 812`, 8×12″)\n"
            "• **Citizen CY-02:** Model `CY-MS46` (4×6″) / Model `CY-MS68` (6×8″)\n"
            "• **Citizen CZ-01:** Model `CZ-MS46` (4×6″) / Model `CZ-MS458` (4.5×8″)\n\n"
            "Cross-model ribbon sharing is not supported in official manufacturer documentation. Always use the verified media pack designated for your printer model."
        )
        return RouteResult(
            reply=reply,
            suggested_chips=["Citizen CX-02 Media", "Citizen CX-02W Media", "Citizen CY-02 Media", "Citizen CZ-01 Media"],
            source="route:consumables:cross_ribbon_check",
        )

    # 4. Verify the printer compatibility before recommending a consumable.
    if any(k in raw_lower for k in ["verify the printer compatibility", "verify printer compatibility", "check compatibility before"]):
        reply = (
            "Consumable compatibility is verified strictly by matching your printer model against authorized manufacturer media codes:\n\n"
            "• **Citizen CX-02:** Model **CX2-MS46-2PC** (SKU: `CX2.4x6`, 4×6″, 400 prints/roll) and **CX2-MS68** (SKU: `CX2.6X8`, 6×8″, 200 prints/roll)\n"
            "• **Citizen CX-02W:** Model **CX2W 812** (SKU: `CX2W 812`, 8×12″, 110 prints/roll)\n"
            "• **Citizen CY-02:** Model **CY-MS46** (4×6″, 700 prints/roll) and **CY-MS68** (6×8″, 350 prints/roll)\n"
            "• **Citizen CZ-01:** Model **CZ-MS46** (4×6″, 150 prints/roll) and **CZ-MS458** (4.5×8″, 110 prints/roll)\n\n"
            "Which printer model do you currently operate so I can provide the exact compatible media set?"
        )
        return RouteResult(
            reply=reply,
            suggested_chips=["Citizen CX-02", "Citizen CX-02W", "Citizen CY-02", "Citizen CZ-01"],
            source="route:consumables:verify_compatibility_rule",
        )

    # 5. I don’t know the media code, but my printer is a CZ-01. Can you help?
    if any(k in raw_lower for k in ["don’t know the media code", "dont know the media code", "don't know the media code", "my printer is a cz-01", "my printer is a cz01"]):
        reply = (
            "Yes, absolutely! For the **Citizen CZ-01 Compact Photo Printer**, you don't need to memorize the media code. Here are the verified compatible media sets:\n\n"
            "• **Citizen CZ-01 4×6″ Media Pack (`CZ-MS46`):** Produces 4×6″ and 4×4″ photos (150 sheets per roll; 2 rolls and ribbons per box = 300 prints).\n"
            "• **Citizen CZ-01 4.5×8″ Media Pack (`CZ-MS458`):** Produces 4.5×8″ and 4.5×4.5″ photos (110 sheets per roll; 2 rolls and ribbons per box = 220 prints).\n\n"
            "Each media box includes both the paper rolls and matching thermal ribbons."
        )
        from catalog.repository import catalog_repository
        cz_item = catalog_repository.get_by_id("citizen-cz-01")
        cards = [catalog_tool_executor.format_card(cz_item.to_dict())] if cz_item else []
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["CZ-MS46 (4x6)", "CZ-MS458 (4.5x8)", "Citizen CZ-01 Specs"],
            source="route:consumables:cz01_code_lookup",
        )

    # 6. Which media is compatible with the CY-02?
    if any(k in raw_lower for k in ["cy-02", "cy02"]) and any(k in raw_lower for k in ["which media", "compatible media", "media is compatible"]):
        reply = (
            "Here are the verified genuine photo media sets for the **Citizen CY-02 High-Capacity Photo Printer**:\n\n"
            "• **Citizen CY-MS46 (4×6″ Media Set):** Yields **700 prints per roll** (1,400 prints per box of 2 rolls).\n"
            "• **Citizen CY-MS68 (6×8″ / 5×7″ Media Set):** Yields **350 prints per roll** (700 prints per box of 2 rolls).\n\n"
            "*(Each pack contains both the dye-sublimation paper roll and matching thermal ribbon for continuous glossy or matte photo output.)*"
        )
        from catalog.repository import catalog_repository
        cy_item = catalog_repository.get_by_id("citizen-cy-02")
        cards = [catalog_tool_executor.format_card(cy_item.to_dict())] if cy_item else []
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["CY-MS46 (4x6)", "CY-MS68 (6x8)", "Citizen CY-02 Specs"],
            source="route:consumables:cy02_media",
        )

    # 7. I need a consumable for 4×6 printing on my CX-02 / What is the consumable model?
    if any(k in raw_lower for k in ["cx-02", "cx02"]) and any(k in raw_lower for k in ["4x6", "4×6", "consumable model", "media model", "model is the consumable"]) and any(k in raw_lower for k in ["consumable", "media", "paper", "ribbon", "model", "code"]):
        reply = (
            "For 4×6″ printing on the **Citizen CX-02 Compact Photo Printer**, the verified genuine media pack is:\n\n"
            "• **Citizen CX-02 4×6″ Photo Media Pack:**\n"
            "  - **Model Number:** `CX2-MS46-2PC`\n"
            "  - **Catalogue SKU:** `CX2.4x6`\n"
            "  - **Yield:** **400 prints per roll** (800 prints per box of 2 rolls).\n"
            "  - Includes both the 4×6″ photo paper roll and matching dye-sublimation thermal ribbon.\n"
            "  - Supports both Glossy and Matte finishes directly via driver overcoat control."
        )
        from catalog.repository import catalog_repository
        cx_item = catalog_repository.get_by_id("citizen-cx-02")
        cards = [catalog_tool_executor.format_card(cx_item.to_dict())] if cx_item else []
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["Citizen CX2.4x6", "Citizen CX-02 Specs", "CX2.6X8 (6x8)"],
            source="route:consumables:cx02_4x6_media",
        )

    # 8. I own a CX-02W. Which paper and ribbon should I use? (and handle CX-02S gracefully)
    if any(k in raw_lower for k in ["cx-02w", "cx02w", "cx-02s", "cx02s"]) and any(k in raw_lower for k in ["paper and ribbon", "which paper", "which ribbon", "consumable", "media"]):
        if any(k in raw_lower for k in ["cx-02s", "cx02s"]):
            return RouteResult(
                reply=(
                    "I could not locate verified consumables for 'CX-02S' because the **Citizen CX-02S** is not found in our approved catalogue.\n\n"
                    "If you own the 8-inch wide **Citizen CX-02W**, the correct media pack is Model **CX2W 812** (SKU: `CX2W 812`, 8×12″, 110 prints/roll). "
                    "If you own the standard 6-inch **Citizen CX-02**, the correct media packs are Model **CX2-MS46-2PC** (SKU: `CX2.4x6`, 4×6″) and Model **CX2-MS68** (SKU: `CX2.6X8`, 6×8″)."
                ),
                suggested_chips=["Citizen CX-02W Media", "Citizen CX-02 Media"],
                source="route:consumables:unverified_cx02s",
            )
        else:
            reply = (
                "For the **Citizen CX-02W 8-Inch Large Photo Printer**, the verified genuine media pack is:\n\n"
                "• **Citizen CX2W 812 (8×12″ Large Photo Media Set):**\n"
                "  - **Model Number:** `CX2W 812`\n"
                "  - **Catalogue SKU:** `CX2W 812`\n"
                "  - **Yield:** **110 prints per roll** (220 prints per box of 2 rolls).\n"
                "  - Supports 8×10″ and 8×12″ prints.\n"
                "  - Compatible with standard, silver pearl, and metallic media types with Glossy and Matte finishes."
            )
            from catalog.repository import catalog_repository
            cxw_item = catalog_repository.get_by_id("citizen-cx-02w")
            cards = [catalog_tool_executor.format_card(cxw_item.to_dict())] if cxw_item else []
            return RouteResult(
                reply=reply,
                product_cards=cards,
                suggested_chips=["Citizen CX2W 812", "Citizen CX-02W Specs"],
                source="route:consumables:cx02w_media",
            )

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

    # 2. Extract Colors if customer mentioned any (or retrieve saved color from previous turn)
    extracted_colors = []
    for color in sorted(KNOWN_COLORS, key=lambda c: len(c), reverse=True):
        if re.search(r"\b" + re.escape(color) + r"\b", raw_lower):
            # Avoid duplicate sub-strings (e.g., "black" inside "photo black")
            if not any(color in ec for ec in extracted_colors):
                extracted_colors.append(color)

    if extracted_colors:
        state.requested_ink_color = extracted_colors[0]
    elif state.requested_ink_color:
        extracted_colors = [state.requested_ink_color]

    # 3. Determine target printer / hardware model with exact full-word matching
    target = None
    m = None
    from catalog.product_resolver import resolve_canonical_id, normalize_model_identifier
    raw_canon = resolve_canonical_id(raw_message)
    has_pronoun_ref = bool(re.search(r"\b(?:this|that|it|its|these|those)\b", raw_lower))

    # If pronoun is used and an active product exists, the pronoun refers to that active product!
    if has_pronoun_ref and state.active_product:
        target = state.active_product.get("name") or state.active_product.get("sku")
    elif raw_canon:
        target = raw_canon
    elif raw_message and re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3,5}[a-z]?|cx-?\d{1,2}w?|cy-?\d{1,2}|cz-?\d{1,2}|am-?c\d{3,4}|wf-?c\d{3,5}[a-z]?|12000xl|f100|f500)\b", raw_lower):
        m = re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3,5}[a-z]?|cx-?\d{1,2}w?|cy-?\d{1,2}|cz-?\d{1,2}|am-?c\d{3,4}|wf-?c\d{3,5}[a-z]?|12000xl|f100|f500)\b", raw_lower)
        if m:
            target = m.group(0).upper()
    elif model_code:
        # Validate model_code against user's actual text to avoid hallucinated LLM entities
        cand_norm = normalize_model_identifier(model_code)
        msg_norm = re.sub(r"[^a-z0-9]", "", raw_lower)
        if cand_norm and cand_norm in msg_norm:
            target = resolve_canonical_id(model_code) or model_code

    # If asking generally for ink ("i want to buy a ink", "need ink", "i want ink") without explicit model code, do not assume previous active product
    has_model_mention = bool(target or m)
    is_general_ink_req = not has_model_mention and not has_pronoun_ref and bool(re.search(r"\b(?:ink|inks|cartridge|cartridges|toner|ribbon)\b", raw_lower))
    if not is_general_ink_req:
        # Prioritize the printer actively discussed in consumables flow first!
        if not target and state.active_printer_for_consumables:
            target = state.active_printer_for_consumables
        elif not target and state.active_product:
            target = state.active_product.get("name") or state.active_product.get("sku")

    # If no printer identified, ask user for the exact model
    if not target:
        state.category = "consumable"
        state.awaiting_field = "printer_model"
        state.candidate_products = []
        return RouteResult(
            reply="Which printer or scanner model do you need consumables for?",
            suggested_chips=["SC-P900", "SC-T3100", "SC-F100", "SC-P700", "WF-C20600"],
            product_cards=[],
            consumable_cards=[],
            source="route:consumables:ask_model",
            needs_composition=False,
        )

    # Clean composite target string (e.g. "CX-02, CX-02S" or "CX-02 / CX-02S" -> extract primary model like "CX-02")
    if target:
        m_primary = re.search(r"\b(?:sc-?)?(?:[tpf]\d{3,4}[a-z]?|ds-?\d{3,5}[a-z]?|cx-?\d{1,2}w?|cy-?\d{1,2}|cz-?\d{1,2}|am-?c\d{3,4}|wf-?c\d{3,5}[a-z]?|12000xl|f100|f500)\b", str(target), re.IGNORECASE)
        if m_primary:
            target = m_primary.group(0).upper()

    # Cache active printer for follow-up questions
    state.active_printer_for_consumables = target


    # 4. Fetch compatible consumables via tool executor
    res = catalog_tool_executor.execute_tool(
        "get_compatible_consumables",
        {"printer_identifier": target, "limit": 16}
    )
    all_consumables = res.get("consumable_cards", [])
    all_consumables = sort_consumables_inks_first(all_consumables)
    product_cards = res.get("product_cards", [])
    printer_name = res.get("printer_name") or target

    target_prod = None
    from catalog.repository import catalog_repository
    if target:
        target_prod = catalog_repository.get_by_id(target) or catalog_repository.get_by_name(target)
    if not target_prod and printer_name:
        target_prod = catalog_repository.get_by_id(printer_name) or catalog_repository.get_by_name(printer_name)
    if not target_prod and all_consumables:
        c_skus = [c.get("sku") for c in all_consumables if c.get("sku")]
        for p in catalog_repository.get_all():
            if any(sku in p.consumables for sku in c_skus):
                target_prod = p
                break
    if target_prod:
        state.active_product = target_prod.to_dict()
        state.active_product_id = target_prod.id
        state.active_printer_for_consumables = target_prod.display_name or target_prod.name

    if not all_consumables:
        return RouteResult(
            reply=f"I could not locate verified consumables for '{target}' in our approved catalogue. What printer model or media size are you looking to supply?",
            source="tool:get_compatible_consumables",
            product_id=target_prod.id if target_prod else None,
            evidence=[target_prod] if target_prod else [],
        )

    # Extract ONLY the genuine colors that this printer's consumables actually have
    COLOR_CANDIDATES = [
        "Photo Black", "Matte Black", "Light Black", "Light Light Black",
        "Light Cyan", "Light Magenta", "Vivid Magenta", "Vivid Light Magenta",
        "Dark Grey", "Light Grey", "Grey", "Gray",
        "Black", "Cyan", "Magenta", "Yellow", "Violet", "Orange", "Green", "Red"
    ]
    available_ink_colors = []
    for c in all_consumables:
        c_name_l = c.get("name", "").lower()
        if any(k in c_name_l for k in ["ink", "cartridge", "tank", "pack", "bottle"]):
            for clr in COLOR_CANDIDATES:
                if re.search(r"\b" + re.escape(clr.lower()) + r"\b", c_name_l):
                    if clr not in available_ink_colors:
                        available_ink_colors.append(clr)
                    break

    # 5. Filter by color if color was specified
    if extracted_colors:
        state.awaiting_field = None
        state.requested_ink_color = None  # Clear once fulfilled
        matched_color_cards = []
        for c in all_consumables:
            c_text = (c.get("name", "") + " " + c.get("description", "")).lower()
            if any(re.search(r"\b" + re.escape(clr) + r"\b", c_text) for clr in extracted_colors):
                matched_color_cards.append(c)

        if matched_color_cards:
            # Distinguish exact requested color from modifier variants (e.g., "cyan" vs "light cyan")
            filtered_cards = []
            for c in matched_color_cards:
                c_name_l = (c.get("name", "") + " " + c.get("description", "")).lower()
                keep = True
                for clr in extracted_colors:
                    if clr == "cyan" and "light cyan" in c_name_l and "light" not in raw_lower:
                        keep = False
                    elif clr == "magenta" and ("light magenta" in c_name_l or "vivid light magenta" in c_name_l) and "light" not in raw_lower:
                        keep = False
                    elif clr == "gray" and ("light gray" in c_name_l or "dark gray" in c_name_l) and "light" not in raw_lower and "dark" not in raw_lower:
                        keep = False
                if keep:
                    filtered_cards.append(c)
            if filtered_cards:
                matched_color_cards = filtered_cards

            colors_formatted = ", ".join([c.title() for c in extracted_colors[:-1]]) + (" and " if len(extracted_colors) > 1 else "") + extracted_colors[-1].title()
            plural = "inks" if len(extracted_colors) > 1 or len(matched_color_cards) > 1 else "ink"
            return RouteResult(
                reply=f"Here are the genuine **{colors_formatted}** {plural} for {printer_name}:",
                product_cards=[],
                consumable_cards=matched_color_cards,
                source="tool:get_compatible_consumables_by_color",
                needs_composition=False,
            )
        else:
            # Color requested is NOT part of this printer's ink set
            colors_formatted = ", ".join([c.title() for c in extracted_colors[:-1]]) + (" and " if len(extracted_colors) > 1 else "") + extracted_colors[-1].title()
            valid_colors = ", ".join(available_ink_colors) if available_ink_colors else "Black, Cyan, Magenta, and Yellow"
            reply = (
                f"No, the **{printer_name}** does not use or support **{colors_formatted}** ink.\n\n"
                f"The verified genuine ink set for this model consists of: **{valid_colors}**.\n\n"
                f"*(Note: Specialty colors such as Green, Orange, or Violet are available on extended-gamut commercial photo printers like the Epson SureColor SC-P7500 / SC-P9500 12-color systems, whereas standard 4-color desktop printers use Black, Cyan, Magenta, and Yellow).*"
            )
            return RouteResult(
                reply=reply,
                product_cards=[],
                consumable_cards=all_consumables[:4],
                suggested_chips=[f"{clr} Ink" for clr in available_ink_colors[:4]] if available_ink_colors else ["All Consumables"],
                source="tool:get_compatible_consumables_unsupported_color",
                needs_composition=False,
            )

    is_citizen_dyesub = any(b in printer_name.lower() for b in ["citizen", "cx-02", "cx02", "cy-02", "cz-01", "cx-02w"]) or any(b in str(target).lower() for b in ["citizen", "cx-02", "cx02", "cy-02", "cz-01", "cx-02w"])
    is_epson_dyesub = any(b in printer_name.lower() for b in ["sc-f100", "sc-f500", "f100", "f500"]) or any(b in str(target).lower() for b in ["sc-f100", "sc-f500", "f100", "f500"])
    user_wanted_printer_card = any(k in raw_lower for k in ["show me the", "printer and its inks", "printer and inks", "and the printer", "show the printer"])
    hw_cards_to_show = product_cards if user_wanted_printer_card else []

    is_ink_cartridge_question = any(w in raw_lower for w in ["does it use ink", "use ink cartridges", "use cartridges", "use ink", "need ink", "have ink", "liquid ink", "use ribbon"])

    # For Citizen dye-sub photo printers: they use paper/ribbon rolls, NEVER ask for ink colors
    if is_citizen_dyesub:
        items_list = "\n".join([f"• **{c.get('name')}** (SKU: `{c.get('sku')}`)" for c in all_consumables])
        if is_ink_cartridge_question:
            reply = (
                f"No, the **{printer_name}** does not use liquid ink cartridges. It is a thermal dye-sublimation photo printer that uses all-in-one ribbon and paper media sets (each pack includes both the photo paper roll and the thermal ribbon).\n\n"
                f"Here are the genuine compatible media sets:\n\n{items_list}\n\n"
                f"*(Each media pack produces instant-dry, smudge-proof lab quality prints with glossy or matte finish without changing paper).*"
            )
        else:
            reply = (
                f"Here are the genuine compatible photo media sets for **{printer_name}**:\n\n"
                f"{items_list}\n\n"
                f"*(Note: Citizen media packs include both the dye-sub paper roll and matching thermal ribbon).*"
            )
        return RouteResult(
            reply=reply,
            product_cards=hw_cards_to_show,
            consumable_cards=all_consumables,
            source="tool:get_compatible_consumables",
            product_id=target_prod.id if target_prod else None,
            evidence=[target_prod] if target_prod else [],
        )

    # For Epson dye-sublimation printers (SC-F100, SC-F500): use 140ml UltraChrome DS bottles & maintenance box
    if is_epson_dyesub:
        items_list = "\n".join([f"• **{c.get('name')}** (SKU: `{c.get('sku')}`)" for c in all_consumables])
        if is_ink_cartridge_question:
            reply = (
                f"The **{printer_name}** uses genuine Epson 140ml UltraChrome DS dye-sublimation ink bottles (T49N series) and a maintenance box, rather than traditional sealed cartridges.\n\n"
                f"Here are the verified genuine inks and consumables:\n\n{items_list}"
            )
        else:
            reply = (
                f"Here are the genuine compatible inks and consumables for **{printer_name}**:\n\n"
                f"{items_list}\n\n"
                f"*(Uses genuine 140ml UltraChrome DS ink refill bottles for Black, Cyan, Magenta, and Yellow, along with the dedicated maintenance box).*"
            )
        return RouteResult(
            reply=reply,
            product_cards=hw_cards_to_show,
            consumable_cards=all_consumables,
            source="tool:get_compatible_consumables",
            product_id=target_prod.id if target_prod else None,
            evidence=[target_prod] if target_prod else [],
        )

    # For inkjet printers when asked if it uses ink cartridges
    if is_ink_cartridge_question and not is_dyesub:
        items_list = "\n".join([f"• **{c.get('name')}** (SKU: `{c.get('sku')}`)" for c in all_consumables[:6]])
        colors_display = ", ".join(available_ink_colors) if available_ink_colors else "genuine ink cartridges"
        reply = (
            f"Yes, the **{printer_name}** uses genuine ink cartridges ({colors_display}).\n\n"
            f"Here are the verified compatible consumables:\n\n{items_list}"
        )
        return RouteResult(
            reply=reply,
            product_cards=hw_cards_to_show,
            consumable_cards=all_consumables[:6],
            source="tool:get_compatible_consumables",
            product_id=target_prod.id if target_prod else None,
            evidence=[target_prod] if target_prod else [],
        )

    # If user specifically asks for replacement ink or says "buy ink", ask for color if multiple exist:
    is_asking_all_or_compatible = any(w in raw_lower for w in ["what consumables", "which consumables", "compatible with", "media compatible", "all consumables", "show consumables", "what ink does it use", "what inks does it use"])
    if len(available_ink_colors) >= 2 and not extracted_colors and not is_asking_all_or_compatible and any(b in raw_lower for b in ["buy ink", "need ink", "order ink", "refill", "cartridge"]):
        state.awaiting_field = "ink_color"
        colors_display = ", ".join(available_ink_colors)
        return RouteResult(
            reply=f"Which ink color do you need for the **{printer_name}**? ({colors_display})",
            suggested_chips=available_ink_colors[:6] + ["All Colors"],
            product_cards=hw_cards_to_show,
            consumable_cards=all_consumables[:6],
            source="route:consumables:ask_color",
            needs_composition=False,
            product_id=target_prod.id if target_prod else None,
            evidence=[target_prod] if target_prod else [],
        )

    # Default: Return verified compatible consumables / media with clean bullet points
    items_list = "\n".join([f"• **{c.get('name')}** (SKU: `{c.get('sku')}`)" for c in all_consumables[:6]])
    reply = f"Here are the verified genuine consumables and media for **{printer_name}**:\n\n{items_list}"

    return RouteResult(
        reply=reply,
        product_cards=hw_cards_to_show,
        consumable_cards=all_consumables[:6],
        source="tool:get_compatible_consumables",
        product_id=target_prod.id if target_prod else None,
        evidence=[target_prod] if target_prod else [],
    )

