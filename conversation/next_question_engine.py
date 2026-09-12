"""
Compatibility Adapter for NextQuestionEngine.
Provides backwards-compatible interface for tests/evaluation/test_evaluation_suite.py
while delegating to the canonical qualification engine.
"""
from typing import Optional, Dict, Any
from domain.conversation_state import ConversationState


class NextQuestionEngine:
    def __init__(self):
        pass

    def evaluate_next_step(self, state: ConversationState) -> Optional[Dict[str, Any]]:
        category = state.category
        reqs = state.requirements or {}

        # Technical CAD / technical_large_format flow
        if category in ("technical_cad", "technical_large_format"):
            # 1. Print size / width
            if not reqs.get("print_size") and not reqs.get("print_width"):
                return {
                    "field": "print_size",
                    "question": "What is the maximum print width or paper format you require (e.g. A1/24\" or A0/36\")?",
                    "importance": "critical",
                    "chips": ["A1 (24-inch)", "A0 (36-inch)", "44-inch"]
                }
            # 2. Scanner required (all 24-inch models in catalogue are dedicated print-only)
            if reqs.get("print_width") != 24 and reqs.get("scan_required") is None and reqs.get("scanner_required") is None:
                return {
                    "field": "scan_required",
                    "question": "Do you need an integrated scanner for copying and scanning, or is print-only sufficient?",
                    "importance": "critical",
                    "chips": ["Integrated Scanner", "Print Only"]
                }
            # 3. Daily volume
            if reqs.get("daily_volume") is None:
                return {
                    "field": "daily_volume",
                    "question": "Approximately how many drawings or plans do you print daily?",
                    "importance": "important",
                    "chips": ["Under 20 drawings", "20–50 drawings", "50+ drawings"]
                }
            return None

        # Office flow
        if category in ("office_printer", "business_office", "office"):
            if not reqs.get("paper_size"):
                return {
                    "field": "paper_size",
                    "question": "What maximum document size do you need—standard A4 or large A3?",
                    "importance": "critical",
                    "chips": ["A4 Standard", "A3 Large Format"]
                }
            if reqs.get("daily_volume") is None:
                return {
                    "field": "daily_volume",
                    "question": "What is your approximate daily printing volume in pages per day?",
                    "importance": "important",
                    "chips": ["Under 100 pages", "100–300 pages", "300+ pages"]
                }
            return None

        # Citizen photo flow
        if category in ("citizen_photo", "photo_booth"):
            if not reqs.get("print_sizes") and not reqs.get("print_size"):
                return {
                    "field": "print_sizes",
                    "question": "Which photo print dimensions do you need (e.g., 4×6″, 6×8″, or 8×10″/8×12″)?",
                    "importance": "critical",
                    "chips": ["4x6 & 6x8", "4x4 / 4.5x8", "8x10 & 8x12"]
                }
            if reqs.get("daily_volume") is None:
                return {
                    "field": "daily_volume",
                    "question": "Approximately how many photos do you expect to print per day or per event?",
                    "importance": "important",
                    "chips": ["Under 200 prints", "200–500 prints", "700+ prints"]
                }
            return None

        return None
