"""
Deterministic Requirement Normalizer for Kepler Tech SalesAI.
Normalizes:
- A1 -> 24 inches (print_width: 24)
- A0 -> 36 inches (print_width: 36)
- 44-inch -> 44
- Monthly volume -> daily volume (e.g. 5,000 monthly -> 200 daily)
- "scan and copy", "multifunction", "print and scan" -> functions: ["print", "scan", "copy"], scanner_required: True
- "without scanner", "no scan", "no scanner", "print only" -> scanner_required: False
- "photo booth", "event photos", "citizen" -> category: "citizen_photo"
- "fine art", "gallery", "photography" -> category: "photography_large_format"
- "cad", "blueprint", "gis", "plotter", "architect" -> category: "technical_large_format"
- "office", "workforce", "documents", "invoices" -> category: "office_printer"
"""
import re
from typing import Dict, Any, Tuple, Optional
from conversation.contextual_slot_resolver import ContextualSlotResolver
from conversation.canonical_entity_normalizer import CanonicalEntityNormalizer


def normalize_category(raw_text: str, current_category: Optional[str] = None) -> Optional[str]:
    """Deterministically identifies or switches product category."""
    text_l = (raw_text or "").lower()

    # 0. Explicit size/model based overrides
    # 64-inch is exclusively Photography Large Format (Epson SC-P20500)
    if bool(re.search(r"\b(?:64[\s-]*(?:inch|in|\")|64inch)\b", text_l)):
        return "photography_large_format"

    # 13-inch (A3+) and 17-inch (A2+) are exclusively Photography Large Format
    if any(k in text_l for k in [
        "13-inch", "13 inch", "13in", "13\"", "13inch",
        "17-inch", "17 inch", "17in", "17\"", "17inch",
        "a2+ printer", "a2 plus printer", "a3+ photo", "a2+ photo"
    ]):
        return "photography_large_format"

    # 1. Citizen photo check (Citizen brand is exclusively direct dye-sub/thermal photo printers)
    if any(k in text_l for k in [
        "citizen", "photo booth", "photobooth", "event photo", "event photos",
        "cz-01", "cx-02", "cy-02", "cx-02w"
    ]) or (
        any(k in text_l for k in ["dye sub", "dyesub", "dye-sub", "dye-sublimation"])
        and any(k in text_l for k in ["photo", "photos", "kiosk", "booth", "event", "4x6", "6x8", "8x10", "8x12"])
    ) or (
        # Bare "event" or "events" echoing the chip label — only when not already a different category
        bool(re.search(r"\bevents?\b", text_l))
        and current_category not in ("office_printer", "photography_large_format", "technical_large_format", "dye_sublimation")
    ):
        if current_category in ("photography_large_format", "photo_printer", "photo"):
            return current_category
        return "citizen_photo"

    # 2. Dye-sublimation / T-Shirt / Merchandise printers (SC-F100, SC-F500)
    if any(k in text_l for k in [
        "f100", "sc-f100", "sc f100", "f500", "sc-f500", "sc f500",
        "sublimation", "dye-sublimation", "dye sublimation",
        "t-shirt printing", "t shirt printing", "tshirt printing",
        "t-shirt printer", "t shirt printer", "tshirt printer",
        "t-shirts printer", "t shirts printer", "tshirts printer",
        "mug printing", "mugs printing", "jersey printing",
        "textile sublimation", "fabric sublimation", "apparel sublimation",
    ]) or (
        any(k in text_l for k in ["dye sub", "dyesub", "dye-sub"])
    ) or (
        any(k in text_l for k in ["t-shirt", "t shirt", "tshirt", "t-shirts", "tshirts"])
        and any(k in text_l for k in ["print", "printer", "printing", "transfer"])
    ) or (
        any(k in text_l for k in ["mug", "mugs", "merchandise", "promotional items"])
        and any(k in text_l for k in ["printer", "printers", "printing", "sublimation"])
    ) or (
        # Bare single-word echoes of the chip label — only safe when no category is set yet
        any(k in text_l for k in ["merchandise", "mugs", "t-shirts", "t shirts", "tshirts"])
        and not current_category
    ):
        return "dye_sublimation"

    # 3. Technical / CAD / Plotters (including common typos like 'plottaer')
    # Also matches single-word user replies that mirror the category question wording
    if any(k in text_l for k in [
        "cad", "cad drawing", "cad drawings",
        "blueprint", "blueprints",
        "plotter", "plotters", "plottaer", "plottaers", "platter",
        "architect", "architectural", "architecture",
        "engineering drawing", "engineering drawings", "engineering",
        "gis", "maps",
        "sc-t", "t3100", "t3700", "t5100", "t5400", "t5405", "t5700", "t7700",
        "technical printer", "technical printers", "technical large format",
        "technical cad", "technical cad plotters",
    ]) or (
        # "technical" or "drawings" alone, only when not already set to another category
        bool(re.search(r"\b(?:technical|drawings?)\b", text_l))
        and current_category not in ("office_printer", "photography_large_format", "citizen_photo", "dye_sublimation")
    ):
        return "technical_large_format"

    # 4. Large-Format / Photo check
    # Also matches single-word replies from the category question ("professional", "photographs")
    if any(k in text_l for k in [
        "surecolor", "fine art", "fine-art",
        "canvas", "canvas printer", "canvas printing", "print on canvas",
        "photo printer", "photo printers",
        "photo printing", "fine art printer", "gallery printer",
        "photographs", "photograph", "photography",
        "photo printers (fine art & photo booth)", "photo printer (fine art & photo booth)",
        "professional photographs", "professional photo", "professional photography",
        "portraits", "portrait",
        "sc-p", "p700", "p900", "p5300", "p6500", "p7500", "p8500", "p9500", "p20500",
        "professional photography & fine art",
    ]) or (
        # "professional" alone (echoing chip wording) or bare "photograph(s)"
        bool(re.search(r"\b(?:professional|photographs?|photography)\b", text_l))
        and current_category not in ("office_printer", "technical_large_format", "citizen_photo", "dye_sublimation")
    ) or (
        "photo" in text_l and any(k in text_l for k in ["desktop", "gallery", "portrait", "fine art", "commercial", "poster", "posters", "production"])
    ) or (
        bool(re.search(r"\b(?:large\s+format|wide\s+format)\b", text_l))
        and not bool(re.search(r"\b(?:a3|office|workforce|copier|cad|plotter)\b", text_l))
        and current_category not in ("office_printer", "technical_large_format")
    ):
        return "photography_large_format"

    # 5. Office / Business Printer check (including A3 / A4 office printers)
    # Also matches "documents", "office", "business" echoed back from the category question
    if any(k in text_l for k in [
        "office", "workforce", "copier", "copiers", "enterprise mfp",
        "business printer", "business printers", "business printing", "business mfp", "business machine",
        "a4 printer", "a3 printer", "a4 colour", "a4 color", "a3 colour", "a3 color",
        "a4 multifunction", "a3 multifunction", "a3 or a4", "a4 or a3", "a3 and a4", "a4 and a3",
        "am-c400", "am-c550", "am-c4000", "am-c5000", "am-c6000",
        "wf-c5890", "wf-c878", "wf-c879", "wf-c21000", "em-c800",
        "office & business documents (a3 / a4)",
    ]) or (
        bool(re.search(r"\bbusiness\b", text_l))
        and any(k in text_l for k in ["printer", "printers", "printing", "document", "documents", "invoices", "office"])
    ) or (
        # Bare "documents" echoing the chip label
        bool(re.search(r"\bdocuments?\b", text_l))
        and current_category not in ("technical_large_format", "photography_large_format", "citizen_photo", "dye_sublimation")
    ) or (
        not current_category and bool(re.search(r"\b(?:a4|a3)\b", text_l)) and not bool(re.search(r"\ba3\+", text_l))
    ):
        return "office_printer"

    return current_category


def extract_deterministic_requirements(text: str, category: Optional[str] = None, awaiting_field: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts and normalizes requirements and corrections deterministically.
    Returns (requirements, corrections).
    """
    text_l = (text or "").lower().strip().replace("×", "x")
    reqs: Dict[str, Any] = {}
    corrections: Dict[str, Any] = {}

    is_correction = CanonicalEntityNormalizer.is_correction(text_l)

    # ── 0. Contextual Slot Resolution ─────────────────────────────────────
    if awaiting_field:
        c_reqs, c_corrs = ContextualSlotResolver.resolve(
            text=text,
            awaiting_field=awaiting_field,
            category=category
        )
        reqs.update(c_reqs)
        corrections.update(c_corrs)

    # ── 1. Scanner & Function Normalization ────────────────────────────────
    if "scanner_required" not in reqs:
        scan_dict = CanonicalEntityNormalizer.normalize_scanner_function(text_l)
        if scan_dict:
            reqs.update(scan_dict)
            if is_correction:
                corrections.update(scan_dict)

    # ── 2. Paper Size & Print Width Normalization ─────────────────────────
    dim_dict = CanonicalEntityNormalizer.normalize_dimensions(text_l, category)
    if dim_dict:
        reqs.update(dim_dict)
        if is_correction:
            corrections.update(dim_dict)

    # Ribbon rewind / no media loss / single paper roll
    if any(k in text_l for k in [
        "without media loss", "with out media loss", "no media loss", "zero media loss",
        "save media", "ribbon rewind", "media loss", "without waste", "without paper waste",
        "single paper roll", "single roll"
    ]):
        reqs["ribbon_rewind"] = True
        if is_correction:
            corrections["ribbon_rewind"] = True

    # ── 3. Volume Normalization (Monthly & Daily) ─────────────────────────
    if "daily_volume" not in reqs:
        vol_dict = CanonicalEntityNormalizer.normalize_volume(text_l)
        if vol_dict:
            reqs.update(vol_dict)
            if is_correction:
                corrections.update(vol_dict)

    # ── 4. Colour Mode ───────────────────────────────────────────────────
    if any(k in text_l for k in ["monochrome", "mono", "black and white", "b&w", "black & white"]):
        reqs["colour_mode"] = "monochrome"
        if is_correction:
            corrections["colour_mode"] = "monochrome"
    elif any(k in text_l for k in ["colour", "color", "full colour", "full color"]):
        reqs["colour_mode"] = "colour"
        if is_correction:
            corrections["colour_mode"] = "colour"
    else:
        if category == "office_printer" and not is_correction and not reqs.get("colour_mode"):
            reqs["colour_mode"] = "colour"

    # ── 5. Application ───────────────────────────────────────────────────
    if any(k in text_l for k in ["cad", "blueprint", "engineering", "architect", "gis", "technical", "drawings", "plans", "plotter", "plotters", "plottaer", "plottaers"]):
        reqs["application"] = "cad"
    elif any(k in text_l for k in ["photo booth", "booth", "event photo", "events", "mobile photo booth"]):
        reqs["application"] = "photo_booth"
        reqs["usage_environment"] = "photo_booth"
    elif any(k in text_l for k in ["fine art", "gallery", "exhibition", "canvas", "canvas printing"]):
        reqs["application"] = "canvas" if "canvas" in text_l else "fine_art"
        if "canvas" in text_l:
            reqs["photo_form_factor"] = "large"
    elif any(k in text_l for k in ["t-shirt", "t shirt", "tshirt", "tshirts", "t-shirts", "jersey", "jerseys", "apparel", "garment"]):
        reqs["application"] = "t_shirt_printing"
    elif any(k in text_l for k in ["mug", "mugs", "phone cover", "phone cases", "custom gift", "promotional merchandise"]):
        reqs["application"] = "promotional_merchandise"
    elif any(k in text_l for k in ["sublimation", "dye-sub", "dye sub"]):
        reqs["application"] = "dye_sublimation"
    elif any(k in text_l for k in ["kiosk", "unattended", "retail kiosk", "unattended retail kiosk"]):
        reqs["usage_environment"] = "retail_kiosk"
    elif any(k in text_l for k in ["studio portrait", "portrait studio", "studio", "studio portraiture"]):
        reqs["usage_environment"] = "studio"

    # ── 6. Roll and Spectro Configurations ───────────────────────────────
    if any(k in text_l for k in ["roll adapter", "roll media", "panoramic", "roll printing"]):
        reqs["roll_printing_required"] = True
    if any(k in text_l for k in ["spectro", "spectrophotometer", "colour calibration", "color calibration"]):
        reqs["spectro_required"] = True
    if any(k in text_l for k in ["dual roll", "two rolls", "dual-roll"]):
        reqs["dual_roll_required"] = True
    if any(k in text_l for k in ["high capacity", "high media capacity", "fixed kiosk", "more than 700", "700 prints"]):
        reqs["high_capacity_required"] = True

    # ── 6b. Photo Form Factor & Brand Normalization ──────────────────────
    if category in ("photography_large_format", "photo_printer", "photo", "citizen_photo", None):
        if any(k in text_l for k in [
            "compact (desktop / portable)", "compact desktop", "compact portable", "compact",
            "desktop", "portable", "small format", "smaller format"
        ]):
            reqs["photo_form_factor"] = "compact"
            if is_correction:
                corrections["photo_form_factor"] = "compact"
        elif any(k in text_l for k in [
            "large format (24″ to 64″)", "large format (24\" to 64\")", "large format (24 to 64)",
            "large format", "large-format", "wide format", "wide-format"
        ]) or (
            category in ("photography_large_format", "photo_printer", "photo") and bool(re.search(r"\blarge\b", text_l)) and not any(k in text_l for k in ["a3", "office", "cad", "technical"])
        ) or (
            reqs.get("print_width") in (24, 44, 64) and category in ("photography_large_format", "citizen_photo", None)
        ):
            reqs["photo_form_factor"] = "large"
            if is_correction:
                corrections["photo_form_factor"] = "large"

        # Width-driven form factor and brand defaults for photography
        if reqs.get("print_width") in (13, 17):
            reqs["photo_form_factor"] = "compact"
            reqs["photo_brand"] = "epson"
            reqs["brand"] = "Epson"
            if is_correction:
                corrections["photo_form_factor"] = "compact"
                corrections["photo_brand"] = "epson"
                corrections["brand"] = "Epson"

    if any(k in text_l for k in [
        "epson desktop (fine art / a3+ / a2+)", "epson desktop", "epson fine art", "epson photo",
        "epson", "fine art", "a3+", "a2+"
    ]):
        reqs["photo_brand"] = "epson"
        reqs["brand"] = "Epson"
        if is_correction:
            corrections["photo_brand"] = "epson"
            corrections["brand"] = "Epson"
    elif any(k in text_l for k in [
        "citizen (photo booth / events)", "citizen photo", "citizen", "photo booth",
        "event photo", "event photography", "instant photo", "dye-sub photo"
    ]) or (
        "portable" in text_l and not any(k in text_l for k in ["desktop", "compact", "fine art", "a3+", "a2+", "gallery", "canvas", "p700", "p900"])
    ) or (
        bool(reqs.get("print_sizes")) and not any(k in text_l for k in ["epson", "fine art", "a3+", "a2+", "p700", "p900"])
    ):
        reqs["photo_brand"] = "citizen"
        reqs["brand"] = "Citizen"
        if is_correction:
            corrections["photo_brand"] = "citizen"
            corrections["brand"] = "Citizen"

    # ── 7. Explicit Product Line Normalization ───────────────────────────
    # A. Explicit corrections & contrast
    if re.search(r"\b(?:said\s+)?workforce\s+pro\b.*?\b(?:not\s+enterprise|instead\s+of\s+enterprise)\b", text_l) or \
       re.search(r"\bpro\b.*?\b(?:not\s+enterprise|instead\s+of\s+enterprise)\b", text_l):
        reqs["product_line"] = "workforce_pro"
        corrections["product_line"] = "workforce_pro"
    elif re.search(r"\b(?:said\s+)?workforce\s+enterprise\b.*?\b(?:not\s+pro|instead\s+of\s+pro)\b", text_l) or \
         re.search(r"\benterprise\b.*?\b(?:not\s+pro|instead\s+of\s+pro)\b", text_l):
        reqs["product_line"] = "workforce_enterprise"
        corrections["product_line"] = "workforce_enterprise"

    # B. Explicitly unspecified / indifferent
    elif any(k in text_l for k in [
        "don't care whether it is pro or enterprise",
        "dont care whether it is pro or enterprise",
        "don't care whether pro or enterprise",
        "dont care whether pro or enterprise",
        "don't mind whether pro or enterprise",
        "dont mind whether pro or enterprise",
        "either pro or enterprise",
        "pro or enterprise",
        "any series",
        "any product line",
        "no preference on series"
    ]):
        reqs["product_line"] = "unspecified"
        if is_correction:
            corrections["product_line"] = "unspecified"

    # C. WorkForce Pro
    elif (any(k in text_l for k in ["workforce pro", "pro model", "pro models", "pro series", "wf-c878", "wf-c879", "wf-c5890", "em-c800"]) or
          bool(re.search(r"\bworkforce\s+pro\b", text_l))) and not any(neg in text_l for neg in ["not pro", "not workforce pro", "no pro"]):
        reqs["product_line"] = "workforce_pro"
        if is_correction:
            corrections["product_line"] = "workforce_pro"

    # D. WorkForce Enterprise
    elif (any(k in text_l for k in ["workforce enterprise", "enterprise printer", "enterprise model", "enterprise models", "enterprise mfp", "enterprise series", "am-c4000", "am-c5000", "am-c6000", "wf-c21000", "am-c400", "am-c550"]) or
          bool(re.search(r"\bworkforce\s+enterprise\b", text_l))) and not any(neg in text_l for neg in ["not enterprise", "not workforce enterprise", "no enterprise"]):
        reqs["product_line"] = "workforce_enterprise"
        if is_correction:
            corrections["product_line"] = "workforce_enterprise"

    # E. SureColor T-Series
    elif any(k in text_l for k in ["surecolor t-series", "surecolor t", "t-series", "t series", "technical series", "sc-t3100", "sc-t3700", "sc-t5100", "sc-t5400", "sc-t5700", "sc-t7700"]):
        reqs["product_line"] = "surecolor_t"
        if is_correction:
            corrections["product_line"] = "surecolor_t"

    # F. SureColor P-Series
    elif any(k in text_l for k in ["surecolor p-series", "surecolor p", "p-series", "p series", "photo series", "sc-p700", "sc-p900", "sc-p5300", "sc-p6500", "sc-p7500", "sc-p8500", "sc-p9500", "sc-p20500"]):
        reqs["product_line"] = "surecolor_p"
        if is_correction:
            corrections["product_line"] = "surecolor_p"

    # G. Citizen
    elif any(k in text_l for k in ["citizen printer", "citizen photo", "cz-01", "cx-02", "cy-02", "cx-02w"]):
        reqs["product_line"] = "citizen"
        if is_correction:
            corrections["product_line"] = "citizen"

    # H. SureColor F-Series
    elif any(k in text_l for k in ["surecolor f-series", "surecolor f", "f-series", "f series", "sublimation series", "sc-f100", "sc-f500", "f100", "f500"]):
        reqs["product_line"] = "surecolor_f"
        if is_correction:
            corrections["product_line"] = "surecolor_f"

    return reqs, corrections


class RequirementNormalizer:
    @staticmethod
    def normalize(text: str, category: Optional[str] = None, awaiting_field: Optional[str] = None) -> Dict[str, Any]:
        reqs, _ = extract_deterministic_requirements(text, category, awaiting_field)
        return reqs

    @staticmethod
    def extract_requirements(text: str, category: Optional[str] = None, awaiting_field: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return extract_deterministic_requirements(text, category, awaiting_field)

    @staticmethod
    def normalize_category(raw_text: str, current_category: Optional[str] = None) -> Optional[str]:
        return normalize_category(raw_text, current_category)


normalizer = RequirementNormalizer()
