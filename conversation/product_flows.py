"""
Kepler Tech SalesAI Product Qualification Flowcharts.

Encodes the exact decision trees from the Product Qualification Flowcharts specification:
- Page 1: Overview (Category Selection)
- Page 2: Office / Multifunction (A4 & A3 MFPs)
- Page 3: CAD / Blueprint / GIS (24", 36", 44" Plotters)
- Page 4: Photo / Fine Art / Gallery (13" to 64" Printers)
- Page 5: Photo Booth / Instant Photo (Citizen 4", 6", 8" Dye-Sub)
- Page 6: Apparel / T-Shirt / Mug (Epson Dye Sublimation)
- Page 7: Scanning Solutions (Professional Scanners)
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


def resolve_flowchart_step(
    category: Optional[str],
    requirements: Dict[str, Any],
    text: str = "",
) -> FlowchartStep:
    """
    Evaluates the customer state and text against the product qualification flowcharts.
    Returns the exact grounded question, chips, and candidate hardware model IDs.
    """
    text_l = (text or "").lower()
    reqs = dict(requirements or {})

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 1: Category Overview
    # ─────────────────────────────────────────────────────────────────────────────
    if not category:
        return FlowchartStep(
            category="overview",
            question="Kepler Tech specializes in official Epson and Citizen commercial equipment across specialized applications. Which category fits your requirements?",
            chips=CATEGORY_OVERVIEW_CHIPS,
            explanation="Select a category to explore verified models and specifications.",
            is_leaf=False,
        )

    cat_norm = category.lower().strip()

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 2: Office / Multifunction Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("office_printer", "office_enterprise", "office_workforce", "office"):
        # Check Paper Size: A4 vs A3
        is_a4 = "a4" in text_l or reqs.get("paper_size") in ("A4", "a4") or "desktop" in text_l
        is_a3 = "a3" in text_l or reqs.get("paper_size") in ("A3", "a3") or "departmental" in text_l or "enterprise" in text_l

        if not is_a4 and not is_a3:
            return FlowchartStep(
                category="office_printer",
                question="Do you require standard A4 output or large-format A3 output for your office documents?",
                chips=["A4 Output", "A3 Output"],
                target_product_id="epson-wf-c5890-dwf",
                supporting_product_ids=["epson-wf-c878r-dwf", "epson-am-c4000"],
                explanation="Epson WorkForce series delivers Heat-Free technology across compact A4 desktop workgroups and high-speed A3 departmental MFPs.",
                is_leaf=False,
            )

        # Branch 1: A4 Output -> Technology & Speed?
        if is_a4:
            if any(k in text_l for k in ["34 ppm", "standard mfp", "wf-c5890", "c5890", "standard"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified standard A4 WorkForce Pro MFP:",
                    chips=["Technical Specs", "Replaceable Ink Packs", "Official Quotation"],
                    target_product_id="epson-wf-c5890-dwf",
                    explanation="**Epson WorkForce Pro WF-C5890 DWF**: Standard 34 ppm color MFP with low power consumption and high-yield ink packs.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["compact rips", "rips", "25 ppm", "em-c800", "c800"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified compact RIPS A4 model:",
                    chips=["Technical Specs", "RIPS High Yield", "Official Quotation"],
                    target_product_id="epson-em-c800",
                    explanation="**Epson WorkForce Pro EM-C800**: Compact RIPS 25 ppm MFP engineered for uninterrupted business document production.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["40 ppm", "am-c400", "c400"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "Line-Head Technology", "Official Quotation"],
                    target_product_id="epson-am-c400",
                    explanation="**Epson WorkForce Enterprise AM-C400**: Line-head enterprise 40 ppm color MFP offering high reliability in a compact footprint.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["55 ppm", "am-c550", "c550"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 55 ppm line-head enterprise A4 MFP:",
                    chips=["Technical Specs", "High-Speed Line-Head", "Official Quotation"],
                    target_product_id="epson-am-c550",
                    explanation="**Epson WorkForce Enterprise AM-C550**: High-speed line-head enterprise 55 ppm MFP for demanding office workgroups.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="office_printer",
                    question="For A4 office printing, what technology and speed class fits your workload?",
                    chips=["Standard MFP (34 ppm)", "Compact RIPS (25 ppm)", "Line-head Enterprise (40 ppm)", "Line-head Enterprise (55 ppm)"],
                    target_product_id="epson-wf-c5890-dwf",
                    supporting_product_ids=["epson-em-c800", "epson-am-c400", "epson-am-c550"],
                    explanation="Choose between standard desktop workgroup printing, compact RIPS bulk ink systems, or high-speed enterprise line-head engines.",
                    is_leaf=False,
                )

        # Branch 2: A3 Output -> Duty & Volume Class?
        if is_a3:
            if any(k in text_l for k in ["departmental rips", "rips", "25 ppm", "wf-c878r", "c878", "c879"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here are the verified A3 departmental RIPS MFPs:",
                    chips=["WF-C878R DWF", "WF-C879R DWF", "RIPS Inks", "Official Quotation"],
                    target_product_id="epson-wf-c878r-dwf",
                    supporting_product_ids=["epson-wf-c879r-dwf"],
                    explanation="**Epson WorkForce Pro WF-C878R / WF-C879R**: Departmental A3 RIPS (25 ppm) delivering up to 86,000 black pages per ink set.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["40 ppm", "am-c4000", "c4000"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 40 ppm enterprise line-head A3 MFP:",
                    chips=["Technical Specs", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c4000",
                    explanation="**Epson WorkForce Enterprise AM-C4000**: Enterprise line-head 40 ppm color MFP designed for medium-to-large departmental workloads.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["50 ppm", "am-c5000", "c5000"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 50 ppm enterprise line-head A3 MFP:",
                    chips=["Technical Specs", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c5000",
                    explanation="**Epson WorkForce Enterprise AM-C5000**: High-speed line-head 50 ppm MFP with enterprise security and modular finishing.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["60 ppm", "am-c6000", "c6000"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified 60 ppm enterprise line-head A3 MFP:",
                    chips=["Technical Specs", "Finishing Options", "Official Quotation"],
                    target_product_id="epson-am-c6000",
                    explanation="**Epson WorkForce Enterprise AM-C6000**: Fast 60 ppm line-head enterprise MFP for heavy central office print volumes.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["100 ppm", "ultra high-speed", "wf-c21000", "c21000"]):
                return FlowchartStep(
                    category="office_printer",
                    question="Here is the verified ultra high-speed 100 ppm enterprise MFP:",
                    chips=["Technical Specs", "Heavy-Duty Finishing", "Official Quotation"],
                    target_product_id="epson-wf-c21000-d4tw",
                    explanation="**Epson WorkForce Enterprise WF-C21000 D4TW**: Flagship 100 ppm ultra high-speed enterprise department printer with high-capacity sheet feeders.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="office_printer",
                    question="For A3 office printing, what duty and volume class do you require?",
                    chips=["Departmental RIPS (25 ppm)", "Line-head 40 ppm (AM-C4000)", "Line-head 50 ppm (AM-C5000)", "Line-head 60 ppm (AM-C6000)", "Ultra High-speed 100 ppm (WF-C21000)"],
                    target_product_id="epson-wf-c878r-dwf",
                    supporting_product_ids=["epson-am-c4000", "epson-am-c5000", "epson-wf-c21000-d4tw"],
                    explanation="Select between economical departmental RIPS or ultra-fast line-head models scaling from 40 up to 100 pages per minute.",
                    is_leaf=False,
                )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 3: CAD / Blueprint / GIS Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("technical_large_format", "technical_cad", "cad", "plotters"):
        is_24 = any(k in text_l for k in ["24", "24-inch", "a1", "sc-t3100", "sc-t3700"])
        is_36 = any(k in text_l for k in ["36", "36-inch", "a0", "sc-t5100", "sc-t5400", "sc-t5405", "sc-t5700"])
        is_44 = any(k in text_l for k in ["44", "44-inch", "sc-t7700", "production 44"])

        if not is_24 and not is_36 and not is_44:
            return FlowchartStep(
                category="technical_large_format",
                question="What plotter width do you require for CAD drawings, blueprints, or GIS mapping?",
                chips=["24-inch (A1)", "36-inch (A0)", "44-inch Production"],
                target_product_id="epson-sc-t3100",
                supporting_product_ids=["epson-sc-t5405", "epson-sc-t7700d"],
                explanation="Kepler Tech supplies the Epson SureColor T-Series, engineered for precise line accuracy and water-resistant UltraChrome XD2/XD3 inks.",
                is_leaf=False,
            )

        # Branch 1: 24-inch (A1) -> Configuration?
        if is_24:
            if any(k in text_l for k in ["entry desktop", "desktop", "entry", "t3100", "sc-t3100"]):
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified entry desktop 24-inch CAD plotter:",
                    chips=["SC-T3100 Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3100",
                    explanation="**Epson SureColor SC-T3100**: Compact 24-inch wireless desktop technical plotter, perfect for small offices and AEC professionals.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["single roll", "t3700e", "sc-t3700e"]):
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified production single roll 24-inch plotter:",
                    chips=["SC-T3700E Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3700e",
                    explanation="**Epson SureColor SC-T3700E**: 24-inch production CAD plotter with compact flat-top design and front-loading roll media.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["dual roll", "t3700d", "sc-t3700d", "t3700de"]):
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified production dual roll 24-inch plotter:",
                    chips=["SC-T3700D Specs", "Compatible Inks", "Official Quotation"],
                    target_product_id="epson-sc-t3700d",
                    supporting_product_ids=["epson-sc-t3700de"],
                    explanation="**Epson SureColor SC-T3700D / SC-T3700DE**: 24-inch dual-roll production plotter with automatic roll switching and high-capacity ink.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="For 24-inch CAD printing, what configuration fits your workflow?",
                    chips=["Entry Desktop (SC-T3100)", "Production Single Roll (SC-T3700E)", "Production Dual Roll (SC-T3700D / DE)"],
                    target_product_id="epson-sc-t3100",
                    supporting_product_ids=["epson-sc-t3700e", "epson-sc-t3700d"],
                    explanation="Choose between entry desktop standalone placement or heavy-duty single/dual roll production units.",
                    is_leaf=False,
                )

        # Branch 2: 36-inch (A0) -> Integrated Scanner?
        if is_36:
            has_scanner = any(k in text_l for k in ["scanner", "mfp", "scan", "copy", "t5100m", "t5400m", "t5700dm"])
            is_print_only = any(k in text_l for k in ["print-only", "print only", "no scanner", "without scanner", "t5100", "t5405", "t5700d"])

            if is_print_only and not has_scanner:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are the verified print-only 36-inch CAD plotters:",
                    chips=["SC-T5100 (Entry)", "SC-T5405 (Fast)", "SC-T5700D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-t5405",
                    supporting_product_ids=["epson-sc-t5100", "epson-sc-t5700d"],
                    explanation="**SureColor SC-T5100 / SC-T5405 / SC-T5700D**: High-speed dedicated print-only 36-inch CAD plotters for engineering and architectural plans.",
                    is_leaf=True,
                )
            elif has_scanner:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here are the verified 36-inch scan & copy MFP systems:",
                    chips=["SC-T5100M (Entry MFP)", "SC-T5400M (Production MFP)", "SC-T5700DM (Dual-Roll MFP)", "Official Quotation"],
                    target_product_id="epson-sc-t5400m",
                    supporting_product_ids=["epson-sc-t5100m", "epson-sc-t5700dm"],
                    explanation="**SureColor SC-T5100M / SC-T5400M / SC-T5700DM**: 36-inch multifunction plotters with integrated CIS scanners for on-site plan copying and scanning.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Do you require a dedicated print-only 36-inch plotter or an integrated scan & copy MFP?",
                    chips=["Print-Only (SC-T5405 / SC-T5700D)", "Scan & Copy MFP (SC-T5400M / SC-T5700DM)"],
                    target_product_id="epson-sc-t5405",
                    supporting_product_ids=["epson-sc-t5400m"],
                    explanation="36-inch plotters are available as dedicated high-speed printers or integrated multifunction workstations with wide-format scanners.",
                    is_leaf=False,
                )

        # Branch 3: 44-inch Production -> Multifunction?
        if is_44:
            has_scanner_44 = any(k in text_l for k in ["mfp", "scanner", "scan", "copy", "t7700dm"])
            if has_scanner_44:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified 44-inch dual-roll MFP CAD plotter:",
                    chips=["SC-T7700DM Specs", "Dual-Roll Inks", "Official Quotation"],
                    target_product_id="epson-sc-t7700dm",
                    explanation="**Epson SureColor SC-T7700DM**: 44-inch high-speed dual-roll multifunction production plotter with integrated 36-inch 600 dpi scanner.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["1.6l", "bulk", "t7700dl"]):
                return FlowchartStep(
                    category="technical_large_format",
                    question="Here is the verified 44-inch bulk-ink CAD plotter:",
                    chips=["SC-T7700DL Specs", "1.6L Ink Packs", "Official Quotation"],
                    target_product_id="epson-sc-t7700dl",
                    explanation="**Epson SureColor SC-T7700DL**: 44-inch high-speed production plotter with 1.6L bulk ink supply system for lowest total cost of ownership.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="technical_large_format",
                    question="Do you require dedicated 44-inch print-only or dual-roll multifunction scanning?",
                    chips=["Print-Only Dual Roll (SC-T7700D)", "1.6L Bulk Inks (SC-T7700DL)", "MFP Dual-Roll (SC-T7700DM)"],
                    target_product_id="epson-sc-t7700d",
                    supporting_product_ids=["epson-sc-t7700dl", "epson-sc-t7700dm"],
                    explanation="The 44-inch SureColor T-Series provides dual-roll automatic feeding, compact flat-top design, and 6-color Adobe PostScript engines.",
                    is_leaf=False,
                )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 4: Photo / Fine Art / Gallery Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("photography_large_format", "photo_fine_art", "photo", "fine_art"):
        is_13 = any(k in text_l for k in ["13", "13-inch", "a3+", "p700", "sc-p700"])
        is_17 = any(k in text_l for k in ["17", "17-inch", "a2+", "p900", "sc-p900", "p5300", "sc-p5300"])
        is_24 = any(k in text_l for k in ["24", "24-inch", "p6500", "p7500", "gallery 24"])
        is_44 = any(k in text_l for k in ["44", "44-inch", "p8500", "p9500", "production 44"])
        is_64 = any(k in text_l for k in ["64", "64-inch", "p20500", "sc-p20500", "bulk fine art"])

        if not any([is_13, is_17, is_24, is_44, is_64]):
            return FlowchartStep(
                category="photography_large_format",
                question="What print width and format do you require for photography and fine art printing?",
                chips=["13-inch A3+ (SC-P700)", "17-inch A2+ (SC-P900 / P5300)", "24-inch Gallery (SC-P7500)", "44-inch Production (SC-P9500)", "64-inch Production (SC-P20500)"],
                target_product_id="epson-sc-p700",
                supporting_product_ids=["epson-sc-p900", "epson-sc-p7500"],
                explanation="Epson SureColor P-Series printers feature UltraChrome PRO pigment inksets, dedicated Photo/Matte Black nozzles, and museum-grade archival stability.",
                is_leaf=False,
            )

        if is_13:
            return FlowchartStep(
                category="photography_large_format",
                question="Here is the verified 13-inch (A3+) professional photo printer:",
                chips=["SC-P700 Specs", "UltraChrome PRO10 Inks", "Official Quotation"],
                target_product_id="epson-sc-p700",
                explanation="**Epson SureColor SC-P700**: 13-inch (A3+) photo printer with 10-colour UltraChrome PRO10 inkset, Carbon Black mode, and dedicated black channels.",
                is_leaf=True,
            )

        if is_17:
            if any(k in text_l for k in ["sheet", "desktop sheet", "p900"]) and "roll" not in text_l and "5300" not in text_l:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 17-inch desktop photo printer:",
                    chips=["SC-P900 Specs", "Inks & Media", "Official Quotation"],
                    target_product_id="epson-sc-p900",
                    explanation="**Epson SureColor SC-P900**: 17-inch (A2+) desktop photo printer with 10-color UltraChrome PRO10 ink for gallery-quality sheet prints.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["heavy duty", "heavy-duty", "10-colour", "p5300", "sc-p5300"]):
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
                    question="For 17-inch printing, do you need desktop sheet feeding, roll unit, or heavy-duty production?",
                    chips=["Desktop Sheet (SC-P900)", "Panoramic Roll Unit (SC-P900)", "10-Colour Heavy Duty (SC-P5300)"],
                    target_product_id="epson-sc-p900",
                    supporting_product_ids=["epson-sc-p5300"],
                    explanation="Choose between the sleek SC-P900 (with optional roll unit) or the heavy-duty production workhorse SC-P5300.",
                    is_leaf=False,
                )

        if is_24:
            if any(k in text_l for k in ["compact", "commercial compact", "p6500", "p6500e", "p6500d"]):
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here are the verified commercial compact 24-inch photo printers:",
                    chips=["SC-P6500E", "SC-P6500D (Dual Roll)", "Official Quotation"],
                    target_product_id="epson-sc-p6500d",
                    supporting_product_ids=["epson-sc-p6500e", "epson-sc-p6500de"],
                    explanation="**Epson SureColor SC-P6500E / D / DE**: 24-inch commercial compact photo printer with 6-colour UltraChrome PRO6 ink and flat-top design.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["12-colour", "master", "p7500", "sc-p7500"]) and "spectro" not in text_l:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 12-colour master 24-inch gallery printer:",
                    chips=["SC-P7500 Specs", "12-Colour Inks", "Official Quotation"],
                    target_product_id="epson-sc-p7500",
                    explanation="**Epson SureColor SC-P7500**: 24-inch master studio printer featuring a 12-colour UltraChrome PRO12 inkset for 99% Pantone coverage.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="photography_large_format",
                    question="What proofing and calibration capability do you require for 24-inch gallery production?",
                    chips=["Commercial Compact (SC-P6500D)", "12-Colour Master (SC-P7500)", "Automated Spectro (SC-P7500 Spectro)"],
                    target_product_id="epson-sc-p7500",
                    supporting_product_ids=["epson-sc-p6500d"],
                    explanation="Choose between commercial production speed (SC-P6500) or master 12-color fine art reproduction with optional spectrophotometer (SC-P7500).",
                    is_leaf=False,
                )

        if is_44:
            if any(k in text_l for k in ["production mfp", "mfp", "p8500", "p8500d", "p8500dm"]):
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 44-inch production MFP photo printer:",
                    chips=["SC-P8500D Specs", "SC-P8500DM (Scanner)", "Official Quotation"],
                    target_product_id="epson-sc-p8500d",
                    supporting_product_ids=["epson-sc-p8500dm"],
                    explanation="**Epson SureColor SC-P8500D / SC-P8500DM**: 44-inch dual-roll production photo printer with optional integrated 36-inch scanner.",
                    is_leaf=True,
                )
            elif any(k in text_l for k in ["12-colour", "master studio", "p9500", "sc-p9500"]) and "spectro" not in text_l:
                return FlowchartStep(
                    category="photography_large_format",
                    question="Here is the verified 44-inch master studio 12-colour printer:",
                    chips=["SC-P9500 Specs", "12-Colour Inks", "Official Quotation"],
                    target_product_id="epson-sc-p9500",
                    explanation="**Epson SureColor SC-P9500**: Flagship 44-inch fine art and contract proofing printer with 12-colour UltraChrome PRO12 inkset.",
                    is_leaf=True,
                )
            else:
                return FlowchartStep(
                    category="photography_large_format",
                    question="What configuration do you require for 44-inch fine art production?",
                    chips=["Production MFP (SC-P8500D)", "Master Studio PRO12 (SC-P9500)", "Spectro Proofer (SC-P9500 Spectro)"],
                    target_product_id="epson-sc-p9500",
                    supporting_product_ids=["epson-sc-p8500d"],
                    explanation="Select high-throughput commercial poster production (SC-P8500) or 12-color master gallery proofing (SC-P9500).",
                    is_leaf=False,
                )

        if is_64:
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
        if any(k in text_l for k in ["4-inch", "4 inch", "cz-01", "ultra-compact", "compact"]):
            return FlowchartStep(
                category="citizen_photo",
                question="Here is the verified 4-inch ultra-compact photo printer:",
                chips=["Citizen CZ-01 Specs", "Media Packs (4x6)", "Official Quotation"],
                target_product_id="citizen-cz-01",
                explanation="**Citizen CZ-01**: Ultra-compact 4-inch dye-sub photo printer weighing only 5.8 kg, ideal for compact kiosks and mobile photographers.",
                is_leaf=True,
            )
        elif any(k in text_l for k in ["6-inch", "6 inch", "cx-02", "cy-02", "event", "700"]):
            return FlowchartStep(
                category="citizen_photo",
                question="Here are the verified 6-inch event photo printers:",
                chips=["Citizen CX-02 (Fast)", "Citizen CY-02 (700 Prints)", "Media Packs (6x8/4x6)", "Official Quotation"],
                target_product_id="citizen-cx-02",
                supporting_product_ids=["citizen-cy-02"],
                explanation="**Citizen CX-02 (Fast, lightweight)** and **Citizen CY-02 (High-capacity 700 prints/roll)**: Industry standard 6-inch dye-sub printers for photo booths.",
                is_leaf=True,
            )
        elif any(k in text_l for k in ["8-inch", "8 inch", "8x10", "8x12", "cx-02w", "wide event"]):
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
                target_product_id="citizen-cx-02",
                supporting_product_ids=["citizen-cz-01", "citizen-cy-02", "citizen-cx-02w"],
                explanation="Citizen dye-sublimation photo printers deliver high-speed, smudge-proof instant prints with gloss and matte finishes without changing paper.",
                is_leaf=False,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 6: Apparel / T-Shirt / Mug (Dye Sublimation)
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("dye_sublimation", "sublimation", "apparel", "tshirt", "mug"):
        if any(k in text_l for k in ["a4", "desktop gifts", "gifts", "mugs", "sc-f100", "f100", "small"]):
            return FlowchartStep(
                category="dye_sublimation",
                question="Here is the verified A4 desktop dye-sublimation printer:",
                chips=["SC-F100 Specs", "140ml Ink Bottles (T49N)", "Official Quotation"],
                target_product_id="epson-sc-f100",
                explanation="**Epson SureColor SC-F100**: Compact A4 desktop dye-sub printer with refillable 140 ml ink tanks, perfect for mugs, phone cases, and small gifts.",
                is_leaf=True,
            )
        elif any(k in text_l for k in ["24", "24-inch", "roll", "apparel", "sportswear", "sc-f500", "f500"]):
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
                target_product_id="epson-sc-f100",
                supporting_product_ids=["epson-sc-f500"],
                explanation="Choose between compact A4 desktop gift printing (SC-F100) or 24-inch roll production for apparel and textile transfers (SC-F500).",
                is_leaf=False,
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # PAGE 7: Scanning Solutions Decision Tree
    # ─────────────────────────────────────────────────────────────────────────────
    if cat_norm in ("scanners", "scanner", "scanning_solutions"):
        if any(k in text_l for k in ["graphic", "fine art", "film", "12000xl", "expression", "photo scanner"]):
            return FlowchartStep(
                category="scanners",
                question="Here is the verified graphic & fine art scanner:",
                chips=["Expression 12000XL", "12000XL Pro (Film)", "Official Quotation"],
                target_product_id="epson-expression-12000xl",
                supporting_product_ids=["epson-expression-12000xl-pro"],
                explanation="**Epson Expression 12000XL / 12000XL Pro**: A3 graphic arts scanner with 2400 x 4800 dpi resolution, optical density of 3.8 DMax, and transparency unit.",
                is_leaf=True,
            )
        elif any(k in text_l for k in ["book", "books", "stack", "stacks", "hybrid", "flatbed", "ds-1630", "ds-6500", "ds-60000", "ds-70000"]):
            return FlowchartStep(
                category="scanners",
                question="Here are the verified hybrid (flatbed + ADF) document scanners:",
                chips=["WorkForce DS-1630 (A4)", "WorkForce DS-6500 (A4 Pro)", "WorkForce DS-60000 (A3)", "Official Quotation"],
                target_product_id="epson-workforce-ds-1630",
                supporting_product_ids=["epson-workforce-ds-6500", "epson-workforce-ds-60000", "epson-workforce-ds-70000"],
                explanation="**Epson WorkForce DS-1630 / DS-6500 / DS-60000**: Versatile flatbed scanners equipped with high-capacity ADFs for books, passports, and bound stacks.",
                is_leaf=True,
            )
        elif any(k in text_l for k in ["sheetfed", "fast sheetfed", "business", "speed", "ds-530", "ds-790", "ds-800", "ds-32000"]):
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
                chips=["Graphic & Fine Art Film", "Books & Stacks (Hybrid Flatbed+ADF)", "Fast Sheetfed Business"],
                target_product_id="epson-workforce-ds-1630",
                supporting_product_ids=["epson-expression-12000xl", "epson-workforce-ds-530ii"],
                explanation="Kepler Tech supplies specialized Epson scanners ranging from museum-grade graphic film units to heavy-duty batch document scanners.",
                is_leaf=False,
            )

    # Fallback to general overview
    return FlowchartStep(
        category=cat_norm,
        question="How can I assist you with Kepler Tech commercial printing and scanning equipment?",
        chips=CATEGORY_OVERVIEW_CHIPS,
        explanation="Please select your application.",
        is_leaf=False,
    )
