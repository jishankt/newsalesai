"""
Deterministic Next-Question Engine.
Evaluates category schemas and conversation state to ask strictly ONE question at a time.
Never asks for already known fields.
"""
from typing import Optional, Dict, Any
from domain.conversation_state import ConversationState
from conversation.requirement_schema import REQUIREMENT_SCHEMAS, QUESTIONS_BY_FIELD, get_question_for_field


class NextQuestionEngine:
    def evaluate_next_step(self, state: ConversationState) -> Optional[Dict[str, Any]]:
        """
        Evaluates current requirements against the category schema.
        Returns the next question dictionary if missing requirements exist, or None if ready.
        """
        cat = state.category
        if not cat:
            state.awaiting_field = "category"
            return {
                "field": "category",
                "question": "Welcome to Kepler Tech! What type of printing or scanning solution are you looking for?",
                "pills": [
                    "CAD & Technical Plotters",
                    "Photo & Fine Art",
                    "Enterprise Office MFP",
                    "Photo Booth / Dye-Sub",
                    "Document Scanners"
                ]
            }

        schema = REQUIREMENT_SCHEMAS.get(cat)
        if not schema:
            return None

        reqs = state.requirements or {}

        # 1. Critical fields (Must be collected first)
        for field in schema.get("critical", []):
            if field not in reqs or reqs[field] is None:
                state.awaiting_field = field
                q_info = get_question_for_field(field, cat)
                return {
                    "field": field,
                    "question": q_info["question"],
                    "pills": q_info.get("pills", [])
                }

        # 2. Important fields (Secondary qualification)
        for field in schema.get("important", []):
            if field not in reqs or reqs[field] is None:
                state.awaiting_field = field
                q_info = get_question_for_field(field, cat)
                return {
                    "field": field,
                    "question": q_info["question"],
                    "pills": q_info.get("pills", [])
                }

        # All critical and important requirements collected
        state.awaiting_field = None
        return None
