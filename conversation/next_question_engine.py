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

    @classmethod
    def get_next_question(
        cls,
        category: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
        unresolved_fields: Optional[Any] = None,
        state: Optional[ConversationState] = None,
    ) -> Optional[Dict[str, Any]]:
        if state is None:
            state = ConversationState(session_id="eval-session")
            if category:
                state.category = category
            if requirements:
                state.requirements = dict(requirements)
        return cls().evaluate_next_step(state)

    def evaluate_next_step(self, state: ConversationState) -> Optional[Dict[str, Any]]:
        category = state.category
        reqs = state.requirements or {}

        # Technical CAD legacy evaluation flow
        if category == "technical_cad":
            if not reqs.get("print_size") and not reqs.get("print_width"):
                return {
                    "field": "print_size",
                    "question": "What is the maximum paper size you need to print (e.g., A0, A1)?",
                    "importance": "critical",
                    "chips": ["A0 (36 inch)", "A1 (24 inch)", "A0+ / 44 inch"]
                }
            if reqs.get("scan_required") is None and reqs.get("scanner_required") is None:
                return {
                    "field": "scan_required",
                    "question": "Do you require scanning functionality (multifunction) or is print-only sufficient?",
                    "importance": "critical",
                    "chips": ["Print Only", "Print + Scan (MFP)"]
                }
            if reqs.get("daily_volume") is None:
                return {
                    "field": "daily_volume",
                    "question": "Approximately how many drawings or posters will you print per day?",
                    "importance": "important",
                    "chips": ["Low (<10/day)", "Medium (10-50/day)", "High (>50/day)"]
                }
            return None

        # Canonical Technical Large Format flow (streamlined: inches -> scanner, no volume)
        if category == "technical_large_format":
            if not reqs.get("print_width"):
                return {
                    "field": "print_width",
                    "question": "What maximum roll width do you require—24-inch (A1), 36-inch (A0), or 44-inch?",
                    "importance": "critical",
                    "chips": ["24-inch (A1)", "36-inch (A0)", "44-inch Wide"]
                }
            if reqs.get("scanner_required") is None:
                return {
                    "field": "scanner_required",
                    "question": "Do you need an integrated wide-format scanner for copying blueprints, or print-only?",
                    "importance": "critical",
                    "chips": ["Yes, with Scanner", "No, Print Only"]
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

        # Citizen photo flow ("if its citizen give all the four")
        if category in ("citizen_photo", "photo_booth"):
            return None

        # Photography and Fine Art / Unified Photo flow
        if category in ("photography_large_format", "photo_fine_art", "photography", "photo_printer"):
            form_factor = reqs.get("photo_form_factor")
            width = reqs.get("print_width")
            if width in (24, 44, 64):
                form_factor = "large"
            elif width in (13, 17) or reqs.get("print_sizes"):
                form_factor = "compact"

            if not form_factor:
                return {
                    "field": "photo_form_factor",
                    "question": "Do you need a compact photo printer (desktop / portable) or a large-format photo & fine art printer (24-inch to 64-inch roll)?",
                    "importance": "critical",
                    "chips": ["Compact (Desktop / Portable)", "Large Format (24″ to 64″)"]
                }

            if form_factor == "large":
                # "if select large send all" -> immediately complete
                return None

            if form_factor == "compact":
                brand = reqs.get("photo_brand") or reqs.get("brand")
                if width in (13, 17) or reqs.get("application") == "fine_art":
                    brand = "epson"
                elif reqs.get("print_sizes") or reqs.get("application") in ("photo_booth", "citizen_photo"):
                    brand = "citizen"

                if not brand:
                    return {
                        "field": "photo_brand",
                        "question": "Which brand or printing application do you prefer—Epson desktop fine art (A3+/A2+ for professional photography) or Citizen instant dye-sub (for photo booths & events)?",
                        "importance": "critical",
                        "chips": ["Epson Desktop (Fine Art / A3+ / A2+)", "Citizen (Photo Booth / Events)"]
                    }
                return None

        # Dye Sublimation flow (F100, F500, T-Shirts, Merchandise)
        if category in ("dye_sublimation", "sublimation"):
            if not reqs.get("paper_size") and not reqs.get("print_width") and not reqs.get("model"):
                return {
                    "field": "paper_size",
                    "question": "What format or print width do you require—compact A4 desktop (for mugs, small gifts, and cut-sheet T-shirt transfers like the SC-F100) or 24-inch roll (for apparel, sportswear, and textiles like the SC-F500)?",
                    "importance": "critical",
                    "chips": ["A4 Desktop (SC-F100)", "24-inch Roll (SC-F500)"]
                }
            if reqs.get("daily_volume") is None:
                return {
                    "field": "daily_volume",
                    "question": "Approximately how many items or transfers do you plan to print daily?",
                    "importance": "important",
                    "chips": ["Under 30 items", "30–100 items", "100+ items"]
                }
            return None

        return None
