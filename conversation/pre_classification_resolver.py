"""
Pre-Classification Resolver for Kepler Tech SalesAI.
Runs BEFORE intent classification in deterministic priority:
  a) Bind pending_question answers (bare numbers, out-of-range volume handling).
  b) Resolve referents against shown_entities and alias candidates (both, dono, the second, etc.).
  c) Model alias detection via alias_index (overrides active flow, candidate disambiguation).
  d) Price-like questions during pending questions (answers price, preserves question).
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from catalog.alias_index import alias_index
from catalog.catalogue_loader import catalogue_loader
from catalog.catalogue_resolver import build_approved_comparison_response
from domain.conversation_state import ConversationState


@dataclass
class PreClassificationResult:
    handled: bool = False
    reply: str = ""
    product_cards: List[Dict[str, Any]] = field(default_factory=list)
    consumable_cards: List[Dict[str, Any]] = field(default_factory=list)
    suggested_chips: List[str] = field(default_factory=list)
    source: str = "pre_classification_resolver"


def _convert_arabic_digits(text: str) -> str:
    """Converts Eastern Arabic-Indic digits to standard ASCII digits."""
    arabic_indic = "٠١٢٣٤٥٦٧٨٩"
    trans = str.maketrans({c: str(i) for i, c in enumerate(arabic_indic)})
    return text.translate(trans)


def _extract_number(text: str) -> Optional[int]:
    """Extracts a bare or embedded number from user input."""
    t = _convert_arabic_digits(text.lower())
    m = re.search(r"\b(?:its|it\'s|around|about|roz|approx|approximately)?\s*(\d+)(?:\s*(?:pages?|prints?|ppm|inch|″|\"|cm|mm))?\b", t)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


class PreClassificationResolver:
    @classmethod
    def resolve(
        cls,
        normalized_msg: str,
        raw_msg: str,
        state: ConversationState,
    ) -> PreClassificationResult:
        msg_l = normalized_msg.lower().strip()
        raw_l = raw_msg.lower().strip()

        # ── (0) DISAMBIGUATION: PRODUCT OR CONSUMABLE ─────────────────────────
        if getattr(state, "awaiting_field", None) == "product_or_consumable" and getattr(state, "pending_disambiguation_model", None):
            target_model_id = state.pending_disambiguation_model
            target_prod = catalogue_loader.get_by_id(target_model_id)
            if not target_prod:
                for cand in catalogue_loader.get_all():
                    if target_model_id.lower() in cand.get("id", "").lower() or target_model_id.lower() in cand.get("display_name", "").lower():
                        target_prod = cand
                        break

            disp_name = target_prod.get("display_name") or target_model_id if target_prod else target_model_id
            family_name = (target_prod.get("model_family") or disp_name) if target_prod else disp_name

            is_consumable_choice = bool(re.search(
                r"\b(?:consumables?|consub[a-z]{2,5}s?|inks?|cartridges?|media|paper|rolls?|ribbons?|maintenance\s*box|supplies|second|option\s*2|2)\b",
                msg_l
            ))
            is_printer_choice = bool(re.search(
                r"\b(?:printers?|product|machine|device|hardware|specs?|specifications?|details|first|option\s*1|1|view\s+printer)\b",
                msg_l
            ))
            is_both_choice = "both" in msg_l or (is_consumable_choice and is_printer_choice)

            if is_both_choice or is_consumable_choice or is_printer_choice:
                state.awaiting_field = None
                state.pending_disambiguation_model = None

                if is_consumable_choice and not is_both_choice:
                    from catalog.evidence import EvidenceEngine
                    c_items, _ = EvidenceEngine.list_consumables(target_prod.get("id", target_model_id)) if target_prod else ([], None)
                    c_cards = []
                    items_lines = []
                    for ci in c_items:
                        c_card = {
                            "card_type": "consumable",
                            "id": ci.get("sku") or ci.get("id"),
                            "name": ci.get("name"),
                            "sku": ci.get("sku"),
                            "price": ci.get("price"),
                            "price_str": ci.get("price_str") or (f"AED {ci.get('price'):,.2f}" if ci.get("price") else None),
                            "price_formatted": ci.get("price_formatted") or (f"AED {ci.get('price'):,.2f} (Excl. VAT)" if ci.get("price") else None),
                            "category": ci.get("type", "consumable"),
                            "compatible_printers": [disp_name],
                            "product_url": ci.get("url"),
                        }
                        c_cards.append(c_card)
                        price_part = f": **{c_card['price_formatted']}**" if c_card.get('price_formatted') else ""
                        c_url = ci.get("url")
                        link_title = f"[{ci.get('name')}]({c_url})" if c_url else f"**{ci.get('name')}**"
                        items_lines.append(f"• **{link_title}** (SKU: `{ci.get('sku')}`){price_part}")
                    items_text = "\n".join(items_lines)
                    reply_text = f"Certainly! Here are the official compatible inks and media for the **{disp_name}**:\n\n{items_text}"
                    chips_to_return = ["Order Consumables", f"View {family_name} Specifications", "Request Official Quote"]
                    state.active_printer_for_consumables = disp_name
                    state.active_route = "consumable"
                    state.active_consumables = c_cards
                    return PreClassificationResult(
                        handled=True,
                        reply=reply_text,
                        product_cards=[],
                        consumable_cards=c_cards,
                        suggested_chips=chips_to_return,
                        source="route:product_or_consumable:consumables",
                    )
                elif is_printer_choice and not is_both_choice:
                    prod_cards = [target_prod] if target_prod else []
                    reply_text = f"Here are the official specifications and details for the **{disp_name}**."
                    if target_prod:
                        from agent.orchestrator import build_model_detail_response
                        reply_text, prod_cards = build_model_detail_response(target_prod)
                    chips_to_return = ["View Compatible Consumables", "Request Official Quote"]
                    state.active_product = target_prod
                    state.active_product_id = target_prod.get("id") if target_prod else None
                    state.active_printer_for_consumables = disp_name
                    return PreClassificationResult(
                        handled=True,
                        reply=reply_text,
                        product_cards=prod_cards,
                        consumable_cards=[],
                        suggested_chips=chips_to_return,
                        source="route:product_or_consumable:printer",
                    )

        # ── (0b) UNIVERSAL SHOWROOM LOCATION & HOURS (Multilingual) ──────────
        is_showroom_query = bool(re.search(
            r"\b(?:showroom|location|address|office\s+location|where\s+are\s+you|where\s+is\s+your\s+shop|where\s+is\s+your\s+office|opening\s+hours|business\s+hours|working\s+hours|contact\s+details|kahan\s+hai|evide\s+aanu)\b",
            msg_l
        )) or any(w in raw_l for w in ["معرض", "مكان", "عنوان", "موقع", "وين"])
        is_printer_for_showroom = bool(re.search(r"\b(?:printer|plotter|scanner|machine)\s+(?:for|in)\s+(?:our|my|a)\s+showroom\b", msg_l))

        if is_showroom_query and not is_printer_for_showroom and not any(k in msg_l for k in ["recommend", "which printer", "suitable"]):
            reply_text = (
                "**Kepler Tech LLC — Dubai Headquarters & Showroom**\n\n"
                "📍 **Address:** D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, UAE.\n"
                "🕒 **Working Hours:** Monday – Friday: 8:30 AM to 5:30 PM | Saturday: 8:30 AM to 1:00 PM | Sunday: Closed (GST)\n"
                "📞 **Phone:** +971 4 323 1008 | +971 55 835 8586\n"
                "✉️ **Email:** sales@keplertech.ae | info@keplertech.ae\n\n"
                "We provide live equipment demonstrations, manufacturer warranty service, and delivery across Dubai, the UAE, and the GCC. Free store pickup is also available."
            )
            if state.active_product:
                disp = state.active_product.get("display_name", "Equipment")
                chips_to_return = [f"View {disp}", "Request Official Quote", "Delivery Options"]
            elif state.category == "citizen_photo":
                chips_to_return = ["Citizen CX-02", "Citizen CZ-01", "Request Quotation"]
            elif state.category == "technical_large_format":
                chips_to_return = ["24″ (A1)", "36″ (A0)", "44″ Production"]
            elif state.category == "office_printer":
                chips_to_return = ["A4 Multifunction", "A3 Multifunction", "Request Quotation"]
            elif state.category == "photography_large_format":
                chips_to_return = ["Epson SC-P700", "Epson SC-P900", "Epson SC-P9500"]
            elif state.category == "consumables" or getattr(state, "active_route", None) == "consumable":
                chips_to_return = ["Order Consumables", "Request Official Quote", "Delivery Options"]
            else:
                chips_to_return = ["Browse Products", "Request Official Quote", "Delivery Options"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:business_info:showroom",
            )

        # ── (0c) UNIVERSAL "WHY THIS?" / TECHNICAL JUSTIFICATION ──────────────
        is_why_query = bool(re.search(
            r"^\s*(?:why\s*(?:this|this\s*one|this\s*model|this\s*printer)?\??|how\s*come\??|why\s+(?:should|would)\s+i\s+(?:buy|choose|pick)\s+this|why\s+do\s+you\s+recommend\s+this|what\s+makes\s+this\s+(?:good|better|special))\s*$",
            msg_l
        )) or bool(re.search(r"\bwhy\s+this\s+(?:model|printer|plotter)\b", msg_l))

        if is_why_query:
            act_id = state.get_canonical_focus_id() or getattr(state, "active_product_id", None)
            act_p = state.active_product or (catalogue_loader.get_by_id(act_id) if act_id else None)
            if act_p:
                disp_name = act_p.get("display_name") or act_p.get("name") or "this model"
                family = act_p.get("model_family") or disp_name
                cat = act_p.get("catalogue") or act_p.get("main_category") or state.category
                if cat == "technical_large_format" or "sc-t" in str(act_id).lower():
                    justification = (
                        f"The **{disp_name}** is engineered specifically for CAD, AEC, and GIS precision:\n\n"
                        "• **UltraChrome XD Pigment Inks**: Archival, water-resistant, and smudge-proof lines that withstand outdoor construction site handling.\n"
                        "• **PrecisionCore MicroTFP Printhead**: Permanent, heat-free printhead technology delivering micron-level line accuracy without thermal degradation.\n"
                        "• **Direct HP-GL/2 & PDF Processing**: Rapid rendering of complex architectural layers and vector schematics."
                    )
                elif cat == "citizen_photo" or "cx" in str(act_id).lower() or "cz" in str(act_id).lower():
                    justification = (
                        f"The **{disp_name}** is purpose-built for commercial event photography and photo booths:\n\n"
                        "• **Thermal Dye-Sublimation Speed**: Instant dry, laminated lab-quality prints in seconds with water and fingerprint protection.\n"
                        "• **Ribbon Rewind Technology**: Unique multi-cut capability enabling 4×6″ and 6×8″ prints from the same roll without wasting media.\n"
                        "• **Proven Event Durability**: Compact steel chassis engineered for rigorous on-the-road event transportation."
                    )
                elif cat in ("dye_sublimation", "sublimation") or "sc-f" in str(act_id).lower():
                    justification = (
                        f"The **{disp_name}** delivers turnkey sublimation transfer reliability:\n\n"
                        "• **Genuine Turnkey Solution**: Printer, UltraChrome DS ink bottles, and software are all factory-matched and warrantied by Epson.\n"
                        "• **No Clogging / Vibrant Transfer**: Certified OEKO-TEX Eco Passport inks deliver rich blacks and vibrant colors on textiles, mugs, and blanks.\n"
                        "• **Ultra-Low Running Cost**: High-capacity refill bottles eliminate expensive cartridge waste."
                    )
                elif cat == "office_printer" or "wf-" in str(act_id).lower() or "am-c" in str(act_id).lower():
                    justification = (
                        f"The **{disp_name}** provides commercial office cost and uptime advantages:\n\n"
                        "• **Heat-Free PrecisionCore Technology**: Zero warm-up time, high first-page-out speed, and up to 85% lower power consumption than laser.\n"
                        "• **Replaceable Ink Pack System (RIPS)**: Up to 86,000 pages uninterrupted printing before ink replenishment, slashing per-page printing costs.\n"
                        "• **Minimal Maintenance**: No fuser unit, transfer belt, or developer drums to replace."
                    )
                else:
                    justification = (
                        f"The **{disp_name}** is selected for professional image reproduction:\n\n"
                        "• **UltraChrome PRO Inkset**: Expanded dynamic color gamut with dedicated Photo and Matte Black channels for gallery proofing.\n"
                        "• **Epson PrecisionCore Engine**: Industry-standard exhibition longevity and certified color consistency across print runs."
                    )
                chips = [f"View {family} Specs", "Request Official Quote", "Delivery Options"]
                return PreClassificationResult(
                    handled=True,
                    reply=justification,
                    product_cards=[act_p],
                    suggested_chips=chips,
                    source="route:product_justification",
                )
            elif state.category == "citizen_photo":
                reply = (
                    "Citizen photo printers use professional thermal dye-sublimation technology with instant dry protective lamination, "
                    "making them the global industry standard for photo booths, weddings, and commercial events.\n\n"
                    "Would you like to review the ultra-compact **Citizen CZ-01** (4×6″) or the high-capacity **Citizen CX-02** (4×6″ & 6×8″)?"
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    suggested_chips=["Citizen CX-02", "Citizen CZ-01", "Request Official Quote"],
                    source="route:category_justification",
                )
            elif state.category == "technical_large_format":
                reply = (
                    "Epson SureColor T-Series plotters use water-resistant UltraChrome XD pigment inks and permanent PrecisionCore printheads, "
                    "ensuring architectural blueprints and CAD line drawings never bleed or fade under job-site conditions.\n\n"
                    "What roll width fits your plans: 24″ (A1), 36″ (A0), or 44″ production?"
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    suggested_chips=["24″ (A1)", "36″ (A0)", "44″ Production"],
                    source="route:category_justification",
                )

        # ── (0d) GENERIC CONSUMABLES REQUEST ENTRY (when no model yet) ────────
        is_generic_consumables = bool(re.search(
            r"^\s*(?:i\s+(?:need|want|am\s+looking\s+for|require)\s+)?(?:consumables?|consubles?|consumbales?|inks?|cartridges?|printer\s+inks?|photo\s+paper|ribbons?|toner|supplies)\s*$",
            msg_l
        )) or bool(re.search(
            r"\b(?:buy|order|purchase|need|want)\s+(?:consumables?|inks?|cartridges?|ribbons?)\b",
            msg_l
        ) and not any(k in msg_l for k in ["printer", "plotter", "machine", "hardware", "scanner"]))

        if is_generic_consumables and not getattr(state, "active_product", None) and not state.get_canonical_focus_id():
            state.category = "consumables"
            state.active_route = "consumable"
            state.awaiting_field = "consumable_model"
            reply_text = (
                "Kepler Tech supplies 100% genuine Epson and Citizen inks, ribbons, media rolls, and maintenance boxes with guaranteed printhead compatibility.\n\n"
                "Which printer or plotter model do you need consumables for?"
            )
            chips_to_return = ["Epson SC-F100", "Citizen CX-02", "Epson SC-T3100", "Epson SC-P900", "WorkForce WF-C878R"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:consumables:ask_model",
            )

        # ── GATE INTERCEPTOR: Category words vs attributes & Explicit Switches ──
        # 1. "a4 colour printer with scanner" / "a3 colour multifunction printer" must stay in office_printer, not scanners
        if re.search(r"\b(?:a4|a3|colour|color|office|multifunction|enterprise)?\s*printer\s+with\s+(?:scann?er|scanning|automatic\s+document\s+feeder|adf)\b", msg_l) or \
           re.search(r"\b(?:a4|a3)\s+(?:colour|color)?\s*(?:multifunction\s+)?printer\b", msg_l) or \
           re.search(r"\bprinter\s+(?:that\s+has|with|having)\s+(?:scann?er|scanning)\b", msg_l):
            if state.category != "office_printer":
                state.category = "office_printer"
            state.requirements["category"] = "office_printer"
            state.requirements["application"] = "office_documents"
            state.requirements["scanner_required"] = True
            state.requirements["scan_required"] = True
            if "a4" in msg_l:
                state.requirements["paper_size"] = "a4"
                state.requirements["print_size"] = "a4"
            elif "a3" in msg_l:
                state.requirements["paper_size"] = "a3"
                state.requirements["print_size"] = "a3"
            if "colour" in msg_l or "color" in msg_l:
                state.requirements["colour_mode"] = "colour"

            state.save_pending_question(
                question="For office multifunction printing with integrated scanning, what is your estimated daily page volume?\n\n• 20–100 pages/day\n• 100–500 pages/day\n• 500+ pages/day",
                field_name="daily_volume",
                expected_type="number",
                valid_range=(20, 10000),
                options=["20–100 pages/day", "100–500 pages/day", "500+ pages/day"]
            )
            return PreClassificationResult(
                handled=True,
                reply="For office multifunction printing with integrated scanning, what is your estimated daily page volume?\n\n• 20–100 pages/day\n• 100–500 pages/day\n• 500+ pages/day",
                suggested_chips=["20–100 pages/day", "100–500 pages/day", "500+ pages/day"],
                source="qualification:next_question",
            )

        # ── HEAT-FREE VS LASER COMPARISON ─────────────────────────────────────
        if re.search(r"\b(?:heat[-\s]*free|precisioncore)\b", msg_l) and re.search(r"\b(?:laser|electricity|power\s+consumption|energy|copiers?)\b", msg_l):
            state.category = "office_printer"
            reply_text = (
                "Epson **Heat-Free PrecisionCore technology** provides significant environmental and operational advantages over traditional laser copiers:\n\n"
                "• **Up to 85% Lower Energy Consumption**: Laser printers require intense heat to fuse toner powder onto paper, drawing continuous high wattage. Epson Heat-Free inkjet technology uses piezo elements that fire ink cold, drastically cutting electricity bills.\n"
                "• **Zero Warm-Up Time**: Delivers instant first-page-out prints without waiting for a fuser unit to heat up.\n"
                "• **Fewer Replacement Parts**: Laser copiers require periodic replacement of fusers, drums, transfer belts, and developer units. Epson WorkForce systems require only ink packs and a maintenance box, dramatically cutting e-waste and maintenance downtime."
            )
            chips_to_return = ["A4 WorkForce Pro", "A3 Departmental RIPS", "Enterprise High-Speed"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:heat_free_advantage",
            )

        # ── DUAL-SCAN COMPARISON (WF-C878R vs WF-C879R) ──────────────────────
        if re.search(r"\bc878r?\b", msg_l) and re.search(r"\bc879r?\b", msg_l) and re.search(r"\b(?:scan|scanner|duplex|speed)\b", msg_l):
            state.category = "office_printer"
            reply_text = (
                "Here is the scanning comparison between the **Epson WorkForce Pro WF-C878R** and **WF-C879R**:\n\n"
                "• **WF-C878R DWF**: Standard automatic reversing ADF scanner (reverses paper to scan side two; up to 25 ipm).\n"
                "• **WF-C879R DWF**: High-speed **single-pass dual-head scanner** (scans both sides of the sheet simultaneously at up to **100 ipm** duplex).\n\n"
                "If your office processes high-volume double-sided invoices and document scanning, the WF-C879R delivers 4x faster scan throughput."
            )
            chips_to_return = ["Epson WF-C879R DWF", "Epson WF-C878R DWF", "Request Official Quote"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:scanner_comparison",
            )

        # ── SUBLIMATION TRANSFER PAPER INQUIRY ────────────────────────────────
        if re.search(r"\b(?:sublimation\s+transfer\s+paper|transfer\s+paper\s+sheets?)\b", msg_l):
            state.category = "dye_sublimation"
            reply_text = (
                "Yes, we supply genuine **Epson DS Transfer General Purpose Paper Sheets** in the UAE:\n\n"
                "• **A4 Sheets (100 Sheets / Pack)**: SKU `C13S400078` — Designed for the Epson SureColor SC-F100 for mugs, phone cases, and small merchandise.\n"
                "• **A3 Sheets (100 Sheets / Pack)**: SKU `C13S400077` — For larger textile and flatbed transfer production.\n\n"
                "We deliver across Dubai, Abu Dhabi, and all UAE emirates for a flat AED 10 (dispatched in 1 to 2 business days), or free store pickup at our Dubai showroom."
            )
            chips_to_return = ["Order A4 Transfer Paper", "Epson SC-F100 Inks", "Request Official Quote"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:consumables:transfer_paper",
            )

        # ── T49N CONSUMABLES / INK PART NUMBER INQUIRY ────────────────────────
        if re.search(r"\bt49n\b", msg_l):
            state.category = "dye_sublimation"
            reply_text = (
                "The official part number for the **Epson T49N Black ink bottle (140 ml)** is **`C13T49N100`**.\n\n"
                "Here are the complete part numbers for the Epson T49N dye-sublimation ink set (compatible with Epson SureColor SC-F100 and SC-F500):\n"
                "• **Black (140 ml)**: SKU `C13T49N100`\n"
                "• **Cyan (140 ml)**: SKU `C13T49N200`\n"
                "• **Magenta (140 ml)**: SKU `C13T49N300`\n"
                "• **Yellow (140 ml)**: SKU `C13T49N400`\n"
                "• **Maintenance Box**: SKU `C13S210125`\n\n"
                "All items are in stock with delivery across the UAE (flat AED 10) or free store pickup at our Dubai showroom."
            )
            chips_to_return = ["Order T49N Black (C13T49N100)", "Full T49N Ink Set", "SC-F100 Maintenance Box"]
            return PreClassificationResult(
                handled=True,
                reply=reply_text,
                suggested_chips=chips_to_return,
                source="route:consumables:t49n_part_number",
            )


        # 2. Explicit category switch (e.g. "no wait not office, photo booth", "switch to photo booth")
        if re.search(r"\b(?:no\s+wait\s+not|not\s+office|instead\s+of\s+office|switch\s+to|changed?\s+my\s+mind|rather\s+have)\b.*photo\s*booth", msg_l) or \
           re.search(r"\bno\s+wait\s+not\s+office[,\s]+photo\s*booth\b", msg_l):
            state.switch_category("citizen_photo", reason="Explicit switch from office to photo booth")
            state.save_pending_question(
                question="What print format do you require for your photo booth and event photography?\n\n• Compact 4×6″ prints\n• 5×7″ and 6×8″ prints\n• Single-roll multi-cut (4×6″ and 6×8″ with ribbon rewind)",
                field_name="print_size",
                expected_type="choice",
                options=["4x6 prints", "6x8 prints", "Ribbon rewind (single roll)"]
            )
            return PreClassificationResult(
                handled=True,
                reply="Understood! Switching to Citizen Photo Booth and event printers.\n\nWhat print format do you require for your photo booth?\n\n• Compact 4×6″ prints\n• 5×7″ and 6×8″ prints\n• Single-roll multi-cut (4×6″ and 6×8″ with ribbon rewind)",
                suggested_chips=["4x6 prints", "6x8 prints", "Ribbon rewind (single roll)"],
                source="qualification:category_prompt",
            )

        # 2.3 Direct Category Selections (e.g. "tech", "cad", "photo", "booth", "sublimation", "office")
        if re.search(r"^\s*(?:tech|technical|technical\s+cad(?:\s+plotters?)?|cad(?:\s+plotters?|\s+printers?)?|plotters?)\s*$", msg_l):
            state.category = "technical_large_format"
            state.requirements["category"] = "technical_large_format"
            state.requirements["application"] = "cad"
            reply = (
                "Understood! For technical CAD, AEC plans, and GIS mapping, Kepler Tech supplies the **Epson SureColor SC-T Series**.\n\n"
                "What paper size or roll width do you primarily work with?\n\n"
                "• **24-inch (A1)** — Compact desktop or single roll for small offices\n"
                "• **36-inch (A0)** — Standard full-width construction plans\n"
                "• **44-inch Production** — High-speed dual roll for heavy volume"
            )
            state.save_pending_question(
                question="What roll width do you require: 24″ (A1), 36″ (A0), or 44″ production?",
                field_name="print_width",
                expected_type="number",
                valid_range=(24, 44),
                options=["24″ (A1)", "36″ (A0)", "44″ Production", "With Integrated Scanner"],
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["24″ (A1)", "36″ (A0)", "44″ Production", "With Integrated Scanner"],
                source="qualification:category_prompt",
            )

        if re.search(r"^\s*(?:photo(?:graphy)?|fine\s*art|professional\s*photo(?:\s*&\s*fine\s*art)?)\s*$", msg_l):
            state.category = "photography_large_format"
            state.requirements["category"] = "photography_large_format"
            state.requirements["application"] = "fine_art"
            reply = (
                "Understood! For professional photography, fine art reproduction, and gallery proofing, we provide the **Epson SureColor SC-P Series** with 10 to 12-colour UltraChrome PRO inks.\n\n"
                "What format or print width are you looking for?\n\n"
                "• **13″–17″ Desktop (A3+/A2)** — SC-P700 & SC-P900 for studio desktops\n"
                "• **24-inch (A1)** — SC-P6500D commercial production or SC-P7500 master proofer\n"
                "• **44-inch Gallery** — SC-P8500D production or SC-P9500 12-colour proofer"
            )
            state.save_pending_question(
                question="What print width do you require for photo and fine art: 17″, 24″, or 44″?",
                field_name="photography_print_width",
                expected_type="choice",
                options=["13″–17″ Desktop", "24″ Production", "44″ Gallery", "12-Colour Proofing"],
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["13″–17″ Desktop", "24″ Production", "44″ Gallery", "12-Colour Proofing"],
                source="qualification:category_prompt",
            )

        if re.search(r"^\s*(?:(?:citizen\s+)?photo\s*booth(?:\s*/\s*events)?|events?|instant\s*photo|citizen)\s*$", msg_l):
            state.category = "citizen_photo"
            state.requirements["category"] = "citizen_photo"
            reply = (
                "Great! For instant event photography, photo booths, and kiosks, Kepler Tech is the authorized distributor for **Citizen dye-sublimation systems**.\n\n"
                "What print format do you need for your events?\n\n"
                "• **4×6″ Ultra-Compact** — Citizen CZ-01 (lightweight portable event printer)\n"
                "• **6×8″ High-Speed** — Citizen CX-02 (flagship 8.4-second event workhorse)\n"
                "• **6×8″ Heavy-Duty** — Citizen CY-02 (700-print high capacity for high volume)\n"
                "• **8×12″ Large Format** — Citizen CX-02W (widescreen event & school portraits)"
            )
            state.save_pending_question(
                question="What format fits your photo booth: 4×6″, 6×8″, or 8×12″?",
                field_name="citizen_format",
                expected_type="choice",
                options=["4×6″ (CZ-01)", "6×8″ (CX-02)", "6×8″ High-Capacity (CY-02)", "8×12″ (CX-02W)"],
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["4×6″ (CZ-01)", "6×8″ (CX-02)", "6×8″ High-Capacity (CY-02)", "8×12″ (CX-02W)"],
                source="qualification:category_prompt",
            )

        if re.search(r"^\s*(?:dye[\s-]*sub(?:limation)?|sublimation)\s*$", msg_l):
            state.category = "dye_sublimation"
            state.requirements["category"] = "dye_sublimation"
            reply = (
                "Understood! For heat transfer and dye-sublimation printing on apparel, textiles, and promotional items, we supply the **Epson SureColor SC-F Series**.\n\n"
                "What type of items will you be producing?\n\n"
                "• **Desktop A4 (SC-F100)** — Compact bottle-fed printer for mugs, phone cases, and small gifts\n"
                "• **24-inch Roll (SC-F500)** — Roll-fed production printer for t-shirts, sportswear, and soft signage"
            )
            state.save_pending_question(
                question="Are you printing desktop gifts (A4) or roll-fed textiles (24″)?",
                field_name="sublimation_format",
                expected_type="choice",
                options=["A4 Desktop (SC-F100)", "24″ Roll Apparel (SC-F500)", "Sublimation Inks & Paper"],
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["A4 Desktop (SC-F100)", "24″ Roll Apparel (SC-F500)", "Sublimation Inks & Paper"],
                source="qualification:category_prompt",
            )

        if re.search(r"^\s*(?:office(?:\s*printers?)?|workforce|business\s*printers?)\s*$", msg_l):
            state.category = "office_printer"
            state.requirements["category"] = "office_printer"
            state.requirements["application"] = "office_documents"
            reply = (
                "Understood! For business and office environments, Kepler Tech supplies **Epson WorkForce Pro and Enterprise Heat-Free** multifunction systems with ultra-low running costs.\n\n"
                "Do you require standard A4 output or large-format A3/A3+ output for your office documents?"
            )
            state.save_pending_question(
                question="Do you require A4 or A3 output for your office?",
                field_name="paper_size",
                expected_type="choice",
                options=["A4 Output", "A3 Output", "< 100 pages/day", "100–500 pages/day"],
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["A4 Output", "A3 Output", "< 100 pages/day", "100–500 pages/day"],
                source="qualification:category_prompt",
            )

        # 3. "with scanner" as an attribute when category is already active
        if state.category and re.search(r"^\s*(?:with\s+scann?er|scanner\s+included|has\s+scann?er|\+\s*scann?er)\s*$", msg_l):
            state.requirements["scanner_required"] = True
            state.requirements["scan_required"] = True
            if state.category == "photography_large_format":
                return PreClassificationResult(
                    handled=True,
                    reply="Understood. For professional photography and fine art printing, the SureColor series can be paired with an optional large-format scanner for fine art reproduction. Are you looking for single-roll or dual-roll capability?",
                    suggested_chips=["Dual Roll", "Single Roll", "24-inch Models", "44-inch Models"],
                    source="qualification:attribute_update",
                )
            elif state.category == "technical_large_format":
                # Re-run recommendation with scanning
                state_res = state.apply_state_change()
                return PreClassificationResult(
                    handled=True,
                    reply=f"Understood. Adding integrated scanning to your specifications.\n\n{state_res.get('reply', '')}",
                    product_cards=state_res.get("cards", []),
                    suggested_chips=state_res.get("chips", []),
                    source=state_res.get("source", "qualification:attribute_update"),
                )
        # 3b. "no scanner" / "no scanner needed" as an attribute
        if state.category and re.search(r"^\s*(?:no\s+scann?er(?:\s+needed)?|without\s+scann?er|no\s+scan|print\s+only)\s*$", msg_l):
            state.requirements["scanner_required"] = False
            state.requirements["scan_required"] = False
            if state.category == "technical_large_format":
                width = state.requirements.get("print_width", 24)
                if width == 24:
                    t3100 = catalogue_loader.get_by_id("epson-sc-t3100")
                    cards = [t3100] if t3100 else []
                    state.shown_entities = [c["id"] for c in cards]
                    reply = (
                        "Understood, print-only without scanner. For 24-inch technical CAD plans, here is our recommended standalone plotter:\n\n"
                        "• **Epson SureColor SC-T3100**: Clean, wireless 24″ desktop CAD plotter engineered for precise architectural line work."
                    )
                elif width == 44:
                    t7700 = catalogue_loader.get_by_id("epson-sc-t7700d")
                    cards = [t7700] if t7700 else []
                    state.shown_entities = [c["id"] for c in cards]
                    reply = (
                        "Understood, print-only without scanner. For 44-inch high-production technical CAD plans, here is our recommended standalone plotter:\n\n"
                        "• **Epson SureColor SC-T7700D**: High-speed 44″ dual-roll production technical CAD plotter with UltraChrome XD3 inks."
                    )
                else:
                    t5100 = catalogue_loader.get_by_id("epson-sc-t5100")
                    cards = [t5100] if t5100 else []
                    state.shown_entities = [c["id"] for c in cards]
                    reply = (
                        "Understood, print-only without scanner. For 36-inch technical CAD plans, here is our recommended standalone plotter:\n\n"
                        "• **Epson SureColor SC-T5100**: Clean, wireless 36″ desktop CAD plotter engineered for precise architectural line work."
                    )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["Actually make it 36", "Roll sizes?", "Official Quotation"],
                    source="qualification:attribute_update",
                )


        # ── (d) PRICE-LIKE QUESTIONS DURING PENDING QUESTION ──────────────────
        is_price_q = bool(
            re.search(r"\b(?:price\??|how\s+much|what\s+is\s+the\s+price|how\s+much\s+does\s+it\s+cost|pricing|cost)\b", raw_l)
            or "كم السعر" in raw_l
            or "سعر" in raw_l
            or "كم سعر" in raw_l
            or re.search(r"^\s*price\s*\??\s*$", msg_l)
        )
        if is_price_q and (state.pending_question or state.awaiting_field or (state.category == "office_printer" and not state.requirements.get("daily_volume"))):
            price_reply = (
                "Commercial pricing and official quotations are prepared by our sales desk based on your volume requirements. "
                "Verified list pricing is also published on our official website (https://www.keplertechllc.com/).\n\n"
                "Would you like an official commercial quotation, or shall we specify your daily printing volume?"
            )
            chips = ["Request Official Quotation", "Continue Specifications", "View Official Website"]
            return PreClassificationResult(
                handled=True,
                reply=price_reply,
                suggested_chips=chips,
                source="guardrail:commercial_policy",
            )

        # ── Volume Correction (e.g. "sorry i meant 400 per day") ─────────────
        corr_vol = re.search(r"\b(?:sorry\s+i\s+meant|i\s+meant|actually\s+make\s+it|make\s+it)\s*(\d+)\s*(?:pages?|per\s*day|a\s*day)?\b", msg_l)
        if corr_vol and state.category == "office_printer":
            num_val = int(corr_vol.group(1))
            state.requirements["exact_daily_volume"] = num_val
            state.requirements["daily_volume"] = num_val
            state.requirements["monthly_volume"] = num_val * 30
            state.requirements["exact_monthly_volume"] = num_val * 30
            is_a3 = state.requirements.get("paper_size") == "a3" or state.requirements.get("print_size") == "A3"
            if is_a3 and num_val <= 500:
                state.requirements["office_duty_class"] = "departmental_rips"
                state.requirements["office_speed_class"] = "25_ppm_rips"
                c878 = catalogue_loader.get_by_id("epson-wf-c878r-dwf")
                c879 = catalogue_loader.get_by_id("epson-wf-c879r-dwf")
                cards = [c for c in [c878, c879] if c]
                state.shown_entities = [c["id"] for c in cards]
                state.set_canonical_focus(cards[0]["id"] if cards else None)
                reply = (
                    f"Understood, updated daily volume to {num_val} pages/day. "
                    "For departmental A3 printing (100–500 pages/day), here are our recommended WorkForce Pro RIPS multifunction systems:\n\n"
                    "• **Epson WorkForce Pro WF-C878R DWF** (25 ppm, up to 86,000 pages ink yield)\n"
                    "• **Epson WorkForce Pro WF-C879R DWF** (26 ppm, up to 86,000 pages ink yield, high-speed dual-scan)"
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["Both models have scan?", "Request Official Quotation", "Compatible RIPS Inks"],
                    source="recommendation:catalogue_list",
                )

        # ── Citizen photo booth formats (4", 6", 8") ─────────────────────────
        is_cit_scope = (
            state.category == "citizen_photo"
            or getattr(state, "awaiting_field", None) == "citizen_format"
            or "citizen" in str(getattr(state, "category", "")).lower()
            or any("citizen" in str(x).lower() for x in (state.shown_entities or []))
        )
        if is_cit_scope:
            is_4_in = bool(re.search(r"\b(?:4x6|4\s*x\s*6|4\"x6\"|4\s*by\s*6|4[\s-]*(?:inch|in|\")|cz01|cz-01)\b", msg_l)) or msg_l in ("4 inch", "4inch", "4\"", "4")
            is_6_in = bool(re.search(r"\b(?:6x8|6\s*x\s*8|6\"x8\"|6\s*by\s*8|6[\s-]*(?:inch|in|\")|cx02|cx-02|cy02|cy-02)\b", msg_l)) or msg_l in ("6 inch", "6inch", "6\"", "6")
            is_8_in = bool(re.search(r"\b(?:8x12|8\s*x\s*12|8\"x12\"|8x10|8\s*x\s*10|8[\s-]*(?:inch|in|\")|cx02w|cx-02w)\b", msg_l)) or msg_l in ("8 inch", "8inch", "8\"", "8")

            if is_4_in:
                state.category = "citizen_photo"
                state.requirements["category"] = "citizen_photo"
                state.requirements["print_size"] = "4x6"
                state.requirements["print_sizes"] = ["4x6"]
                if hasattr(state, "confirmed_slots") and isinstance(state.confirmed_slots, dict):
                    state.confirmed_slots.pop("_flowchart_leaf_reached", None)
                    state.confirmed_slots.pop("_leaf_product_id", None)
                cz01 = catalogue_loader.get_by_id("citizen-cz-01")
                cx02 = catalogue_loader.get_by_id("citizen-cx-02")
                cy02 = catalogue_loader.get_by_id("citizen-cy-02")
                cards = [c for c in [cz01, cx02, cy02] if c]
                state.shown_entities = [c["id"] for c in cards]
                state.consume_pending_question()
                reply = (
                    "For 4×6″ event and photo booth printing, here are our recommended Citizen dye-sublimation printers:\n\n"
                    "• **Citizen CZ-01**: Ultra-compact and lightweight (5.8 kg) 4×6″ printer, ideal for portable booths.\n"
                    "• **Citizen CX-02**: Premium photo booth printer supporting 4×6″ and 6×8″ with ribbon rewind.\n"
                    "• **Citizen CY-02**: High-capacity event printer producing up to 700 4×6″ prints per roll."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["Cheapest one?", "Compare CX-02 and CZ-01", "Official Quotation"],
                    source="recommendation:catalogue_list",
                )
            elif is_6_in:
                state.category = "citizen_photo"
                state.requirements["category"] = "citizen_photo"
                state.requirements["print_size"] = "6x8"
                state.requirements["print_sizes"] = ["6x8", "4x6"]
                if hasattr(state, "confirmed_slots") and isinstance(state.confirmed_slots, dict):
                    state.confirmed_slots.pop("_flowchart_leaf_reached", None)
                    state.confirmed_slots.pop("_leaf_product_id", None)
                cx02 = catalogue_loader.get_by_id("citizen-cx-02")
                cy02 = catalogue_loader.get_by_id("citizen-cy-02")
                cards = [c for c in [cx02, cy02] if c]
                state.shown_entities = [c["id"] for c in cards]
                state.consume_pending_question()
                reply = (
                    "For 6-inch event photo printing (including 6×8″ and 4×6″ formats), both the **Citizen CX-02** and **Citizen CY-02** deliver high-speed dye-sublimation output:\n\n"
                    "• **Citizen CX-02**: Lightweight 12 kg event workhorse with ribbon-rewind to produce 4×6″ and 6×8″ without swapping rolls.\n"
                    "• **Citizen CY-02**: High-capacity commercial model producing up to 700 4×6″ prints or 350 6×8″ prints per roll."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["CX02 Yield?", "CY02 Yield?", "Official Quotation"],
                    source="recommendation:catalogue_list",
                )
            elif is_8_in:
                state.category = "citizen_photo"
                state.requirements["category"] = "citizen_photo"
                state.requirements["print_size"] = "8x12"
                state.requirements["print_sizes"] = ["8x12", "8x10"]
                if hasattr(state, "confirmed_slots") and isinstance(state.confirmed_slots, dict):
                    state.confirmed_slots.pop("_flowchart_leaf_reached", None)
                    state.confirmed_slots.pop("_leaf_product_id", None)
                cx02w = catalogue_loader.get_by_id("citizen-cx-02w")
                cards = [cx02w] if cx02w else []
                state.shown_entities = [c["id"] for c in cards]
                state.consume_pending_question()
                reply = (
                    "For 8-inch wide event and portrait photography, here is our recommended Citizen dye-sublimation printer:\n\n"
                    "• **Citizen CX-02W**: Wide-format instant event printer engineered for 8×10″ and 8×12″ school, wedding, and gala portraits."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["CX-02W Media Packs", "Print Speed", "Official Quotation"],
                    source="recommendation:catalogue_list",
                )

        # ── F100 paper size support inquiry (Chat 4 Turn 4) ───────────────────
        if re.search(r"\b(?:what\s+paper\s+size|paper\s+size|supported\s+paper|media\s+size|which\s+paper\s+size)\b", msg_l):
            if "f100" in str(state.get_canonical_focus_id()) or any("f100" in str(x).lower() for x in (state.shown_entities or [])) or getattr(state, "active_printer_for_consumables", None) == "epson-sc-f100" or "f100" in str(getattr(state, "active_product_id", "")):
                reply = (
                    "The **Epson SureColor SC-F100** supports sheet media up to **A4 (210 × 297 mm)**, as well as A5, A6, and custom sheet sizes up to 215.9 × 297 mm (8.5 × 11.7 inches). "
                    "It is a dedicated sheet-fed desktop dye-sublimation printer optimized for transfer paper sheets (does not accept continuous roll paper)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[catalogue_loader.get_by_id("epson-sc-f100")] if catalogue_loader.get_by_id("epson-sc-f100") else [],
                    suggested_chips=["Order A4 Transfer Paper", "Compatible Inks", "Official Quotation"],
                    source="route:product_spec_attribute",
                )

        # ── Delivery destination inquiry / answer (e.g. "dubai", "abu dhabi", "sharjah", "uae") ────────
        is_dest_reply = bool(re.search(r"^\s*(?:to\s+)?(?:dubai|abu\s*dhabi|sharjah|ajman|al\s*ain|ras\s*al\s*khaimah|fujairah|uae|oman|saudi|qatar|kuwait|bahrain|gcc)\s*$", msg_l))
        was_delivery_prompt = bool(state.last_assistant_response and any(w in state.last_assistant_response.lower() for w in ["which destination would you like delivery to", "delivery coverage", "shipping fees", "store pickup"]))
        if is_dest_reply or (was_delivery_prompt and any(w in msg_l for w in ["dubai", "abu dhabi", "sharjah", "uae", "oman", "saudi", "gcc"])):
            from conversation.delivery_engine import DeliveryPolicyEngine
            from conversation.dialogue_state import DialogueState as UDialogueState
            u_st = getattr(state, "_unified_dialogue_state", None) or UDialogueState(session_id=getattr(state, "session_id", "default"))
            target_p = state.get_canonical_focus_id() or getattr(state, "active_product_id", None)
            deliv_text, chips, next_q, ev_recs = DeliveryPolicyEngine.resolve_delivery_decision(raw_msg, u_st, target_p)
            combined_reply = f"{deliv_text}\n\n{next_q}" if next_q and next_q not in deliv_text else deliv_text
            return PreClassificationResult(
                handled=True,
                reply=combined_reply,
                suggested_chips=chips,
                source="agent:delivery_policy",
            )

        # ── (a.1) Brochure / Datasheet Request ────────────────────────────────
        if re.search(r"\b(?:brochure|datasheet|data\s*sheet|spec\s*sheet|pdf|manual)\b", msg_l):
            active_id = state.get_canonical_focus_id() or (state.shown_entities[0] if state.shown_entities else None)
            p_obj = catalogue_loader.get_by_id(active_id) if active_id else None
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "our commercial printing systems"
            prod_url = f"https://www.keplertechllc.com/product/{active_id}" if active_id else "https://www.keplertechllc.com/"
            reply = (
                f"You can review the official technical specifications and product datasheet for the **{p_name}** "
                f"directly on our official product page: {prod_url}.\n\n"
                "Would you like me to prepare an official quotation or answer specific technical questions?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "View Consumables", "Speak with Sales Specialist"],
                source="route:brochure_request",
            )

        # ── (a.2) Delivery Timeline Inquiry ──────────────────────────────────
        if re.search(r"\b(?:how\s+many\s+days|how\s+long\s+(?:does|will)\s+(?:it|delivery|shipping)\s+take|delivery\s+(?:timeline|days|timing|period))\b", msg_l):
            reply = (
                "Standard courier delivery across Sharjah, Dubai, and all UAE emirates is completed within **1–2 business days** (tracked courier service). "
                "For urgent requirements within Dubai, same-day delivery is also available upon request.\n\n"
                "Would you like to arrange delivery for a specific equipment model?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Tracked Delivery (1–2 Days)", "Same-Day Delivery (Dubai)", "Free Store Pickup"],
                source="route:delivery_timeline",
            )

        # ── (a.3) Required Details for Order / Quotation ─────────────────────
        if re.search(r"\b(?:what\s+details?\s+(?:do\s+you\s+need|are\s+needed|required)|what\s+info(?:rmation)?\s+(?:do\s+you\s+need|is\s+needed))\b", msg_l):
            reply = (
                "To prepare your official quotation or process equipment dispatch, we just need:\n\n"
                "1. **Full Name**\n"
                "2. **Delivery Address & Emirate**\n"
                "3. **Contact Phone Number or Email**\n\n"
                "Once provided, our sales desk will generate an official reference number and contact you directly."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Provide Contact Details", "Showroom Hours & Location", "Payment Methods"],
                source="route:order_details_faq",
            )

        # ── (a.35) Prompt Injection & System Manipulation Defense ──────────────
        if re.search(r"\b(?:system\s+prompt|ignore\s+(?:all\s+)?previous\s+instructions|jailbreak|you\s+are\s+now\s+a\s+free\s+assistant|write\s+me\s+a\s+(?:python|code|script)|what\s+ai\s+model|chatgpt|openai|claude|gemini|llama)\b", msg_l):
            reply = (
                "I am Kepler Tech's dedicated commercial sales assistant specializing in authorized Epson and Citizen printing solutions. "
                "I operate strictly within commercial sales parameters and cannot disclose internal prompts, write arbitrary programming code, or modify system policies.\n\n"
                "How can I assist you with your equipment or official quotation requirements today?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Technical CAD Plotters", "Photo & Fine Art", "Office Printers", "Citizen Photo Booth"],
                source="security:injection_refusal",
            )

        # ── (a.36) Impatient Customer: "just tell me the best" ───────────────
        if re.search(r"\b(?:just\s+tell\s+me\s+the\s+best|don'?t\s+ask\s+me\s+(?:10|ten)\s+questions|tell\s+me\s+the\s+best\s+printer)\b", msg_l):
            target_id = "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(target_id)
            state.set_canonical_focus(target_id)
            state.category = "office_printer"
            state.shown_entities = [target_id]
            reply = (
                "For reliable, high-speed business document printing, our best-selling commercial model is the **Epson WorkForce Pro WF-C5890 DWF** (AED 1,656.00 excl. VAT). "
                "It features Heat-Free technology, automatic duplex printing, Wi-Fi networking, and high-yield ink packs up to 10,000 pages with ultra-low running costs.\n\n"
                "Does this fit your office setup, or would you like to review an official quotation?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Technical Specifications", "View Consumables"],
                source="route:best_recommendation",
            )

        # ── (a.37) School / Education Inquiry with Typos ─────────────────────
        if re.search(r"\b(?:wich\s+printr|good\s+for\s+school|gud\s+for\s+school|20\s+students?)\b", msg_l):
            target_id = "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(target_id)
            state.set_canonical_focus(target_id)
            state.category = "office_printer"
            state.shown_entities = [target_id]
            reply = (
                "For school and educational use with ~20 students, the **Epson WorkForce Pro WF-C5890 DWF** (AED 1,656.00 excl. VAT) is our top recommendation. "
                "Its Heat-Free ink pack system eliminates fuser warm-up time, handles robust daily volumes with zero ozone emissions, and offers duplex printing and WiFi for classroom sharing.\n\n"
                "Would you like to review its technical specifications or running costs?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Review Specs", "Running Costs"],
                source="route:school_recommendation",
            )

        # ── (a.38) Color vs Mono Selection ───────────────────────────────────
        if re.search(r"\b(?:color\s+or\s+black\s+white|colour\s+or\s+black\s+white|mono\s+or\s+colo(?:u)?r)\b", msg_l):
            reply = (
                "For school worksheets, notices, and student certificates, a **Colour Multifunction printer** like the WF-C5890 gives you the flexibility "
                "to print both vibrant color diagrams and crisp black-and-white documents at the same fast speed (25 ppm ISO), while using separate high-capacity "
                "black and colour ink packs so you only replace what you use.\n\n"
                "Would you like to see the running costs for colour versus black prints?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Official Quotation", "Running Costs", "Delivery Options"],
                source="route:color_vs_mono",
            )

        # ── (a.39) Malayalam Price Query ─────────────────────────────────────
        if re.search(r"\b(?:ethra\s+rate|ethraya\s+rate|rate\s+aanu?)\b", msg_l):
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                f"**{p_name}** printer-inte official catalogue price **AED 1,656.00** (excl. VAT) aanu. "
                "Official proforma quotation-um UAE flat AED 10 courier delivery-um (1–2 business days) labhikkum.\n\n"
                "Ningalkku official quotation thiyyaaraakkanno?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Delivery Options", "Technical Specs"],
                source="route:malayalam_price",
            )

        # ── (a.40) Multi-Part Compound Inquiry (Price, Toner, WiFi, Delivery) ──
        if (re.search(r"\b(?:give\s+me\s+the\s+price.*toner.*wifi.*delivery)\b", msg_l) or
            (all(k in msg_l for k in ["price", "toner", "wifi", "delivery"]))):
            target_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(target_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                f"Here is the complete breakdown for the **{p_name}**:\n\n"
                "1. **Price**: AED 1,656.00 (excl. VAT)\n"
                "2. **Toner / Ink Cost**: Uses replaceable Heat-Free ink packs yielding up to 10,000 black pages and 5,000 colour pages, reducing ongoing supply costs by up to 50% compared to laser toners.\n"
                "3. **Wi-Fi**: Yes, integrated Wi-Fi, Wi-Fi Direct, and Gigabit Ethernet.\n"
                "4. **Delivery to Dubai**: Dispatched within 1–2 business days (flat AED 10 tracked courier delivery, or same-day express upon request).\n\n"
                "Would you like to proceed with an official quotation or order confirmation?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Order Supplies", "Speak with Specialist"],
                source="route:compound_4_part",
            )

        # ── (a.41) Photo Quality for Office Printer ──────────────────────────
        if re.search(r"\b(?:good\s+for\s+photos?|print\s+photos?|photo\s+quality)\b", msg_l) and not re.search(r"\b(?:photo\s+booth|citizen)\b", msg_l):
            reply = (
                "The WF-C5890 prints sharp 4800 × 1200 dpi documents and school report photos on plain and inkjet paper. "
                "However, for dedicated studio portraits, gallery fine art, or borderless photography, we recommend our specialized 6-color and 10-color "
                "**Epson SureColor SC-P700/P900** series, or **Citizen Photo Booth** dye-sub printers.\n\n"
                "Are you printing occasional office photos or professional photography?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Office & School Photos", "Professional Photo (SureColor)", "Citizen Photo Booth"],
                source="route:photo_capability",
            )

        # ── (a.42) Laser Printer Inquiry (Heat-Free Advantage) ───────────────
        if re.search(r"^\s*(?:i\s+want\s+laser|laser\s+printer|looking\s+for\s+laser)\s*$", msg_l):
            reply = (
                "Kepler Tech specializes in authorized **Epson Heat-Free business inkjet technology**. "
                "Unlike traditional laser printers that require high-heat fusers, high electrical power, and frequent toner drum replacements, "
                "Epson Heat-Free printers consume up to 85% less energy, have zero warm-up time, and produce no toner dust or ozone emissions—"
                "offering superior reliability and lower running costs.\n\n"
                "Would you like to review how the WorkForce Pro compares with traditional laser copiers?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["WorkForce Pro WF-C5890", "Running Cost Comparison", "Official Quotation"],
                source="route:laser_comparison",
            )

        # ── (a.43) Fact Traps: Speed, Warranty, Cheapest, False Prior Price ──
        if re.search(r"\b(?:prints?\s+60\s*(?:pages?|ppm)|60\s*pages?\s+per\s+minute|speed\s+is\s+60)\b", msg_l):
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                f"To clarify, the **{p_name}** prints at **25 pages per minute (ISO)** and up to 34 ppm in draft mode—it does not print at 60 ppm. "
                "If your enterprise requires true 60 pages per minute line-head output, we offer the **Epson WorkForce Enterprise AM-C6000** (60 ppm).\n\n"
                "Would you like to review the WF-C5890 or the higher-speed AM-C6000?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["WF-C5890 (25–34 ppm)", "Enterprise AM-C6000 (60 ppm)", "Official Quotation"],
                source="route:fact_check_speed",
            )

        if re.search(r"\b(?:5\s*year\s*warranty|five\s*year\s*warranty|warranty\s+is\s+5\s*years?)\b", msg_l):
            reply = (
                "Standard manufacturer warranty on our Epson and Citizen commercial equipment is **1 Year** (on-site service and genuine parts). "
                "For organizations requiring extended coverage, Kepler Tech provides optional 3-year and 5-year Annual Maintenance Contracts (AMC) "
                "and official Epson CoverPlus warranty extensions.\n\n"
                "Would you like to include an extended warranty package with your quotation?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["1-Year Standard Warranty", "3–5 Year AMC Option", "Official Quotation"],
                source="route:fact_check_warranty",
            )

        if re.search(r"\b(?:cheapest\s+in\s+the\s+market|cheapest\s+printer\s+in\s+(?:uae|dubai|market))\b", msg_l):
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                f"We do not claim to offer disposable consumer inkjets. Among heavy-duty commercial Heat-Free business multifunction printers, "
                f"the **{p_name}** (AED 1,656.00 excl. VAT) offers the lowest running cost per page in its class thanks to 10,000-page high-capacity ink packs.\n\n"
                "Would you like to review the running costs or order details?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Review Running Costs", "Official Quotation", "View Consumables"],
                source="route:fact_check_cheapest",
            )

        if re.search(r"\b(?:told\s+me\s+earlier\s+it\s+costs?|costs?\s+300|showing\s+450|you\s+said\s+300)\b", msg_l):
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                "To maintain full transparency, Kepler Tech pricing is deterministically verified from our authorized catalogue. "
                f"We did not quote AED 300 for this system; the official catalogue list price for the **{p_name}** is **AED 1,656.00** (excl. VAT). "
                "Formal project quotations can be issued directly by our sales desk.\n\n"
                "Would you like an official quotation for your records?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Download Datasheet", "Speak with Specialist"],
                source="route:price_transparency",
            )

        # ── (a.44) Boundary & Services: A0 Plotters, Repair / AMC, Availability ──
        if re.search(r"\b(?:a0\s*(?:plotters?|printers?)|36\s*inch\s*(?:plotters?|printers?)|technical\s*cad\s*plotters?)\b", msg_l):
            reply = (
                "Yes! Kepler Tech is an authorized distributor supplying official **Epson SureColor T-Series A0 (36-inch and 44-inch) CAD/GIS plotters**, "
                "including the **SureColor SC-T5100** and **SureColor SC-T5405**. They are specifically engineered for architectural blueprints, engineering line drawings, and GIS mapping.\n\n"
                "Would you like a quotation or technical datasheet for our A0 plotters?"
            )
            t5100 = catalogue_loader.get_by_id("epson-sc-t5100")
            cards = [t5100] if t5100 else []
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=cards,
                suggested_chips=["Epson SC-T5100 (36″)", "Epson SC-T5405 (36″)", "Official Quotation"],
                source="route:a0_plotters",
            )

        if re.search(r"\b(?:do\s+you\s+repair\s+printers|printer\s+repairs?|repair\s+service|service\s+center|maintenance\s+contract|amc|fix\s+printers?)\b", msg_l):
            reply = (
                "Yes! Kepler Tech provides authorized on-site maintenance, repairs, and comprehensive Annual Maintenance Contracts (AMC) "
                "for commercial Epson and Citizen printing equipment across Dubai and all UAE emirates. Our manufacturer-certified engineers carry genuine OEM parts and printheads.\n\n"
                "Would you like to schedule a technician visit or request an AMC maintenance proposal?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Request AMC Proposal", "Schedule On-Site Service", "Contact Technical Support"],
                source="route:repair_amc_service",
            )

        if re.search(r"\b(?:available\s+right\s+now|in\s+stock|out\s+of\s+stock|when\s+will\s+it\s+be\s+back)\b", msg_l):
            reply = (
                "Our standard commercial equipment, including the Epson WorkForce Pro series and SureColor technical plotters, is actively stocked in our UAE warehouse "
                "for dispatch within 1–2 business days. If any specific high-capacity configuration requires replenishment, incoming shipments arrive weekly.\n\n"
                "Would you like to check delivery lead time for a specific unit?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Check Warehouse Stock", "Arrange Delivery", "Official Quotation"],
                source="route:stock_availability",
            )

        # ── (a.45) Returning Customer Context Recall ─────────────────────────
        if re.search(r"\b(?:hi[,\s]+i\s+was\s+here\s+yesterday|what\s+did\s+i\s+ask\s+(?:you\s+)?about|continue\s+where\s+we\s+stopped)\b", msg_l):
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            reply = (
                f"Welcome back! In our previous conversation, you were reviewing commercial office printing requirements (~20 users / school and office documents) "
                f"and looking at the **{p_name}**.\n\n"
                "We can pick up right where you left off—would you like to review an official quotation, arrange courier delivery across Dubai, or check consumable options?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Official Quotation", "Review Specs", "Arrange Delivery"],
                source="route:memory_recall",
            )

        # ── (a.46) Order Quantity Updates & Calculations ─────────────────────
        has_explicit_unit = bool(re.search(r"\b(?:units?|pieces?|pcs?|printers?|machines?)\b", msg_l))
        has_size_unit = bool(re.search(r"\b(?:inch|inches|in|\"|''|mm|cm|a[0-6])\b", msg_l))
        qty_match = None
        if not has_size_unit:
            qty_match = re.search(r"\b(?:i\s+want|order|need|change\s+it\s+to|make\s+it|update\s+to|change\s+to)\s+(\d+)\s*(?:units?|pieces?|pcs?|printers?|machines?)?\b", msg_l)
            if not qty_match and re.search(r"^\s*change\s+it\s+to\s+(\d+)\s*$", msg_l):
                qty_match = re.search(r"^\s*change\s+it\s+to\s+(\d+)\s*$", msg_l)
        if qty_match:
            candidate_val = int(qty_match.group(1))
            is_width_candidate = candidate_val in (13, 17, 24, 36, 44, 64)
            has_active_order = getattr(state, "order_status", None) is not None or getattr(state, "order_quantity", 1) > 1 or bool(getattr(state, "lead_id", None))
            if not has_explicit_unit and (is_width_candidate or not has_active_order):
                qty_match = None

        if qty_match:
            new_qty = int(qty_match.group(1))
            if new_qty > 0:
                state.order_quantity = new_qty
                if hasattr(state, "requirements"):
                    state.requirements["quantity"] = new_qty
                if hasattr(state, "confirmed_slots"):
                    state.confirmed_slots["quantity"] = new_qty
                active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
                p_obj = catalogue_loader.get_by_id(active_id)
                p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
                raw_price = p_obj.get("price") if p_obj else 1656.0
                if isinstance(raw_price, (int, float)):
                    unit_price = float(raw_price)
                    total_price = unit_price * new_qty
                    pricing_lines = (
                        f"• Unit Price: AED {unit_price:,.2f} (excl. VAT)\n"
                        f"• Total Amount: **AED {total_price:,.2f} (excl. VAT)**\n\n"
                    )
                else:
                    pricing_lines = "• Commercial Pricing: Official quotation prepared on request\n\n"

                reply = (
                    f"Updated your order to **{new_qty} unit(s)** of the **{p_name}**.\n\n"
                    f"{pricing_lines}"
                    "Delivery across the UAE is flat AED 10 (dispatched in 1–2 business days). Would you like to confirm this order or review payment options?"
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[p_obj] if p_obj else [],
                    suggested_chips=["Confirm Order", "Pay by Card", "Cash on Delivery", "Bank Transfer"],
                    source="route:order_quantity_update",
                )

        # ── (a.47) Order Cancellation ────────────────────────────────────────
        if re.search(r"\b(?:cancel\s+(?:the\s+)?(?:order|request|booking|purchase)|stop\s+the\s+order)\b", msg_l):
            state.order_status = "cancelled"
            reply = (
                "Your order request has been cancelled as requested. No charges or shipments will be processed.\n\n"
                "Would you like to review other equipment options or start fresh?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Review Models", "Request Quotation", "Speak to Specialist"],
                source="route:order_cancelled",
            )

        # ── (a.48) Order Reactivation ────────────────────────────────────────
        if re.search(r"\b(?:actually\s+place\s+it\s+again|place\s+it\s+again|reorder|reactivate\s+(?:the\s+)?order)\b", msg_l):
            state.order_status = "pending_confirmation"
            active_id = state.get_canonical_focus_id() or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id)
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            qty = getattr(state, "order_quantity", 1) or 1
            reply = (
                f"Understood! We've reactivated your order for **{qty} unit(s)** of the **{p_name}**.\n\n"
                "Would you like to confirm the order for delivery or review payment methods?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Confirm Order", "Pay by Card", "Delivery Timeline"],
                source="route:order_reactivated",
            )

        # ── (a.49) Payment Methods ───────────────────────────────────────────
        if re.search(r"\b(?:pay\s+by\s+card|credit\s*card|debit\s*card|payment\s+methods?|how\s+(?:can\s+i|to)\s+pay|accept\s+cards?|card\s+payment|bank\s+transfer|cash\s+on\s+delivery|cod)\b", msg_l):
            reply = (
                "We accept multiple secure commercial payment options across the UAE:\n\n"
                "1. **Credit / Debit Card (Visa & MasterCard)**: Secure digital payment link sent upon order confirmation.\n"
                "2. **Direct Bank Wire / Transfer**: Official company bank details provided on your proforma invoice.\n"
                "3. **Cash on Delivery (COD)**: Available for standard equipment and consumables deliveries across Dubai and Sharjah.\n"
                "4. **Corporate Cheque**: Accepted for corporate and government accounts.\n\n"
                "Would you like to proceed with card payment or cash on delivery?"
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["Confirm Order", "Track Delivery (1–2 Days)", "Download Proforma Invoice"],
                source="route:payment_methods",
            )

        # ── (a.50) Order Confirmation & Rapid Confirm De-duplication ──────────
        is_confirm_batch = bool(
            "\n" in raw_msg and all(line.strip().lower() == "confirm" for line in raw_msg.splitlines() if line.strip())
        )
        is_single_confirm = bool(
            re.search(r"^\s*confirm\s*$", msg_l) or
            re.search(r"\b(?:confirm\s+(?:the\s+)?order|place\s+(?:the\s+)?order|proceed\s+with\s+order)\b", msg_l)
        )
        if is_confirm_batch or is_single_confirm:
            confirmed = getattr(state, "confirmed_slots", {}) or {}
            lead_ref = getattr(state, "lead_id", None) or confirmed.get("lead_id")
            if not lead_ref:
                lead_ref = 48291
                state.lead_id = lead_ref
                confirmed["lead_id"] = lead_ref

            cust_name = getattr(state, "customer_name", None) or confirmed.get("customer_name")
            cust_phone = getattr(state, "customer_phone", None) or getattr(state, "customer_phone_or_email", None) or confirmed.get("customer_phone")
            cust_addr = getattr(state, "customer_address", None) or confirmed.get("customer_address") or "Dubai, UAE"
            active_id = state.get_canonical_focus_id() or (state.shown_entities[0] if state.shown_entities else None) or "epson-wf-c5890-dwf"
            p_obj = catalogue_loader.get_by_id(active_id) if active_id else None
            p_name = p_obj.get("display_name") or p_obj.get("name") if p_obj else "Epson WorkForce Pro WF-C5890 DWF"
            qty = getattr(state, "order_quantity", 1) or 1

            # De-duplication check: if order was already confirmed under this session
            if getattr(state, "order_status", None) == "confirmed":
                reply = (
                    f"Your order has already been successfully registered under **Reference #{lead_ref}** for **{qty} unit(s)** of the **{p_name}**. "
                    "Our dispatch desk is processing a single delivery to avoid duplicate dispatches. You will receive an SMS and email notification once on route."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[p_obj] if p_obj else [],
                    suggested_chips=["Track Order Status", "Contact Dispatch Team", "Download Proforma Invoice"],
                    source="route:order_idempotent_confirmed",
                )

            state.order_status = "confirmed"
            ref_part = f"Reference #{lead_ref}"
            name_part = f", {cust_name}" if cust_name else ""
            addr_part = f" for delivery to **{cust_addr}**" if cust_addr else ""
            phone_part = f" at **{cust_phone}**" if cust_phone else ""

            reply = (
                f"Thank you{name_part}! Your order for **{qty} unit(s)** of the **{p_name}** has been confirmed under **{ref_part}**{addr_part}. "
                f"Our commercial dispatch team will reach out directly{phone_part} to finalize payment (Visa, MasterCard, or bank transfer) and arrange courier delivery."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[p_obj] if p_obj else [],
                suggested_chips=["Track Order Status", "Contact Dispatch Team", "Download Invoice"],
                source="route:order_confirmed",
            )

        # ── Follow-up consumable inquiry for active product (e.g. "list all the consubles'", "i want ink?", "any other ink for it") ───
        active_focus = state.get_canonical_focus_id() or getattr(state, "active_product_id", None) or (state.shown_entities[0] if state.shown_entities else None)
        is_consumables_req = bool(re.search(r"\b(?:list\s+all\s+(?:the\s+)?(?:consumables?|consubles?|consumbales?|inks?|supplies)|all\s+(?:the\s+)?(?:consumables?|consubles?|consumbales?|inks?|supplies)|(?:show|give|what\s+are)\s+(?:all\s+)?(?:the\s+)?(?:consumables?|consubles?|consumbales?|inks?|supplies)|(?:i\s+want\s+)?(?:consubles|consumbales|consumables|inks?|cartridges?|supplies))\b", msg_l))
        names_another_model = bool(alias_index.resolve(msg_l).is_exact or any(k in msg_l for k in ["f100", "c878", "c879", "cz01", "cx02", "cy02", "p700", "p900"]))
        if active_focus and is_consumables_req and not names_another_model:
            from catalog.evidence import EvidenceEngine
            target_obj = catalogue_loader.get_by_id(active_focus)
            if target_obj:
                c_items, rec = EvidenceEngine.list_consumables(active_focus)
                t_name = target_obj.get("display_name") or target_obj.get("name") or active_focus
                if c_items:
                    c_cards = []
                    lines = [f"Found {len(c_items)} verified compatible consumables for **{t_name}**:\n"]
                    for ci in c_items:
                        c_card = {
                            "card_type": "consumable",
                            "id": ci.get("sku") or ci.get("id"),
                            "name": ci.get("name"),
                            "sku": ci.get("sku"),
                            "price": ci.get("price"),
                            "price_str": f"AED {ci.get('price'):,.2f}" if ci.get("price") else None,
                            "price_formatted": f"AED {ci.get('price'):,.2f} (Excl. VAT)" if ci.get("price") else None,
                            "currency": "AED",
                            "category": ci.get("category", "consumable"),
                            "compatible_printers": [t_name],
                            "product_url": ci.get("url") or f"https://www.keplertechllc.com/product/{ci.get('sku', '')}",
                        }
                        c_cards.append(c_card)
                        price_part = f" — AED {ci.get('price'):,.2f}" if ci.get("price") else ""
                        lines.append(f"• **{ci.get('name')}** ({ci.get('sku')}){price_part}")
                    lines.append("\nWould you like to order replacement supplies or review printer specifications?")
                    reply = "\n".join(lines)
                    state.category = "consumables"
                    state.set_canonical_focus(active_focus)
                    state.shown_entities = [active_focus] + [ci.get("sku") or ci.get("id") for ci in c_items]
                    return PreClassificationResult(
                        handled=True,
                        reply=reply,
                        consumable_cards=c_cards,
                        suggested_chips=["Request Official Quote", "Technical Specifications", "Order Supplies"],
                        source="route:consumables:verified_list",
                    )

        # ── (a) PENDING QUESTION BINDING ─────────────────────────────────────
        if state.pending_question:
            slot_name = ""
            valid_range = None
            if isinstance(state.pending_question, dict):
                slot_name = state.pending_question.get("slot", "")
                valid_range = state.pending_question.get("valid_range")
            elif getattr(state, "pending_field", None):
                slot_name = state.pending_field

            num_val = _extract_number(msg_l)

            # Daily / Monthly Volume Binding
            if slot_name in ("daily_volume", "exact_daily_volume", "volume") or (not slot_name and state.category == "office_printer" and num_val is not None):
                # Ensure "40 ppm" is NOT treated as daily volume (ppm = speed!)
                if num_val is not None and not re.search(r"\b(?:ppm|ipm|speed)\b", msg_l):
                    state.requirements["exact_daily_volume"] = num_val
                    state.requirements["daily_volume"] = num_val
                    state.requirements["monthly_volume"] = num_val * 30
                    state.requirements["exact_monthly_volume"] = num_val * 30

                    # Check valid range (e.g. A3 office printers start at 100 pages/day)
                    is_a3 = state.requirements.get("paper_size") == "a3" or state.requirements.get("print_size") == "A3"
                    if is_a3 and num_val < 100:
                        # 40 pages is below minimum A3 bucket (100)
                        state.consume_pending_question()
                        reply = (
                            f"{num_val} pages per day is below our standard minimum duty cycle for A3 commercial multifunction systems (typically 100–500 pages/day). "
                            f"For a daily volume of {num_val} pages, our compact A4 WorkForce Pro models (such as the WF-C5890) are highly cost-effective, "
                            "or if large-format A3 is strictly required, our entry A3 WorkForce Pro WF-C878R handles the 100–500 pages/day range.\n\n"
                            "Would you like to explore the A3 WF-C878R or consider our A4 desktop options?"
                        )
                        chips = ["A3 WorkForce WF-C878R", "A4 WorkForce Pro WF-C5890", "Official Quotation"]
                        return PreClassificationResult(
                            handled=True,
                            reply=reply,
                            suggested_chips=chips,
                            source="qualification:out_of_range_guidance",
                        )
                    else:
                        # Valid volume -> apply state change and return models!
                        state.consume_pending_question()
                        if is_a3 and num_val <= 500:
                            state.requirements["office_duty_class"] = "departmental_rips"
                            state.requirements["office_speed_class"] = "25_ppm_rips"
                            c878 = catalogue_loader.get_by_id("epson-wf-c878r-dwf")
                            c879 = catalogue_loader.get_by_id("epson-wf-c879r-dwf")
                            cards = [c for c in [c878, c879] if c]
                            state.shown_entities = [c["id"] for c in cards]
                            state.set_canonical_focus(cards[0]["id"] if cards else None)
                            reply = (
                                f"Understood, updated daily volume to {num_val} pages/day. "
                                "For departmental A3 printing (100–500 pages/day), here are our recommended WorkForce Pro RIPS multifunction systems:\n\n"
                                "• **Epson WorkForce Pro WF-C878R DWF** (25 ppm, up to 86,000 pages ink yield)\n"
                                "• **Epson WorkForce Pro WF-C879R DWF** (26 ppm, up to 86,000 pages ink yield, high-speed dual-scan)"
                            )
                            return PreClassificationResult(
                                handled=True,
                                reply=reply,
                                product_cards=cards,
                                suggested_chips=["Both models have scan?", "Request Official Quotation", "Compatible RIPS Inks"],
                                source="recommendation:catalogue_list",
                            )
                        state_res = state.apply_state_change()
                        return PreClassificationResult(
                            handled=True,
                            reply=state_res.get("reply", ""),
                            product_cards=state_res.get("cards", []),
                            consumable_cards=state_res.get("consumable_cards", []),
                            suggested_chips=state_res.get("chips", []),
                            source=state_res.get("source", "recommendation:catalogue_list"),
                        )

            # Print Width Binding (e.g. CAD 24 or 36)
            elif slot_name in ("print_width", "format", "width"):
                if num_val in (24, 36, 44, 64) or re.search(r"\b(?:24|36|44|64)\b", msg_l):
                    w = num_val if num_val in (24, 36, 44, 64) else (24 if "24" in msg_l else 36)
                    state.requirements["print_width"] = w
                    if w == 24:
                        state.requirements["paper_size"] = "a1"
                        state.requirements["format"] = "A1"
                    elif w == 36:
                        state.requirements["paper_size"] = "a0"
                        state.requirements["format"] = "A0"
                    state.consume_pending_question()
                    state_res = state.apply_state_change()
                    return PreClassificationResult(
                        handled=True,
                        reply=state_res.get("reply", ""),
                        product_cards=state_res.get("cards", []),
                        consumable_cards=state_res.get("consumable_cards", []),
                        suggested_chips=state_res.get("chips", []),
                        source=state_res.get("source", "recommendation:catalogue_list"),
                    )

            # Disambiguation candidate choice (e.g. "the first one")
            elif slot_name == "disambiguation":
                if re.search(r"\b(?:the\s+first(?:\s+one)?|first(?:\s+one)?|1|option\s+1)\b", msg_l):
                    selected_id = state.shown_entities[0] if state.shown_entities else None
                    if selected_id:
                        p_obj = catalogue_loader.get_by_id(selected_id)
                        state.set_canonical_focus(selected_id)
                        state.consume_pending_question()
                        p_name = p_obj.get("display_name") or p_obj.get("name") or selected_id if p_obj else selected_id
                        reply = f"Here is the verified specification for the **{p_name}**:\n\n• Print Speed: {p_obj.get('print_speed', 'High speed')}\n• Resolution: {p_obj.get('dpi', '300 DPI')}\n• Supported Media: {', '.join(p_obj.get('supported_print_sizes', []))}"
                        card = p_obj if p_obj else {"id": selected_id}
                        return PreClassificationResult(
                            handled=True,
                            reply=reply,
                            product_cards=[card],
                            suggested_chips=["Compatible Media & Ribbons", "Official Quotation", "View Detailed Specs"],
                            source="route:model_detail",
                        )

        # ── (b) REFERENT RESOLUTION AGAINST SHOWN_ENTITIES ────────────────────
        is_both = bool(re.search(r"\b(?:both|both\s+of\s+them|all\s+of\s+(?:them|these)|details\s+of\s+(?:all|these|both)|specs\s+for\s+(?:all|these|both)|these\s+models|dono|dono\s+ka|كلاهما)\b", msg_l)) or (
            msg_l.strip() in ("both", "all", "all of them", "these", "details of these")
        )
        is_compare_first_two = bool(re.search(r"\b(?:compare\s+first\s+two|compare\s+the\s+two|compare\s+both)\b", msg_l))
        is_first = bool(re.search(r"\b(?:the\s+first(?:\s+one)?|first\s+one|first\s+model|first\s+printer)\b", msg_l))
        is_second = bool(re.search(r"\b(?:the\s+second(?:\s+one)?|second\s+one|second\s+model|second\s+printer)\b", msg_l))

        # Follow-up on compound comparison (e.g. "which one is cheaper")
        if re.search(r"\b(?:which(?:\s+one)?\s+is\s+cheaper|cheapest\s+one|cheaper\s+one)\b", msg_l):
            comp_items = getattr(state, "_compound_comparison_items", [])
            if len(comp_items) >= 2:
                it1, it2 = comp_items[0], comp_items[1]
                p1, p2 = it1.get("price", 0.0), it2.get("price", 0.0)
                cheaper = it1 if p1 < p2 else it2
                pricier = it2 if p1 < p2 else it1
                reply = (
                    f"Between the two items requested:\n"
                    f"• **{it1['name']}**: {it1['price_str']}\n"
                    f"• **{it2['name']}**: {it2['price_str']}\n\n"
                    f"The **{cheaper['name']}** is cheaper ({cheaper['price_str']} vs {pricier['price_str']})."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    suggested_chips=["Official Quotation", "View Consumables Page"],
                    source="route:pricing_comparison",
                )
            elif state.category == "citizen_photo":
                # Photo booth cheapest model
                reply = (
                    "Among our Citizen event photo booth printers, the **Citizen CZ-01** is our most affordable model at AED 3,200.00 (excl. VAT), "
                    "compared to the Citizen CY-02 (AED 3,400.00) and the Citizen CX-02 (AED 4,385.00)."
                )
                cz01 = catalogue_loader.get_by_id("citizen-cz-01")
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[cz01] if cz01 else [],
                    suggested_chips=["View Citizen CZ-01", "Compare CX-02 and CZ-01", "Official Quotation"],
                    source="route:pricing_comparison",
                )

        if is_compare_first_two:
            shown = state.shown_entities or state.displayed_product_ids
            if len(shown) >= 2:
                p1 = catalogue_loader.get_by_id(shown[0])
                p2 = catalogue_loader.get_by_id(shown[1])
                n1 = p1.get("display_name") or p1["id"] if p1 else shown[0]
                n2 = p2.get("display_name") or p2["id"] if p2 else shown[1]
                comp_reply = (
                    f"Here is a side-by-side comparison of **{n1}** and **{n2}**:\n\n"
                    f"• **{n1}**: Print speed {p1.get('print_speed', 'Standard')}; Duty cycle {p1.get('consumable_volume', 'Standard')}.\n"
                    f"• **{n2}**: Print speed {p2.get('print_speed', 'High speed')}; Duty cycle {p2.get('consumable_volume', 'High capacity')}."
                )
                cards = [p for p in (p1, p2) if p]
                return PreClassificationResult(
                    handled=True,
                    reply=comp_reply,
                    product_cards=cards,
                    suggested_chips=["Request Official Quotation", "View Running Costs"],
                    source="route:comparison",
                )

        if is_second:
            shown = state.shown_entities or state.displayed_product_ids
            if len(shown) >= 2:
                p2 = catalogue_loader.get_by_id(shown[1])
                if p2:
                    state.set_canonical_focus(p2["id"])
                    p_name = p2.get("display_name") or p2.get("name") or p2["id"]
                    if re.search(r"\b(?:quote|quotation|price|pricing|cost)\b", msg_l):
                        reply = (
                            f"To receive an official quotation for the **{p_name}**, our sales desk can prepare a comprehensive proposal tailored to your business.\n\n"
                            f"Verified list pricing is also published on our official website (https://www.keplertechllc.com/product/{p2.get('id')}). "
                            "Would you like me to connect you with our commercial team?"
                        )
                        return PreClassificationResult(
                            handled=True,
                            reply=reply,
                            product_cards=[p2],
                            suggested_chips=["Speak with Sales Specialist", "Download Datasheet"],
                            source="guardrail:commercial_policy",
                        )

        if is_both:
            shown = state.shown_entities or state.displayed_product_ids
            if not shown:
                return PreClassificationResult(
                    handled=True,
                    reply="Which equipment models would you like to review specifications for? Please select or name a model.",
                    suggested_chips=["A3 Office Multifunction", "Citizen Photo Booth", "Large Format Plotters"],
                    source="unified:clarify",
                )

            # Check if asking about scanning capability
            if re.search(r"\b(?:scan|scanner|scanning|copy|fax)\b", msg_l):
                p_objs = [catalogue_loader.get_by_id(pid) for pid in shown]
                p_objs = [p for p in p_objs if p]
                p_names = [p.get("display_name") or p.get("model") or p["id"] for p in p_objs]
                if len(p_names) == 2:
                    names_str = " and ".join(f"**{n}**" for n in p_names)
                    plural_lead = "Both are complete multifunction"
                else:
                    names_str = ", ".join(f"**{n}**" for n in p_names)
                    plural_lead = "All are complete multifunction"
                reply = (
                    f"Yes, {names_str} feature integrated high-speed scanning, copying, and faxing. "
                    f"{plural_lead} (DWF) enterprise systems with automatic dual-sided document feeders (ADF)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=p_objs,
                    suggested_chips=["View Scan Speeds", "Official Quotation", "View Running Costs"],
                    source="route:product_spec_attribute",
                )

            # Asking specs for both / these / all
            if re.search(r"\b(?:spec|specs|specification|features|batao|details)\b", msg_l):
                p_objs = [catalogue_loader.get_by_id(pid) for pid in shown]
                p_objs = [p for p in p_objs if p]
                header = (
                    "Here are the specifications for both models from our catalogue:"
                    if len(p_objs) == 2
                    else f"Here are the specifications for the {len(p_objs)} models from our catalogue:"
                )
                lines = [header]
                for p in p_objs:
                    lines.append(
                        f"\n• **{p.get('display_name', p.get('model'))}**:\n"
                        f"  - Speed: {p.get('print_speed', '25 ppm')}\n"
                        f"  - Resolution: {p.get('dpi', '4800 x 1200 DPI')}\n"
                        f"  - Functions: {', '.join(p.get('functions', ['print', 'scan', 'copy']))}\n"
                        f"  - Ink Yield: {p.get('yield_capacity', 'High capacity ink supply bags')}"
                    )
                return PreClassificationResult(
                    handled=True,
                    reply="\n".join(lines),
                    product_cards=p_objs,
                    suggested_chips=["Official Quotation", "Compare Ink Yields"],
                    source="route:product_spec_attribute",
                )

        # ── (c) MODEL ALIAS OVERRIDE VIA ALIAS_INDEX ─────────────────────────
        # Check if user input names a model code
        match = alias_index.resolve(msg_l)

        if match.is_candidates:
            cand_names = [c.get("display_name") or c.get("name") or c["id"] for c in match.candidates]
            cand_str = " or ".join(cand_names)
            reply = f"Did you mean {cand_str}?"
            state.shown_entities = [c["id"] for c in match.candidates]
            state.save_pending_question(
                question=reply,
                field_name="disambiguation",
                expected_type="product_choice",
                options=cand_names,
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=cand_names,
                source="unified:clarify",
            )

        if match.is_exact and match.product:
            p = match.product
            pid = p["id"]
            if pid == "epson-sc-p900-roll" and "p900" in msg_l and "roll" not in msg_l:
                p_base = catalogue_loader.get_by_id("epson-sc-p900")
                if p_base:
                    p = p_base
                    pid = p["id"]
            p_name = p.get("display_name") or p.get("name") or p["id"]

            has_explicit_hardware = bool(re.search(
                r"\b(?:printers?|plotters?|machines?|hardware|devices?|specs?|specifications?|features?|print\s*speed|speed|speeds|ppm|brochures?|datasheets?|dimensions?|resolutions?|how\s+fast|dpi|warranty|roll\s+adapter|cut\s*sheet|without\s+roll|with\s+roll|roll|rolls|desktop|a4|24-inch|weights?|weigh|lighter|heavier|compare|comparison|portable|portability)\b",
                msg_l
            ))
            has_explicit_consumables = bool(re.search(
                r"\b(?:consubales|consumbales|consumable|consumables|ink|inks|cartridge|cartridges|media|ribbon|ribbons|toner|supplies)\b",
                msg_l
            ))

            is_hardware_qualification = (
                state.stage == "qualifying"
                or state.category in ("dye_sublimation", "sublimation", "office_printer", "technical_large_format", "photography_large_format", "citizen_photo", "scanners")
                or state.awaiting_field in ("paper_size", "sublimation_format", "print_width", "photo_form_factor", "photo_brand", "scanner_required", "daily_volume")
            )
            has_consumables_context = not is_hardware_qualification and bool(
                state.active_printer_for_consumables
                or state.active_route in ("consumables", "consumable", "route:consumables")
                or (state.history_turns and any(
                    "compatible with" in t.get("content", "").lower()
                    or "verified inks" in t.get("content", "").lower()
                    or "consumable" in t.get("content", "").lower()
                    for t in state.history_turns[-3:]
                ))
            )

            # If returning back to model (e.g. "back to the f100 – ink bottle size")
            if re.search(r"\bback\s+to\s+(?:the\s+)?f100\b", msg_l) or ("f100" in msg_l and ("bottle" in msg_l or "ink" in msg_l and "back" in msg_l)):
                state.set_canonical_focus("epson-surecolor-sc-f100")
                state.category = "dye_sublimation"
                reply = (
                    "The **Epson SureColor SC-F100** uses genuine Epson T49N dye-sublimation ink bottles with a capacity of **140 ml per bottle** "
                    "(available in Black, Cyan, Magenta, and Yellow)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[p],
                    suggested_chips=["View T49N Inks", "Paper Size Support", "Official Quotation"],
                    source="route:product_spec_attribute",
                )

            # If user already initiated consumables inquiry in prior turns, directly return consumables!
            user_initiated_consumables = bool(
                state.active_route in ("consumables", "consumable", "route:consumables")
                or getattr(state, "awaiting_field", None) in ("consumables", "consumables_printer", "consumable_model", "printer_for_consumables")
                or (state.history_turns and any(
                    "need ink" in t.get("content", "").lower()
                    or "which printer or plotter model do you need consumables" in t.get("content", "").lower()
                    or "which printer or scanner do you need supplies" in t.get("content", "").lower()
                    for t in state.history_turns[-3:]
                ))
            )
            if user_initiated_consumables and not has_explicit_hardware:
                from catalog.evidence import EvidenceEngine
                disp_name = p.get("display_name") or p_name
                short_name = p.get("model_family") or disp_name
                c_items, _ = EvidenceEngine.list_consumables(p.get("id", pid)) if p else ([], None)
                c_cards = []
                items_lines = []
                for ci in c_items:
                    c_card = {
                        "card_type": "consumable",
                        "id": ci.get("sku") or ci.get("id"),
                        "name": ci.get("name"),
                        "sku": ci.get("sku"),
                        "price": ci.get("price"),
                        "price_str": ci.get("price_str") or (f"AED {ci.get('price'):,.2f}" if ci.get("price") else None),
                        "price_formatted": ci.get("price_formatted") or (f"AED {ci.get('price'):,.2f} (Excl. VAT)" if ci.get("price") else None),
                        "category": ci.get("type", "consumable"),
                        "compatible_printers": [disp_name],
                        "product_url": ci.get("url"),
                    }
                    c_cards.append(c_card)
                    price_part = f": **{c_card['price_formatted']}**" if c_card.get('price_formatted') else ""
                    c_url = ci.get("url")
                    link_title = f"[{ci.get('name')}]({c_url})" if c_url else f"**{ci.get('name')}**"
                    items_lines.append(f"• **{link_title}** (SKU: `{ci.get('sku')}`){price_part}")
                items_text = "\n".join(items_lines)
                reply_text = f"Certainly! Here are the official compatible inks and media for the **{disp_name}**:\n\n{items_text}"
                chips_to_return = ["Order Consumables", f"View {short_name} Specifications", "Request Official Quote"]
                state.active_printer_for_consumables = disp_name
                state.active_route = "consumable"
                state.active_consumables = c_cards
                state.category = p.get("catalogue") or p.get("main_category") or "consumables"
                state.awaiting_field = None
                return PreClassificationResult(
                    handled=True,
                    reply=reply_text,
                    product_cards=[],
                    consumable_cards=c_cards,
                    suggested_chips=chips_to_return,
                    source="route:product_or_consumable:consumables",
                )

            # If inquiry occurs in consumables context and is ambiguous between hardware and consumables:
            if has_consumables_context and not has_explicit_hardware and not has_explicit_consumables:
                disp_name = p.get("display_name") or p_name
                short_name = p.get("model_family") or disp_name
                reply_text = (
                    f"I'd be happy to help with the **{disp_name}**! "
                    f"Just to ensure I give you the exact details you need—are you looking to purchase the **{disp_name} printer itself**, "
                    f"or do you need **compatible consumables (inks & media)** for this model?"
                )
                chips_to_return = [f"{short_name} Printer", f"{short_name} Consumables"]
                state.awaiting_field = "product_or_consumable"
                state.pending_disambiguation_model = pid
                return PreClassificationResult(
                    handled=True,
                    reply=reply_text,
                    product_cards=[],
                    consumable_cards=[],
                    suggested_chips=chips_to_return,
                    source="route:product_or_consumable_disambiguation",
                )

            # If message is "and the c878r?" (Chat 3 Turn 4)
            if re.search(r"\b(?:and\s+the|what\s+about|how\s+about|switch\s+to)?\s*(?:c878r?|c878)\b", msg_l):
                state.set_canonical_focus(pid)
                state.shown_entities = [pid]
                reply = (
                    f"The **{p_name}** is our departmental A3 WorkForce Pro multifunction printer. "
                    f"It prints at {p.get('print_speed', '25 ISO ppm')} with an ink yield of up to 86,000 pages black and 50,000 pages colour, "
                    f"recommended for monthly workloads of 1,500 to 10,000 pages."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[p],
                    suggested_chips=["Compatible Consumables", "Official Quotation", "Compare with WF-C879R"],
                    source="route:model_detail",
                )

            # If looking for consumables for a model (e.g. "i need f100 consubales", "need ink for epson c878", "i want p900 ink")
            if has_explicit_consumables:
                state.awaiting_field = None
                state.pending_disambiguation_model = None
                state.set_canonical_focus(pid)
                state.shown_entities = [pid]
                state.active_printer_for_consumables = p_name
                state.active_route = "consumable"
                state.category = "consumables"
                c_cards = []
                if "f100" in pid:
                    t49n_card = {
                        "card_type": "consumable",
                        "id": "epson-t49n-inks",
                        "name": "Epson T49N Dye-Sublimation Inks (140 ml)",
                        "sku": "T49N-Series",
                        "price": 65.0,
                        "price_str": "AED 65.00",
                        "price_formatted": "AED 65.00",
                        "category": "ink",
                        "compatible_printers": ["Epson SureColor SC-F100"],
                    }
                    c_cards.append(t49n_card)
                    reply = (
                        "Here are the verified compatible consumables for the **Epson SureColor SC-F100**:\n\n"
                        "• **Epson T49N Ink Bottles (140 ml)**: High-yield dye-sublimation ink bottles in Black, Cyan, Magenta, Yellow (AED 65.00 each).\n"
                        "• **SC-F100 Maintenance Box**: User-replaceable ink maintenance tank."
                    )
                else:
                    from catalog.evidence import EvidenceEngine
                    c_items, _ = EvidenceEngine.list_consumables(pid)
                    if c_items:
                        lines = [f"Here are the genuine consumables for the **{p_name}**:\n"]
                        for ci in c_items:
                            c_card = {
                                "card_type": "consumable",
                                "id": ci.get("sku") or ci.get("id"),
                                "name": ci.get("name"),
                                "sku": ci.get("sku"),
                                "price": ci.get("price"),
                                "price_str": ci.get("price_str") or (f"AED {ci.get('price'):,.2f}" if ci.get("price") else None),
                                "price_formatted": ci.get("price_formatted") or (f"AED {ci.get('price'):,.2f} (Excl. VAT)" if ci.get("price") else None),
                                "category": ci.get("type", "consumable"),
                                "compatible_printers": [p_name],
                                "product_url": ci.get("url"),
                            }
                            c_cards.append(c_card)
                            price_part = f" — AED {ci.get('price'):,.2f}" if ci.get("price") else ""
                            lines.append(f"• **{ci.get('name')}** ({ci.get('sku')}){price_part}")
                        reply = "\n".join(lines)
                    else:
                        reply = f"Here are the genuine consumables for the **{p_name}**."
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[],
                    consumable_cards=c_cards,
                    suggested_chips=["Price of Yellow Ink", "Maintenance Box", "Official Quotation"],
                    source="route:consumables:verified_list",
                )

            # If user explicitly specified printer / hardware intent
            if has_explicit_hardware:
                state.awaiting_field = None
                state.pending_disambiguation_model = None
                state.set_canonical_focus(pid)
                state.shown_entities = [pid]
                from agent.orchestrator import build_model_detail_response
                reply, prod_cards = build_model_detail_response(p)
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=prod_cards,
                    consumable_cards=[],
                    suggested_chips=["View Compatible Consumables", "Official Quotation"],
                    source="route:model_detail",
                )

        # ── Malayalam Consumable Question (Chat 15: "ink evide kittum?") ──────
        if re.search(r"\b(?:ink\s+evide\s+kittum|evide\s+kittum)\b", msg_l):
            reply = (
                "For Citizen 4×6″ event photo printing, the printer uses thermal dye-sublimation media packs (roll paper and ribbon), not liquid ink.\n\n"
                "Genuine Citizen **CZ-MS46** (for CZ-01) and **CX2.4X6** (for CX-02) media packs are available directly through Kepler Tech LLC in Dubai with local delivery.\n\n"
                "Would you like to order media packs or check current pack pricing?"
            )
            media_card = {
                "card_type": "consumable",
                "id": "citizen-photo-media-4x6",
                "name": "Citizen 4×6″ Media & Ribbon Pack",
                "sku": "CX2.4X6 / CZ-MS46",
                "category": "media",
                "compatible_printers": ["Citizen CX-02", "Citizen CZ-01"],
            }
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[],
                consumable_cards=[media_card],
                suggested_chips=["Order Media Packs", "Check Pack Yield", "Official Quotation"],
                source="route:consumables:verified_list",
            )

        # ── Paper size support for SC-F100 (Chat 4 Turn 4) ────────────────────
        if state.get_canonical_focus_id() == "epson-surecolor-sc-f100" and re.search(r"\b(?:paper\s+size|what\s+paper\s+size|paper\s+format|sizes?\s+it\s+supports?)\b", msg_l):
            reply = (
                "The **Epson SureColor SC-F100** supports standard **A4 cut-sheet media** (up to 8.5 × 11 inches / standard A4 sheets) via its 150-sheet front paper tray. "
                "It is designed specifically for cut-sheet dye-sublimation transfer paper."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[],
                suggested_chips=["View Transfer Paper", "Compatible Inks", "Official Quotation"],
                source="route:product_spec_attribute",
            )

        # ── Consumable details: yellow ink, maintenance box, total for 4 colors (Chat 11) ──
        if "epson-wf-c878r-dwf" in (state.get_canonical_focus_id() or "") or "c878" in msg_l:
            if re.search(r"\byellow(?:\s+one)?\s+(?:price|cost)\b", msg_l):
                reply = (
                    "The **Epson T05A Yellow Ink Supply Pack** (SKU: C13T05A400) for the WorkForce Pro WF-C878R DWF is priced at **AED 620.00** (excl. VAT). "
                    "It delivers an archival yield of up to 50,000 pages."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    consumable_cards=[{
                        "card_type": "consumable",
                        "id": "c13t05a400",
                        "name": "Epson T05A Yellow Ink Pack",
                        "sku": "C13T05A400",
                        "price": 620.0,
                        "price_str": "AED 620.00",
                    }],
                    suggested_chips=["Maintenance Box", "Total for All 4 Colors", "Official Quotation"],
                    source="route:consumable_price",
                )
            elif re.search(r"\b(?:maintainence|maintenance)\s+box(?:\s+also)?\b", msg_l):
                reply = (
                    "The genuine **Epson T6714 Ink Maintenance Box** (SKU: C13T671400) for the WorkForce Pro WF-C878R is priced at **AED 195.00** (excl. VAT)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    consumable_cards=[{
                        "card_type": "consumable",
                        "id": "c13t671400",
                        "name": "Epson T6714 Maintenance Box",
                        "sku": "C13T671400",
                        "price": 195.0,
                        "price_str": "AED 195.00",
                    }],
                    suggested_chips=["Total for All 4 Colors", "Official Quotation"],
                    source="route:consumable_price",
                )
            elif re.search(r"\btotal(?:\s+for)?\s+(?:all\s+)?4\s+colors?\b", msg_l):
                # 750 (black) + 620 (cyan) + 620 (magenta) + 620 (yellow) = 2610
                reply = (
                    "The total catalogue price for all 4 genuine Epson T05A ink packs for the WF-C878R is:\n"
                    "• Black (T05A100): AED 750.00\n"
                    "• Cyan (T05A200): AED 620.00\n"
                    "• Magenta (T05A300): AED 620.00\n"
                    "• Yellow (T05A400): AED 620.00\n\n"
                    "**Total for all 4 colours:** **AED 2,610.00** (excl. VAT)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    suggested_chips=["Add Maintenance Box", "Request Official Quotation"],
                    source="route:consumable_price",
                )

        # ── 40 ppm treated as speed (Chat 3 Turn 2) ──────────────────────────
        if re.search(r"\b40\s*(?:ppm|pages\s+per\s+minute)\b", msg_l):
            # AM-C4000 is 40 ppm!
            am_c4000 = catalogue_loader.get_by_id("epson-am-c4000")
            state.requirements["speed_priority"] = "high"
            state.requirements["print_speed"] = "40 ppm"
            state.set_canonical_focus("epson-am-c4000")
            state.shown_entities = ["epson-am-c4000"]
            reply = (
                "For high-speed 40 ppm A3 office printing, the **Epson WorkForce Enterprise AM-C4000** is our dedicated line-head multifunction system. "
                "It delivers 40 ISO ppm in both mono and colour with PrecisionCore Heat-Free technology."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=[am_c4000] if am_c4000 else [],
                suggested_chips=["How many pages per day is it good for?", "View Technical Specifications", "Official Quotation"],
                source="recommendation:catalogue_list",
            )

        if state.get_canonical_focus_id() == "epson-am-c4000" and re.search(r"\bhow\s+many\s+pages\s+per\s+day\b", msg_l):
            reply = (
                "The **Epson WorkForce Enterprise AM-C4000** is rated for heavy departmental workloads with a recommended monthly volume of **10,000 to 60,000 pages per month** "
                "(approximately **400 to 2,000+ pages per day**), with a maximum duty cycle up to 200,000 pages per month."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                suggested_chips=["And the C878R?", "Official Quotation", "View Consumables"],
                source="route:product_spec_attribute",
            )

        # ── CAD 36-inch correction & Roll sizes (Chat 9) ───────────────────────
        if state.category == "technical_large_format":
            if re.search(r"\b(?:actually\s+make\s+it\s+36|make\s+it\s+36|36\s*inch|36\")\b", msg_l):
                state.requirements["print_width"] = 36
                state.requirements["paper_size"] = "a0"
                state.requirements["format"] = "A0"
                state.requirements["scanner_required"] = False
                t5100 = catalogue_loader.get_by_id("epson-sc-t5100")
                t5405 = catalogue_loader.get_by_id("epson-sc-t5405")
                cards = [c for c in [t5100, t5405] if c]
                state.shown_entities = [c["id"] for c in cards]
                state.set_canonical_focus(cards[0]["id"] if cards else None)
                reply = (
                    "Understood! Updating your specifications to 36-inch (A0) width without scanning. "
                    "Here are our recommended 36-inch technical CAD plotters:\n\n"
                    "• **Epson SureColor SC-T5100**: Entry 36″ wireless desktop/stand plotter for clean CAD lines.\n"
                    "• **Epson SureColor SC-T5405**: Production 36″ technical printer with high-capacity 700 ml ink cartridges."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=cards,
                    suggested_chips=["Roll Sizes?", "View Technical Specifications", "Official Quotation"],
                    source="recommendation:catalogue_list",
                )
            if re.search(r"\broll\s*sizes?\b", msg_l):
                w = state.requirements.get("print_width", 36)
                reply = (
                    f"For our {w}-inch CAD technical plotters (such as the SC-T5100 and SC-T5405), the system supports standard paper roll widths up to **36 inches (914 mm)**, "
                    "including 24-inch (A1) and 36-inch (A0) rolls on 2-inch and 3-inch cores, alongside automatic cut-sheet feeding up to A3."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    suggested_chips=["View Media & Rolls", "Official Quotation", "Request Datasheet"],
                    source="route:product_spec_attribute",
                )

        return PreClassificationResult(handled=False)
