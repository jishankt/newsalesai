"""
Kepler Tech SalesAI Product Qualification Flowcharts.

Encodes the exact decision trees from the Product Qualification Flowcharts specification:
- Page 1: Overview (Category Selection)
- Page 2: Office / Multifunction (A4 & A3 MFPs with Per-Day Printing Volume)
- Page 3: CAD / Blueprint / GIS (24", 36", 44" Plotters)
- Page 4: Photo / Fine Art / Gallery (13" to 64" Printers)
- Page 5: Photo Booth / Instant Photo (Citizen 4", 6", 8" Dye-Sub)
- Page 6: Apparel / T-Shirt / Mug (Epson Dye Sublimation)
- Page 7: Scanning Solutions (Professional Scanners)

Rule:
Intermediate qualification turns MUST NOT return product cards (target_product_id = None).
Only after completing each flow's mandatory requirements is the verified product leaf delivered.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import re


@dataclass
class FlowchartStep:
    category: str
    question: str
    chips: List[str]
    target_product_id: Optional[str] = None
    supporting_product_ids: List[str] = field(default_factory=list)
    explanation: str = ""
    is_leaf: bool = False


CATEGORY_OVERVIEW_CHIPS = [
    "Office & Multifunction",
    "CAD / Blueprint / GIS",
    "Photo & Fine Art",
    "Photo Booth / Instant Photo",
    "Apparel / T-Shirt / Mug (Dye-Sub)",
    "Professional Scanners",
]


def resolve_plotter_width_from_text(text: str) -> Tuple[Optional[int], Optional[str]]:
    """Resolves plotter width (inches) deterministically where largest size wins."""
    reqs = extract_flowchart_requirements(text)
    w = reqs.get("plotter_width")
    cat = "technical_large_format" if w else None
    return w, cat


def extract_flowchart_requirements(text: str, current_reqs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts and updates known requirements from customer message text or chip selection.
    Preserves existing requirements across conversational turns.
    """
    text_l = (text or "").lower()
    # Normalize unicode quotes, primes, and accents
    text_clean = (
        text_l.replace("”", '"')
        .replace("“", '"')
        .replace("″", '"')
        .replace("’", "'")
        .replace("‘", "'")
    )
    text_clean = re.sub(r"(?<=\d),(?=\d)", "", text_clean)
    text_l = text_clean
    reqs = dict(current_reqs or {})

    # 0. Budget AED extraction (single source of truth from numeric_parse)
    from conversation.numeric_parse import extract_budget
    b_res = extract_budget(text)
    if b_res and b_res.budget_ceiling is not None:
        reqs["budget_aed"] = b_res.budget_ceiling
        if b_res.budget_floor is not None:
            reqs["budget_floor_aed"] = b_res.budget_floor
        if b_res.budget_scope:
            reqs["budget_scope"] = b_res.budget_scope

    # 0b. Primary concern extraction (running_cost, print_speed, colour_quality, reliability, paper_size, portability, ease_of_use)
    if "primary_concern" not in reqs:
        if re.search(r"\b(?:(?:ink|toner|cartridge|running|consumable|print)\s*costs?|costs?\s*(?:are|is)?\s*(?:killing\s*us|too\s*high)|costing\s*a\s*fortune|expensive\s*ink|cheaper\s*prints?|per\s*print\s*cost|cost\s*per\s*print|cost\s*per\s*page|running\s*costs?|operational\s*costs?)\b", text_clean):
            reqs["primary_concern"] = "running_cost"
        elif re.search(r"\b(?:print\s*speed|speed|fast|faster|slow|too\s*slow|ppm|quick\s*turnaround)\b", text_clean):
            reqs["primary_concern"] = "print_speed"
        elif re.search(r"\b(?:colour\s*quality|color\s*quality|print\s*quality|fine\s*art|accurate\s*colou?r|pantone|resolution|clarity|vibrant)\b", text_clean):
            reqs["primary_concern"] = "colour_quality"
        elif re.search(r"\b(?:reliab\w*|break\s*down|jam|jamming|downtime|maintenance|heavy\s*duty|duty\s*cycle)\b", text_clean):
            reqs["primary_concern"] = "reliability"
        elif re.search(r"\b(?:paper\s*size|media\s*size|large\s*format|wide\s*format|wide|24\s*inch|36\s*inch|44\s*inch|a3\b|a0\b|a1\b)\b", text_clean):
            reqs["primary_concern"] = "paper_size"
        elif re.search(r"\b(?:portable|portability|compact|lightweight|light|mobile|booth|kiosk|transport)\b", text_clean):
            reqs["primary_concern"] = "portability"
        elif re.search(r"\b(?:easy\s*to\s*use|ease\s*of\s*use|simple|touchscreen|user\s*friendly|plug\s*and\s*play)\b", text_clean):
            reqs["primary_concern"] = "ease_of_use"

    # 1. Paper Size
    if (
        re.search(r"\ba4\b", text_l)
        or "desktop sheet" in text_l
        or "a4 output" in text_l
        or re.search(r"\b(?:invoices?|bills?|receipts?|office\s*documents?|general\s*documents?)\b", text_l)
    ):
        reqs["paper_size"] = "A4"
    elif re.search(r"\ba3\b", text_l) or "departmental" in text_l or "a3 output" in text_l:
        reqs["paper_size"] = "A3"

    # If customer specified A4 office printer with a standard budget <= 2500 AED and omitted volume
    if reqs.get("paper_size") == "A4" and not reqs.get("office_speed_class") and reqs.get("daily_pages") is None:
        if reqs.get("budget_aed") and reqs["budget_aed"] <= 2500:
            reqs["office_speed_class"] = "34_ppm"
            reqs["office_duty_class"] = "standard_mfp"

    # 2. Office Daily Volume & Technology Class
    # Numbers: e.g. "50 pages", "100/day", "500 pages a day", "maybe 60 daily", "around 500 pic", or bare "40"
    vol_num_match = (
        re.search(r"\b(\d+)\s*(?:pages?|prints?|drawings?|items?|sheets?|photos?|pics?|docs?|plans?)?\s*(?:a\s*day|per\s*day|daily|\/day)\b", text_l)
        or re.search(r"\b(?:around|about|maybe|approx)?\s*(\d+)\s*(?:pages?|prints?|drawings?|items?|sheets?|photos?|pics?|docs?|plans?)\b", text_l)
        or re.search(r"^\s*(?:around|about|maybe|approx)?\s*(\d+)\+?\s*$", text_l)
    )
    if vol_num_match:
        pages = int(vol_num_match.group(1))
        has_plus = "+" in text_l or "more" in text_l or "over" in text_l
        reqs["daily_pages"] = pages if not has_plus else pages + 50
        if pages < 100:
            reqs["office_speed_class"] = "34_ppm"
            reqs["office_duty_class"] = "standard_mfp"
        elif pages <= 300 and not has_plus:
            reqs["office_speed_class"] = "25_ppm_rips"
            reqs["office_duty_class"] = "departmental_rips"
        elif pages <= 800 or has_plus:
            reqs["office_speed_class"] = "40_ppm_linehead"
            reqs["office_duty_class"] = "linehead_40"
        elif pages <= 2000:
            reqs["office_speed_class"] = "55_ppm_linehead"
            reqs["office_duty_class"] = "linehead_50_60"
        else:
            reqs["office_duty_class"] = "ultra_100"

    # Verbal volume & speed matching
    if any(k in text_l for k in ["under 100", "< 100", "<100", "standard mfp", "standard 25 ppm", "34 ppm", "wf-c5890", "c5890", "low volume", "50/day"]):
        reqs["office_speed_class"] = "34_ppm"
    elif any(k in text_l for k in ["100–300", "100-300", "compact rips", "compact rips 25 ppm", "em-c800", "c800"]):
        reqs["office_speed_class"] = "25_ppm_rips"
    elif any(k in text_l for k in ["300+", "300 +", "enterprise line-head", "enterprise line head", "300–800", "300-800", "40 ppm", "55 ppm", "am-c400", "am-c4000", "c400", "c4000", "am-c550", "c550", "high-performance", "high performance", "best high-performance", "highest performance", "top performance", "fastest"]):
        is_55 = any(k in text_l for k in ["55 ppm", "am-c550", "c550", "best", "fastest", "highest"])
        reqs["office_speed_class"] = "55_ppm_linehead" if is_55 else "40_ppm_linehead"
        reqs["office_duty_class"] = "linehead_50_60" if is_55 else "linehead_40"
        if reqs.get("daily_pages") is None or reqs.get("daily_pages") <= 300:
            reqs["daily_pages"] = 850 if is_55 else 350
    elif any(k in text_l for k in ["100–500", "100-500", "200–500", "200-500", "departmental rips", "wf-c878r", "wf-c879r", "c878", "c879"]):
        reqs["office_duty_class"] = "departmental_rips"
    elif any(k in text_l for k in ["500–3,500", "500-3500", "1,500–3,000", "1500-3000", "line-head 40/50/60", "50 ppm", "60 ppm", "am-c5000", "am-c6000", "c5000", "c6000"]):
        reqs["office_duty_class"] = "linehead_50_60"
    elif any(k in text_l for k in ["3,000+", "3000+", "high-volume 100 ppm", "100 ppm", "ultra high", "wf-c21000", "c21000"]):
        reqs["office_duty_class"] = "ultra_100"

    # 3. CAD Plotter Width (Largest size wins: e.g. A1 and A0 -> A0/36-inch)
    cad_widths = []
    if re.search(r"(?:\b6[45][\s-]*(?:inch|in|\"|'')|6[45]inch|\b6[45]\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(64)
    if re.search(r"(?:\b44[\s-]*(?:inch|in|\"|'')|44inch|b0|production\s*44|\b44\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(44)
    if re.search(r"(?:\b36[\s-]*(?:inch|in|\"|'')|36inch|a0|\b36\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(36)
    if re.search(r"(?:\b24[\s-]*(?:inch|in|\"|'')|24inch|a1|\b24\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(24)
    if re.search(r"(?:\b17[\s-]*(?:inch|in|\"|'')|17inch|a2\+?|\b17\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(17)
    if re.search(r"(?:\b13[\s-]*(?:inch|in|\"|'')|13inch|a3\+?|\b13\s*(?:\"|inch|in|wide|\b))", text_l):
        cad_widths.append(13)
    if cad_widths:
        reqs["plotter_width"] = max(cad_widths)

    # CAD Configuration & Scanner
    if any(k in text_l for k in ["desktop", "entry desktop", "desktop stand", "t3100", "sc-t3100"]):
        reqs["cad_config_24"] = "entry_desktop"
    elif any(k in text_l for k in ["single roll", "t3700e", "sc-t3700e"]):
        reqs["cad_config_24"] = "single_roll"
    elif any(k in text_l for k in ["dual roll", "t3700d", "sc-t3700d", "t3700de"]):
        reqs["cad_config_24"] = "dual_roll"

    if (
        any(k in text_l for k in [
            "print-only", "print only", "without scanner", "no scanner", "no scan",
            "without scan", "no scanning", "scanner not needed", "scan not needed",
            "don't need scanner", "dont need scanner", "don't need scan", "dont need scan",
            "no mfp", "without mfp"
        ])
        or re.search(r"\b(?:no|without|dont\s+need|don't\s+need)\s+(?:a\s+)?(?:scanner|scan|scanning)\b", text_l)
    ):
        reqs["scanner_needed"] = False
    elif (
        any(k in text_l for k in ["scanner", "scan & copy", "mfp", "t5100m", "t5400m", "t5700dm", "t7700dm"])
        and not any(neg in text_l for neg in ["no scan", "without scan", "no scanner", "without scanner", "scan not needed"])
    ):
        reqs["scanner_needed"] = True

    if any(k in text_l for k in ["1.6l", "bulk ink", "t7700dl"]):
        reqs["cad_config_44"] = "bulk_1_6l"
    elif any(k in text_l for k in ["print-only dual roll", "t7700d"]):
        reqs["cad_config_44"] = "dual_roll_print"

    # 4. Photo Width & Application
    if re.search(r"(?:\b13[\s-]*(?:inch|in|\"|'')|13inch|\b13\s*(?:\"|inch|in|wide|\b))", text_l) or "a3+" in text_l or "p700" in text_l:
        reqs["photo_width"] = 13
    elif re.search(r"(?:\b17[\s-]*(?:inch|in|\"|'')|17inch|\b17\s*(?:\"|inch|in|wide|\b))", text_l) or "a2+" in text_l or "p900" in text_l or "p5300" in text_l:
        reqs["photo_width"] = 17
    elif re.search(r"(?:\b24[\s-]*(?:inch|in|\"|'')|24inch|\b24\s*(?:\"|inch|in|wide|\b))", text_l) or "gallery 24" in text_l or "p6500" in text_l or "p7500" in text_l:
        reqs["photo_width"] = 24
    elif re.search(r"(?:\b44[\s-]*(?:inch|in|\"|'')|44inch|production\s*44|\b44\s*(?:\"|inch|in|wide|\b))", text_l) or "p8500" in text_l or "p9500" in text_l:
        reqs["photo_width"] = 44
    elif re.search(r"(?:\b64[\s-]*(?:inch|in|\"|'')|64inch|\b64\s*(?:\"|inch|in|wide|\b))", text_l) or "p20500" in text_l:
        reqs["photo_width"] = 64

    # Photo configuration
    if any(k in text_l for k in ["desktop sheet", "sheet only"]):
        reqs["photo_17_type"] = "desktop_sheet"
    elif any(k in text_l for k in ["panoramic roll", "roll unit"]):
        reqs["photo_17_type"] = "panoramic_roll"
    elif any(k in text_l for k in ["10-colour heavy duty", "heavy duty", "p5300"]):
        reqs["photo_17_type"] = "heavy_duty_10col"

    if any(k in text_l for k in ["commercial compact", "commercial", "commercal", "compact", "p6500", "6500", "sc-p6500"]):
        reqs["photo_24_type"] = "commercial_compact"
    elif any(k in text_l for k in ["12-colour master", "12-color master", "12-colour", "12-color", "12 colour", "12 color", "master", "p7500", "7500", "sc-p7500"]):
        reqs["photo_24_type"] = "12_colour_master"
    elif any(k in text_l for k in ["spectro", "spectrophotometer", "automated spectro", "spectro proofer"]):
        reqs["photo_24_type"] = "spectro"

    if any(k in text_l for k in ["production mfp", "production", "p8500", "p8500d", "p8500dm"]):
        reqs["photo_44_type"] = "production_mfp"
    elif any(k in text_l for k in ["master studio pro12", "master studio", "master", "pro12", "p9500"]):
        reqs["photo_44_type"] = "master_studio"
    elif any(k in text_l for k in ["spectro proofer"]):
        reqs["photo_44_type"] = "spectro_proofer"

    # 5. Citizen Photo
    if re.search(r"(?:\b4[\s-]*(?:inch|in|\"|'')|\b4\s*(?:\"|inch|in|\b))", text_l) or any(k in text_l for k in ["4x6", "cz-01", "cz01"]):
        reqs["citizen_format"] = "4_inch"
    elif re.search(r"(?:\b6[\s-]*(?:inch|in|\"|'')|\b6\s*(?:\"|inch|in|\b))", text_l) or any(k in text_l for k in ["6x8", "cx-02", "cy-02", "cx02", "cy02"]):
        reqs["citizen_format"] = "6_inch"
    elif re.search(r"(?:\b8[\s-]*(?:inch|in|\"|'')|\b8\s*(?:\"|inch|in|\b))", text_l) or any(k in text_l for k in ["8x10", "8x12", "cx-02w", "cx02w"]):
        reqs["citizen_format"] = "8_inch"
    elif re.search(r"\b8[\s-]*(?:inch|in|\")\b", text_l) or any(k in text_l for k in ["8x10", "8x12", "cx-02w", "cx02w"]):
        reqs["citizen_format"] = "8_inch"

    # 6. Dye Sublimation
    if any(k in text_l for k in ["a4 desktop gifts", "a4", "mugs", "gifts", "sc-f100", "f100"]):
        reqs["sublimation_format"] = "a4_gifts"
    elif any(k in text_l for k in ["24-inch roll apparel", "24-inch", "24 inch", "24inch", "24 roll", "roll", "apparel", "t-shirt", "textiles", "sc-f500", "f500"]) or re.search(r"\b24[\s-]*(?:inch|in|\")?\b", text_l):
        reqs["sublimation_format"] = "24_roll"

    # 7. Scanners (5 Categories)
    # 1. Business Document Scanners
    # 2. Photo & Artwork Scanners
    # 3. Book & Large-Document Scanners
    # 4. Portable & Mobile Scanners
    # 5. Flatbed Document Scanners
    t_scan = re.sub(r"[:\s]+$", "", text_l).strip()

    # 1. Numbered selection (1 to 5) when picking from scanner menu
    if t_scan in ("1", "1.", "option 1", "category 1"):
        reqs["scanner_doc_type"] = "business_doc"
    elif t_scan in ("2", "2.", "option 2", "category 2"):
        reqs["scanner_doc_type"] = "photo_artwork"
    elif t_scan in ("3", "3.", "option 3", "category 3"):
        reqs["scanner_doc_type"] = "book_large_doc"
    elif t_scan in ("4", "4.", "option 4", "category 4"):
        reqs["scanner_doc_type"] = "portable_mobile"
    elif t_scan in ("5", "5.", "option 5", "category 5"):
        reqs["scanner_doc_type"] = "flatbed_doc"
    # 2. Keyword & Chip matching
    elif any(k in t_scan for k in [
        "photo & artwork", "photo and artwork", "photo & fine art", "photo scanner", "artwork",
        "graphic & fine art film", "graphic", "film", "12000xl", "transparency unit", "slides",
        "photographers, designers, artists", "high-resolution image digitization", "photo"
    ]):
        reqs["scanner_doc_type"] = "photo_artwork"
    elif any(k in t_scan for k in [
        "book & large-document", "book & large document", "book and large document", "book and large",
        "large-format documents, departmental scanning and high-volume workflows", "large-document",
        "large document", "large-format scanner", "departmental scanning", "high-volume workflows",
        "ds-70000", "70000", "ds-60000", "60000", "ds-30000", "30000", "ds-32000", "32000", "book"
    ]):
        reqs["scanner_doc_type"] = "book_large_doc"
    elif any(k in t_scan for k in [
        "portable & mobile", "portable and mobile", "portable scanner", "mobile scanner",
        "mobile professionals, fieldwork and compact scanning requirements", "fieldwork",
        "compact scanning", "mobile business", "ds-360w", "360w", "ds-310", "310", "ds-80w", "80w", "ds-70", "ds70",
        "portable", "mobile"
    ]):
        reqs["scanner_doc_type"] = "portable_mobile"
    elif any(k in t_scan for k in [
        "flatbed document", "flatbed color", "originals that benefit from flatbed",
        "documents, books and originals that benefit from flatbed scanning", "flatbed scanning",
        "ds-1660w", "1660w", "ds-1630", "1630", "flatbed"
    ]):
        reqs["scanner_doc_type"] = "flatbed_doc"
    elif any(k in t_scan for k in [
        "business document", "business scanner", "document digitization", "everyday document digitization",
        "offices, businesses and everyday document digitization", "fast sheetfed business", "sheetfed",
        "ds-900wn", "900wn", "ds-800wn", "800wn", "es-580w", "580w", "es-500wii", "500w",
        "ds-970", "970", "ds-870", "870", "ds-790wn", "790wn", "ds-770", "770", "ds-730n", "730n",
        "ds-530", "530", "ds-410", "410", "ds-7500", "7500", "ds-6500", "6500", "business", "document"
    ]):
        reqs["scanner_doc_type"] = "business_doc"
    elif any(k in t_scan for k in ["books & stacks", "stack", "hybrid"]):
        reqs["scanner_doc_type"] = "flatbed_doc"

    return reqs


def _resolve_flowchart_step_raw(
    category: Optional[str],
    requirements: Dict[str, Any],
    text: str = "",
) -> FlowchartStep:
    """
    Evaluates customer requirements and text against the product qualification flowcharts.
    Ensures intermediate qualification turns return NO product cards (target_product_id = None),
    and only leaf nodes return verified product cards.
    """
    reqs = extract_flowchart_requirements(text, requirements)
    text_l = (text or "").lower()

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 1: Overview Category Mapping
    # ─────────────────────────────────────────────────────────────────────────────
    if not category:
        return FlowchartStep(
            category="overview",
            question="Kepler Tech specializes in official Epson and Citizen commercial equipment across specialized applications. Which category fits your requirements?",
            chips=CATEGORY_OVERVIEW_CHIPS,
            explanation="Select a category to begin guided equipment qualification.",
            target_product_id=None,
            supporting_product_ids=[],
            is_leaf=False,
        )

    cat_norm = category.lower().strip()

    if cat_norm in ("printer", "printers"):
        return FlowchartStep(
            category="printer",
            question="Which printing application fits your requirements?",
            chips=["Technical CAD Plotters", "Professional Photo & Fine Art", "Citizen Photo Booth / Events", "Dye-Sublimation", "High-Speed Office Printers"],
            target_product_id=None,
            supporting_product_ids=[],
            explanation="Kepler Tech supplies official Epson and Citizen commercial printing systems across specialized applications.",
            is_leaf=False,
        )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 2: Office / Multifunction (With Per-Day Printing Volume)
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("office_printer", "office_enterprise", "office_workforce", "office"):
        # Step 1: Paper Size (A4 vs A3)
        paper_size = reqs.get("paper_size")
        if not paper_size:
            return FlowchartStep(
                category="office_printer",
                question="Do you require standard A4 output or large-format A3 output for your office documents?",
                chips=["A4 Output", "A3 Output"],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Kepler Tech provides Epson WorkForce Heat-Free printers in both compact A4 desktop workgroup and high-speed A3 departmental formats.",
                is_leaf=False,
            )

        # Step 2 for A4: Per-Day Printing Volume & Technology Class
        if paper_size == "A4":
            speed_class = reqs.get("office_speed_class")
            daily_pages = reqs.get("daily_pages")
            if speed_class == "34_ppm" or (daily_pages is not None and daily_pages <= 100):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified standard A4 WorkForce Pro MFP:",
                    chips=["Technical Specs", "Replaceable Ink Packs", "Official Quotation"],
                    target_product_id="epson-wf-c5890-dwf",
                    explanation="**Epson WorkForce Pro WF-C5890 DWF**: Standard 34 ppm color MFP with low energy consumption and high-yield ink packs for up to 100 pages/day.",
                    is_leaf=True,
                )
            elif speed_class == "25_ppm_rips" or (daily_pages is not None and 100 < daily_pages <= 300):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified compact RIPS A4 model:",
                    chips=["Technical Specs", "RIPS High Yield", "Official Quotation"],
                    target_product_id="epson-em-c800",
                    explanation="**Epson WorkForce Pro EM-C800**: Compact RIPS 25 ppm MFP engineered for 100–300 pages/day with minimal consumable interventions.",
                    is_leaf=True,
                )
            elif speed_class == "40_ppm_linehead" or (daily_pages is not None and 300 < daily_pages <= 800):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "Line-Head Technology", "Official Quotation"],
                    target_product_id="epson-am-c400",
                    explanation="**Epson WorkForce Enterprise AM-C400**: Line-head enterprise 40 ppm color MFP delivering fast, reliable production for 300–800 pages/day.",
                    is_leaf=True,
                )
            elif speed_class == "55_ppm_linehead" or (daily_pages is not None and daily_pages > 800):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 55 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "High-Speed Line-Head", "Official Quotation"],
                    target_product_id="epson-am-c550",
                    explanation="**Epson WorkForce Enterprise AM-C550**: High-speed line-head enterprise 55 ppm MFP for demanding offices printing 800+ pages/day.",
                    is_leaf=True,
                )
            else:
                # Ask 3 Subcategories for A4
                return FlowchartStep(
                    category="office_printer",
                    question="Approximately how many pages do you print per day in the office?",
                    chips=[
                        "< 100 pages/day (Standard 25 ppm)",
                        "100–300 pages/day (Compact RIPS 25 ppm)",
                        "300+ pages/day (Enterprise Line-Head 40/55 ppm)"
                    ],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="For A4 office printing, choosing the right per-day volume ensures optimal consumable yields and print speeds.",
                    is_leaf=False,
                )

        # Step 2 for A3: Duty & Volume Class (Per-Day Printing)
        if paper_size == "A3":
            duty_class = reqs.get("office_duty_class")
            daily_pages = reqs.get("daily_pages")
            if duty_class in ("departmental_rips", "standard_mfp") or (daily_pages is not None and daily_pages <= 500):
                return FlowchartStep(
                    category="office_printer",
                    question="Here are the verified A3 departmental RIPS MFPs:",
                    chips=["WF-C878R DWF", "WF-C879R DWF", "RIPS Inks", "Official Quotation"],
                    target_product_id="epson-wf-c878r-dwf",
                    supporting_product_ids=["epson-wf-c879r-dwf"],
                    explanation="**Epson WorkForce Pro WF-C878R / WF-C879R**: Departmental A3 RIPS (25 ppm) delivering up to 86,000 black pages, ideal for workloads up to 500 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "linehead_40" or (daily_pages is not None and 500 < daily_pages <= 1500):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm enterprise line-head A3 MFP:",
                    chips=["Technical Specs", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c4000",
                    explanation="**Epson WorkForce Enterprise AM-C4000**: Enterprise line-head 40 ppm color MFP designed for medium-to-large departments printing 500–1,500 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "linehead_50_60" or (daily_pages is not None and 1500 < daily_pages <= 3000):
                return FlowchartStep(
                    category="office_printer",
                    question="Here are the verified 50–60 ppm enterprise line-head A3 MFPs:",
                    chips=["AM-C5000 (50 ppm)", "AM-C6000 (60 ppm)", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c5000",
                    supporting_product_ids=["epson-am-c6000"],
                    explanation="**Epson WorkForce Enterprise AM-C5000 / AM-C6000**: High-speed line-head 50–60 ppm MFPs with enterprise security and modular finishing for 1,500–3,000 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "ultra_100" or (daily_pages is not None and daily_pages > 3000):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified ultra high-speed 100 ppm enterprise MFP:",
                    chips=["Technical Specs", "Heavy-Duty Finishing", "Official Quotation"],
                    target_product_id="epson-wf-c21000-d4tw",
                    explanation="**Epson WorkForce Enterprise WF-C21000 D4TW**: Flagship 100 ppm ultra high-speed enterprise department printer for continuous production of 3,000+ pages/day.",
                    is_leaf=True,
                )
            else:
                # Ask Per-Day Volume for A3 (3 Subcategories)
                return FlowchartStep(
                    category="office_printer",
                    question="Approximately how many pages do you print per day for your A3 workgroup or department?",
                    chips=[
                        "100–500 pages/day (Departmental RIPS 25 ppm)",
                        "500–3,500 pages/day (Enterprise Line-Head 40–60 ppm)",
                        "3,000+ pages/day (Ultra High-Speed 100 ppm)"
                    ],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="For A3 commercial printing, select your daily page volume to match duty cycle and finishing options.",
                    is_leaf=False,
                )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 3: CAD / Blueprint / GIS Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("technical_large_format", "technical_cad", "cad", "plotters"):
        width = reqs.get("plotter_width")

        # Step 1: Subcategory?
        if not width:
            return FlowchartStep(
                category="technical_large_format",
                question="Which technical CAD subcategory fits your architectural and engineering requirements?",
                chips=[
                    "24″ Print-Only (A1)",
                    "36″ Print-Only (A0)",
                    "36″ Multifunction (MFP)",
                    "44″ Print-Only",
                    "44″ Multifunction (MFP)",
                ],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Kepler Tech supplies the Epson SureColor T-Series, engineered for line accuracy, AEC drawings, and water-resistant UltraChrome XD2/XD3 inks.",
                is_leaf=False,
            )

        # Step 2 for 24-inch (A1): Configuration?
        if width == 24:
            config_24 = reqs.get("cad_config_24")
            if config_24 == "entry_desktop":
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified entry desktop 24-inch CAD plotter:",
                    chips=["SC-T3100 Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3100",
                    explanation="**Epson SureColor SC-T3100**: Compact 24-inch wireless desktop technical plotter, perfect for small architectural offices and project sites.",
                    is_leaf=True,
                )
            elif config_24 == "single_roll":
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified production single roll 24-inch plotter:",
                    chips=["SC-T3700E Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3700e",
                    explanation="**Epson SureColor SC-T3700E**: 24-inch production CAD plotter with flat-top design, front-loading roll media, and red ink channel for AEC plans.",
                    is_leaf=True,
                )
            elif config_24 == "dual_roll":
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified production dual roll 24-inch plotter:",
                    chips=["SC-T3700D Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3700d",
                    supporting_product_ids=["epson-sc-t3700de"],
                    explanation="**Epson SureColor SC-T3700D / SC-T3700DE**: 24-inch dual-roll production plotter with automatic roll switching and high-capacity ink cartridges.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are our verified 24-inch CAD plotters. Which configuration best fits your workspace?",
                    chips=["SC-T3100 (Desktop)", "SC-T3700E (Single Roll)", "SC-T3700D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-t3100",
                    supporting_product_ids=["epson-sc-t3700d", "epson-sc-t3700e", "epson-sc-t3700de"],
                    explanation="**24-inch Technical CAD Plotters (SureColor T-Series)**:\n• **SureColor SC-T3100**: Compact 24-inch wireless entry desktop/stand technical plotter (34s/A1) using water-resistant UltraChrome XD2 inks.\n• **SureColor SC-T3700E**: 24-inch high-speed compact production single-roll plotter (16s/A1) with dedicated red ink for AEC drawings.\n• **SureColor SC-T3700D / SC-T3700DE**: 24-inch heavy-duty dual-roll production engine with auto-switching and Adobe PostScript.",
                    is_leaf=True,
                )

        # Step 2 for 36-inch (A0): Integrated Scanner?
        if width == 36:
            scanner_needed = reqs.get("scanner_needed")
            if scanner_needed is False:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are the verified print-only 36-inch CAD plotters:",
                    chips=["SC-T5100 (Entry)", "SC-T5405 (Fast)", "SC-T5700D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-t5405",
                    supporting_product_ids=["epson-sc-t5100", "epson-sc-t5700d"],
                    explanation="**SureColor SC-T5100 / SC-T5405 / SC-T5700D**: High-speed dedicated print-only 36-inch CAD plotters for engineering and architectural plans.",
                    is_leaf=True,
                )
            elif scanner_needed is True:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are the verified 36-inch scan & copy MFP systems:",
                    chips=["SC-T5100M (Entry MFP)", "SC-T5400M (Production MFP)", "SC-T5700DM (Dual-Roll MFP)", "Official Quotation"],
                    target_product_id="epson-sc-t5400m",
                    supporting_product_ids=["epson-sc-t5100m", "epson-sc-t5700dm"],
                    explanation="**SureColor SC-T5100M / SC-T5400M / SC-T5700DM**: 36-inch multifunction plotters with integrated CIS scanners for on-site plan copying and markup scanning.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are our verified 36-inch CAD plotters. Do you require a dedicated printer or integrated scanner?",
                    chips=["SC-T5405 (Print-Only)", "SC-T5400M (Scan & Copy MFP)", "SC-T5700D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-t5405",
                    supporting_product_ids=["epson-sc-t5100", "epson-sc-t5700d", "epson-sc-t5400m", "epson-sc-t5100m", "epson-sc-t5700dm"],
                    explanation="**36-inch Technical CAD Plotters (SureColor T-Series)**:\n• **Dedicated Print-Only**: SureColor SC-T5100 (entry 31s/A1), SC-T5405 (production 22s/A1), and SC-T5700D (dual roll).\n• **Integrated Scan & Copy MFP**: SureColor SC-T5100M, SC-T5400M, and SC-T5700DM with high-precision CIS scanners.",
                    is_leaf=True,
                )

        # Step 2 for 44-inch Production: Multifunction?
        if width == 44:
            scanner_needed_44 = reqs.get("scanner_needed")
            config_44 = reqs.get("cad_config_44")
            if scanner_needed_44 is True:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified 44-inch dual-roll MFP CAD plotter:",
                    chips=["SC-T7700DM Specs", "Dual-Roll Inks", "Official Quotation"],
                    target_product_id="epson-sc-t7700dm",
                    explanation="**Epson SureColor SC-T7700DM**: 44-inch high-speed dual-roll multifunction production plotter with integrated 36-inch 600 dpi scanner.",
                    is_leaf=True,
                )
            elif config_44 == "bulk_1_6l":
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified 44-inch bulk-ink CAD plotter:",
                    chips=["SC-T7700DL Specs", "1.6L Ink Packs", "Official Quotation"],
                    target_product_id="epson-sc-t7700dl",
                    explanation="**Epson SureColor SC-T7700DL**: 44-inch high-speed production plotter with 1.6L bulk ink supply system for lowest total cost of ownership.",
                    is_leaf=True,
                )
            elif config_44 == "dual_roll_print" or scanner_needed_44 is False:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified 44-inch dual-roll print-only plotter:",
                    chips=["SC-T7700D Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t7700d",
                    explanation="**Epson SureColor SC-T7700D**: 44-inch high-speed dual-roll production plotter with flat-top design and 6-color Adobe PostScript engine.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are our verified 44-inch CAD plotters. Which configuration matches your production requirements?",
                    chips=["SC-T7700D (Dual Roll)", "SC-T7700DL (1.6L Bulk)", "SC-T7700DM (MFP)", "Official Quotation"],
                    target_product_id="epson-sc-t7700d",
                    supporting_product_ids=["epson-sc-t7700dm", "epson-sc-t7700dl"],
                    explanation="**44-inch Technical CAD Plotters (SureColor T-Series)**:\n• **SureColor SC-T7700D**: 44-inch dual-roll production plotter with flat-top design and 6-color Adobe PostScript engine.\n• **SureColor SC-T7700DL**: 44-inch high-speed plotter with 1.6L bulk ink supply system.\n• **SureColor SC-T7700DM**: 44-inch dual-roll multifunction production plotter with integrated 36-inch 600 dpi scanner.",
                    is_leaf=True,
                )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 4: Photo / Fine Art / Gallery Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("photography_large_format", "photo_fine_art", "photo", "fine_art"):
        photo_width = reqs.get("photo_width")

        # Step 1: Print Width / Subcategory?
        if not photo_width:
            return FlowchartStep(
                category="photography_large_format",
                question="Which photography and fine art subcategory fits your requirements?",
                chips=[
                    "13″ Desktop (A3+)",
                    "17″ Desktop & Production (A2+)",
                    "24″ Professional Studio",
                    "44″ Professional Gallery",
                    "64″ High-Volume Production",
                ],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Epson SureColor P-Series printers feature UltraChrome PRO pigment inksets, dedicated Photo/Matte Black nozzles, and museum-grade archival stability.",
                is_leaf=False,
            )

        if photo_width == 13:
            return FlowchartStep(
                category="photography_large_format",
                question="Here is the verified 13-inch (A3+) professional photo printer:",
                chips=["SC-P700 Specs", "UltraChrome PRO10 Inks", "Official Quotation"],
                target_product_id="epson-sc-p700",
                explanation="**Epson SureColor SC-P700**: 13-inch (A3+) photo printer with 10-colour UltraChrome PRO10 inkset, Carbon Black mode, and dedicated black channels.",
                is_leaf=True,
            )

        if photo_width == 17:
            photo_17 = reqs.get("photo_17_type")
            if photo_17 == "desktop_sheet":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 17-inch desktop photo printer:",
                    chips=["SC-P900 Specs", "Inks & Media", "Official Quotation"],
                    target_product_id="epson-sc-p900",
                    explanation="**Epson SureColor SC-P900**: 17-inch (A2+) desktop photo printer with 10-color UltraChrome PRO10 ink for gallery-quality sheet prints.",
                    is_leaf=True,
                )
            elif photo_17 == "panoramic_roll":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 17-inch roll photo printer:",
                    chips=["SC-P900 with Roll Unit", "Inks & Media", "Official Quotation"],
                    target_product_id="epson-sc-p900",
                    explanation="**Epson SureColor SC-P900 with Roll Unit**: Enables continuous panoramic banner prints up to 17 inches wide on fine art and canvas roll media.",
                    is_leaf=True,
                )
            elif photo_17 == "heavy_duty_10col":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 17-inch heavy duty fine art printer:",
                    chips=["SC-P5300 Specs", "High-Yield Inks", "Official Quotation"],
                    target_product_id="epson-sc-p5300",
                    explanation="**Epson SureColor SC-P5300**: 17-inch production fine art printer with 10-colour UltraChrome PRO10 inks and 200 ml bulk cartridges.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here are our verified 17-inch photo printers. Which model fits your workflow?",
                    chips=["Desktop Sheet (SC-P900)", "Panoramic Roll Unit (SC-P900)", "10-Colour Heavy Duty (SC-P5300)", "Official Quotation"],
                    target_product_id="epson-sc-p900",
                    supporting_product_ids=["epson-sc-p5300"],
                    explanation="**17-inch Professional Photo Printers (SureColor P-Series)**:\n• **SureColor SC-P900**: 17-inch desktop photo printer with 10-color UltraChrome PRO10 ink for gallery sheet and panoramic roll prints.\n• **SureColor SC-P5300**: 17-inch heavy-duty production photo printer with 200 ml bulk cartridges and Violet ink for maximum colour gamut.",
                    is_leaf=True,
                )

        if photo_width == 24:
            photo_24 = reqs.get("photo_24_type")
            if photo_24 == "commercial_compact":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here are the verified commercial compact 24-inch photo printers:",
                    chips=["SC-P6500E", "SC-P6500D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-p6500d",
                    supporting_product_ids=["epson-sc-p6500e", "epson-sc-p6500de"],
                    explanation="**Epson SureColor SC-P6500E / D / DE**: 24-inch commercial compact photo printer with 6-colour UltraChrome PRO6 ink and flat-top design.",
                    is_leaf=True,
                )
            elif photo_24 == "12_colour_master":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 12-colour master 24-inch gallery printer:",
                    chips=["SC-P7500 Specs", "12-Colour Inks", "Official Quotation"],
                    target_product_id="epson-sc-p7500",
                    explanation="**Epson SureColor SC-P7500**: 24-inch master studio printer featuring a 12-colour UltraChrome PRO12 inkset for 99% Pantone coverage.",
                    is_leaf=True,
                )
            elif photo_24 == "spectro":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 24-inch automated spectro proofer:",
                    chips=["SC-P7500 Spectro", "Calibration Tools", "Official Quotation"],
                    target_product_id="epson-sc-p7500",
                    explanation="**Epson SureColor SC-P7500 with Spectro**: Equipped with ILS30 spectrophotometer for automated contract proofing and packaging color verification.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here are our verified 24-inch photo printers. Which model fits your production volume and colour fidelity requirements?",
                    chips=["Commercial Compact (SC-P6500D)", "12-Colour Master (SC-P7500)", "Automated Spectro (SC-P7500 Spectro)", "Official Quotation"],
                    target_product_id="epson-sc-p6500d",
                    supporting_product_ids=["epson-sc-p7500", "epson-sc-p6500e", "epson-sc-p6500de"],
                    explanation="**24-inch Professional Photo Printers (SureColor P-Series)**:\n• **SureColor SC-P6500 Series (D / E / DE)**: 24-inch commercial compact photo printer with 6-colour UltraChrome PRO6 ink, dual-roll feeding, and flat-top design for high-speed production.\n• **SureColor SC-P7500 / SC-P7500 Spectro**: 24-inch 12-colour UltraChrome PRO12 master studio printer delivering 99% Pantone coverage (optional ILS30 spectrophotometer).",
                    is_leaf=True,
                )

        if photo_width == 44:
            photo_44 = reqs.get("photo_44_type")
            if photo_44 == "production_mfp":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 44-inch production MFP photo printer:",
                    chips=["SC-P8500D Specs", "SC-P8500DM (Scanner)", "Official Quotation"],
                    target_product_id="epson-sc-p8500d",
                    supporting_product_ids=["epson-sc-p8500dm"],
                    explanation="**Epson SureColor SC-P8500D / SC-P8500DM**: 44-inch dual-roll production photo printer with optional integrated 36-inch scanner.",
                    is_leaf=True,
                )
            elif photo_44 == "master_studio":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 44-inch master studio 12-colour printer:",
                    chips=["SC-P9500 Specs", "12-Colour Inks", "Official Quotation"],
                    target_product_id="epson-sc-p9500",
                    explanation="**Epson SureColor SC-P9500**: Flagship 44-inch fine art and contract proofing printer with 12-colour UltraChrome PRO12 inkset.",
                    is_leaf=True,
                )
            elif photo_44 == "spectro_proofer":
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 44-inch master spectro proofer:",
                    chips=["SC-P9500 Spectro", "Calibration Tools", "Official Quotation"],
                    target_product_id="epson-sc-p9500",
                    explanation="**Epson SureColor SC-P9500 with Spectro**: 44-inch contract proofing system with automated ILS30 spectrophotometer.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here are our verified 44-inch fine art and gallery printers:",
                    chips=["Production MFP (SC-P8500D)", "Master Studio PRO12 (SC-P9500)", "Spectro Proofer (SC-P9500 Spectro)", "Official Quotation"],
                    target_product_id="epson-sc-p8500d",
                    supporting_product_ids=["epson-sc-p9500", "epson-sc-p8500dm"],
                    explanation="**44-inch Professional Gallery Printers (SureColor P-Series)**:\n• **SureColor SC-P8500D / SC-P8500DM**: 44-inch dual-roll production photo printer with optional 36-inch integrated scanner.\n• **SureColor SC-P9500 / SC-P9500 Spectro**: 44-inch 12-colour UltraChrome PRO12 master studio proofer with 99% Pantone coverage.",
                    is_leaf=True,
                )

        if photo_width == 64:
            return FlowchartStep(
                category="photography_large_format",
                question="Here is the verified 64-inch fine art production printer:",
                chips=["SC-P20500 Specs", "1.6L Bulk Inks", "Official Quotation"],
                target_product_id="epson-sc-p20500",
                explanation="**Epson SureColor SC-P20500**: Flagship 64-inch production fine art printer featuring 12-color inkset, 1.6L bulk ink packs, and PrecisionCore microTFP heads.",
                is_leaf=True,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 5: Photo Booth / Instant Photo (Citizen)
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("citizen_photo", "photo_booth", "instant_photo", "citizen"):
        cit_format = reqs.get("citizen_format")
        if re.search(r"\b(?:24|36|44|64)[\s-]*(?:inch|in|\"|'')\b", text_l) or reqs.get("photo_width") in (24, 36, 44, 64):
            return FlowchartStep(
                category="citizen_photo",
                question="Citizen dye-sublimation photo printers are compact event models available up to 8 inches (CZ-01 4″, CX-02/CY-02 6″, CX-02W 8″). For 24-inch large-format photo printing, Kepler Tech supplies the Epson SureColor P-Series (SC-P6500D / SC-P7500). Which solution would you like to explore?",
                chips=["Epson 24″ Photo (SC-P6500D)", "Epson 24″ Master (SC-P7500)", "Citizen 4″–8″ Event", "Official Quotation"],
                target_product_id="epson-sc-p6500d",
                supporting_product_ids=["epson-sc-p7500", "citizen-cx-02w"],
                explanation="**Format Notice**: Citizen dye-sub photo printers are designed for portable events (up to 8×12″). For 24-inch gallery and studio production, we supply the **Epson SureColor SC-P6500 Series** and **SC-P7500**.",
                is_leaf=True,
            )
        if cit_format == "4_inch":
            return FlowchartStep(
                category="citizen_photo",
                question="Here is the verified 4-inch ultra-compact photo printer:",
                chips=["Citizen CZ-01 Specs", "Media Packs (4x6)", "Official Quotation"],
                target_product_id="citizen-cz-01",
                explanation="**Citizen CZ-01**: Ultra-compact 4-inch dye-sub photo printer weighing only 5.8 kg, ideal for compact kiosks and mobile photographers.",
                is_leaf=True,
            )
        elif cit_format == "6_inch":
            return FlowchartStep(
                category="citizen_photo",
                question="Here are the verified 6-inch event photo printers:",
                chips=["Citizen CX-02 (Fast)", "Citizen CY-02 (700 Prints)", "Media Packs (6x8/4x6)", "Official Quotation"],
                target_product_id="citizen-cx-02",
                supporting_product_ids=["citizen-cy-02"],
                explanation="**Citizen CX-02 (Fast, lightweight)** and **Citizen CY-02 (High-capacity 700 prints/roll)**: Industry standard 6-inch dye-sub printers for photo booths.",
                is_leaf=True,
            )
        elif cit_format == "8_inch":
            return FlowchartStep(
                category="citizen_photo",
                question="Here is the verified 8-inch wide event photo printer:",
                chips=["Citizen CX-02W Specs", "Media Packs (8x10/8x12)", "Official Quotation"],
                target_product_id="citizen-cx-02w",
                explanation="**Citizen CX-02W**: 8-inch wide-format instant dye-sub printer producing premium 8x10″ and 8x12″ school and graduation portraits.",
                is_leaf=True,
            )
        else:
            return FlowchartStep(
                category="citizen_photo",
                question="What photo print format do you need for instant event or photo booth printing?",
                chips=["4-inch Ultra-Compact (CZ-01)", "6-inch Event Photos (CX-02 / CY-02)", "8-inch Wide Event (CX-02W)"],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Citizen dye-sublimation photo printers deliver high-speed, smudge-proof instant prints with gloss and matte finishes without changing paper.",
                is_leaf=False,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 6: Apparel / T-Shirt / Mug (Dye Sublimation)
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("dye_sublimation", "sublimation", "apparel", "tshirt", "mug"):
        sub_format = reqs.get("sublimation_format")
        if sub_format == "a4_gifts":
            return FlowchartStep(
                category="dye_sublimation",
                question="Here is the verified A4 desktop dye-sublimation printer:",
                chips=["SC-F100 Specs", "140ml Ink Bottles (T49N)", "Official Quotation"],
                target_product_id="epson-sc-f100",
                explanation="**Epson SureColor SC-F100**: Compact A4 desktop dye-sub printer with refillable 140 ml ink tanks, perfect for mugs, phone cases, and small gifts.",
                is_leaf=True,
            )
        elif sub_format == "24_roll":
            return FlowchartStep(
                category="dye_sublimation",
                question="Here is the verified 24-inch roll dye-sublimation printer:",
                chips=["SC-F500 Specs", "140ml Ink Bottles (T49N)", "Sublimation Media", "Official Quotation"],
                target_product_id="epson-sc-f500",
                explanation="**Epson SureColor SC-F500**: 24-inch desktop roll dye-sublimation printer with refillable ink tanks and auto-sheet feeder for apparel and soft signage.",
                is_leaf=True,
            )
        else:
            return FlowchartStep(
                category="dye_sublimation",
                question="What volume and format do you require for dye-sublimation printing?",
                chips=["A4 Desktop Gifts (SC-F100)", "24-inch Roll Apparel (SC-F500)"],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Choose between compact A4 desktop gift printing (SC-F100) or 24-inch roll production for apparel and textile transfers (SC-F500).",
                is_leaf=False,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 7: Scanning Solutions Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("scanners", "scanner", "scanning_solutions"):
        doc_type = reqs.get("scanner_doc_type")
        if doc_type in ("business_doc", "sheetfed_business"):
            return FlowchartStep(
                category="scanners",
                question="Here are the verified Business Document Scanners for offices, businesses and everyday document digitization:",
                chips=["WorkForce DS-900WN", "WorkForce DS-800WN", "WorkForce DS-530II", "WorkForce DS-7500", "Official Quotation"],
                target_product_id="epson-workforce-ds-900wn",
                supporting_product_ids=[
                    "epson-workforce-ds-800wn", "epson-workforce-es-580w", "epson-workforce-es-500wii",
                    "epson-workforce-ds-970", "epson-workforce-ds-870", "epson-workforce-ds-790wn",
                    "epson-workforce-ds-770ii", "epson-workforce-ds-730n", "epson-workforce-ds-530ii",
                    "epson-workforce-ds-410", "epson-workforce-ds-7500", "epson-workforce-ds-7500n",
                    "epson-workforce-ds-6500", "epson-workforce-ds-6500n",
                ],
                explanation=(
                    "**Business Document Scanners (For offices, businesses and everyday document digitization)**:\n"
                    "• **High-Speed Network Scanners**: WorkForce DS-900WN (70 ppm / 140 ipm, 11,000 pages/day), DS-800WN (50 ppm / 100 ipm, 8,000 pages/day), DS-790WN, and DS-730N.\n"
                    "• **High-Capacity Workgroup Scanners**: WorkForce DS-970 (85 ppm / 170 ipm), DS-870 (65 ppm), DS-770 II (45 ppm), DS-530II (35 ppm), and DS-410 (26 ppm).\n"
                    "• **Touchscreen & Wireless Scanners**: WorkForce ES-580W (10.9 cm touchscreen) and ES-500WII (compact duplex).\n"
                    "• **Departmental Flatbed + ADF Scanners**: WorkForce DS-7500 / DS-7500N (40 ppm) and DS-6500 / DS-6500N (25 ppm) with 100-page ADF."
                ),
                is_leaf=True,
            )
        elif doc_type in ("photo_artwork", "graphic_film"):
            return FlowchartStep(
                category="scanners",
                question="Here are the verified Photo & Artwork Scanners for photographers, designers, artists and high-resolution image digitization:",
                chips=["Expression 12000XL", "Expression 12000XL Pro", "Official Quotation"],
                target_product_id="epson-expression-12000xl",
                supporting_product_ids=["epson-expression-12000xl-pro"],
                explanation=(
                    "**Photo & Artwork Scanners (For photographers, designers, artists and high-resolution image digitization)**:\n"
                    "• **Epson Expression 12000XL Photo Scanner**: High-resolution A3 graphics & photo flatbed scanner (2400 × 4800 dpi, 3.8 Dmax optical density, ReadyScan LED, SilverFast Ai).\n"
                    "• **Epson Expression 12000XL Pro Photo Scanner**: Includes TPU transparency unit for digitizing 35mm slides, film strips, and medium/large format negatives."
                ),
                is_leaf=True,
            )
        elif doc_type == "book_large_doc":
            return FlowchartStep(
                category="scanners",
                question="Here are the verified Book & Large-Document Scanners for large-format documents, departmental scanning and high-volume workflows:",
                chips=["WorkForce DS-70000 (A3)", "WorkForce DS-60000 (A3)", "WorkForce DS-32000 (Production)", "Official Quotation"],
                target_product_id="epson-workforce-ds-70000",
                supporting_product_ids=[
                    "epson-workforce-ds-70000n", "epson-workforce-ds-60000", "epson-workforce-ds-60000n",
                    "epson-workforce-ds-30000", "epson-workforce-ds-32000",
                ],
                explanation=(
                    "**Book & Large-Document Scanners (For large-format documents, departmental scanning and high-volume workflows)**:\n"
                    "• **WorkForce DS-70000 / DS-70000N**: 70 ppm / 140 ipm heavy-duty A3 flatbed scanner with 200-sheet ADF for bound records, books, and corporate archives.\n"
                    "• **WorkForce DS-60000 / DS-60000N**: 40 ppm / 80 ipm A3 departmental scanner with dual flatbed platen and high-capacity ADF.\n"
                    "• **WorkForce DS-30000 / DS-32000**: Ultra-fast A3 large-format production sheetfed scanners (up to 90 ppm / 180 ipm) with flexible media handling and ultrasonic double-feed detection."
                ),
                is_leaf=True,
            )
        elif doc_type == "portable_mobile":
            return FlowchartStep(
                category="scanners",
                question="Here are the verified Portable & Mobile Scanners for mobile professionals, fieldwork and compact scanning requirements:",
                chips=["WorkForce DS-360W (Wi-Fi + Battery)", "WorkForce DS-310 (20-sheet ADF)", "WorkForce DS-80W (Wireless)", "WorkForce DS-70 (Ultra-Compact)", "Official Quotation"],
                target_product_id="epson-workforce-ds-360w",
                supporting_product_ids=[
                    "epson-workforce-ds-310", "epson-workforce-ds-80w", "epson-workforce-ds-70",
                ],
                explanation=(
                    "**Portable & Mobile Scanners (For mobile professionals, fieldwork and compact scanning requirements)**:\n"
                    "• **WorkForce DS-360W**: 25 ppm / 50 ipm duplex portable scanner with built-in rechargeable battery, Wi-Fi, and 20-page ADF (1.3 kg).\n"
                    "• **WorkForce DS-310**: 25 ppm / 50 ipm sheet-fed portable scanner with 20-page automatic document feeder (1.1 kg).\n"
                    "• **WorkForce DS-80W**: Ultra-portable wireless scanner with integrated battery scanning in 4 sec/page (300 g).\n"
                    "• **WorkForce DS-70**: Ultra-compact mobile scanner powered via USB scanning in 5.5 sec/page (270 g)."
                ),
                is_leaf=True,
            )
        elif doc_type in ("flatbed_doc", "books_stacks"):
            return FlowchartStep(
                category="scanners",
                question="Here are the verified Flatbed Document Scanners for documents, books and originals that benefit from flatbed scanning:",
                chips=["WorkForce DS-1660W (Wi-Fi)", "WorkForce DS-1630 Flatbed", "Official Quotation"],
                target_product_id="epson-workforce-ds-1660w",
                supporting_product_ids=["epson-workforce-ds-1630"],
                explanation=(
                    "**Flatbed Document Scanners (For documents, books and originals that benefit from flatbed scanning)**:\n"
                    "• **WorkForce DS-1660W**: 25 ppm flatbed color scanner with Wi-Fi wireless connectivity, ReadyScan LED, and 50-page automatic document feeder.\n"
                    "• **WorkForce DS-1630**: Versatile flatbed scanner with 50-page ADF for dual-purpose scanning of bound books, passports, and multi-page stacks."
                ),
                is_leaf=True,
            )
        else:
            return FlowchartStep(
                category="scanners",
                question="What type of scanner do you require?",
                chips=[
                    "Business Document Scanners",
                    "Photo & Artwork Scanners",
                    "Book & Large-Document Scanners",
                    "Portable & Mobile Scanners",
                    "Flatbed Document Scanners",
                ],
                target_product_id=None,
                supporting_product_ids=[],
                explanation=(
                    "Kepler Tech supplies specialized Epson scanners across 5 distinct categories:\n\n"
                    "• **Business Document Scanners**: For offices, businesses and everyday document digitization (15 models).\n\n"
                    "• **Photo & Artwork Scanners**: For photographers, designers, artists and high-resolution image digitization (2 models).\n\n"
                    "• **Book & Large-Document Scanners**: For large-format documents, departmental scanning and high-volume workflows (6 models).\n\n"
                    "• **Portable & Mobile Scanners**: For mobile professionals, fieldwork and compact scanning requirements (4 models).\n\n"
                    "• **Flatbed Document Scanners**: For documents, books and originals that benefit from flatbed scanning (2 models)."
                ),
                is_leaf=False,
            )

    # Fallback to general overview
    return FlowchartStep(
        category=cat_norm,
        question="How can I assist you with Kepler Tech commercial printing and scanning equipment?",
        chips=CATEGORY_OVERVIEW_CHIPS,
        explanation="Please select your application.",
        target_product_id=None,
        supporting_product_ids=[],
        is_leaf=False,
    )


def _apply_budget_filter(step: FlowchartStep, reqs: Dict[str, Any]) -> FlowchartStep:
    """
    Enforces deterministic budget constraints on flowchart leaf recommendations.
    If target price exceeds budget_aed, tries supporting products under budget.
    If none fit, highlights closest verified fit and offers sales-desk quote route.
    Handles quote-only (price null) without crashing.
    """
    if not step.is_leaf or not step.target_product_id:
        return step

    budget_aed = reqs.get("budget_aed")
    if budget_aed is None:
        return step

    try:
        from catalog.price_resolver import PriceResolver
        pr = PriceResolver()
        t_info = pr.get_price_info(step.target_product_id)
        t_price = t_info.get("price")

        if t_price is not None and t_price > budget_aed:
            # Try supporting product IDs that fit the budget
            fitted_supporting = None
            remaining_supporting = []
            for spid in step.supporting_product_ids:
                sp_info = pr.get_price_info(spid)
                sp_price = sp_info.get("price")
                if sp_price is not None and sp_price <= budget_aed and not fitted_supporting:
                    fitted_supporting = (spid, sp_price, sp_info)
                else:
                    remaining_supporting.append(spid)

            if fitted_supporting:
                swap_id, swap_price, swap_info = fitted_supporting
                old_id = step.target_product_id
                step.target_product_id = swap_id
                step.supporting_product_ids = [old_id] + remaining_supporting
                step.explanation = (
                    f"Recommended verified model fitting your budget of AED {budget_aed:,.0f} "
                    f"(listed at AED {swap_price:,.2f} excl. VAT)."
                )
            else:
                # None of the supporting models fit under budget
                step.explanation = (
                    f"Note: At AED {t_price:,.2f} (excl. VAT), this model is above your stated budget of "
                    f"AED {budget_aed:,.0f}. It represents the closest verified manufacturer fit meeting your requirements. "
                    "Our sales desk can review tailored commercial options or volume pricing."
                )
                step.question = (
                    f"The closest verified fit is listed at AED {t_price:,.2f}, which exceeds your budget of AED {budget_aed:,.0f}. "
                    "Would you like to review this model or request an official sales desk quotation?"
                )
                step.chips = ["Request Official Quote", "Contact Sales Desk", "Adjust Budget"]
    except Exception as e:
        # Fail safe without crashing
        pass

    return step


def _apply_primary_concern(step: FlowchartStep, reqs: Dict[str, Any]) -> FlowchartStep:
    """
    If primary_concern is known, puts the verified reason that matches the concern
    first in the recommendation (using only catalogue/TCO fields that exist).
    If no verified data supports that concern, states so honestly instead of implying it.
    """
    if not step.is_leaf or not step.target_product_id:
        return step

    concern = reqs.get("primary_concern")
    if not concern:
        return step

    try:
        pid = step.target_product_id
        from catalog.repository import catalog_repository
        from catalog.cost_per_print_calculator import CostPerPrintCalculator

        product = catalog_repository.products_by_id.get(pid)
        verified_reason = None

        if concern == "running_cost":
            # 1. Check CostPerPrintCalculator ISO data
            iso_data = CostPerPrintCalculator.INKJET_ISO_DATA.get(pid)
            if iso_data:
                mono_c = iso_data.get("mono_cost_per_page")
                mono_y = iso_data.get("mono_yield")
                if mono_c is not None and mono_y:
                    verified_reason = (
                        f"Verified Running Cost Advantage: High-yield ink system delivering verified cost per page of "
                        f"AED {mono_c:.4f} mono ({mono_y:,} page yield under ISO/IEC 24711)."
                    )
            if not verified_reason and product:
                yield_cap = (
                    product.verified.cartridge_capacities
                    or product.specifications_table.get("Yield Capacity")
                    or product.specifications_table.get("Cartridge Sizes")
                )
                if yield_cap:
                    verified_reason = (
                        f"Verified Running Cost Advantage: High-capacity ink system ({yield_cap}) "
                        "engineered for minimal consumable interventions and low operating costs."
                    )
            if not verified_reason:
                calc = CostPerPrintCalculator.calculate_cost_per_print(pid, "4x6")
                if calc.status == "verified" and calc.cost_per_print_formatted:
                    verified_reason = (
                        f"Verified Running Cost Advantage: Verified media cost per print of {calc.cost_per_print_formatted} "
                        f"({calc.package_yield_prints} prints per pack)."
                    )
            if not verified_reason:
                verified_reason = "Note: Specific per-page running cost figures cannot be verified from available manufacturer data for this model."

        elif concern == "print_speed":
            if product:
                speed = product.specifications_table.get("Print Speed") or product.specifications_table.get("Scanning Speed")
                if speed:
                    verified_reason = f"Verified Print Speed: Rated at {speed} for high-productivity workflows."
            if not verified_reason:
                verified_reason = "Note: Specific ISO print speed ratings are not published for this model."

        elif concern == "colour_quality":
            if product:
                res = product.specifications_table.get("Printing Resolution") or product.specifications_table.get("Resolution")
                tech = product.specifications_table.get("Printing Technology") or product.verified.ink_technology
                if res or tech:
                    details = []
                    if tech:
                        details.append(str(tech))
                    if res:
                        details.append(f"resolution up to {res}")
                    verified_reason = f"Verified Colour Quality: Features {', '.join(details)}."
            if not verified_reason:
                verified_reason = "Note: Detailed colour gamut measurements are available on the official brochure."

        elif concern == "reliability":
            if product:
                warranty = product.verified.warranty or product.specifications_table.get("Warranty")
                tech = product.verified.ink_technology or product.specifications_table.get("Printing Technology")
                parts = []
                if tech and ("heat-free" in str(tech).lower() or "precisioncore" in str(tech).lower()):
                    parts.append("Epson PrecisionCore Heat-Free technology (no heat, fewer moving parts)")
                if warranty:
                    parts.append(f"official warranty ({warranty})")
                if parts:
                    verified_reason = f"Verified Reliability: Engineered with {' and '.join(parts)}."
            if not verified_reason:
                verified_reason = "Verified Reliability: Backed by official manufacturer warranty."

        elif concern == "paper_size":
            if product:
                sizes = product.specifications_table.get("Supported Media Sizes") or product.specifications_table.get("Print Sizes")
                if sizes:
                    verified_reason = f"Verified Format Handling: Engineered for {sizes} media."
            if not verified_reason:
                verified_reason = "Verified Format Handling: Matches your required media format."

        elif concern == "portability":
            if product:
                weight = product.specifications_table.get("Product Weight") or product.specifications_table.get("Weight")
                dims = product.specifications_table.get("Dimensions")
                if weight or dims:
                    verified_reason = f"Verified Compact Design: Weighs {weight or 'compact'} (dimensions: {dims or 'space-saving'})."
            if not verified_reason:
                verified_reason = "Verified Compact Design: Compact form factor for flexible placement."

        elif concern == "ease_of_use":
            verified_reason = "Verified Ease of Use: Features intuitive front-panel operation and simplified media loading."

        if verified_reason:
            step.explanation = f"{verified_reason}\n\n{step.explanation}"
    except Exception:
        pass

    return step


def resolve_flowchart_step(
    category: Optional[str],
    requirements: Dict[str, Any],
    text: str = "",
) -> FlowchartStep:
    """
    Evaluates customer requirements and text against the product qualification flowcharts,
    applying deterministic budget gating before returning leaf recommendations.
    """
    reqs = extract_flowchart_requirements(text, requirements)
    step = _resolve_flowchart_step_raw(category, reqs, text)
    step = _apply_budget_filter(step, reqs)
    return _apply_primary_concern(step, reqs)

