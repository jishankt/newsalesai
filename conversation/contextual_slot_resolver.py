"""
Universal Contextual Slot Resolver for Kepler Tech SalesAI.

Deterministically resolves user conversational turns when the assistant is awaiting
a specific qualification or relaxation field (state.awaiting_field).

Handles:
- Chip exact and partial substring matching
- Ordinal & index references ("first one", "option 2", "1", "2")
- Bare affirmative / negative tokens ("yes", "no", "sure", "nope")
- Shorthand, abbreviations, and domain aliases ("CAD", "MFP", "roll", "A4", "A3")
- Numeric values and descriptive volume tiers ("low", "medium", "high")
- Relaxation transitions (e.g. 24" print-only vs 36" multifunction)
"""

import re
from typing import Dict, Any, List, Optional, Tuple


class ContextualSlotResolver:
    """Universal schema-driven resolver for conversational qualification turns."""

    # ── 1. Ordinal References Mapping ─────────────────────────────────────────
    ORDINAL_PATTERNS = [
        (re.compile(r"\b(?:1st|first|first\s+one|option\s+1|choice\s+1|#1|^1$)\b", re.I), 0),
        (re.compile(r"\b(?:2nd|second|second\s+one|option\s+2|choice\s+2|#2|^2$)\b", re.I), 1),
        (re.compile(r"\b(?:3rd|third|third\s+one|option\s+3|choice\s+3|#3|^3$)\b", re.I), 2),
        (re.compile(r"\b(?:4th|fourth|fourth\s+one|option\s+4|choice\s+4|#4|^4$)\b", re.I), 3),
        (re.compile(r"\b(?:5th|fifth|fifth\s+one|option\s+5|choice\s+5|#5|^5$)\b", re.I), 4),
    ]

    # ── 2. Generic Affirmative & Negative Matchers ───────────────────────────
    AFFIRMATIVE_RE = re.compile(
        r"^(?:yes|yeah|yep|yup|sure|definitely|absolutely|affirmative|i\s+do|we\s+do|needed|required|include|including|with|true|ok|okay|correct|please)(?:,?\s*(?:please|thanks|thank\s*you|that\s*works|sounds\s*good|fine))?$",
        re.I
    )
    NEGATIVE_RE = re.compile(
        r"^(?:no|nope|nah|not|none|negative|without|false|never|skip)(?:,?\s*(?:thanks|thank\s*you|please|not\s*needed|unnecessary|not\s*required|no\s*need))?$",
        re.I
    )

    @classmethod
    def resolve(
        cls,
        text: str,
        awaiting_field: Optional[str],
        category: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
        active_chips: Optional[List[str]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Resolves text specifically in the context of the awaiting field.
        Returns: (requirements_updates, corrections)
        """
        if not text or not awaiting_field:
            return {}, {}

        text_clean = text.strip()
        text_l = text_clean.lower().replace("×", "x").replace("″", "\"").replace("’", "'")
        reqs: Dict[str, Any] = {}
        corrections: Dict[str, Any] = {}
        curr_reqs = requirements or {}
        chips = active_chips or []

        # ── Step A: Check Ordinal Selection Against Active Chips ─────────────
        if chips:
            for pattern, idx in cls.ORDINAL_PATTERNS:
                if pattern.search(text_l):
                    if 0 <= idx < len(chips):
                        selected_chip = chips[idx]
                        # Recursively resolve using the selected chip text
                        return cls.resolve(
                            selected_chip,
                            awaiting_field,
                            category,
                            requirements,
                            active_chips=None  # Prevent loop
                        )

        # ── Step B: Field-Specific Contextual Resolvers ───────────────────────

        # 1. Scanner / Multifunction Requirement
        if awaiting_field in ("scanner_required", "scan_required"):
            # Explicit negation phrases ALWAYS mean scanner_required = False
            is_explicit_negation = any(neg in text_l for neg in [
                "print only", "printer only", "just print", "only print",
                "without scanner", "without scanning", "no scanner", "no scan",
                "don't need scanner", "dont need scanner", "do not need a scanner",
                "do not need scanner", "not needed", "not required"
            ])
            if is_explicit_negation:
                reqs["scanner_required"] = False
                reqs["functions"] = ["print"]
                return reqs, corrections

            # Check affirmative scanner (e.g. "need a scanner", "with scanner", or standalone "scanner", "scan", "mfp", "copier")
            has_affirmative_scanner = bool(re.search(
                r"\b(?:i\s+(?:need|want|would\s+like|prefer)|looking\s+for|switch\s+to|show\s+me|with\s+(?:a\s+)?scanner|need\s+(?:a\s+)?scanner|ineed|iwant)\b.*?\b(?:scann?er|scanning)\b",
                text_l
            )) or any(pos in text_l for pos in [
                "with scanner", "need scanner", "need a scanner", "integrated scanner",
                "multifunction", "scan and copy", "with copy", "all in one", "all-in-one",
                "multifunctional"
            ]) or bool(re.search(r"\b(?:scanner|scan|scanning|mfp|copier)\b", text_l))

            # If user said bare "no" / "nope" without affirmative intent
            if cls.NEGATIVE_RE.search(text_l) and not has_affirmative_scanner:
                reqs["scanner_required"] = False
                reqs["functions"] = ["print"]
                return reqs, corrections

            if has_affirmative_scanner or cls.AFFIRMATIVE_RE.search(text_l):
                reqs["scanner_required"] = True
                reqs["functions"] = ["print", "scan", "copy"]
                return reqs, corrections

        # 2. Print Width (Technical CAD or Large Format)
        if awaiting_field in ("print_width", "photography_print_width"):
            # Direct bare numbers
            num_match = re.search(r"\b(13|17|24|36|44|64|65)\b", text_l)
            if num_match:
                width_val = int(num_match.group(1))
                if width_val == 65:
                    width_val = 64
                reqs["print_width"] = width_val
                if width_val == 24:
                    reqs["paper_size"] = "a1"
                elif width_val == 36:
                    reqs["paper_size"] = "a0"
                elif width_val == 64:
                    reqs["paper_size"] = "64-inch"
                return reqs, corrections

            # Explicit size labels
            if any(k in text_l for k in ["a1", "24-inch", '24"', "a1 size"]):
                reqs["print_width"] = 24
                reqs["paper_size"] = "a1"
                return reqs, corrections
            if any(k in text_l for k in ["a0", "36-inch", '36"', "a0 size"]):
                reqs["print_width"] = 36
                reqs["paper_size"] = "a0"
                return reqs, corrections
            if any(k in text_l for k in ["44-inch", '44"', "wide", "widest", "extra wide"]):
                reqs["print_width"] = 44
                return reqs, corrections
            if any(k in text_l for k in ["13-inch", "a3+"]):
                reqs["print_width"] = 13
                return reqs, corrections
            if any(k in text_l for k in ["17-inch", "a2+"]):
                reqs["print_width"] = 17
                return reqs, corrections

            # Relative size vocabulary — mirrors how users think about chip options
            # "small" / "narrow" → 24-inch (A1, smallest standard CAD width)
            if any(k in text_l for k in ["small", "smallest", "narrow", "narrowest", "compact"]):
                reqs["print_width"] = 24
                reqs["paper_size"] = "a1"
                return reqs, corrections
            # "medium" / "mid" → 36-inch (A0, the mid-range option)
            if any(k in text_l for k in ["medium", "mid", "middle", "moderate", "average"]):
                reqs["print_width"] = 36
                reqs["paper_size"] = "a0"
                return reqs, corrections
            # "large" / "biggest" → 44-inch (widest standard CAD width)
            if any(k in text_l for k in ["large", "largest", "big", "biggest", "wider", "44 inch"]):
                reqs["print_width"] = 44
                return reqs, corrections

        # 3. Photo Form Factor (Compact vs Large Format)
        if awaiting_field == "photo_form_factor":
            if any(k in text_l for k in [
                "compact", "desktop", "portable", "small", "smaller",
                "a3+", "a2+", "13", "17",
                "p700", "p900", "p5300", "citizen"
            ]):
                reqs["photo_form_factor"] = "compact"
                return reqs, corrections
            if any(k in text_l for k in [
                "large", "large format", "larger",
                "roll", "wide", "wide format", "wider",
                "production", "gallery", "commercial", "studio",
                "big", "bigger", "biggest",
                "24", "44", "64", "65",
                "p6500", "p7500", "p8500", "p9500", "p20500"
            ]):
                reqs["photo_form_factor"] = "large"
                if not ("24" in text_l and "64" in text_l):
                    if any(k in text_l for k in ["64", "65", "p20500"]):
                        reqs["print_width"] = 64
                        reqs["paper_size"] = "64-inch"
                    elif any(k in text_l for k in ["44", "p7500", "p8500", "p9500"]):
                        reqs["print_width"] = 44
                        reqs["paper_size"] = "44-inch"
                    elif any(k in text_l for k in ["24", "p6500"]):
                        reqs["print_width"] = 24
                        reqs["paper_size"] = "24-inch"
                return reqs, corrections

        # 4. Photo Brand (Epson Fine Art vs Citizen Event)
        if awaiting_field in ("photo_brand", "brand"):
            if any(k in text_l for k in ["citizen", "photo booth", "photobooth", "booth", "event", "events", "instant", "thermal", "kiosk", "cz-01", "cx-02", "cy-02", "cx-02w"]):
                reqs["photo_brand"] = "citizen"
                reqs["brand"] = "citizen"
                reqs["category"] = "citizen_photo"
                return reqs, corrections
            if any(k in text_l for k in ["epson", "fine art", "studio", "gallery", "a3+", "a2+", "p700", "p900", "p5300", "ultrachrome"]):
                reqs["photo_brand"] = "epson"
                reqs["brand"] = "epson"
                return reqs, corrections

        # 5. Paper Size (Office or Dye Sublimation)
        if awaiting_field == "paper_size":
            if category in ("dye_sublimation", "sublimation"):
                if any(k in text_l for k in ["a4", "desktop", "compact", "small", "mugs", "mug", "gifts", "f100", "sc-f100"]):
                    reqs["paper_size"] = "a4"
                    reqs["model"] = "epson-sc-f100"
                    reqs["print_width"] = 8.5
                    reqs["product_line"] = "surecolor_f"
                    return reqs, corrections
                if any(k in text_l for k in ["24", "roll", "apparel", "textile", "textiles", "t-shirt", "t-shirts", "sportswear", "signage", "f500", "sc-f500"]):
                    reqs["print_width"] = 24
                    reqs["paper_size"] = "24-inch"
                    reqs["model"] = "epson-sc-f500"
                    reqs["product_line"] = "surecolor_f"
                    return reqs, corrections
            else:
                # Office printer — A4 natural synonyms
                if any(k in text_l for k in [
                    "a4", "standard", "compact", "letter",
                    "small", "normal", "regular", "default",
                    "basic", "office size", "smaller"
                ]):
                    reqs["paper_size"] = "a4"
                    return reqs, corrections
                # A3 natural synonyms
                if any(k in text_l for k in [
                    "a3", "large", "tabloid", "ledger", "wide",
                    "bigger", "larger", "a3 size", "bigger format"
                ]):
                    reqs["paper_size"] = "a3"
                    return reqs, corrections

        # 6. Daily Volume (All Categories)
        if awaiting_field == "daily_volume":
            # Direct range (e.g. 100-300, 10 to 50)
            range_match = re.search(r"(\d+)\s*(?:to|-|–)\s*(\d+)", text_l)
            if range_match:
                reqs["daily_volume"] = (int(range_match.group(1)) + int(range_match.group(2))) // 2
                return reqs, corrections

            # Direct number
            num_match = re.search(r"\b(\d+)\b", text_l)
            if num_match:
                val = int(num_match.group(1))
                if "month" in text_l:
                    val = max(1, val // 25)
                reqs["daily_volume"] = val
                return reqs, corrections

            # Descriptive volume tiers — expanded with natural vague language
            if any(k in text_l for k in [
                "low", "under 50", "under 100", "under 200", "under 30",
                "light", "few", "a few", "not many", "not much",
                "minimal", "small volume", "occasional", "rarely", "infrequent",
                "not a lot", "not that many", "little"
            ]):
                reqs["daily_volume"] = 30
                return reqs, corrections
            if any(k in text_l for k in [
                "medium", "moderate", "50-200", "100-300", "200-500", "30-100",
                "mid", "average", "normal volume", "some", "regular", "daily use"
            ]):
                reqs["daily_volume"] = 120
                return reqs, corrections
            if any(k in text_l for k in [
                "high", "heavy", "200+", "300+", "700+", "100+", "high volume",
                "a lot", "lots", "loads", "many", "tonnes", "tons",
                "very high", "production", "bulk", "constant", "all day",
                "very busy", "non stop", "nonstop", "heavy duty", "always printing"
            ]):
                reqs["daily_volume"] = 350
                return reqs, corrections

        # 7. Citizen Print Sizes
        if awaiting_field in ("print_sizes", "print_size"):
            if any(k in text_l for k in ["2x6", "6x2", "photo strip", "strip", "2-inch strip"]):
                reqs["print_sizes"] = ["2x6"]
                return reqs, corrections
            if any(k in text_l for k in ["4x6", "6x4", "6x8", "8x6", "standard", "medium", "cx-02"]):
                reqs["print_sizes"] = ["4x6", "6x8"]
                return reqs, corrections
            if any(k in text_l for k in ["4x4", "4.5x8", "compact", "small", "cz-01"]):
                reqs["print_sizes"] = ["4x4", "4.5x8"]
                return reqs, corrections
            if any(k in text_l for k in ["8x10", "10x8", "8x12", "12x8", "large", "cy-02", "cx-02w"]):
                reqs["print_sizes"] = ["8x10", "8x12"]
                return reqs, corrections

        # 8. Colour Mode
        if awaiting_field == "colour_mode":
            # Check monochrome FIRST to prevent "black" from accidentally hitting colour
            if any(k in text_l for k in [
                "mono", "monochrome",
                "black and white", "black & white",
                "b&w", "b/w", "bw",
                "black only", "black", "greyscale", "grayscale",
                "no colour", "no color", "no"
            ]):
                reqs["colour_mode"] = "monochrome"
                return reqs, corrections
            # Colour
            if any(k in text_l for k in [
                "colour", "color", "full colour", "full color",
                "coloured", "colored", "vibrant", "cmyk",
                "both", "yes", "all colours", "all colors"
            ]):
                reqs["colour_mode"] = "colour"
                return reqs, corrections

        # 9. Product Line (Office)
        if awaiting_field == "product_line":
            if any(k in text_l for k in ["pro", "workforce pro"]):
                reqs["product_line"] = "workforce_pro"
                return reqs, corrections
            if any(k in text_l for k in ["enterprise", "workforce enterprise"]):
                reqs["product_line"] = "workforce_enterprise"
                return reqs, corrections
            if any(k in text_l for k in ["any", "either", "both", "no preference", "all"]):
                reqs["product_line"] = "any"
                return reqs, corrections

        # 10. General Category — covers every token the bot uses in the question + chip labels
        if awaiting_field == "category":
            # a. Citizen Event / Photo Booth (checked FIRST to prevent "event photos" → photography_large_format)
            if any(k in text_l for k in [
                "photo booth", "photobooth", "booth", "kiosk",
                "event photo", "event photos", "event",
                "instant photo", "instant photos", "instant",
                "citizen", "cz-01", "cx-02", "cy-02", "cx-02w",
                "event photos (photo booth)",
            ]):
                reqs["category"] = "citizen_photo"
                return reqs, corrections

            # b. Technical CAD Plotters
            if any(k in text_l for k in [
                "cad", "cad drawing", "cad drawings",
                "blueprint", "blueprints",
                "plotter", "plotters", "plottaer",
                "engineering", "engineering drawing", "engineering drawings",
                "gis", "maps",
                "architect", "architectural", "architecture",
                "technical", "drawings", "drawing",
                "technical cad plotters",
            ]):
                reqs["category"] = "technical_large_format"
                return reqs, corrections

            # c. Dye-Sublimation Merchandise
            if any(k in text_l for k in [
                "sublimation", "dye-sublimation", "dye sublimation",
                "dye-sub", "dyesub", "dye sub",
                "t-shirt", "t-shirts", "tshirt", "tshirts", "shirts",
                "mug", "mugs",
                "merchandise", "sublimation merchandise",
                "apparel", "textile", "textiles",
                "dye-sublimation (t-shirts & mugs)",
            ]):
                reqs["category"] = "dye_sublimation"
                return reqs, corrections

            # d. Professional Photography & Fine Art (checked AFTER citizen/booth)
            if any(k in text_l for k in [
                "photo", "photos", "photograph", "photographs", "photography",
                "fine art", "fine-art",
                "gallery", "portrait", "portraits",
                "professional", "professional photography",
                "surecolor p",
                "professional photography & fine art",
            ]):
                reqs["category"] = "photography_large_format"
                return reqs, corrections

            # e. Office & Business Documents
            if any(k in text_l for k in [
                "office", "business", "workforce",
                "document", "documents",
                "invoices", "reports",
                "office & business documents",
                "office & business documents (a3 / a4)",
                "office enterprise documents",
            ]):
                reqs["category"] = "office_printer"
                return reqs, corrections

            # f. Professional Scanners
            if any(k in text_l for k in [
                "scanner", "scanners", "professional scanner", "professional scanners",
                "document scanner", "photo scanner", "hybrid scanner", "flatbed scanner",
            ]):
                reqs["category"] = "scanners"
                return reqs, corrections


        # 11. Relaxation State Handling
        if awaiting_field == "relaxation":
            # Case 1: Technical CAD 24" + Scanner offered 36" SC-T5100M
            if curr_reqs.get("print_width") == 24 and curr_reqs.get("scanner_required") is True:
                if cls.AFFIRMATIVE_RE.search(text_l) or any(k in text_l for k in [
                    "36", "36-inch", "36\"", "t5100m", "sc-t5100m", "multifunction", "larger", "switch to 36", "show 36"
                ]):
                    reqs["print_width"] = 36
                    reqs["scanner_required"] = True
                    corrections["print_width"] = 36
                    return reqs, corrections
                if cls.NEGATIVE_RE.search(text_l) or any(k in text_l for k in [
                    "24", "24-inch", "24\"", "print only", "without scanner", "keep 24", "no scanner"
                ]):
                    reqs["scanner_required"] = False
                    corrections["scanner_required"] = False
                    return reqs, corrections

            # Case 2: Technical CAD 44" + Scanner offered 36" SC-T5100M
            if curr_reqs.get("print_width") == 44 and curr_reqs.get("scanner_required") is True:
                if cls.AFFIRMATIVE_RE.search(text_l) or any(k in text_l for k in [
                    "36", "36-inch", "36\"", "t5100m", "sc-t5100m", "multifunction"
                ]):
                    reqs["print_width"] = 36
                    reqs["scanner_required"] = True
                    corrections["print_width"] = 36
                    return reqs, corrections
                if cls.NEGATIVE_RE.search(text_l) or any(k in text_l for k in [
                    "44", "44-inch", "44\"", "print only", "without scanner"
                ]):
                    reqs["scanner_required"] = False
                    corrections["scanner_required"] = False
                    return reqs, corrections

            # Case 3: Office A3 + Print-Only offered A3 Multifunction (WF-C878R) vs A4 Print-Only
            if str(curr_reqs.get("paper_size", "")).lower() == "a3" and curr_reqs.get("scanner_required") is False:
                if any(k in text_l for k in ["a3", "multifunction", "wf-c878r", "c878r", "yes", "sure"]):
                    reqs["paper_size"] = "a3"
                    reqs["scanner_required"] = True
                    corrections["scanner_required"] = True
                    return reqs, corrections
                if any(k in text_l for k in ["a4", "print only", "dedicated a4", "no"]):
                    reqs["paper_size"] = "a4"
                    reqs["scanner_required"] = False
                    corrections["paper_size"] = "a4"
                    return reqs, corrections

        # 12. Scanner Intent / Subcategory
        if awaiting_field in ("scanner_intent", "scanner_intent_professional", "scanner_type", "subcategory") or (category in ("scanners", "scanner") and awaiting_field in ("scanner_intent", "scanner_intent_professional")):
            # a. Both can do / Hybrid
            if any(k in text_l for k in [
                "both", "hybrid", "dual", "flatbed and adf", "flatbed + adf", "both can do",
                "books and documents", "photos and documents", "both (flatbed + adf)", "flatbed with feeder",
                "both (flatbed and adf)", "flatbed and sheetfed", "flatbed and feeder"
            ]):
                reqs["scanner_intent"] = "hybrid"
                reqs["subcategory"] = "hybrid_scanners"
                return reqs, corrections

            # b. Photo / Film / High-Res
            if any(k in text_l for k in [
                "photo", "photos", "film", "slide", "slides", "negatives", "high-res", "high res",
                "photo & film", "transparency", "fine art", "photo & film (high-res)", "12000xl"
            ]):
                reqs["scanner_intent"] = "photo"
                reqs["subcategory"] = "photo_scanners"
                return reqs, corrections

            # c. Business / Document
            if any(k in text_l for k in [
                "business", "document", "documents", "business documents", "office",
                "invoice", "invoices", "contracts", "receipts", "sheetfed", "portable", "mobile"
            ]):
                reqs["scanner_intent"] = "business"
                reqs["subcategory"] = "business_scanners"
                return reqs, corrections

        return {}, {}
