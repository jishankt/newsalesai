"""
Requirement Extractor & Python-Grounded Validator.
Extracts explicit facts without allowing the model to hallucinate missing values.
"""
import re
from typing import Dict, Any, Tuple, Optional
from domain.conversation_state import ConversationState


class RequirementExtractor:
    def extract_and_validate(self, text: str, state: ConversationState) -> Dict[str, Any]:
        """
        Extracts verified customer requirements from raw text using strictly validated rules.
        """
        msg_lower = text.lower().strip()
        extracted: Dict[str, Any] = {}

        # ── 1. Print Size Extraction ─────────────────────────────────────────
        if re.search(r"\b(?:a0|36\s*inch|36\"|36inch)\b", msg_lower):
            extracted["print_size"] = "A0"
        elif re.search(r"\b(?:a1|24\s*inch|24\"|24inch)\b", msg_lower):
            extracted["print_size"] = "A1"
        elif re.search(r"\b(?:a2|17\s*inch|17\"|17inch)\b", msg_lower):
            extracted["print_size"] = "A2"
        elif re.search(r"\b(?:both\s*a4\s*(?:and|&)\s*a3|a3\s*(?:and|&)\s*a4)\b", msg_lower):
            extracted["print_size"] = "A3"
        elif re.search(r"\b(?:a3\+?|tabloid|ledger|13\s*inch|13\"|13inch)\b", msg_lower):
            extracted["print_size"] = "A3"
        elif re.search(r"\b(?:a4|a4\s*size|standard\s*a4)\b", msg_lower):
            extracted["print_size"] = "A4"
        elif re.search(r"\b(?:44\s*inch|44\"|44inch|large format production)\b", msg_lower):
            extracted["print_size"] = "44-inch"
        elif re.search(r"\b(?:2x6|6x2|4x6|5x7|6x8|8x10|8x12|2\s*x\s*6|6\s*x\s*2|4\s*x\s*6|5\s*x\s*7|6\s*x\s*8|8\s*x\s*10|8\s*x\s*12)\b", msg_lower):
            req_match = re.search(r"\b(?:my\s+request\s+to\s+print|i\s+(?:asked|wanted|requested|need)\s+to\s+print)\s+([0-9\s*x×]+)", msg_lower)
            if req_match:
                m_sub = re.search(r"\b(?:2x6|6x2|4x6|5x7|6x8|8x10|8x12|2\s*x\s*6|6\s*x\s*2|4\s*x\s*6|5\s*x\s*7|6\s*x\s*8|8\s*x\s*10|8\s*x\s*12)\b", req_match.group(1))
                raw_sz = m_sub.group(0) if m_sub else req_match.group(1)
            else:
                raw_sz = re.search(r"\b(?:2x6|6x2|4x6|5x7|6x8|8x10|8x12|2\s*x\s*6|6\s*x\s*2|4\s*x\s*6|5\s*x\s*7|6\s*x\s*8|8\s*x\s*10|8\s*x\s*12)\b", msg_lower).group(0)
            norm_sz = re.sub(r"\s+", "", raw_sz)
            extracted["print_size"] = f"{norm_sz} inches"
        else:
            # Check for numeric dimensions in cm, meters, or mm
            m_metric = re.search(r"\b(\d+(?:\.\d+)?)\s*(cm|m|meter|metre|metter|mm)\b", msg_lower)
            if m_metric:
                val = float(m_metric.group(1))
                unit = m_metric.group(2)
                mm = val * 1000 if unit in ("m", "meter", "metre", "metter") else (val * 10 if unit == "cm" else val)
                if mm >= 841:
                    extracted["print_size"] = "A0"
                elif mm >= 594:
                    extracted["print_size"] = "A1"
                elif mm >= 420:
                    extracted["print_size"] = "A2"
                elif mm >= 297:
                    extracted["print_size"] = "A3+"
                elif mm >= 210:
                    extracted["print_size"] = "A4"

        # Contextual relative size mappings:
        if not extracted.get("print_size"):
            if state.awaiting_field == "print_size" or state.category in ("photo_fine_art", "photo_booth") or any(w in msg_lower for w in ["compact desktop", "large format", "large-format"]):
                if any(k in msg_lower for k in ["compact desktop", "compact", "small desktop"]):
                    extracted["print_size"] = "compact desktop"
                elif any(k in msg_lower for k in ["large format", "large-format", "wide format", "production roll", "production print"]):
                    extracted["print_size"] = "large format"

            if not extracted.get("print_size"):
                vague_size_matches = re.findall(r"\b(?:large|larger|big|bigger|huge|wide|small|smaller|compact|mini)\b", msg_lower)
                if vague_size_matches:
                    extracted.setdefault("vague_terms", []).append("size")



        # ── 2. Scanner Requirement Extraction ────────────────────────────────
        scanner_negated = bool(
            re.search(r"\b(?:do\s+not\s+need|don'?t\s+need|no\s+need\s+(?:for\s+)?|without|no|not)\b.*?\b(?:scanner|scanning|scan)\b", msg_lower)
            or re.search(r"\b(?:scanning|scanner|scan)\s+(?:is\s+)?(?:not\s+(?:needed|required|necessary|important|essential)|no\s+need|unnecessary)\b", msg_lower)
            or any(neg in msg_lower for neg in [
                "no scanner", "without scanner", "not scanner", "don't need scanner", 
                "dont need scanner", "print only", "printer only", "only print", "only printer",
                "printing only", "no scan", "no scanning", "just print", "just printer",
                "scanner not needed", "scan not needed", "scanner not important", "scanner not necessary",
                "scanner no need", "scan no need", "actually scan not needed", "actually no scanner",
                "scanner not critical", "no need scanner"
            ])
        )

        is_capability_q = bool(re.search(
            r"\b(?:does\s+(?:it|this(?:\s+printer)?)\s+(?:have|feature|include|come\s+with|offer|support)|"
            r"can\s+(?:it|this(?:\s+printer)?)\s+(?:scan|support|do)|"
            r"has\s+(?:it|this)\s+(?:got|a\s+scanner|scanner)|"
            r"is\s+there\s+a\s+scanner|has\s+scanner\?|scanner\?)",
            msg_lower
        ))

        if scanner_negated:
            extracted["scan_required"] = False
        elif not is_capability_q and (
            bool(re.search(r"\b(?:must\s+have|need|require|requires?|want|include|with)\b.*?\b(?:scanner|scanning|scan)\b", msg_lower))
            or bool(re.search(r"\b(?:scanner|scanning|scan)\s+(?:is\s+)?(?:required|needed|essential|must|included)\b", msg_lower))
            or any(pos in msg_lower for pos in [
                "with scanner", "need scanner", "need a scanner", "scanner required", "built-in scan", 
                "integrated scan", "scanning as well", "scan as well", "multifunction", "mfp",
                "both", "both printing and scanning", "both print and scan", "printing and scanning", 
                "printing & scanning", "print and scan", "print & scan", "scannin", "scaning", "scanner too", "scanning too"
            ]) or (state.awaiting_field == "scan_required" and any(k in msg_lower for k in ["yes", "yep", "yeah", "sure", "both", "need", "scanner", "scanning", "scannin", "scaning", "scan", "include"]))
        ):
            extracted["scan_required"] = True
        elif state.awaiting_field == "scan_required" and any(k in msg_lower for k in [
            "no", "nope", "without", "print only", "printer only", "only print", "only printer", 
            "printing only", "no scanner", "just print", "just printer", "no scan"
        ]):
            extracted["scan_required"] = False

        # ── 3. Volume Extraction ─────────────────────────────────────────────
        # Only extract if awaiting volume or explicitly in volume context
        is_volume_context = (
            state.awaiting_field in ("daily_volume", "print_volume", "volume")
            or any(vkw in msg_lower for vkw in [
                "volume", "per day", "a day", "every day", "daily", "per month", "monthly",
                "drawings per", "drawings", "pages per", "page per", "pages", "page",
                "workload", "heavy duty", "production volume",
                "photos at each event", "photos per event", "at each event", "each event",
                "per event", "photos at", "prints at", "photos", "prints per", "photos per"
            ])
        )
        if is_volume_context:
            # Check explicit tier keywords if awaiting volume or volume keywords present
            if state.awaiting_field in ("daily_volume", "print_volume", "volume") or any(vkw in msg_lower for vkw in ["pages per", "drawings per", "prints per", "per day", "daily", "monthly", "per month", "volume"]):
                if any(re.search(rf"\b{re.escape(hv)}\b", msg_lower) for hv in ["high volume", "large volume", "heavy duty", "production volume", "large"]):
                    extracted["daily_volume"] = "high"
                elif any(re.search(rf"\b{re.escape(mv)}\b", msg_lower) for mv in ["medium volume", "moderate volume", "medium", "moderate", "mid"]):
                    extracted["daily_volume"] = "medium"
                elif any(re.search(rf"\b{re.escape(lv)}\b", msg_lower) for lv in ["low volume", "small volume", "light duty", "under 50", "minimal", "low", "small"]):
                    extracted["daily_volume"] = "low"

            if "daily_volume" not in extracted:
                msg_no_dims = re.sub(r"\b\d+\s*(?:x|\*)\s*\d+\b", "", msg_lower)
                msg_no_dims = re.sub(r"\b\d+\s*(?:mm|cm|inch|\"|gsm|dpi|ml)\b", "", msg_no_dims)
                vol_match = re.search(r"\b(\d{1,6})\b", msg_no_dims)
                if vol_match:
                    try:
                        val = int(vol_match.group(1))
                        if any(mkw in msg_lower for mkw in ["month", "monthly", "per month", "a month", "/month"]):
                            extracted["monthly_volume"] = val
                            val = max(1, val // 30)
                        else:
                            extracted["monthly_volume"] = val * 30
                        extracted["exact_daily_volume"] = val

                        if "under" in msg_lower and val <= 50:
                            extracted["daily_volume"] = "low"
                        elif "drawings per day" in msg_lower or "20 drawings" in msg_lower or "drawings" in msg_lower or state.category == "technical_cad":
                            extracted["daily_volume"] = "high" if val >= 50 else ("medium" if val >= 10 else "low")
                        elif any(ekw in msg_lower for ekw in ["event", "photos", "prints"]):
                            # For events/photos, 400+ requires high-capacity roll units (like CY-02 with 700 prints)
                            extracted["daily_volume"] = val
                            extracted["event_volume"] = val
                        elif state.category == "office_enterprise":
                            extracted["daily_volume"] = "high" if val >= 200 else ("medium" if val >= 50 else "low")
                        elif state.category == "scanner":
                            extracted["daily_volume"] = "high" if val >= 4000 else ("medium" if val >= 1000 else "low")
                        else:
                            extracted["daily_volume"] = val
                    except ValueError:
                        pass

            if "daily_volume" not in extracted:
                if any(re.search(rf"\b{re.escape(hv)}\b", msg_lower) for hv in ["high volume", "heavy duty", "production volume", "low volume", "moderate volume", "medium volume"]):
                    extracted.setdefault("vague_terms", []).append("volume")

        # ── 4. Speed Extraction (Exact numbers only; flag vague terms) ───────
        m_ppm = re.search(r"\b(\d{1,3})\s*ppm\b", msg_lower)
        if m_ppm:
            extracted["speed"] = f"{m_ppm.group(1)} ppm"
        elif any(hs in msg_lower for hs in ["high speed", "fast", "speedy", "quick"]):
            extracted.setdefault("vague_terms", []).append("speed")

        # ── 5. Quality / Vague Professional Flags ────────────────────────────
        if any(q in msg_lower for q in ["professional", "pro quality"]):
            extracted.setdefault("vague_terms", []).append("professional")

        # ── 6. Application Extraction ────────────────────────────────────────
        if any(app in msg_lower for app in ["architect", "architecture", "cad", "blueprint", "engineering", "technical drawings"]):
            extracted["application"] = "CAD"
        elif any(app in msg_lower for app in ["fine art", "photo gallery", "exhibition"]):
            extracted["application"] = "Photo & Fine Art"
        elif any(app in msg_lower for app in ["photo booth", "event photo", "events", "party booth"]):
            extracted["application"] = "Photo Booth"

        # ── 7. Brand Extraction ──────────────────────────────────────────────
        if re.search(r"\b(?:citizen|cx-?02|cy-?02|cz-?01|op900)\b", msg_lower):
            extracted["brand"] = "Citizen"
        elif re.search(r"\b(?:epson|surecolor|workforce)\b", msg_lower):
            extracted["brand"] = "Epson"

        # ── 8. Scanner Type Extraction ───────────────────────────────────────
        if state.category == "scanner" or state.awaiting_field == "scanner_type" or "scanner" in msg_lower:
            if any(w in msg_lower for w in ["sheetfed", "sheet fed", "sheet-fed", "sheetfed document", "high-speed network", "fast document"]):
                extracted["scanner_type"] = "sheetfed"
            elif any(w in msg_lower for w in ["flatbed", "flat bed", "a3 flatbed", "flatbed scanner", "bound book", "photo scanner"]):
                extracted["scanner_type"] = "flatbed"

        return extracted


CATEGORY_RULES = {
    "technical_cad": [
        "cad", "architect", "blueprint", "engineering drawing",
        "technical drawing", "plotter", "gis"
    ],
    "photo_booth": [
        "photo booth", "event photo", "instant photo",
        "citizen photo printer", "dye sublimation photo",
        "8x12", "8x10"
    ],
    "photo_fine_art": [
        "fine art", "gallery", "exhibition",
        "fine art photography", "gallery proof", "p700", "p900",
        "p7500", "p9500"
    ],
    "office_enterprise": [
        "office printer", "office printing", "office document", "office documents",
        "office use", "workgroup", "copier", "enterprise mfp", "business printer", "pages per day"
    ],
    "scanner": [
        "document scanner", "sheetfed scanner",
        "flatbed scanner", "scan documents", "adf"
    ]
}


def classify_category(text: str) -> Optional[str]:
    """
    Classify product category based on strong domain phrases.
    Guardrail: Does NOT use 'photo' alone to decide fine-art printing,
    nor 'pages' alone to decide office printing.
    """
    msg_lower = (text or "").lower()

    # Check negative scanner context first
    has_no_scanner = any(neg in msg_lower for neg in ["no scanner", "without scanner", "not scanner", "don't need scanner", "dont need scanner"])

    for cat, phrases in CATEGORY_RULES.items():
        if cat == "scanner" and has_no_scanner:
            continue
        for phrase in phrases:
            # Word boundary check for acronyms/short words like cad, adf, gis
            if len(phrase) <= 4:
                if re.search(rf"\b{re.escape(phrase)}\b", msg_lower):
                    return cat
            elif phrase in msg_lower:
                return cat

    return None


requirement_extractor = RequirementExtractor()

