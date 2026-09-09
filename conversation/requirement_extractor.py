"""
Requirement Extractor & Python-Grounded Validator.
Extracts explicit facts without allowing the model to hallucinate missing values.
"""
import re
from typing import Dict, Any, Tuple
from domain.conversation_state import ConversationState


class RequirementExtractor:
    def extract_and_validate(self, text: str, state: ConversationState) -> Dict[str, Any]:
        """
        Extracts verified customer requirements from raw text using strictly validated rules.
        """
        msg_lower = text.lower().strip()
        extracted: Dict[str, Any] = {}

        # ── 1. Print Size Extraction ─────────────────────────────────────────
        if any(s in msg_lower for s in ["a0", "36-inch", "36\"", "36 inch", "36inch"]):
            extracted["print_size"] = "A0"
        elif any(s in msg_lower for s in ["a1", "24-inch", "24\"", "24 inch", "24inch"]):
            extracted["print_size"] = "A1"
        elif any(s in msg_lower for s in ["a2", "17-inch", "17\"", "17 inch", "17inch"]):
            extracted["print_size"] = "A2"
        elif any(s in msg_lower for s in ["a3", "13-inch", "13\"", "13 inch", "13inch", "a3+"]):
            extracted["print_size"] = "A3+"
        elif any(s in msg_lower for s in ["44-inch", "44\"", "44 inch", "large format production"]):
            extracted["print_size"] = "44-inch"
        elif any(s in msg_lower for s in ["4x6", "4 x 6", "4*6", "6x4"]):
            extracted["print_size"] = "4x6\""
        elif any(s in msg_lower for s in ["6x8", "6 x 8", "6*8", "8x6"]):
            extracted["print_size"] = "6x8\""
        elif any(s in msg_lower for s in ["5x7", "5 x 7", "5*7", "7x5"]):
            extracted["print_size"] = "5x7\""

        # ── 2. Scanner Requirement Extraction ────────────────────────────────
        if any(neg in msg_lower for neg in [
            "no scanner", "without scanner", "not scanner", "don't need scanner", 
            "dont need scanner", "print only", "only print", "printing only", "no scan"
        ]):
            extracted["scan_required"] = False
        elif any(pos in msg_lower for pos in [
            "with scanner", "need scanner", "scanner required", "built-in scan", 
            "integrated scan", "scanning as well", "scan as well", "multifunction", "mfp"
        ]):
            extracted["scan_required"] = True

        # ── 3. Volume Extraction ─────────────────────────────────────────────
        # Only extract if explicitly mentioned
        if any(hv in msg_lower for hv in ["high volume", "heavy duty", "50+", "50 drawings", "production volume", "100+"]):
            extracted["daily_volume"] = "high"
        elif any(mv in msg_lower for mv in ["medium volume", "10-50", "20 drawings", "30 drawings", "moderate"]):
            extracted["daily_volume"] = "medium"
        elif any(lv in msg_lower for lv in ["low volume", "1-10", "occasional", "few prints", "5 drawings"]):
            extracted["daily_volume"] = "low"

        # ── 4. Speed Extraction ──────────────────────────────────────────────
        if any(hs in msg_lower for hs in ["60-100", "high speed", "fast", "100 ppm", "75 ppm", "60 ppm"]):
            extracted["speed"] = "60-100 ppm"
        elif any(ms in msg_lower for ms in ["40-55", "40 ppm", "55 ppm", "medium speed", "heat-free"]):
            extracted["speed"] = "40-55 ppm"

        # ── 5. Application Extraction ────────────────────────────────────────
        if any(app in msg_lower for app in ["architect", "architecture", "cad", "blueprint", "engineering", "technical drawings"]):
            extracted["application"] = "CAD"
        elif any(app in msg_lower for app in ["fine art", "photo gallery", "exhibition", "photography"]):
            extracted["application"] = "Photo & Fine Art"
        elif any(app in msg_lower for app in ["photo booth", "events", "party booth"]):
            extracted["application"] = "Photo Booth"

        return extracted


requirement_extractor = RequirementExtractor()
