"""
Phase 4 Test Suite: Anti-Repetition and Question Loop Prevention.

Validates:
1. If paper_size and daily_volume exist in state, forbid asking daily volume question again.
2. Question ledger / loop detector prevents asking the same qualification question twice in 6 turns.
3. Multi-turn similarity check (0.85 threshold) checks past 6 turns (not just 1-2 turns) and prevents repeating identical questions with superficial prefixes.
"""

import unittest
from conversation.dialogue_state import DialogueState, ReferentResolver
from conversation.understanding import understand_turn
from conversation.policy import PolicyEngine
from conversation.response_plan import ResponsePlanBuilder
from conversation.question_ledger import canonicalize_semantic_key


class TestAuditPhase4RepetitionLoops(unittest.TestCase):

    def test_semantic_canonicalization_daily_volume(self):
        """canonicalize_semantic_key must recognize daily volume phrases."""
        key = canonicalize_semantic_key("Approximately how many pages do you print per day in the office?")
        self.assertEqual(key, "daily_volume")

        key2 = canonicalize_semantic_key("How many pages do you print per day for your A3 workgroup?")
        self.assertEqual(key2, "daily_volume")

    def test_no_repeat_volume_question_when_volume_and_size_known(self):
        """When paper_size and daily_volume are already known, never ask volume again."""
        state = DialogueState(session_id="test-rep-vol-1")
        state.category = "office_printer"
        state.requirements = {
            "category": "office_printer",
            "paper_size": "A4",
            "daily_volume": 500,
            "daily_pages": 500,
        }
        state.confirmed_slots = {
            "category": "office_printer",
            "paper_size": "A4",
            "daily_volume": 500,
            "daily_pages": 500,
        }

        turn = understand_turn("What models do you recommend?")
        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        reply_lower = plan.formatted_reply.lower()
        self.assertNotIn("how many pages do you print per day", reply_lower)
        self.assertNotIn("how many pages per day", reply_lower)

    def test_multi_turn_similarity_breaks_loop_across_6_turns(self):
        """Repetition check across 6 turns must detect loop when identical question recurred 4 turns ago."""
        from conversation.response_plan import ResponsePlanValidator, ResponsePlan

        state = DialogueState(session_id="test-rep-sim-1")
        state.category = "office_printer"
        state.turn_count = 5

        earlier_question = (
            "For A3 commercial printing, select your daily page volume to match duty cycle and finishing options.\n\n"
            "Approximately how many pages do you print per day for your A3 workgroup or department?\n\n"
            "• 100–500 pages/day (Departmental RIPS 25 ppm)\n"
            "• 500–3,500 pages/day (Enterprise Line-Head 40–60 ppm)\n"
            "• 3,000+ pages/day (Ultra High-Speed 100 ppm)"
        )
        state.recent_assistant_replies = [
            earlier_question,
            "We have fast A3 color printers available.",
            "Delivery takes 1-2 business days across Dubai.",
            "Warranty is 1 year official manufacturer carry-in."
        ]

        # Candidate plan that repeats earlier_question 4 turns later
        plan = ResponsePlan(
            direct_answer=earlier_question,
            formatted_reply=earlier_question,
            is_valid=True,
        )

        turn = understand_turn("Can you show me the printers?")
        resolved = ReferentResolver.resolve_turn(turn, state)
        ResponsePlanValidator.validate(plan, resolved, state)

        # Must NOT re-spew earlier_question with cheap prefix
        self.assertNotIn("Regarding your operational workflow:\n\nFor A3 commercial printing", plan.formatted_reply)
        self.assertNotIn("To continue with your equipment selection:\n\nFor A3 commercial printing", plan.formatted_reply)
        # Must change the reply away from the repeated question to prevent the loop
        self.assertNotEqual(plan.formatted_reply, earlier_question)


if __name__ == "__main__":
    unittest.main()
