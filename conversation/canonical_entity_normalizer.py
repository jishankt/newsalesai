"""
Canonical Entity and Unit Normalizer for Kepler Tech SalesAI.

Provides deterministic, unified normalization for:
1. Print dimensions (photo sizes, roll widths, imperial/metric conversions)
2. Print volumes (daily vs monthly canonical conversions)
3. Functions & Scanner requirements (positive and negative assertions)
4. Hardware capabilities & form factors
5. Dialogue act classification (differentiating capability inquiries from user constraints)
"""

import re
from typing import Dict, Any, List, Optional, Tuple


class CanonicalEntityNormalizer:
    """Unified engine for extracting and canonicalizing domain entities."""

    # ── Dialogue Act Patterns ──────────────────────────────────────────────
    CAPABILITY_QUERY_PATTERN = re.compile(
        r"\b(?:can\s+(?:i|it|this(?:\s+printer)?|we|you)\s+(?:print|cut|do|support|handle|fit|produce|take)\b|"
        r"does\s+(?:it|this(?:\s+printer)?)\s+(?:support|print|cut|handle|do)\b|"
        r"is\s+(?:it|this(?:\s+printer)?)\s+(?:able|capable)\b|"
        r"can\s+we\s+do\b|is\s+there\s+support\b|support\s+(?:for\s+)?(?:2x6|4x6|a0|a1|a3|a4|roll|canvas)|"
        r"(?:f100|f500|p900|p700|cx-02|cx-02w|cy-02|cz-01)\s+can\s+print\b|"
        r"can\s+this\s+printer\b|possible\s+to\s+print)\b",
        re.IGNORECASE
    )

    CORRECTION_PATTERN = re.compile(
        r"\b(?:actually|instead|changed my mind|correction|i meant|no scanner needed|"
        r"sorry|apologies|my bad|my mistake|make that|change to|update to|switch to|"
        r"rather|incorrect|wrong|not\s+\w+)\b",
        re.IGNORECASE
    )

    # ── Photo Dimension Patterns (Order Agnostic, Imperial & Metric) ────────
    PHOTO_SIZE_RULES: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"(?:^|[^\w])(?:2(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*6(?:\s*inch|\s*in|[\"\'\s])*|6(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*2(?:\s*inch|\s*in|[\"\'\s])*|photo\s*strip|2-inch\s*strip|2x6\s*strip)(?:$|[^\w])", re.I), "2x6"),
        (re.compile(r"(?:^|[^\w])(?:4(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*6(?:\s*inch|\s*in|[\"\'\s])*|6(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*4(?:\s*inch|\s*in|[\"\'\s])*|10\s*cm\s*(?:x|\*|by)\s*15\s*cm|15\s*cm\s*(?:x|\*|by)\s*10\s*cm|10\s*(?:x|\*|by)\s*15\s*cm|15\s*(?:x|\*|by)\s*10\s*cm|100\s*mm\s*(?:x|\*|by)\s*150\s*mm|150\s*mm\s*(?:x|\*|by)\s*100\s*mm)(?:$|[^\w])", re.I), "4x6"),
        (re.compile(r"(?:^|[^\w])(?:5(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*7(?:\s*inch|\s*in|[\"\'\s])*|7(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*5(?:\s*inch|\s*in|[\"\'\s])*|13\s*cm\s*(?:x|\*|by)\s*18\s*cm|18\s*cm\s*(?:x|\*|by)\s*13\s*cm|13\s*(?:x|\*|by)\s*18\s*cm|18\s*(?:x|\*|by)\s*13\s*cm)(?:$|[^\w])", re.I), "5x7"),
        (re.compile(r"(?:^|[^\w])(?:6(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*8(?:\s*inch|\s*in|[\"\'\s])*|8(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*6(?:\s*inch|\s*in|[\"\'\s])*|15\s*cm\s*(?:x|\*|by)\s*20\s*cm|20\s*cm\s*(?:x|\*|by)\s*15\s*cm|15\s*(?:x|\*|by)\s*20\s*cm|20\s*(?:x|\*|by)\s*15\s*cm)(?:$|[^\w])", re.I), "6x8"),
        (re.compile(r"(?:^|[^\w])(?:8(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*10(?:\s*inch|\s*in|[\"\'\s])*|10(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*8(?:\s*inch|\s*in|[\"\'\s])*|20\s*cm\s*(?:x|\*|by)\s*25\s*cm|25\s*cm\s*(?:x|\*|by)\s*20\s*cm|20\s*(?:x|\*|by)\s*25\s*cm)(?:$|[^\w])", re.I), "8x10"),
        (re.compile(r"(?:^|[^\w])(?:8(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*12(?:\s*inch|\s*in|[\"\'\s])*|12(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*8(?:\s*inch|\s*in|[\"\'\s])*|20\s*cm\s*(?:x|\*|by)\s*30\s*cm|30\s*cm\s*(?:x|\*|by)\s*20\s*cm|20\s*(?:x|\*|by)\s*30\s*cm)(?:$|[^\w])", re.I), "8x12"),
        (re.compile(r"(?:^|[^\w])(?:4(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*4(?:\s*inch|\s*in|[\"\'\s])*|4\.5(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*4\.5(?:\s*inch|\s*in|[\"\'\s])*|4\.5(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*8(?:\s*inch|\s*in|[\"\'\s])*|8(?:\s*inch|\s*in|[\"\'\s])*\s*(?:x|\*|by)\s*4\.5(?:\s*inch|\s*in|[\"\'\s])*|10\s*cm\s*(?:x|\*|by)\s*10\s*cm|10\s*(?:x|\*|by)\s*10\s*cm)(?:$|[^\w])", re.I), "4x4"),
    ]

    # Metric and imperial roll width conversion mappings
    METRIC_WIDTH_MAP: List[Tuple[re.Pattern, int, str]] = [
        (re.compile(r"\b(?:914\s*mm|91\.4\s*cm|841\s*mm|84\.1\s*cm|90\s*cm|900\s*mm|0\.9\s*m(?:eter|etre)?s?|0\.91\s*m(?:eter|etre)?s?|3\s*feet|3\s*ft|3\s*')\b", re.I), 36, "a0"),
        (re.compile(r"\b(?:610\s*mm|61\s*cm|594\s*mm|59\.4\s*cm|60\s*cm|600\s*mm|0\.6\s*m(?:eter|etre)?s?|0\.61\s*m(?:eter|etre)?s?|2\s*feet|2\s*ft|2\s*')\b", re.I), 24, "a1"),
        (re.compile(r"\b(?:1118\s*mm|111\.8\s*cm|1067\s*mm|110\s*cm|1100\s*mm|100\s*cm|1000\s*mm|1\s*m(?:eter|etre)|1\.0\s*m(?:eter|etre)?s?|1\.1\s*m(?:eter|etre)?s?|1\.12\s*m(?:eter|etre)?s?|3\.6\s*feet|3\.7\s*feet)\b", re.I), 44, "44-inch"),
        (re.compile(r"\b(?:1626\s*mm|162\.6\s*cm|160\s*cm|1600\s*mm|165\s*cm|1650\s*mm|1\.6\s*m(?:eter|etre)?s?|1\.63\s*m(?:eter|etre)?s?|1\.65\s*m(?:eter|etre)?s?|4\s*feet|4\s*ft|5\s*feet|5\s*ft|5\.3\s*feet|5\.4\s*feet|5\.5\s*feet)\b", re.I), 64, "64-inch"),
        (re.compile(r"\b(?:329\s*mm|32\.9\s*cm|33\s*cm|30\s*cm|0\.33\s*m(?:eter|etre)?s?|1\s*foot|1\s*ft|1\.1\s*feet)\b", re.I), 13, "a3+"),
        (re.compile(r"\b(?:432\s*mm|43\.2\s*cm|43\s*cm|42\s*cm|40\s*cm|0\.43\s*m(?:eter|etre)?s?|1\.4\s*feet|1\.5\s*feet)\b", re.I), 17, "a2+"),
    ]

    @classmethod
    def convert_unit_to_inches(cls, val: float, unit: str) -> Optional[float]:
        """Converts meters, cm, mm, feet, or inches to inches with domain safety boundaries."""
        u = unit.lower().strip()
        if u in ("m", "meter", "meters", "metre", "metres"):
            if 0.25 <= val <= 2.0:
                return val * 39.3701
        elif u in ("cm", "centimeter", "centimeters", "centimetre", "centimetres"):
            if 25.0 <= val <= 200.0:
                return val / 2.54
        elif u in ("mm", "millimeter", "millimeters", "millimetre", "millimetres"):
            if 250.0 <= val <= 2000.0:
                return val / 25.4
        elif u in ("ft", "feet", "foot", "'"):
            if 0.8 <= val <= 6.0:
                return val * 12.0
        elif u in ("in", "inch", "inches", '"', "″", "''"):
            if 8.0 <= val <= 66.0:
                return val
        return None

    @classmethod
    def map_inches_to_printer_class(cls, w_in: float) -> Tuple[Optional[int], Optional[str]]:
        """Maps continuous inch measurement to standard commercial printer width class."""
        if w_in <= 13.5:
            return 13, "a3+"
        elif w_in <= 17.5:
            return 17, "a2+"
        elif w_in <= 24.5:
            return 24, "a1"
        elif w_in <= 36.5:
            return 36, "a0"
        elif w_in <= 44.5:
            return 44, "44-inch"
        elif w_in <= 66.0:
            return 64, "64-inch"
        return None, None

    @classmethod
    def is_capability_query(cls, text: str) -> bool:
        """Determines if the customer message is asking about printer specifications/capabilities."""
        if not text:
            return False
        return bool(cls.CAPABILITY_QUERY_PATTERN.search(text))

    @classmethod
    def is_correction(cls, text: str) -> bool:
        """Detects whether user is correcting a previous preference."""
        if not text:
            return False
        return bool(cls.CORRECTION_PATTERN.search(text))

    @classmethod
    def extract_photo_sizes(cls, text: str) -> List[str]:
        """Extracts canonical photo sizes in order-agnostic format."""
        found: List[str] = []
        for pattern, canonical in cls.PHOTO_SIZE_RULES:
            if pattern.search(text):
                if canonical not in found:
                    found.append(canonical)
        return found

    @classmethod
    def normalize_dimensions(cls, text: str, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Normalizes roll widths, paper sizes, and photo dimensions.
        Returns dictionary of normalized requirement fields.
        """
        res: Dict[str, Any] = {}
        text_l = text.lower()

        # 0. Photo sizes (2D dimensions take precedence over 1D roll widths)
        photo_sizes = cls.extract_photo_sizes(text_l)
        if photo_sizes:
            res["print_sizes"] = photo_sizes
            if not any(k in text_l for k in ["roll", "plotter", "cad", "blueprint", "wide format", "large format"]):
                return res

        # 1. Check metric conversions
        for pat, width, size_code in cls.METRIC_WIDTH_MAP:
            if pat.search(text_l):
                res["print_width"] = width
                res["paper_size"] = "24-inch" if (width == 24 and category == "dye_sublimation") else size_code
                return res

        # 2. Sublimation specific models F100 & F500
        if any(k in text_l for k in ["f100", "sc-f100", "sc f100"]):
            res["model"] = "epson-sc-f100"
            res["paper_size"] = "a4"
            res["print_width"] = 8.5
            res["product_line"] = "surecolor_f"
            return res
        elif any(k in text_l for k in ["f500", "sc-f500", "sc f500"]):
            res["model"] = "epson-sc-f500"
            res["paper_size"] = "24-inch"
            res["print_width"] = 24
            res["product_line"] = "surecolor_f"
            return res

        is_explicit_vol = bool(re.search(
            r"\b(?:pages?|drawings?|prints?|photos?|photographs?|plans?|docs?|sheets?|copies|items?|per\s*day|a\s*day|every\s*day|daily|/day|per\s*month|a\s*month|monthly|/month|volume)\b",
            text_l
        ))
        is_large_range = bool(re.search(r"\b24\b.*?\b64\b", text_l))

        # 3. Imperial roll widths & Standard DIN sizes
        # A0 / 36-inch
        if re.search(r"\b(?:a0|36[\s-]*(?:inch|in|\")|36inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b36\b", text_l))):
            res["print_width"] = 36
            res["paper_size"] = "a0"
        # A1 / 24-inch
        elif not is_large_range and (re.search(r"\b(?:a1|24[\s-]*(?:inch|in|\")|24inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b24\b", text_l)))):
            res["print_width"] = 24
            res["paper_size"] = "24-inch" if category == "dye_sublimation" else "a1"
        # 44-inch / B0
        elif re.search(r"\b(?:44[\s-]*(?:inch|in|\")|44inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b44\b", text_l))):
            res["print_width"] = 44
            res["paper_size"] = "44-inch"
        # 64-inch (and 65-inch approximations)
        elif not is_large_range and (re.search(r"\b(?:6[45][\s-]*(?:inch|in|\"|'')|6[45]inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b6[45]\b", text_l)))):
            res["print_width"] = 64
            res["paper_size"] = "64-inch"
        # 13-inch (A3+)
        elif re.search(r"\b(?:13[\s-]*(?:inch|in|\")|13inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b13\b", text_l))) or (
            bool(re.search(r"\ba3\+(?!\w)", text_l)) and not bool(re.search(r"\ba2\+(?!\w)", text_l))
        ):
            res["print_width"] = 13
            res["paper_size"] = "a3+"
        # 17-inch (A2+)
        elif re.search(r"\b(?:17[\s-]*(?:inch|in|\")|17inch)\b", text_l) or (not is_explicit_vol and bool(re.search(r"\b17\b", text_l))) or (
            bool(re.search(r"\ba2\+(?!\w)", text_l)) and not bool(re.search(r"\ba3\+(?!\w)", text_l))
        ):
            res["print_width"] = 17
            res["paper_size"] = "a2+"
        # A3 (office or standalone)
        elif re.search(r"\b(?:a3|tabloid|ledger)\b", text_l):
            res["paper_size"] = "a3"
        # A4
        elif re.search(r"\b(?:a4|standard\s*a4)\b", text_l):
            res["paper_size"] = "a4"
            if category == "dye_sublimation":
                res["print_width"] = 8.5
        elif category == "dye_sublimation":
            if any(k in text_l for k in ["mug", "mugs", "phone case", "phone cases", "desktop", "cut sheet", "cut-sheet"]):
                res["paper_size"] = "a4"
                res["print_width"] = 8.5
            elif any(k in text_l for k in ["roll", "sportswear", "signage", "wide format", "wide-format"]):
                res["paper_size"] = "24-inch"
                res["print_width"] = 24

        # Continuous / arbitrary dimension widths across inches, feet, meters, cm, mm
        if not res.get("print_width"):
            unit_match = re.search(
                r"\b(?:upto|up\s+to|around|max(?:imum)?\s+|min(?:imum)?\s+|width\s+of\s+|size\s+of\s+)?(\d+(?:\.\d+)?)\s*"
                r"(inch(?:es)?|in|\"|″|feet|foot|ft|'|meters?|metres?|m(?![a-z])|centimeters?|centimetres?|cm|millimeters?|millimetres?|mm)(?![a-zA-Z])",
                text_l
            )
            if unit_match:
                raw_num = float(unit_match.group(1))
                unit_str = unit_match.group(2).lower()
                w_in = cls.convert_unit_to_inches(raw_num, unit_str)
                if w_in:
                    p_w, p_sz = cls.map_inches_to_printer_class(w_in)
                    if p_w:
                        res["print_width"] = p_w
                        res["paper_size"] = "24-inch" if (p_w == 24 and category == "dye_sublimation") else p_sz

        # 4. Photo sizes
        photo_sizes = cls.extract_photo_sizes(text_l)
        if photo_sizes:
            res["print_sizes"] = photo_sizes

        return res

    @classmethod
    def normalize_volume(cls, text: str) -> Dict[str, int]:
        """
        Extracts and converts print volume to daily_volume and monthly_volume.
        Canonical conversion: 25 operating days per business month.
        """
        res: Dict[str, int] = {}
        text_l = text.lower()

        is_explicit_vol = bool(re.search(
            r"\b(?:pages?|drawings?|prints?|photos?|photographs?|plans?|docs?|sheets?|copies|items?|per\s*day|a\s*day|every\s*day|daily|/day|per\s*month|a\s*month|monthly|/month|volume)\b",
            text_l
        ))

        # 1. Monthly volume check (e.g. 6000 monthly -> daily = 6000 // 30 = 200)
        monthly_match = re.search(r"(\d[\d,\s]*)\s*[^.\n,]*?\b(?:per\s*month|a\s*month|monthly|/month|every\s*month)\b", text_l)
        if monthly_match:
            raw_num = monthly_match.group(1).replace(",", "").replace(" ", "")
            try:
                val = int(raw_num)
                res["monthly_volume"] = val
                res["daily_volume"] = max(1, val // 30)
                return res
            except ValueError:
                pass

        # 2. Numeric range (e.g. "20 to 30", "20-30", "20 to 30 prints a day")
        range_match = re.search(r"\b(\d+)\s*(?:to|-|–)\s*(\d+)\b", text_l)
        if range_match:
            try:
                n1 = int(range_match.group(1))
                n2 = int(range_match.group(2))
                avg_val = (n1 + n2) // 2
                res["daily_volume"] = avg_val
                res["monthly_volume"] = avg_val * 30
                return res
            except ValueError:
                pass

        # 3. Daily volume check with explicit units / phrasing
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
                        res["daily_volume"] = daily
                        res["monthly_volume"] = daily * 30
                        return res
                except ValueError:
                    pass

        # 4. Short utterance numeric fallback (e.g. "20")
        if len(text_l.split()) <= 5:
            single_match = re.search(r"\b(\d+)\b", text_l)
            if single_match:
                try:
                    n = int(single_match.group(1))
                    is_width = bool(re.search(rf"\b{n}[\s-]*(?:inch|in|\")", text_l))
                    if not is_width:
                        if is_explicit_vol or n not in (13, 17, 24, 36, 44, 64):
                            res["daily_volume"] = n
                            res["monthly_volume"] = n * 25
                            return res
                except ValueError:
                    pass

        return res

    @classmethod
    def normalize_scanner_function(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Extracts scanner and function requirements with strict negation precedence.
        """
        text_l = text.lower()
        # Explicit negation first
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
            return {
                "scanner_required": False,
                "functions": ["print"]
            }

        scanner_affirmed = bool(
            re.search(r"\b(?:need\s+to\s+scan|need\s+(?:a\s+)?scanner|need\s+scanning|scanner\s+(?:integrated|required)|integrated\s+scanner|with\s+(?:an?\s+)?integrated\s+scanner)\b", text_l)
            or any(pos in text_l for pos in [
                "with scanner", "need scanner", "need a scanner", "scanner required", "built-in scan",
                "integrated scan", "scanner integrated", "scanning as well", "scan as well", "multifunction", "mfp",
                "scan and copy", "print and scan", "printing and scanning", "copy and scan",
                "print, scan and copy", "printing, scanning and copying", "make copies"
            ])
        )

        if scanner_affirmed:
            return {
                "scanner_required": True,
                "functions": ["print", "scan", "copy"]
            }

        return None
