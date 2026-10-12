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

from typing import Dict, Any, List, Optional
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


def extract_flowchart_requirements(text: str, current_reqs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts and updates known requirements from customer message text or chip selection.
    Preserves existing requirements across conversational turns.
    """
    text_l = (text or "").lower()
    reqs = dict(current_reqs or {})

    # 1. Paper Size
    if re.search(r"\ba4\b", text_l) or "desktop sheet" in text_l or "a4 output" in text_l:
        reqs["paper_size"] = "A4"
    elif re.search(r"\ba3\b", text_l) or "departmental" in text_l or "a3 output" in text_l:
        reqs["paper_size"] = "A3"

    # 2. Office Daily Volume & Technology Class
    # Numbers: e.g. "50 pages", "100/day", "500 pages a day"
    vol_num_match = re.search(r"\b(\d+)\s*(?:pages?|prints?|drawings?|items?)\s*(?:a\s*day|per\s*day|daily)?\b", text_l)
    if vol_num_match:
        pages = int(vol_num_match.group(1))
        reqs["daily_pages"] = pages
        if pages < 100:
            reqs["office_speed_class"] = "34_ppm"
            reqs["office_duty_class"] = "standard_mfp"
        elif pages <= 300:
            reqs["office_speed_class"] = "25_ppm_rips"
            reqs["office_duty_class"] = "departmental_rips"
        elif pages <= 800:
            reqs["office_speed_class"] = "40_ppm_linehead"
            reqs["office_duty_class"] = "linehead_40"
        elif pages <= 2000:
            reqs["office_speed_class"] = "55_ppm_linehead"
            reqs["office_duty_class"] = "linehead_50_60"
        else:
            reqs["office_duty_class"] = "ultra_100"

    # Verbal volume & speed matching
    if any(k in text_l for k in ["under 100", "standard mfp", "34 ppm", "wf-c5890", "c5890", "low volume", "50/day"]):
        reqs["office_speed_class"] = "34_ppm"
    elif any(k in text_l for k in ["100–300", "100-300", "compact rips", "em-c800", "c800"]):
        reqs["office_speed_class"] = "25_ppm_rips"
    elif any(k in text_l for k in ["300–800", "300-800", "40 ppm", "am-c400", "am-c4000", "c400", "c4000"]):
        reqs["office_speed_class"] = "40_ppm_linehead"
        reqs["office_duty_class"] = "linehead_40"
    elif any(k in text_l for k in ["800+", "55 ppm", "am-c550", "c550"]):
        reqs["office_speed_class"] = "55_ppm_linehead"
    elif any(k in text_l for k in ["200–500", "200-500", "departmental rips", "wf-c878r", "wf-c879r", "c878", "c879"]):
        reqs["office_duty_class"] = "departmental_rips"
    elif any(k in text_l for k in ["1,500–3,000", "1500-3000", "50 ppm", "60 ppm", "am-c5000", "am-c6000", "c5000", "c6000"]):
        reqs["office_duty_class"] = "linehead_50_60"
    elif any(k in text_l for k in ["3,000+", "3000+", "100 ppm", "ultra high", "wf-c21000", "c21000"]):
        reqs["office_duty_class"] = "ultra_100"

    # 3. CAD Plotter Width
    if re.search(r"\b24[\s-]*(?:inch|in|\")\b", text_l) or "a1" in text_l:
        reqs["plotter_width"] = 24
    elif re.search(r"\b36[\s-]*(?:inch|in|\")\b", text_l) or "a0" in text_l:
        reqs["plotter_width"] = 36
    elif re.search(r"\b44[\s-]*(?:inch|in|\")\b", text_l) or "production 44" in text_l:
        reqs["plotter_width"] = 44

    # CAD Configuration & Scanner
    if any(k in text_l for k in ["entry desktop", "desktop stand", "t3100", "sc-t3100"]):
        reqs["cad_config_24"] = "entry_desktop"
    elif any(k in text_l for k in ["single roll", "t3700e", "sc-t3700e"]):
        reqs["cad_config_24"] = "single_roll"
    elif any(k in text_l for k in ["dual roll", "t3700d", "sc-t3700d", "t3700de"]):
        reqs["cad_config_24"] = "dual_roll"

    if any(k in text_l for k in ["print-only", "print only", "without scanner", "no scanner"]):
        reqs["scanner_needed"] = False
    elif any(k in text_l for k in ["scanner", "scan & copy", "mfp", "t5100m", "t5400m", "t5700dm", "t7700dm"]):
        reqs["scanner_needed"] = True

    if any(k in text_l for k in ["1.6l", "bulk ink", "t7700dl"]):
        reqs["cad_config_44"] = "bulk_1_6l"
    elif any(k in text_l for k in ["print-only dual roll", "t7700d"]):
        reqs["cad_config_44"] = "dual_roll_print"

    # 4. Photo Width & Application
    if re.search(r"\b13[\s-]*(?:inch|in|\")\b", text_l) or "a3+" in text_l or "p700" in text_l:
        reqs["photo_width"] = 13
    elif re.search(r"\b17[\s-]*(?:inch|in|\")\b", text_l) or "a2+" in text_l or "p900" in text_l or "p5300" in text_l:
        reqs["photo_width"] = 17
    elif re.search(r"\b24[\s-]*(?:inch|in|\")\b", text_l) or "gallery 24" in text_l or "p6500" in text_l or "p7500" in text_l:
        reqs["photo_width"] = 24
    elif re.search(r"\b44[\s-]*(?:inch|in|\")\b", text_l) or "p8500" in text_l or "p9500" in text_l:
        reqs["photo_width"] = 44
    elif re.search(r"\b64[\s-]*(?:inch|in|\")\b", text_l) or "p20500" in text_l:
        reqs["photo_width"] = 64

    # Photo configuration
    if any(k in text_l for k in ["desktop sheet", "sheet only"]):
        reqs["photo_17_type"] = "desktop_sheet"
    elif any(k in text_l for k in ["panoramic roll", "roll unit"]):
        reqs["photo_17_type"] = "panoramic_roll"
    elif any(k in text_l for k in ["10-colour heavy duty", "heavy duty", "p5300"]):
        reqs["photo_17_type"] = "heavy_duty_10col"

    if any(k in text_l for k in ["commercial compact", "compact", "p6500"]):
        reqs["photo_24_type"] = "commercial_compact"
    elif any(k in text_l for k in ["12-colour master", "master", "p7500"]):
        reqs["photo_24_type"] = "12_colour_master"
    elif any(k in text_l for k in ["spectro", "spectrophotometer"]):
        reqs["photo_24_type"] = "spectro"

    if any(k in text_l for k in ["production mfp", "p8500d", "p8500dm"]):
        reqs["photo_44_type"] = "production_mfp"
    elif any(k in text_l for k in ["master studio pro12", "pro12", "p9500"]):
        reqs["photo_44_type"] = "master_studio"
    elif any(k in text_l for k in ["spectro proofer"]):
        reqs["photo_44_type"] = "spectro_proofer"

    # 5. Citizen Photo
    if re.search(r"\b4[\s-]*(?:inch|in|\")\b", text_l) or any(k in text_l for k in ["4x6", "cz-01", "cz01"]):
        reqs["citizen_format"] = "4_inch"
    elif re.search(r"\b6[\s-]*(?:inch|in|\")\b", text_l) or any(k in text_l for k in ["6x8", "cx-02", "cy-02", "cx02", "cy02"]):
        reqs["citizen_format"] = "6_inch"
    elif re.search(r"\b8[\s-]*(?:inch|in|\")\b", text_l) or any(k in text_l for k in ["8x10", "8x12", "cx-02w", "cx02w"]):
        reqs["citizen_format"] = "8_inch"

    # 6. Dye Sublimation
    if any(k in text_l for k in ["a4 desktop gifts", "a4", "mugs", "gifts", "sc-f100", "f100"]):
        reqs["sublimation_format"] = "a4_gifts"
    elif any(k in text_l for k in ["24-inch roll apparel", "24-inch", "apparel", "t-shirt", "textiles", "sc-f500", "f500"]):
        reqs["sublimation_format"] = "24_roll"

    # 7. Scanners
    if any(k in text_l for k in ["graphic & fine art film", "graphic", "film", "12000xl", "photo scanner"]):
        reqs["scanner_doc_type"] = "graphic_film"
    elif any(k in text_l for k in ["books & stacks", "book", "stack", "hybrid", "flatbed", "ds-1630", "ds-6500", "ds-60000", "ds-70000"]):
        reqs["scanner_doc_type"] = "books_stacks"
    elif any(k in text_l for k in ["fast sheetfed business", "sheetfed", "ds-530", "ds-790", "ds-800", "ds-32000"]):
        reqs["scanner_doc_type"] = "sheetfed_business"

    return reqs


def resolve_flowchart_step(
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
            chips=["Technical CAD Plotters", "Professional Photo & Fine Art", "Dye-Sublimation", "High-Speed Office Printers"],
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
            if speed_class == "34_ppm":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified standard A4 WorkForce Pro MFP:",
                    chips=["Technical Specs", "Replaceable Ink Packs", "Official Quotation"],
                    target_product_id="epson-wf-c5890-dwf",
                    explanation="**Epson WorkForce Pro WF-C5890 DWF**: Standard 34 ppm color MFP with low energy consumption and high-yield ink packs for up to 100 pages/day.",
                    is_leaf=True,
                )
            elif speed_class == "25_ppm_rips":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified compact RIPS A4 model:",
                    chips=["Technical Specs", "RIPS High Yield", "Official Quotation"],
                    target_product_id="epson-em-c800",
                    explanation="**Epson WorkForce Pro EM-C800**: Compact RIPS 25 ppm MFP engineered for 100–300 pages/day with minimal consumable interventions.",
                    is_leaf=True,
                )
            elif speed_class == "40_ppm_linehead":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "Line-Head Technology", "Official Quotation"],
                    target_product_id="epson-am-c400",
                    explanation="**Epson WorkForce Enterprise AM-C400**: Line-head enterprise 40 ppm color MFP delivering fast, reliable production for 300–800 pages/day.",
                    is_leaf=True,
                )
            elif speed_class == "55_ppm_linehead":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 55 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "High-Speed Line-Head", "Official Quotation"],
                    target_product_id="epson-am-c550",
                    explanation="**Epson WorkForce Enterprise AM-C550**: High-speed line-head enterprise 55 ppm MFP for demanding offices printing 800+ pages/day.",
                    is_leaf=True,
                )
            else:
                # Ask Per-Day Volume for A4
                return FlowchartStep(
                    category="office_printer",
                    question="Approximately how many pages do you print per day in the office?",
                    chips=[
                        "Under 100 pages/day (Standard 34 ppm)",
                        "100–300 pages/day (Compact RIPS 25 ppm)",
                        "300–800 pages/day (Line-head 40 ppm)",
                        "800+ pages/day (High-Speed 55 ppm)"
                    ],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="For A4 office printing, choosing the right per-day volume ensures optimal consumable yields and print speeds.",
                    is_leaf=False,
                )

        # Step 2 for A3: Duty & Volume Class (Per-Day Printing)
        if paper_size == "A3":
            duty_class = reqs.get("office_duty_class")
            if duty_class == "departmental_rips":
                return FlowchartStep(
                    category="office_printer",
                    question="Here are the verified A3 departmental RIPS MFPs:",
                    chips=["WF-C878R DWF", "WF-C879R DWF", "RIPS Inks", "Official Quotation"],
                    target_product_id="epson-wf-c878r-dwf",
                    supporting_product_ids=["epson-wf-c879r-dwf"],
                    explanation="**Epson WorkForce Pro WF-C878R / WF-C879R**: Departmental A3 RIPS (25 ppm) delivering up to 86,000 black pages, ideal for 200–500 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "linehead_40":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm enterprise line-head A3 MFP:",
                    chips=["Technical Specs", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c4000",
                    explanation="**Epson WorkForce Enterprise AM-C4000**: Enterprise line-head 40 ppm color MFP designed for medium-to-large departments printing 500–1,500 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "linehead_50_60":
                return FlowchartStep(
                    category="office_printer",
                    question="Here are the verified 50–60 ppm enterprise line-head A3 MFPs:",
                    chips=["AM-C5000 (50 ppm)", "AM-C6000 (60 ppm)", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c5000",
                    supporting_product_ids=["epson-am-c6000"],
                    explanation="**Epson WorkForce Enterprise AM-C5000 / AM-C6000**: High-speed line-head 50–60 ppm MFPs with enterprise security and modular finishing for 1,500–3,000 pages/day.",
                    is_leaf=True,
                )
            elif duty_class == "ultra_100":
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified ultra high-speed 100 ppm enterprise MFP:",
                    chips=["Technical Specs", "Heavy-Duty Finishing", "Official Quotation"],
                    target_product_id="epson-wf-c21000-d4tw",
                    explanation="**Epson WorkForce Enterprise WF-C21000 D4TW**: Flagship 100 ppm ultra high-speed enterprise department printer for continuous production of 3,000+ pages/day.",
                    is_leaf=True,
                )
            else:
                # Ask Per-Day Volume for A3
                return FlowchartStep(
                    category="office_printer",
                    question="Approximately how many pages do you print per day for your A3 workgroup or department?",
                    chips=[
                        "200–500 pages/day (Departmental RIPS 25 ppm)",
                        "500–1,500 pages/day (Line-head 40 ppm)",
                        "1,500–3,000 pages/day (Line-head 50/60 ppm)",
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

        # Step 1: Plotter Width?
        if not width:
            return FlowchartStep(
                category="technical_large_format",
                question="What plotter width do you require for CAD drawings, blueprints, or GIS mapping?",
                chips=["24-inch (A1)", "36-inch (A0)", "44-inch Production"],
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
                    question="For 24-inch CAD printing, what configuration fits your workspace?",
                    chips=["Entry Desktop (SC-T3100)", "Production Single Roll (SC-T3700E)", "Production Dual Roll (SC-T3700D / DE)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="Select between compact desktop placement or heavy-duty single/dual roll production engines.",
                    is_leaf=False,
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
                    question="Do you require a dedicated print-only 36-inch plotter or an integrated scan & copy MFP?",
                    chips=["Print-Only (SC-T5405 / SC-T5700D)", "Scan & Copy MFP (SC-T5400M / SC-T5700DM)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="36-inch plotters are available as dedicated high-speed printers or integrated multifunction workstations with wide-format scanners.",
                    is_leaf=False,
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
                    question="Do you require dedicated 44-inch print-only or dual-roll multifunction scanning?",
                    chips=["Print-Only Dual Roll (SC-T7700D)", "1.6L Bulk Inks (SC-T7700DL)", "MFP Dual-Roll (SC-T7700DM)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="The 44-inch SureColor T-Series provides dual-roll automatic feeding, compact flat-top design, and 6-color Adobe PostScript engines.",
                    is_leaf=False,
                )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 4: Photo / Fine Art / Gallery Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("photography_large_format", "photo_fine_art", "photo", "fine_art"):
        photo_width = reqs.get("photo_width")

        # Step 1: Print Width / Application?
        if not photo_width:
            return FlowchartStep(
                category="photography_large_format",
                question="What print width and format do you require for photography and fine art printing?",
                chips=["13-inch (A3+)", "17-inch (A2+)", "24-inch Gallery", "44-inch Production", "64-inch Production"],
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
                    question="For 17-inch printing, do you need desktop sheet feeding, roll support, or heavy-duty production?",
                    chips=["Desktop Sheet (SC-P900)", "Panoramic Roll Unit (SC-P900)", "10-Colour Heavy Duty (SC-P5300)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="Choose between the sleek SC-P900 (with optional roll unit) or the heavy-duty production workhorse SC-P5300.",
                    is_leaf=False,
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
                    question="What proofing and calibration capability do you require for 24-inch gallery production?",
                    chips=["Commercial Compact (SC-P6500D)", "12-Colour Master (SC-P7500)", "Automated Spectro (SC-P7500 Spectro)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="Choose between commercial production speed (SC-P6500) or master 12-color fine art reproduction with optional spectrophotometer (SC-P7500).",
                    is_leaf=False,
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
                    question="What configuration do you require for 44-inch fine art production?",
                    chips=["Production MFP (SC-P8500D)", "Master Studio PRO12 (SC-P9500)", "Spectro Proofer (SC-P9500 Spectro)"],
                    target_product_id=None,
                    supporting_product_ids=[],
                    explanation="Select high-throughput commercial poster production (SC-P8500) or 12-color master gallery proofing (SC-P9500).",
                    is_leaf=False,
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
        if doc_type == "graphic_film":
            return FlowchartStep(
                category="scanners",
                question="Here is the verified graphic & fine art scanner:",
                chips=["Expression 12000XL", "12000XL Pro (Film)", "Official Quotation"],
                target_product_id="epson-expression-12000xl",
                supporting_product_ids=["epson-expression-12000xl-pro"],
                explanation="**Epson Expression 12000XL / 12000XL Pro**: A3 graphic arts scanner with 2400 x 4800 dpi resolution, optical density of 3.8 DMax, and transparency unit.",
                is_leaf=True,
            )
        elif doc_type == "books_stacks":
            return FlowchartStep(
                category="scanners",
                question="Here are the verified hybrid (flatbed + ADF) document scanners:",
                chips=["WorkForce DS-1630 (A4)", "WorkForce DS-6500 (A4 Pro)", "WorkForce DS-60000 (A3)", "Official Quotation"],
                target_product_id="epson-workforce-ds-1630",
                supporting_product_ids=["epson-workforce-ds-6500", "epson-workforce-ds-60000", "epson-workforce-ds-70000"],
                explanation="**Epson WorkForce DS-1630 / DS-6500 / DS-60000**: Versatile flatbed scanners equipped with high-capacity ADFs for books, passports, and bound stacks.",
                is_leaf=True,
            )
        elif doc_type == "sheetfed_business":
            return FlowchartStep(
                category="scanners",
                question="Here are the verified fast sheetfed business scanners:",
                chips=["WorkForce DS-530II", "WorkForce DS-790WN (Network)", "WorkForce DS-32000 (A3 Production)", "Official Quotation"],
                target_product_id="epson-workforce-ds-530ii",
                supporting_product_ids=["epson-workforce-ds-790wn", "epson-workforce-ds-800wn", "epson-workforce-ds-32000"],
                explanation="**Epson WorkForce DS-530II / DS-790WN / DS-32000**: Ultra-fast sheetfed document scanners scaling from 35 ppm up to 90 ppm / 180 ipm production.",
                is_leaf=True,
            )
        else:
            return FlowchartStep(
                category="scanners",
                question="What type of documents or media will you be scanning?",
                chips=["Fast Sheetfed Business Scanners", "Photo & Fine Art Film Scanners", "Books & Stacks (Hybrid Flatbed+ADF)"],
                target_product_id=None,
                supporting_product_ids=[],
                explanation="Kepler Tech supplies specialized Epson scanners ranging from museum-grade graphic film units to heavy-duty batch document scanners.",
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
