"""
Phase 3 Test Suite: Single source of truth for state and hard constraint self-correction.

Validates:
1. Unified Intent taxonomy (domain.conversation_types and conversation.understanding).
2. Requirement extraction handles negation and corrections (e.g. "I meant A3, not A4").
3. Mid-flow size correction purges stale shortlisted products and updates active focus.
4. ResponsePlanValidator enforces hard constraints against confirmed slots.
"""

import unittest
from domain.conversation_types import Intent as DomainIntent
from conversation.understanding import Intent as UnderstandingIntent, understand_turn
from conversation.product_flows import extract_flowchart_requirements
from conversation.dialogue_state import DialogueState, ReferentResolver
from conversation.policy import PolicyEngine
from conversation.response_plan import ResponsePlanBuilder, ResponsePlanValidator


class TestAuditPhase3StateCorrection(unittest.TestCase):

    def test_intent_taxonomy_unified(self):
        """Intent enums must be unified so there is a single canonical taxonomy."""
        # Check that commerce and router intents exist on the canonical Intent
        self.assertEqual(DomainIntent.GREETING, UnderstandingIntent.GREETING)
        self.assertEqual(DomainIntent.CORRECTION, UnderstandingIntent.CORRECTION)
        self.assertEqual(DomainIntent.PRODUCT_INFO, UnderstandingIntent.PRODUCT_INFO)
        self.assertEqual(DomainIntent.RECOMMEND, UnderstandingIntent.RECOMMEND)
        self.assertEqual(DomainIntent.COMPARE, UnderstandingIntent.COMPARE)
        self.assertEqual(DomainIntent.CONSUMABLES_LOOKUP, UnderstandingIntent.CONSUMABLES_LOOKUP)
        self.assertIs(DomainIntent, UnderstandingIntent)

    def test_paper_size_negation_extraction(self):
        """Paper size extraction must respect negations and explicit corrections."""
        req1 = extract_flowchart_requirements("No, wait, I meant A3 size, not A4")
        self.assertEqual(req1.get("paper_size"), "A3", f"Expected A3 but got {req1.get('paper_size')}")

        req2 = extract_flowchart_requirements("Actually I need A4, not A3")
        self.assertEqual(req2.get("paper_size"), "A4", f"Expected A4 but got {req2.get('paper_size')}")

        req3 = extract_flowchart_requirements("I want A3 instead of A4")
        self.assertEqual(req3.get("paper_size"), "A3", f"Expected A3 but got {req3.get('paper_size')}")

        req4 = extract_flowchart_requirements("We don't want A4 office documents, we need A3")
        self.assertEqual(req4.get("paper_size"), "A3", f"Expected A3 but got {req4.get('paper_size')}")

    def test_mid_flow_size_correction_purges_shortlist(self):
        """A mid-flow correction from A4 to A3 must purge A4 shortlists and recommend A3 models."""
        state = DialogueState(session_id="test-correction-size-1")
        state.category = "office_printers"
        state.requirements = {"category": "office_printers", "paper_size": "A4"}
        state.confirmed_slots = {"category": "office_printers", "paper_size": "A4"}
        state.candidate_products = ["epson-wf-c5890", "epson-em-c800"]
        state.shortlisted_products = ["epson-wf-c5890", "epson-em-c800"]

        # User corrects size
        correction_text = "No, wait, I meant A3 size, not A4"
        turn = understand_turn(correction_text)
        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        # The reply must NOT recommend A4 printers (WF-C5890, EM-C800, AM-C400)
        reply_lower = plan.formatted_reply.lower()
        self.assertNotIn("wf-c5890", reply_lower, "Response still recommends A4 WF-C5890 after A3 correction!")
        self.assertNotIn("em-c800", reply_lower, "Response still recommends A4 EM-C800 after A3 correction!")
        self.assertNotIn("am-c400", reply_lower, "Response still recommends A4 AM-C400 after A3 correction!")

        # The state requirements must be updated to A3
        self.assertEqual(state.requirements.get("paper_size"), "A3")
        self.assertEqual(state.confirmed_slots.get("paper_size"), "A3")

        # Stale A4 shortlists must be cleared or replaced with A3 models
        for pid in state.candidate_products:
            self.assertNotIn("c5890", pid)
            self.assertNotIn("c800", pid)
            self.assertNotIn("am-c400", pid)

    def test_response_plan_validator_blocks_paper_size_mismatch(self):
        """ResponsePlanValidator must reject product cards that violate confirmed paper_size."""
        state = DialogueState(session_id="test-val-1")
        state.category = "office_printers"
        state.confirmed_slots = {"paper_size": "A3"}
        state.requirements = {"paper_size": "A3"}

        turn = understand_turn("Show me options")
        resolved = ReferentResolver.resolve_turn(turn, state)
        decision = PolicyEngine.decide(resolved, state)
        plan = ResponsePlanBuilder.build(decision, resolved, state)

        # Artificially inject an A4 card into the plan
        plan.product_cards = [
            {"id": "epson-wf-c5890", "name": "Epson WorkForce Pro WF-C5890", "max_paper_size": "A4"}
        ]
        plan.formatted_reply = "Here is the Epson WF-C5890 for your office."

        ResponsePlanValidator.validate(plan, resolved, state)
        # Should detect paper size mismatch
        self.assertFalse(plan.is_valid, "Validator should invalidate plan with A4 card when user confirmed A3")


if __name__ == "__main__":
    unittest.main()
