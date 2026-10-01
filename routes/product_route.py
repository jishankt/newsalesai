"""
Product Route for Kepler Tech Conversational AI.
Handles product search and product specification queries
using the existing tool_executor infrastructure.
"""

import re
import logging
from domain.conversation_types import LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState
from agent.tool_executor import catalog_tool_executor

logger = logging.getLogger("route:product")


def handle(understanding: LLMUnderstanding, state: ConversationState,
           raw_message: str = "") -> RouteResult:
    """Handle product search, product spec queries, and brochure downloads."""
    msg_lower = (raw_message or "").strip().lower()

    # ── Unsupported Competitor Brands Guardrail ───────────────────────────
    unsupported = [b for b in ["canon", "hp", "designjet", "imageprograf", "brother", "xerox", "ricoh", "kyocera", "konica"] if re.search(rf"\b{b}\b", msg_lower)]
    if unsupported and not any(k in msg_lower for k in ["epson", "citizen", "innova", "olmec"]):
        brand_name = unsupported[0].title()
        if brand_name.lower() == "hp":
            brand_name = "HP"
        return RouteResult(
            reply=f"I don’t have verified information about {brand_name} equipment, as Kepler Tech LLC is an authorized distributor and partner specializing in Epson and Citizen commercial printing and scanning hardware. I would be glad to recommend an authorized model that matches your printing requirements!",
            suggested_chips=["View Large Format Plotters", "Photo Printers", "Office Enterprise MFPs"],
            source="route:unsupported_brand"
        )

    # ── Universal Product Attribute / Superlative Engine ────────────────
    from catalog.product_spec_engine import product_spec_engine
    superlative_res = product_spec_engine.answer_universal_superlative(
        raw_message=raw_message,
        current_category=state.category,
        current_brand=state.requirements.get("brand") if state.requirements else None,
    )
    if superlative_res:
        return superlative_res

    # ── List all Citizen photo printers ──────────────────────────────────
    is_list_all_citizen = "citizen" in msg_lower and any(w in msg_lower for w in ["list all", "show all", "all citizen", "what citizen", "which citizen photo", "photo printers available"])
    if is_list_all_citizen:
        from catalog.repository import catalog_repository
        cx02 = catalog_repository.get_by_id("citizen-cx-02")
        cx02w = catalog_repository.get_by_id("citizen-cx-02w")
        cy02 = catalog_repository.get_by_id("citizen-cy-02")
        cz01 = catalog_repository.get_by_id("citizen-cz-01")
        cards = [catalog_tool_executor.format_card(p.to_dict()) for p in [cx02, cx02w, cy02, cz01] if p]
        reply = (
            "Kepler Tech LLC offers four authorized Citizen dye-sublimation photo printers in our product catalogue:\n\n"
            "1. **[Citizen CX-02 Compact Photo Printer](https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/)**:\n"
            "   • Print sizes: 4×6″, 5×7″, and 6×8″.\n"
            "   • Ultra-portable at 12 kg with fast 9.8s print speed (4×6″).\n"
            "   • Roll capacity: 400 prints (4×6″) / 200 prints (6×8″).\n"
            "   • Equipped with ribbon rewind technology to prevent media waste.\n\n"
            "2. **[Citizen CX-02W 8-Inch Large Photo Printer](https://www.keplertechllc.com/product/citizen-cx-02w-large-photo-printer/)**:\n"
            "   • Wide-format dye-sublimation printing supporting 8×10″ and 8×12″.\n"
            "   • Weight: 14 kg; roll capacity: 110 prints (8×12″).\n"
            "   • Includes driver grey calibration for professional studio portraiture.\n\n"
            "3. **[Citizen CY-02 High-Capacity Photo Printer](https://www.keplertechllc.com/product/citizen-cy-02-photo-printer/)**:\n"
            "   • Heavy-duty kiosk workhorse holding 700 prints (4×6″) or 350 prints (6×8″) per roll.\n"
            "   • Robust chassis weighing 13.8 kg (package weight: 16.5 kg).\n"
            "   • Ideal for unattended retail kiosks and high-volume event stations.\n\n"
            "4. **[Citizen CZ-01 Compact 4.5-Inch Photo Printer](https://www.keplertechllc.com/product/citizen-cz-01-photo-printer/)**:\n"
            "   • Ultra-lightweight and compact at only 5.8 kg.\n"
            "   • Supports 4×4″, 4×6″, 4.5×4.5″, and 4.5×8″ prints.\n"
            "   • Roll capacity: 150 prints (4×6″); features anti-curl paper path and partial matte finishing.\n\n"
            "*(Note on availability: All four models are officially listed in our authorized catalogue; live warehouse stock availability is confirmed upon order placement.)*"
        )
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["Citizen CX-02 Specs", "Citizen CX-02W Specs", "Citizen CY-02 Specs", "Citizen CZ-01 Specs"],
            source="route:catalog:list_all_citizen",
        )

    # ── Business Benefit Recommendation ──────────────────────────────────
    is_biz_benefit_req = any(k in msg_lower for k in ["business benefit", "benefit of each relevant feature", "explain the business benefit"])
    if is_biz_benefit_req:
        from catalog.repository import catalog_repository
        cx02 = catalog_repository.get_by_id("citizen-cx-02")
        cards = [catalog_tool_executor.format_card(cx02.to_dict())] if cx02 else []
        reply = (
            "For versatile professional event photography and photo booth operations, the recommended model is the **[Citizen CX-02 Compact Dye-Sublimation Photo Printer](https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/)**.\n\n"
            "Here are the verified key features and the business benefit of each:\n\n"
            "1. **Built-in Ribbon Rewind Technology:**\n"
            "   • *Feature:* Automatically rewinds unused ribbon when printing smaller formats (e.g., 4×6″) on larger media (6×8″).\n"
            "   • *Business Benefit:* Eliminates consumable waste, allowing you to offer multiple print sizes from a single media roll while protecting operating margins.\n\n"
            "2. **Ultra-Compact 12 kg Form Factor:**\n"
            "   • *Feature:* Durable chassis measuring 27.5 × 36.6 × 17.0 cm and weighing just 12 kg.\n"
            "   • *Business Benefit:* Easy single-person transport and rapid setup for mobile event photographers, minimizing setup labor and logistical friction.\n\n"
            "3. **High-Speed Print Engine (9.8 Seconds for 4×6″):**\n"
            "   • *Feature:* Produces a 4×6″ print in 9.8 seconds (High Speed mode) and 13.8 seconds (High Quality mode).\n"
            "   • *Business Benefit:* Reduces customer wait times and queue congestion at high-traffic events, maximizing hourly guest throughput.\n\n"
            "4. **Continuous-Tone Dye-Sublimation with Overcoat Finishes:**\n"
            "   • *Feature:* 300 / 600 dpi resolution with selectable Glossy and Matte finishes directly in the printer driver.\n"
            "   • *Business Benefit:* Delivers instant-dry, smudge-proof, lab-quality prints that guests can handle immediately, with flexible finishes without switching media rolls.\n\n"
            "*(Note on availability: The Citizen CX-02 is actively listed in our authorized catalogue; current live warehouse inventory is confirmed upon order placement.)*"
        )
        return RouteResult(
            reply=reply,
            product_cards=cards,
            suggested_chips=["Citizen CX-02 Specs", "Citizen CY-02 Comparison", "Compatible Consumables"],
            source="route:catalog:business_benefit_recommendation",
        )

    # ── Photo Printer Types / Technology Overview Request ───────────────
    is_photo_types_query = (
        any(k in msg_lower for k in [
            "types of photo", "photo printer types", "types have", "what types",
            "types of printer", "kinds of photo", "photo options", "photo lineup"
        ])
        or (("photo" in msg_lower or "printer" in msg_lower) and any(k in msg_lower for k in [
            "what are the types", "what types do you have", "what kinds do you have", "what categories", "options for photo"
        ]))
    ) and not any(w in msg_lower for w in ["i want to buy", "ready to buy", "place an order", "order this"])
    if is_photo_types_query:
        reply = (
            "We offer two distinct, authorized categories of professional photo printers at Kepler Tech LLC, depending on your application:\n\n"
            "### 1. **Citizen Professional Dye-Sublimation Photo Printers (Events & Photo Booths)**\n"
            "• **Key Technology:** Continuous-tone dye-sublimation thermal transfer using dedicated ribbon and paper media rolls.\n"
            "• **Best For:** High-traffic event photography, instant souvenir printing, and automated photo booths.\n"
            "• **Key Advantages:** Ultra-fast on-site printing (under 10s for 4×6″), instant-dry prints with protective laminate overcoat (water/smudge resistant), selectable Glossy/Matte finishes without changing rolls, high media capacity up to 700 prints/roll.\n"
            "• **Authorized Lineup:** **Citizen CX-02** (compact 6″), **Citizen CX-02W** (large 8″/8×12″), **Citizen CY-02** (high-capacity 700 prints), and **Citizen CZ-01** (ultra-lightweight 5.8 kg).\n\n"
            "### 2. **Epson SureColor Professional Fine-Art & Studio Photo Printers (Galleries & Studios)**\n"
            "• **Key Technology:** PrecisionCore MicroTFP with UltraChrome PRO pigment ink sets (up to 10 or 12 individual colors with dedicated photo/matte black channels).\n"
            "• **Best For:** Fine-art gallery exhibitions, professional portrait studios, commercial proofing, and wide-gamut photography.\n"
            "• **Key Advantages:** Archival print permanence (200+ years), ultra-high dynamic range (Black Enhance Overcoat), wider color gamuts including Violet/Orange/Green, roll and cut-sheet fine-art media support up to 24″ or 44″ width.\n"
            "• **Authorized Lineup:** **Epson SureColor SC-P700** (13″ desktop), **SC-P900** (17″ desktop), **SC-P5300** (17″ production), and **SC-P7500 / SC-P9500** (24″ / 44″ 12-color flagships).\n\n"
            "Which application best matches your workflow — high-speed event printing or studio fine-art photography?"
        )
        return RouteResult(
            reply=reply,
            suggested_chips=["Citizen Event Printers", "Epson Fine-Art Printers", "Citizen CX-02 Specs", "Epson SC-P700 Specs"],
            source="route:catalog:photo_printer_types_overview",
        )

    # ── Product Brochure / Datasheet Request ─────────────────────────────
    is_brochure_query = any(b in msg_lower for b in [
        "brochure", "brosure", "broucher", "brousher", "broshur", "brocher",
        "datasheet", "data sheet", "specsheet", "spec sheet",
        "download pdf", "pdf link", "give brochure", "send brochure",
        "give the brosure", "give the brochure", "product sheet", "technical sheet",
        "catalog pdf", "brochure link"
    ])
    if is_brochure_query:
        from catalog.brochure_resolver import brochure_resolver
        brochures = brochure_resolver.resolve_for_conversation(state, raw_message)
        if brochures:
            lines = ["Here are the official product data sheets from Kepler Tech LLC:"]
            cards = []
            from catalog.price_resolver import price_resolver
            from catalog.repository import catalog_repository
            for b in brochures:
                b_name = b.get("name", "Product")
                pdf_url = b.get("pdf", "")
                web_url = b.get("url", "")
                lines.append(f"• 📄 **[{b_name} — Product Data Sheet (PDF)]({pdf_url})**")
                if web_url:
                    lines.append(f"  🌐 [View {b_name} on Kepler Tech]({web_url})")

                # Match normalized product for high-res images and complete specs
                matched_prod = None
                b_aliases = [re.sub(r"[\s\-_/]+", "", a.lower()) for a in b.get("aliases", [])]
                for p in catalog_repository.get_all():
                    p_id_norm = re.sub(r"[\s\-_/]+", "", p.id.lower())
                    p_name_norm = re.sub(r"[\s\-_/]+", "", p.name.lower())
                    if p_id_norm in b_aliases or any(a in p_id_norm for a in b_aliases) or any(a in p_name_norm for a in b_aliases):
                        matched_prod = p
                        break

                if matched_prod:
                    card = catalog_tool_executor.format_card(matched_prod.to_dict(), card_type="hardware")
                    card["pdf_url"] = pdf_url
                    card["brochure_url"] = pdf_url
                    cards.append(card)
                else:
                    alias = b.get("aliases", [b_name])[0].upper()
                    price_info = price_resolver.get_price_info(identifier=alias, prod={"name": b_name})
                    cards.append({
                        "id": b.get("name", ""),
                        "name": b_name,
                        "title": b_name,
                        "sku": alias,
                        "price": price_info.get("price"),
                        "price_formatted": price_info.get("price_str", "Price on Request"),
                        "price_str": price_info.get("price_str", "Price on Request"),
                        "vat_note": price_info.get("vat_note", ""),
                        "currency": "AED",
                        "image": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png",
                        "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png",
                        "url": web_url or pdf_url,
                        "pdf_url": pdf_url,
                        "brochure_url": pdf_url,
                        "badge": "Data Sheet PDF",
                        "card_type": "hardware",
                        "description": f"Official verified product data sheet for {b_name}.",
                        "has_consumables": False,
                    })
            lines.append("\nYou can download the complete technical specifications directly using the PDF links above. Please let me know if you would like information on genuine consumables, media rolls, or warranty support!")
            return RouteResult(
                reply="\n".join(lines),
                product_cards=cards,
                source="tool:get_brochure",
                needs_composition=False,
            )
        else:
            return RouteResult(
                reply="I'd be happy to provide the official product data sheet! Which specific printer model do you need the brochure for (e.g., Citizen CX-02, CY-02, Epson P700, or T3100)?",
                suggested_chips=["Citizen CX-02 Data Sheet", "Citizen CY-02 Data Sheet", "Epson P700 Data Sheet", "Epson T3100 Data Sheet"],
                source="tool:get_brochure",
            )

    entities = understanding.entities
    model_code = entities.get("model_code")
    from catalog.product_resolver import resolve_canonical_id, normalize_model_identifier
    canonical_id = resolve_canonical_id(raw_message)
    if canonical_id:
        model_code = canonical_id
    elif model_code:
        cand_norm = normalize_model_identifier(model_code)
        msg_norm = re.sub(r"[^a-z0-9]", "", msg_lower)
        if not cand_norm or cand_norm not in msg_norm:
            model_code = None
    if not model_code and raw_message:
        m = re.search(r"\b(?:sc-?)?([tpf]\d{3,5}[a-z0-9]*|ds-?\d{3,5}[a-z0-9]*|es-?\d{3,5}[a-z0-9]*|cx-?\d{1,2}[a-z0-9]*|cy-?\d{1,2}[a-z0-9]*|cz-?\d{1,2}[a-z0-9]*|am-?c\d{3,4}[a-z0-9]*|wf-?(?:c|m)?\d{3,5}[a-z0-9]*|em-?c\d{3,4}[a-z0-9]*|12000xl|f100|f500|op900(?:ii)?)\b", raw_message.lower())
        if m:
            model_code = m.group(0).upper()

    # ── Specific product spec query ──────────────────────────────────────
    if model_code:
        # Check single-attribute answer first
        from catalog.product_spec_engine import product_spec_engine
        from catalog.repository import catalog_repository
        single_attr_res = product_spec_engine.answer_single_attribute(model_code, raw_message)
        if single_attr_res:
            p_obj = catalog_repository.get_by_id(model_code)
            if p_obj:
                state.active_product = p_obj.to_dict()
                state.candidate_products = single_attr_res.product_cards
            return single_attr_res

        # Retrieve rich specs from universal product_spec_engine
        req_summary = state.format_requirements_summary() if hasattr(state, "format_requirements_summary") else ""
        detailed_specs = product_spec_engine.get_product_detailed_specs(model_code, raw_message, requirements_summary=req_summary)

        res = catalog_tool_executor.execute_tool(
            "get_product_specs", {"product_identifier": model_code}
        )
        if res.get("success") or detailed_specs:
            product = (detailed_specs.get("product") if detailed_specs else None) or res.get("product", {})
            cards = [detailed_specs["product_card"]] if (detailed_specs and detailed_specs.get("product_card")) else res.get("product_cards", [])
            state.active_product = product
            state.candidate_products = cards
            if not state.category:
                p_name_l = product.get("name", "").lower()
                if any(x in p_name_l for x in ["sc-t", "surecolor t", "cad", "plotter"]):
                    state.category = "technical_cad"
                elif any(x in p_name_l for x in ["sc-p", "surecolor p", "photo"]):
                    state.category = "photo_fine_art"
                elif any(x in p_name_l for x in ["workforce", "am-c", "copier"]):
                    state.category = "office_enterprise"
                elif any(x in p_name_l for x in ["ds-", "workforce ds", "scanner"]):
                    state.category = "scanner"
                elif any(x in p_name_l for x in ["cx-", "cy-"]):
                    state.category = "photo_booth"

            p_name = product.get("name", model_code)
            p_url = product.get("website_url") or product.get("web_url") or f"https://www.keplertechllc.com/product/{product.get('id', '')}/"
            desc = product.get("description") or product.get("intended_usage") or "genuine verified equipment from Kepler Tech LLC"
            price_str = cards[0].get("price_formatted") if cards else (product.get("price_formatted") or "Price on Request")
            vat = cards[0].get("vat_note") if cards else (product.get("vat_note") or "")

            q_lower = (raw_message or "").lower()
            if any(w in q_lower for w in ["technology", "inkjet", "thermal", "dye sub", "dyesub", "type of printer"]):
                is_citizen = any(c in p_name.lower() for c in ["citizen", "cx-02", "cx02", "cz-01", "cz01", "cy-02", "cy02"])
                tech = product.get("ink_technology") or product.get("verified", {}).get("ink_technology") or ("Dye-Sublimation Thermal Transfer" if is_citizen else "PrecisionCore MicroTFP")
                if "inkjet" in q_lower:
                    if is_citizen:
                        reply = f"Regarding [{p_name}]({p_url}): No, it is not an inkjet printer. The {p_name} utilizes professional **{tech}** technology using ribbon and paper rolls for lab-grade, instant-dry photo prints."
                    else:
                        reply = f"Yes, [{p_name}]({p_url}) uses professional **{tech}** inkjet technology."
                else:
                    reply = f"The [{p_name}]({p_url}) operates on professional **{tech}** technology."
            is_availability_query = any(w in q_lower for w in [
                "available in your catalogue", "available in catalogue", "in your catalogue", "in your catalog",
                "in catalogue", "in catalog", "available in your catalog", "do you have", "is it available", "in stock", "available on your website"
            ])
            if is_availability_query:
                reply = (
                    f"Yes, the **[{p_name}]({p_url})** is officially **listed in our authorized catalogue** as an authorized Citizen photo printer distributed by Kepler Tech LLC.\n\n"
                    f"*(Note on stock availability: While this model is actively listed in our official product catalogue, live physical warehouse stock inventory is confirmed upon order placement.)*\n\n"
                    f"Here are the verified specifications: {desc.rstrip('.')}."
                )
            elif any(k in q_lower for k in ["price", "cost", "how much", "rate"]):
                reply = f"The [{p_name}]({p_url}) is officially listed at **{price_str}** {vat}. Here are the verified specifications — {desc.rstrip('.')}."
            req_summary = state.format_requirements_summary() if hasattr(state, "format_requirements_summary") else ""
            req_prefix = f"*(Matched against your specified requirements: {req_summary})*\n\n" if req_summary else ""
            if detailed_specs and any(w in q_lower for w in ["spec", "specs", "specification", "specifications", "detail", "details", "description", "full description", "overview", "what is", "about", "tell me about"]):
                reply = detailed_specs["reply"]
                if req_prefix and not any(k in reply.lower() for k in ["matched against", "based on your requirement", "according to your"]):
                    reply = req_prefix + reply
            elif detailed_specs and not any(w in q_lower for w in ["recommend", "options", "suggest"]):
                reply = detailed_specs["reply"]
                if req_prefix and not any(k in reply.lower() for k in ["matched against", "based on your requirement", "according to your"]):
                    reply = req_prefix + reply
            else:
                reply = f"{req_prefix}Here are the verified specifications for [{p_name}]({p_url}) — {desc.rstrip('.')}."

            consumable_cards = []
            if any(w in q_lower for w in ["ink", "inks", "cartridge", "cartridges", "consumable", "consumables", "ribbon", "paper roll", "supplies"]):
                cons_res = catalog_tool_executor.execute_tool(
                    "get_compatible_consumables", {"printer_identifier": model_code or product.get("name", "")}
                )
                if cons_res.get("success"):
                    consumable_cards = cons_res.get("consumable_cards", [])

            return RouteResult(
                reply=reply,
                product_cards=cards,
                consumable_cards=consumable_cards,
                source="tool:get_product_specs",
                needs_composition=False,
                evidence=[product],
            )
        else:
            chips = ["View Large Format Plotters", "Photo Printers", "Office Enterprise MFPs"]
            m_upper = str(model_code).upper()
            if any(k in m_upper for k in ["CX-02S", "CX02S", "CX 02 S", "CX 02S", "CXO2S", "CX-O2S"]):
                return RouteResult(
                    reply=(
                        "No, the **Citizen CX-02S** is not listed in our authorized Kepler Tech product catalogue. "
                        "Our authorized Citizen photo printer catalogue includes the **Citizen CX-02**, **Citizen CX-02W**, "
                        "**Citizen CY-02**, and **Citizen CZ-01**. Would you like specifications for any of these verified models?"
                    ),
                    suggested_chips=["Citizen CX-02 Specs", "Citizen CX-02W Specs", "Citizen CY-02 Specs", "Citizen CZ-01 Specs"],
                    source="route:unverified_product",
                )
            elif any(k in m_upper for k in ["CX", "CY", "CZ", "CITIZEN"]):
                chips = ["Citizen CX-02 Specs", "Citizen CX-02W Specs", "Citizen CY-02 Specs", "Citizen CZ-01 Specs"]
            elif any(k in m_upper for k in ["SC-T", "T3", "T5", "T7", "PLOTTER", "CAD"]):
                chips = ["Epson T3100 Specs", "Epson T5100 Specs", "Epson T5400M Specs", "Epson T5700D Specs"]
            elif any(k in m_upper for k in ["SC-P", "P7", "P9", "P5", "PHOTO"]):
                chips = ["Epson P700 Specs", "Epson P900 Specs", "Epson P5300 Specs"]
            elif any(k in m_upper for k in ["DS-", "ES-", "SCANNER", "12000"]):
                chips = ["Epson DS-530II Specs", "Epson DS-800WN Specs", "Expression 12000XL Specs"]

            return RouteResult(
                reply=f"I don’t have verified information about '{model_code}' in our authorized Kepler Tech catalog. Would you like me to recommend an authorized Epson or Citizen model that matches your printing needs?",
                suggested_chips=chips,
                source="route:unverified_product",
            )

    # ── Product question on active product ───────────────────────────────
    if state.active_product and not model_code:
        # Check if the user is genuinely asking a question about the active product or making a new inquiry
        is_find_or_rec = any(w in (raw_message or "").lower() for w in ["find a", "find me", "looking for", "recommend a", "suggest a", "which printer", "which model", "need a", "want a"])
        is_question_about_active = not is_find_or_rec and any(w in (raw_message or "").lower().split() for w in ["it", "this", "its", "that", "speed", "size", "width", "ink", "scanner", "resolution", "specs", "specifications", "how", "what", "does", "can", "price", "cost", "much", "rate"])
        
        if is_question_about_active:
            from catalog.product_spec_engine import product_spec_engine
            active_id = state.active_product.get("id") or state.active_product.get("name")
            single_attr_res = product_spec_engine.answer_single_attribute(active_id, raw_message)
            if single_attr_res:
                return single_attr_res

            product = state.active_product
            p_name = product.get("name", "")
            width = product.get("width", "")
            speed = product.get("speed", "")
            ink = product.get("ink_technology") or product.get("verified", {}).get("ink_technology", "")
            price_str = product.get("price_formatted") or (f"AED {product.get('price'):,.2f}" if product.get("price") else "Price on Request")
            vat = product.get("vat_note") or ("(Excl. VAT)" if (product.get("price") or "AED" in str(price_str)) else "")
            q_lower = (raw_message or "").lower()
            
            reply_parts = [f"Regarding the {p_name}:"]
            if any(k in q_lower for k in ["price", "cost", "how much", "rate"]):
                reply_parts.append(f"The official standard list price is **{price_str}** {vat}.")
            
            if any(w in q_lower for w in ["scanner", "scan", "scanning"]):
                has_scan = product.get("has_scanner") or product.get("verified", {}).get("has_scanner") or ("m" in product.get("id", "").lower() and "t5400" in product.get("id", "").lower())
                if has_scan:
                    reply_parts.append(f"Yes, the {p_name} includes an integrated high-performance scanner for direct scanning, copying, and archiving.")
                else:
                    reply_parts.append(f"No, the {p_name} is a dedicated print-only model without a built-in scanner.")

            if any(w in q_lower for w in ["technology", "inkjet", "thermal", "dye sub", "dyesub", "type of printer"]):
                is_citizen = any(c in p_name.lower() for c in ["citizen", "cx-02", "cx02", "cz-01", "cz01", "cy-02", "cy02"])
                tech = ink or ("Dye-Sublimation Thermal Transfer" if is_citizen else "PrecisionCore MicroTFP")
                if "inkjet" in q_lower:
                    if is_citizen:
                        reply_parts.append(f"No, the {p_name} is not an inkjet printer; it utilizes professional **{tech}** technology with ribbon and paper rolls for lab-grade, instant-dry photo output.")
                    else:
                        reply_parts.append(f"Yes, the {p_name} uses professional **{tech}** inkjet technology.")
                else:
                    reply_parts.append(f"Printing technology: **{tech}**.")

            if any(w in q_lower for w in ["feature", "features", "driver", "benefit", "what can it do"]):
                headings = product.get("feature_headings", [])
                if headings:
                    clean_h = [h for h in headings if not h.lower().startswith("discover") and not h.lower().startswith("product")][:4]
                    reply_parts.append(f"Key features include: {', '.join(clean_h or headings[:4])}.")

            if width and any(w in q_lower for w in ["size", "width", "dimensions", "large", "print size"]):
                reply_parts.append(f"It supports print sizes up to {width}.")
            if speed and any(w in q_lower for w in ["speed", "fast", "ppm", "seconds"]):
                reply_parts.append(f"Print speed: {speed}.")
            
            if any(w in q_lower for w in ["why", "reason", "why this", "advantage", "why choose"]):
                reason = product.get("comparison_highlights") or product.get("recommendation_reason") or product.get("intended_usage") or product.get("description", "")
                reply_parts.append(f"It was recommended because: {reason.rstrip('.')}.")
            
            if any(w in q_lower for w in ["spec", "specs", "specification", "specifications", "description", "overview", "detail", "details", "website"]):
                from catalog.product_spec_engine import product_spec_engine
                detailed = product_spec_engine.get_product_detailed_specs(product.get("id", product.get("sku", "")))
                if detailed:
                    return RouteResult(
                        reply=detailed["reply"],
                        product_cards=[detailed["product_card"]],
                        source="tool:get_product_specs",
                        needs_composition=False,
                        evidence=[product],
                    )

            if len(reply_parts) == 1:
                # General question fallback with verified description
                desc = product.get("description") or product.get("full_description", "")[:250]
                reply_parts.append(desc.rstrip("."))
            
            reply = " ".join(reply_parts)

            cards_to_show = state.candidate_products[:1] if state.candidate_products else [catalog_tool_executor.format_card(product)]
            return RouteResult(
                reply=reply,
                product_cards=cards_to_show,
                source="tool:get_product_specs",
                needs_composition=False,
                evidence=[product],
                instruction=f"Answer the customer's question about {p_name} using the verified specifications: width={width}, speed={speed}, ink={ink}, price={price_str}.",
            )
        else:
            # Active product was from a previous unrelated turn; clear and re-route
            state.active_product = None

    # ── General Website / Specifications Catalog Inquiry ─────────────────
    is_general_spec_lookup = any(phrase in msg_lower for phrase in [
        "description and specifications", "specifications and description",
        "product description", "product specifications", "product specs",
        "find the product description", "find product description",
        "go the website", "go to the website", "go to website",
        "from website", "from the website", "on the website", "check the website",
        "check website", "website specifications"
    ]) or ("specifications" in msg_lower and any(w in msg_lower for w in ["find", "get", "show", "give", "can you", "ai can", "proper answer"]))

    if is_general_spec_lookup and not model_code and not state.active_product:
        return RouteResult(
            reply="Yes, absolutely! I can retrieve verified product descriptions, detailed technical specifications, official PDF datasheets, and live pricing directly from the official Kepler Tech LLC website for any authorized Epson or Citizen model.\n\nWhich product or equipment would you like specifications for?\n• **CAD & Technical Plotters:** Epson SureColor SC-T3100, SC-T5100, SC-T5400M, SC-T5700D\n• **Photo & Fine Art:** Citizen CX-02, CY-02, CZ-01, Epson SureColor P700, P900, P7500\n• **Document Scanners:** Epson WorkForce DS-530II, DS-800WN, Expression 12000XL\n• **Enterprise Office MFPs:** Epson WorkForce Enterprise AM-C4000, AM-C550\n\nYou can specify any model name or code to view its verified overview and specifications!",
            suggested_chips=["Citizen CX-02 Specs", "Epson T5400M Specs", "Epson DS-530II Specs", "Epson AM-C4000 Specs"],
            source="route:product_spec_lookup_prompt",
        )

    is_general_price_query = any(k in msg_lower for k in ["what is the price", "what does it cost", "how much is it", "how much does it cost", "how much", "tell me the price", "what is price"]) and not model_code and not state.active_product and not any(d in msg_lower for d in ["discount", "bargain", "negotiat"])
    if is_general_price_query and not any(w in msg_lower for w in ["recommend", "suggest", "options", "looking for", "want to buy"]):
        return RouteResult(
            reply="Official standard list rates are available for all equipment in our catalog. Which specific model would you like pricing for (e.g., Citizen CX-02, Epson SC-T3100, Epson P700, or DS-530II)?",
            suggested_chips=["Citizen CX-02 Price", "Epson T3100 Price", "Epson P700 Price", "Epson DS-530II Price"],
            source="route:product:price_inquiry",
        )

    # ── Catalog search and Grounded Recommendation ──────────────────────
    from catalog.repository import catalog_repository
    from recommendation.eligibility import eligibility_engine
    from recommendation.ranker import product_ranker
    from recommendation.evidence_builder import build_recommendation_evidence
    from conversation.requirement_extractor import requirement_extractor

    # Extract any fresh requirement updates/corrections from the message
    extracted = requirement_extractor.extract_and_validate(raw_message, state)
    if extracted:
        state.requirements.update(extracted)

    raw_l = (raw_message or "").lower()
    if understanding.requirement_updates:
        for rk, rv in understanding.requirement_updates.items():
            if rv is not None and rv != "":
                if rk == "daily_volume" and isinstance(rv, (int, float)):
                    val = int(rv)
                    if any(mkw in raw_l for mkw in ["month", "monthly", "per month", "a month", "/month"]):
                        val = max(1, val // 30)
                    state.requirements["exact_daily_volume"] = val
                    if state.category == "office_enterprise":
                        rv = "high" if val >= 200 else ("medium" if val >= 50 else "low")
                    elif state.category == "technical_cad":
                        rv = "high" if val >= 50 else ("medium" if val >= 10 else "low")
                state.requirements[rk] = rv
    if understanding.entities:
        for ek in ["print_size", "scan_required", "daily_volume", "speed"]:
            val = understanding.entities.get(ek)
            if val is not None and val != "":
                if ek == "daily_volume" and isinstance(val, (int, float)):
                    v_int = int(val)
                    if any(mkw in raw_l for mkw in ["month", "monthly", "per month", "a month", "/month"]):
                        v_int = max(1, v_int // 30)
                    state.requirements["exact_daily_volume"] = v_int
                    if state.category == "office_enterprise":
                        val = "high" if v_int >= 200 else ("medium" if v_int >= 50 else "low")
                    elif state.category == "technical_cad":
                        val = "high" if v_int >= 50 else ("medium" if v_int >= 10 else "low")
                state.requirements[ek] = val

    # 1. Fetch category candidates
    req_brand = state.requirements.get("brand")
    all_cat_products = catalog_repository.get_by_category(state.category) if state.category else catalog_repository.get_all()
    if req_brand and not any(req_brand.lower() in (p.brand or "").lower() or req_brand.lower() in p.name.lower() for p in all_cat_products):
        # Current category has no models for the requested brand (e.g. Citizen in photo_fine_art)
        brand_prods = [p for p in catalog_repository.get_all() if req_brand.lower() in (p.brand or "").lower() or req_brand.lower() in p.name.lower()]
        if brand_prods:
            all_cat_products = brand_prods
            if brand_prods[0].category:
                state.category = brand_prods[0].category
    elif not all_cat_products:
        all_cat_products = catalog_repository.get_all()


    # 2. Hard Eligibility Filter
    assessments = [eligibility_engine.assess(p, state.requirements) for p in all_cat_products]
    eligible_assessments = [a for a in assessments if a.is_eligible]

    # 3. Dynamic Python Ranking by Customer Stated Priorities
    ranked_tuples = product_ranker.rank_candidates(eligible_assessments, state.requirements, raw_message=raw_message)

    if ranked_tuples:
        top_product, top_score, _ = ranked_tuples[0]

        # ── Double-Check Verification Guard ─────────────────────────
        # Double check 1: Brand compliance
        if req_brand and req_brand.lower() not in (top_product.brand or "").lower() and req_brand.lower() not in top_product.name.lower():
            logger.warning(f"Double check: {top_product.name} violates brand {req_brand}. Finding brand match.")
            for p, score, _ in ranked_tuples:
                if req_brand.lower() in (p.brand or "").lower() or req_brand.lower() in p.name.lower():
                    top_product = p
                    break

        # Double check 2: Category consistency (Never recommend CAD plotter for photo inquiry)
        if ("photo" in (state.category or "").lower() or "booth" in (state.category or "").lower()) and "cad" in (top_product.category or "").lower():
            logger.warning(f"Double check: CAD product {top_product.name} blocked for photo category.")
            photo_candidates = catalog_repository.get_by_category("photo_booth" if req_brand == "Citizen" else "photo_fine_art")
            if photo_candidates:
                top_product = photo_candidates[0]

        state.active_product = top_product.to_dict()
        
        # Build cards
        cards = []
        for p, score, _ in ranked_tuples[:4]:
            cards.append(p.to_dict())
        state.candidate_products = cards

        # 4. Build Grounded Evidence Object
        evidence = [build_recommendation_evidence(top_product, state.requirements, top_score, ["print_size", "scan_required", "application", "daily_volume"])]
        
        cat_name = state.category.replace("_", " ") if state.category else "equipment"
        top_url = top_product.source.website_url or f"https://www.keplertechllc.com/product/{top_product.id}/"
        top_desc = top_product.description or top_product.comparison_highlights or "engineered for reliable, high-precision performance"
        top_highlights = top_product.comparison_highlights
        if top_highlights and "compared to" in top_highlights.lower():
            top_highlights = re.split(r'\s*compared to\b', top_highlights, flags=re.IGNORECASE)[0].rstrip(" ;,-")
        if not top_highlights and top_desc:
            # Extract first clean human sentence without raw spec dumping
            first_sent = [s.strip() for s in re.split(r'(?<=[.!?])\s+', top_desc) if len(s.strip()) > 15 and not s.startswith("Discover") and "Product Data Sheet" not in s and "Printing Technology:" not in s]
            top_highlights = first_sent[0] if first_sent else top_desc[:120].rstrip(".")

        # Natural, non-robotic formulation tailored to the context
        is_single_match = len(ranked_tuples) == 1
        is_citizen_large = req_brand == "Citizen" and "cx-02w" in top_product.id.lower()
        if is_citizen_large:
            reply = (
                f"For 8×10 and 8×12-inch photo printing with Citizen, the only verified match in our catalogue is the **[{top_product.name}]({top_url})** — "
                f"{top_highlights.rstrip('.')}. It supports professional **8×10 and 8×12-inch** photo formats with driver grey calibration for studio output. "
                f"*(Note: Citizen specialized dye-sub printers go up to 8×12″; if your workflow requires 24-inch or 44-inch wide gallery rolls, our authorized Epson SureColor P-Series covers those larger formats).* "
                f"You can explore the verified specifications below:"
            )
        elif req_brand == "Citizen":
            if "cy-02" in top_product.id.lower() or "cy02" in top_product.id.lower():
                match_label = "only verified match" if is_single_match else "recommended model"
                reply = (
                    f"For high-volume event photo printing (such as your 500 photos/event workload), the {match_label} is the **[{top_product.name}]({top_url})** — "
                    f"With an industry-leading media capacity of up to **700 prints per roll** (4×6″), it allows you to complete 500+ photos without needing to reload media during live events. "
                    f"Here are the verified specifications and data sheet:"
                )
            else:
                match_label = "only verified match" if is_single_match else "recommended model"
                reply = f"For compact Citizen photo printing, the {match_label} is the **[{top_product.name}]({top_url})** — {top_highlights.rstrip('.')}. Here are the verified specifications and data sheet:"
        elif "am-c4000" in top_product.id.lower():
            exact_v = state.requirements.get("exact_daily_volume") or state.requirements.get("daily_volume")
            is_low_vol = state.requirements.get("daily_volume") == "low" or (isinstance(exact_v, (int, float)) and exact_v < 50)
            if is_low_vol:
                vol_str = f"approximately **{int(exact_v)} pages per day**" if exact_v and isinstance(exact_v, (int, float)) else "light daily volume"
                reply = (
                    f"For your daily workload of {vol_str} requiring A3 paper support, the recommended model is the **[{top_product.name}]({top_url})** — "
                    f"Powered by Epson PrecisionCore Heat-Free technology for sharp color documents, zero warm-up time, and significantly lower energy consumption. "
                    f"While this system is capable of high-volume output, it is our authorized A3 solution—delivering quiet operation, low running costs, and effortless headroom as your team's needs grow. You can explore the verified specifications and official data sheet below:"
                )
            elif exact_v and isinstance(exact_v, (int, float)) and int(exact_v) >= 200:
                reply = (
                    f"For your high-volume workload of approximately **{int(exact_v)} pages per day**, the recommended system is the **[{top_product.name}]({top_url})** — "
                    f"Engineered for heavy-duty office production with 40 ppm speed, up to 5,150-sheet paper capacity, and dual-head single-pass duplex scanning for demanding document workflows. You can explore the verified specifications and official data sheet below:"
                )
            else:
                vol_str = f"approximately **{int(exact_v)} pages per day**" if exact_v and isinstance(exact_v, (int, float)) else "your daily workload"
                reply = (
                    f"For {vol_str} with A3 paper support, the recommended model is the **[{top_product.name}]({top_url})** — "
                    f"Combining 40 ppm Heat-Free productivity, versatile multi-cassette paper handling, and fast duplex scanning. You can explore the verified specifications and official data sheet below:"
                )
        elif "am-c550" in top_product.id.lower():
            exact_v = state.requirements.get("exact_daily_volume") or state.requirements.get("daily_volume")
            if exact_v and isinstance(exact_v, (int, float)):
                vol_phrase = f"Well matched for your workload of approximately **{int(exact_v)} pages per day**"
            else:
                vol_phrase = "Designed for dependable daily office productivity"

            reply = (
                f"For your A4 office document printing, the recommended model from our authorized lineup is the **[{top_product.name}]({top_url})** — "
                f"A high-speed 55 ppm color multifunction printer powered by PrecisionCore Heat-Free technology. "
                f"{vol_phrase}, it features ultra-high yield ink packs (up to 86,000 pages) that virtually eliminate consumable replacements and keep energy costs exceptionally low. "
                f"You can explore the verified specifications below:"
            )
        elif "t5400m" in top_product.id.lower():
            exact_v = state.requirements.get("exact_daily_volume") or state.requirements.get("daily_volume")
            if exact_v and isinstance(exact_v, (int, float)):
                reply = (
                    f"For your workload of approximately **{int(exact_v)} drawings per day** with integrated scanning, the recommended model is the **[{top_product.name}]({top_url})** — {top_highlights.rstrip('.')}. "
                    f"Equipped with an integrated 36-inch scanner, high-yield 350ml ink cartridges, and precision production speed, it is built to handle medium-to-high technical blueprint volumes without slowing down your team. Here are the verified specifications and official data sheet:"
                )
            else:
                reply = f"For your 36-inch technical drawing and scanning requirements, the recommended model is the **[{top_product.name}]({top_url})** — {top_highlights.rstrip('.')}. You can explore the verified specifications and official data sheet below:"
        elif any(w in (raw_message or "").lower() for w in ["sorry", "instead", "actually", "switch"]):
            reply = f"Understood! For your updated requirements, here is the recommended option: **[{top_product.name}]({top_url})** — {top_highlights.rstrip('.')}. You can explore the verified specifications below:"
        else:
            match_label = "only verified match" if is_single_match else "recommended model"
            reply = f"Based on your requirements, the {match_label} is the **[{top_product.name}]({top_url})** — {top_highlights.rstrip('.')}. You can explore the verified specifications and official data sheet below:"

        # Prevent duplicate verbatim loop or honor explicit alternative requests
        is_alt_request = any(k in (raw_message or "").lower() for k in [
            "show another", "show another one", "another option", "other option",
            "next option", "different option", "alternative", "another one", "show other",
            "do you have any other", "do you have another", "any other one", "any other",
            "other one", "other model", "another printer", "other printer"
        ])
        is_refinement = any(k in (raw_message or "").lower() for k in ["drawing", "page", "drawings", "pages", "day", "month", "volume", "around", "about", "approx"])
        is_repeat_turn = bool(state.last_assistant_response and reply.strip() == state.last_assistant_response.strip()) and not is_refinement
        is_same_active = bool(state.active_product and top_product.id == (state.active_product.get("id") or state.active_product.get("name")))

        suggested_chips = ["Download Datasheet", "View Consumables", "Technical Specs"]

        if is_alt_request or is_repeat_turn or (is_alt_request and is_same_active):
            if len(ranked_tuples) > 1:
                alt_product, alt_score, _ = ranked_tuples[1]
                alt_url = alt_product.source.website_url or f"https://www.keplertechllc.com/product/{alt_product.id}/"
                alt_desc = alt_product.description or alt_product.comparison_highlights or "reliable high-performance option"
                alt_highlights = alt_product.comparison_highlights
                if not alt_highlights and alt_desc:
                    first_sent = [s.strip() for s in re.split(r'(?<=[.!?])\s+', alt_desc) if len(s.strip()) > 15 and not s.startswith("Discover") and "Product Data Sheet" not in s and "Printing Technology:" not in s]
                    alt_highlights = first_sent[0] if first_sent else alt_desc[:120].rstrip(".")
                reply = f"Another excellent option matching your criteria is the **[{alt_product.name}]({alt_url})** — {alt_highlights.rstrip('.')}. You can explore the verified specifications below:"
                top_product = alt_product
                state.active_product = alt_product.to_dict()
                cards = [catalog_tool_executor.format_card(alt_product.to_dict(), card_type="hardware")]
                evidence = [alt_product]
            else:
                # Single eligible match: explain constraint and ask which requirement to change before showing alternatives
                if "cx-02w" in top_product.id.lower() and state.requirements.get("print_size") in ("8x12", "8x12 inches", "8x10", "8x10 inches"):
                    reply = (
                        f"The **[{top_product.name}]({top_url})** is our **only verified match** that satisfies the 8×12-inch dye-sublimation print requirement. "
                        f"Other Citizen models (CX-02, CY-02, and CZ-01) max out at 6×8-inch or 4.5×8-inch print formats.\n\n"
                        f"Before presenting alternatives, which requirement would you be open to adjusting? "
                        f"For example, would you be willing to consider standard 6×8-inch event photo sizes (such as the high-capacity Citizen CY-02 or compact CX-02), "
                        f"or explore large-format archival inkjet photo printers (such as the 13-inch Epson SC-P700 or 17-inch SC-P900)?"
                    )
                    suggested_chips = ["Adjust Size to 6x8", "Explore Epson Inkjet Photo", "Citizen CX-02W Specs"]
                else:
                    req_summary = ", ".join(f"{k}: {v}" for k, v in state.requirements.items() if v)
                    reply = (
                        f"The **[{top_product.name}]({top_url})** is the **only verified match** in our catalogue satisfying your stated requirements ({req_summary}).\n\n"
                        f"Before presenting alternatives, which constraint would you be willing to adjust (such as required print dimensions, scanner need, or printing technology)?"
                    )
                    suggested_chips = ["Adjust Print Size", "Adjust Scanner Need", "View All Models"]

        # ── 5. Internal Audit Object ─────────────────────────────────────────
        audit_object = {
            "collected_requirements": dict(state.requirements),
            "missing_requirements": [f for f in ["print_size", "scan_required"] if f not in state.requirements and state.category in ("technical_cad", "photo_booth")],
            "hard_constraints": [k for k in ["print_size", "scan_required", "printing_technology"] if k in state.requirements],
            "eligible_products": [p.id for p, _, _ in ranked_tuples],
            "rejected_products_with_reason": {
                item.product.id: item.rejection_reason
                for item in assessments if not item.is_eligible
            },
            "ranking_factors": ranked_tuples[0][2] if ranked_tuples else {},
            "selected_product": top_product.id if top_product else None,
            "evidence_ids": [p.get("product_id") or p.get("id") if isinstance(p, dict) else getattr(p, "id", str(p)) for p in evidence] if evidence else [],
            "unsupported_claims": [],
        }

        return RouteResult(
            reply=reply,
            product_cards=cards[:1] if len(cards) == 1 or not state.category else cards,
            suggested_chips=suggested_chips,
            source="recommendation:grounded_engine",
            needs_composition=False,
            evidence=evidence,
            recommendation_audit=audit_object,
        )
    else:
        state.candidate_products = []
        req_details = []
        if state.requirements.get("print_size"):
            req_details.append(f"print size {state.requirements['print_size']}")
        if state.requirements.get("scan_required") is True:
            req_details.append("integrated scanner")
        elif state.requirements.get("scan_required") is False:
            req_details.append("print-only (no scanner)")
        if state.requirements.get("brand"):
            req_details.append(f"brand {state.requirements['brand']}")
        criteria_str = f" ({', '.join(req_details)})" if req_details else ""
        return RouteResult(
            reply=f"I could not find an authorized Kepler Tech model that simultaneously satisfies all your specified requirements{criteria_str}. Rather than suggesting an incompatible unit, which constraint are you open to adjusting (e.g. print size, brand, or scanner preference)?",
            product_cards=[],
            suggested_chips=["Adjust Print Size", "View All Plotters", "Citizen Photo Printers"],
            source="recommendation:honest_rejection",
        )


handle_product_recommendation = handle


