"""
Deterministic Requirement Normalizer for Kepler Tech SalesAI.
Normalizes:
- A1 -> 24 inches (print_width: 24)
- A0 -> 36 inches (print_width: 36)
- 44-inch -> 44
- Monthly volume -> daily volume (e.g. 6,000 monthly -> 200 daily)
- "scan and copy", "multifunction", "print and scan" -> functions: ["print", "scan", "copy"], scanner_required: True
- "without scanner", "no scan", "no scanner", "print only" -> scanner_required: False
- "photo booth", "event photos", "citizen" -> category: "citizen_photo"
- "fine art", "gallery", "photography" -> category: "photography_large_format"
- "cad", "blueprint", "gis", "plotter", "architect" -> category: "technical_large_format"
- "office", "workforce", "documents", "invoices" -> category: "office_printer"
"""
import re
from typing import Dict, Any, Tuple, Optional


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

    # 1. Citizen photo check (Citizen brand is exclusively photo printers)
    if any(k in text_l for k in [
        "citizen", "photo booth", "photobooth", "event photo", "event photos",
        "cz-01", "cx-02", "cy-02", "cx-02w"
    ]):
        return "citizen_photo"

    # Dye-sublimation desktop (SC-F100) - merchandise, textiles, mugs, promotional
    if any(k in text_l for k in ["f100", "sc-f100", "sc f100"]) or (
        any(k in text_l for k in ["sublimation", "dye-sub", "dye sub"])
        and any(k in text_l for k in ["textile", "mug", "fabric", "merchandise", "apparel", "t-shirt", "promotional", "desktop sublimation"])
    ):
        return "dye_sublimation"

    if any(k in text_l for k in ["dye sub", "dyesub", "dye-sub", "dye-sublimation"]):
        return "citizen_photo"

    # 2. Technical / CAD check
    if any(k in text_l for k in [
        "cad", "blueprint", "blueprints", "plotter", "plotters", "architect", "architectural",
        "engineering drawing", "engineering drawings", "gis", "sc-t", "t3100", "t3700",
        "t5100", "t5400", "t5405", "t5700", "t7700", "technical printer", "technical printers"
    ]):
        return "technical_large_format"

    # 3. Photography / Fine Art check
    if any(k in text_l for k in [
        "fine art", "fine-art", "gallery", "photo printer", "photo printers",
        "photography", "photograph", "photographs", "photographer",
        "professional photo", "portrait photo", "portrait printing", "production photo",
        "sc-p", "p700", "p900", "p5300", "p6500", "p7500", "p8500", "p9500", "p20500"
    ]) or ("photo" in text_l and any(k in text_l for k in ["desktop", "gallery", "portrait", "fine art", "commercial", "poster", "posters", "production"])) or (
        bool(re.search(r"\b(?:large\s+format|wide\s+format)\b", text_l)) and current_category in ("citizen_photo", "office_printer")
    ):
        return "photography_large_format"

    # 4. Office Printer check
    if any(k in text_l for k in [
        "office", "workforce", "copier", "copiers", "enterprise mfp",
        "a4 printer", "a3 printer", "a4 colour", "a4 color", "a3 colour", "a3 color",
        "a4 multifunction", "a3 multifunction",
        "am-c400", "am-c550", "am-c4000", "am-c5000", "am-c6000",
        "wf-c5890", "wf-c878", "wf-c879", "wf-c21000", "em-c800"
    ]) or (not current_category and bool(re.search(r"\b(?:a4|a3)\b", text_l)) and not bool(re.search(r"\ba3\+", text_l))):
        return "office_printer"

    return current_category


def extract_deterministic_requirements(text: str, category: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts and normalizes requirements and corrections deterministically.
    Returns (requirements, corrections).
    """
    text_l = (text or "").lower().strip().replace("×", "x")
    reqs: Dict[str, Any] = {}
    corrections: Dict[str, Any] = {}

    is_correction = any(w in text_l for w in ["actually", "instead", "changed my mind", "correction", "i meant", "no scanner needed"])

    # ── 1. Scanner & Function Normalization ────────────────────────────────
    # Check explicit negation first!
    scanner_negated = bool(
        re.search(r"\b(?:do\s+not\s+need|don'?t\s+need|no\s+need\s+for|without|no|not)\b.*?\b(?:scanner|scanning|scan)\b", text_l)
        or re.search(r"\b(?:scanning|scanner)\s+(?:is\s+)?not\s+(?:needed|required)\b", text_l)
        or any(neg in text_l for neg in [
            "without scanner", "no scanner", "not scanner", "don't need scanner", 
            "dont need scanner", "print only", "printer only", "only print", 
            "only printer", "printing only", "no scan", "no scanning", "just print", "just printer",
            "only need printing", "only need print"
        ])
    )

    if scanner_negated:
        reqs["scanner_required"] = False
        reqs["functions"] = ["print"]
        if is_correction:
            corrections["scanner_required"] = False
            corrections["functions"] = ["print"]

    elif bool(
        re.search(r"\b(?:need\s+to\s+scan|need\s+(?:a\s+)?scanner|need\s+scanning|scanner\s+(?:integrated|required)|integrated\s+scanner|with\s+(?:an?\s+)?integrated\s+scanner)\b", text_l)
        or any(pos in text_l for pos in [
            "with scanner", "need scanner", "need a scanner", "scanner required", "built-in scan",
            "integrated scan", "scanner integrated", "scanning as well", "scan as well", "multifunction", "mfp",
            "scan and copy", "print and scan", "printing and scanning", "copy and scan",
            "print, scan and copy", "printing, scanning and copying", "make copies"
        ])
    ):
        reqs["scanner_required"] = True
        reqs["functions"] = ["print", "scan", "copy"]
        if is_correction:
            corrections["scanner_required"] = True
            corrections["functions"] = ["print", "scan", "copy"]

    # ── 2. Paper Size & Print Width Normalization ─────────────────────────
    # A0 -> 36 inches
    if re.search(r"\b(?:a0|36[\s-]*(?:inch|in|\")|36inch)\b", text_l):
        reqs["print_width"] = 36
        reqs["paper_size"] = "a0"
        if is_correction:
            corrections["print_width"] = 36
            corrections["paper_size"] = "a0"
    # A1 -> 24 inches
    elif re.search(r"\b(?:a1|24[\s-]*(?:inch|in|\")|24inch)\b", text_l):
        reqs["print_width"] = 24
        reqs["paper_size"] = "a1"
        if is_correction:
            corrections["print_width"] = 24
            corrections["paper_size"] = "a1"
    # 44-inch -> 44
    elif re.search(r"\b(?:44[\s-]*(?:inch|in|\")|44inch)\b", text_l):
        reqs["print_width"] = 44
        reqs["paper_size"] = "44-inch"
        if is_correction:
            corrections["print_width"] = 44
    # 64-inch
    elif re.search(r"\b(?:64[\s-]*(?:inch|in|\")|64inch)\b", text_l):
        reqs["print_width"] = 64
        reqs["paper_size"] = "64-inch"
    # 13-inch (A3+)
    elif re.search(r"\b(?:13[\s-]*(?:inch|in|\")|13inch|a3\+)", text_l):
        reqs["print_width"] = 13
        reqs["paper_size"] = "a3+"
    # 17-inch (A2+)
    elif re.search(r"\b(?:17[\s-]*(?:inch|in|\")|17inch|a2\+)", text_l):
        reqs["print_width"] = 17
        reqs["paper_size"] = "a2"
    # A3
    elif re.search(r"\b(?:a3|tabloid|ledger)\b", text_l):
        reqs["paper_size"] = "a3"
    # A4
    elif re.search(r"\b(?:a4|standard\s*a4)\b", text_l):
        reqs["paper_size"] = "a4"

    # Photo sizes (Citizen / Photo)
    photo_sizes = []
    if re.search(r"\b(?:4x4|4\.5x4\.5|4\.5x8)\b", text_l):
        photo_sizes.append("4x4")
    if re.search(r"\b4x6\b", text_l):
        photo_sizes.append("4x6")
    if re.search(r"\b5x7\b", text_l):
        photo_sizes.append("5x7")
    if re.search(r"\b6x8\b", text_l):
        photo_sizes.append("6x8")
    if re.search(r"\b8x10\b", text_l):
        photo_sizes.append("8x10")
    if re.search(r"\b8x12\b", text_l):
        photo_sizes.append("8x12")
    if photo_sizes:
        reqs["print_sizes"] = list(set(photo_sizes))

    # ── 3. Volume Normalization (Monthly -> Daily) ────────────────────────
    # Check for monthly volume (e.g., 1,200 monthly -> 40 daily)
    monthly_match = re.search(r"(\d[\d,\s]*)\s*[^.\n,]*?\b(?:per\s*month|a\s*month|monthly|/month|every\s*month)\b", text_l)
    if monthly_match:
        raw_num = monthly_match.group(1).replace(",", "").replace(" ", "")
        try:
            val = int(raw_num)
            reqs["monthly_volume"] = val
            daily = max(1, val // 30)
            reqs["daily_volume"] = daily
            if is_correction:
                corrections["daily_volume"] = daily
        except ValueError:
            pass

    # Check for daily volume
    if "daily_volume" not in reqs:
        daily_patterns = [
            r"(?:daily\s+volume|volume\s+daily|volume\s+per\s+day|volume\s+is|expect|produce|process|print)\s*(?:is\s+)?(?:approximately|around|about|~|more\s+than)?\s*(\d[\d,\s]*)\s*(?:pages?|drawings?|prints?|photos?|photographs?|plans?|docs?)?\s*(?:per\s*day|a\s*day|every\s*day|daily|/day|per\s*event)",
            r"(\d[\d,\s]*)\s*(?:pages?|drawings?|prints?|photos?|photographs?|plans?|docs?)?\s*(?:per\s*day|a\s*day|every\s*day|daily|/day|per\s*event)",
            r"(?:around|about|approx|approximately|~|more\s+than)\s*(\d[\d,\s]*)\s*(?:pages?|drawings?|prints?|photos?|photographs?|plans?|docs?)\s*(?:a\s*day|per\s*day|every\s*day|daily|per\s*event)?",
        ]
        for pat in daily_patterns:
            daily_match = re.search(pat, text_l)
            if daily_match:
                raw_num = daily_match.group(1).replace(",", "").replace(" ", "")
                try:
                    daily = int(raw_num)
                    is_width = bool(re.search(rf"\b{daily}[\s-]*(?:inch|in|\")", text_l))
                    if not is_width:
                        reqs["daily_volume"] = daily
                        if is_correction:
                            corrections["daily_volume"] = daily
                        break
                except ValueError:
                    pass

    # Check for bare numbers or ranges (e.g. "20", "30", "20 to 30", "20-30", "around 50")
    if "daily_volume" not in reqs:
        range_match = re.search(r"\b(\d+)\s*(?:to|-|–)\s*(\d+)\b", text_l)
        if range_match:
            try:
                n1 = int(range_match.group(1))
                n2 = int(range_match.group(2))
                avg_val = (n1 + n2) // 2
                reqs["daily_volume"] = avg_val
                if is_correction:
                    corrections["daily_volume"] = avg_val
            except ValueError:
                pass
        else:
            # If the user message is concise (<= 5 words) and contains a number
            if len(text_l.split()) <= 5:
                single_match = re.search(r"\b(\d+)\b", text_l)
                if single_match:
                    try:
                        n = int(single_match.group(1))
                        # Never treat width dimensions (e.g. 36-inch, 24") as volume
                        is_width = bool(re.search(rf"\b{n}[\s-]*(?:inch|in|\")", text_l))
                        if not is_width:
                            if n not in (13, 17, 24, 36, 44, 64) or bool(re.search(r"\b(?:pages?|prints?|drawings?|docs?|photos?)\b", text_l)) or len(text_l.split()) <= 2:
                                reqs["daily_volume"] = n
                                if is_correction:
                                    corrections["daily_volume"] = n
                    except ValueError:
                        pass

    # ── 4. Colour Mode ───────────────────────────────────────────────────
    if any(k in text_l for k in ["monochrome", "mono", "black and white", "b&w", "black & white"]):
        reqs["colour_mode"] = "monochrome"
    elif any(k in text_l for k in ["colour", "color", "full colour", "full color"]):
        reqs["colour_mode"] = "colour"
    else:
        # Default for the 41 catalog products is colour (all 41 approved catalogue entries are colour printers)
        if category == "office_printer" and not is_correction and not reqs.get("colour_mode"):
            reqs["colour_mode"] = "colour"

    # ── 5. Application ───────────────────────────────────────────────────
    if any(k in text_l for k in ["cad", "blueprint", "engineering", "architect", "gis", "technical", "drawings", "plans"]):
        reqs["application"] = "cad"
    elif any(k in text_l for k in ["photo booth", "booth", "event photo", "events", "mobile photo booth"]):
        reqs["application"] = "photo_booth"
        reqs["usage_environment"] = "photo_booth"
    elif any(k in text_l for k in ["fine art", "gallery", "exhibition", "photography", "photographs", "portrait"]):
        reqs["application"] = "fine_art"
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

    # ── 7. Explicit Product Line Normalization ───────────────────────────
    # A. Explicit corrections & contrast (e.g. "I said WorkForce Pro, not Enterprise")
    if re.search(r"\b(?:said\s+)?workforce\s+pro\b.*?\b(?:not\s+enterprise|instead\s+of\s+enterprise)\b", text_l) or \
       re.search(r"\bpro\b.*?\b(?:not\s+enterprise|instead\s+of\s+enterprise)\b", text_l):
        reqs["product_line"] = "workforce_pro"
        corrections["product_line"] = "workforce_pro"
    elif re.search(r"\b(?:said\s+)?workforce\s+enterprise\b.*?\b(?:not\s+pro|instead\s+of\s+pro)\b", text_l) or \
         re.search(r"\benterprise\b.*?\b(?:not\s+pro|instead\s+of\s+pro)\b", text_l):
        reqs["product_line"] = "workforce_enterprise"
        corrections["product_line"] = "workforce_enterprise"

    # B. Explicitly unspecified / indifferent (e.g. "I don't care whether it is Pro or Enterprise")
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

    return reqs, corrections


class RequirementNormalizer:
    @staticmethod
    def normalize(text: str, category: Optional[str] = None) -> Dict[str, Any]:
        reqs, _ = extract_deterministic_requirements(text, category)
        return reqs

    @staticmethod
    def extract_requirements(text: str, category: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return extract_deterministic_requirements(text, category)

    @staticmethod
    def normalize_category(raw_text: str, current_category: Optional[str] = None) -> Optional[str]:
        return normalize_category(raw_text, current_category)


normalizer = RequirementNormalizer()
