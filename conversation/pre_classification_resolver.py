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

        # ── GATE INTERCEPTOR: Category words vs attributes & Explicit Switches ──
        # 1. "a4 colour printer with scanner" must stay in office_printer, not scanners
        if re.search(r"\b(?:a4|a3|colour|color|office)?\s*printer\s+with\s+scann?er\b", msg_l) or \
           re.search(r"\bprinter\s+(?:that\s+has|with|having)\s+scann?er\b", msg_l):
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

        # ── Citizen photo booth 4x6 prints (Chat 18 Turn 4) ───────────────────
        if state.category == "citizen_photo" and re.search(r"\b(?:4x6|4\s*x\s*6|4\"x6\"|4\s*by\s*6)\b", msg_l):
            state.requirements["print_size"] = "4x6"
            state.requirements["print_sizes"] = ["4x6"]
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

        # ── Citizen photo booth 6x8 multi-format (Chat 6 Turn 3) ──────────────
        if state.category == "citizen_photo" and re.search(r"\b(?:6x8|6\s*x\s*8|6\"x8\"|6\s*by\s*8)\b", msg_l):
            cx02 = catalogue_loader.get_by_id("citizen-cx-02")
            cy02 = catalogue_loader.get_by_id("citizen-cy-02")
            cards = [c for c in [cx02, cy02] if c]
            state.shown_entities = [c["id"] for c in cards]
            reply = (
                "For multi-format printing including 6×8″ and 4×6″ prints, both the **Citizen CX-02** and **Citizen CY-02** support 6×8″ media:\n\n"
                "• **Citizen CX-02**: Lightweight 12 kg event printer with ribbon-rewind feature to print both 4×6″ and 6×8″ without changing media.\n"
                "• **Citizen CY-02**: High-capacity workhorse producing up to 350 6×8″ prints per roll for large-volume event photography."
            )
            return PreClassificationResult(
                handled=True,
                reply=reply,
                product_cards=cards,
                suggested_chips=["CX02 Yield?", "CY02 Yield?", "Official Quotation"],
                source="recommendation:catalogue_list",
            )

        # ── F100 paper size support inquiry (Chat 4 Turn 4) ───────────────────
        if re.search(r"\b(?:what\s+paper\s+size|paper\s+size|supported\s+paper|media\s+size|which\s+paper\s+size)\b", msg_l):
            if state.get_canonical_focus_id() == "epson-sc-f100" or "f100" in (state.shown_entities or []) or getattr(state, "active_printer_for_consumables", None) == "epson-sc-f100" or "epson-sc-f100" in (state.shown_entities or []):
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
        is_both = bool(re.search(r"\b(?:both|dono|dono\s+ka|all|these|كلاهما)\b", msg_l))
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
                p_objs = [catalogue_loader.get_by_id(pid) for pid in shown[:2]]
                p_names = [p.get("display_name") or p.get("model") or p["id"] for p in p_objs if p]
                names_str = " and ".join(f"**{n}**" for n in p_names) if p_names else "Both models"
                reply = (
                    f"Yes, {names_str} feature integrated high-speed scanning, copying, and faxing. "
                    "Both are complete multifunction (DWF) enterprise systems with automatic dual-sided document feeders (ADF)."
                )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[p for p in p_objs if p],
                    suggested_chips=["View Scan Speeds", "Official Quotation", "View Running Costs"],
                    source="route:product_spec_attribute",
                )

            # Asking specs for both
            if re.search(r"\b(?:spec|specs|specification|features|batao|details)\b", msg_l):
                p_objs = [catalogue_loader.get_by_id(pid) for pid in shown[:2]]
                lines = ["Here are the specifications for both models from our catalogue:"]
                for p in p_objs:
                    if p:
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
                    product_cards=[p for p in p_objs if p],
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
            p_name = p.get("display_name") or p.get("name") or p["id"]

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

            # If returning back to model (e.g. "back to the f100 – ink bottle size")
            if re.search(r"\bback\s+to\s+(?:the\s+)?f100\b", msg_l) or ("f100" in msg_l and "bottle" in msg_l):
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

            # If looking for consumables for a model (e.g. "i need f100 consubales", "need ink for epson c878")
            if re.search(r"\b(?:consubales|consumbales|consumable|consumables|ink|inks|cartridge|cartridges)\b", msg_l):
                state.set_canonical_focus(pid)
                state.shown_entities = [pid]
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
                    reply = (
                        f"Here are the genuine consumables for the **{p_name}**:\n\n"
                        "• **Epson DURABrite Pro Ink Packs (T05A Series)**: Available in Black (T05A100 - AED 750.00), Cyan (T05A200 - AED 620.00), Magenta (T05A300 - AED 620.00), and Yellow (T05A400 - AED 620.00).\n"
                        "• **Epson T6714 Maintenance Box (C13T671400)**: AED 195.00."
                    )
                return PreClassificationResult(
                    handled=True,
                    reply=reply,
                    product_cards=[],
                    consumable_cards=c_cards,
                    suggested_chips=["Price of Yellow Ink", "Maintenance Box", "Official Quotation"],
                    source="route:consumables:verified_list",
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
