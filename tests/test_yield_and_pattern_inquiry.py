"""
Tests for Yield & Capacity and Pattern / Finishing specification retrieval.
Verifies that all 43 products have verified fields in the database and that
the conversational orchestrator delivers exact verified responses when customers ask.
"""
import unittest
from catalog.catalogue_loader import catalogue_loader
from catalog.catalogue_resolver import build_model_detail_response
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator
from validation.deterministic_validator import deterministic_validator


class TestYieldAndPatternInquiry(unittest.TestCase):

    def setUp(self):
        self.products = catalogue_loader.get_all()

    def test_all_43_products_have_yield_and_pattern_fields(self):
        """Every approved catalogue product must have yield_capacity and pattern_and_finishing."""
        self.assertEqual(len(self.products), 43)
        for p in self.products:
            pid = p["id"]
            self.assertIn("yield_capacity", p, f"{pid} is missing yield_capacity")
            self.assertIn("pattern_and_finishing", p, f"{pid} is missing pattern_and_finishing")
            self.assertTrue(bool(p["yield_capacity"]), f"{pid} has empty yield_capacity")
            self.assertTrue(bool(p["pattern_and_finishing"]), f"{pid} has empty pattern_and_finishing")

    def test_model_detail_response_includes_yield_and_pattern(self):
        """Model detail specifications must include Yield & Capacity and Finishing & Pattern."""
        for p in self.products:
            reply, cards = build_model_detail_response(p)
            self.assertIn("• **Yield & Capacity:**", reply)
            self.assertIn("• **Finishing & Pattern:**", reply)
            is_valid, violations = deterministic_validator.validate(
                reply, context={"product_id": p["id"], "source": "catalog"}
            )
            self.assertTrue(is_valid, f"Validation failure on {p['id']}: {violations}")

    def test_inquiry_citizen_cx02_yield_capacity(self):
        """Customer asks: 'what is the yield capacity of citizen cx-02?'"""
        state = ConversationState(session_id="test-cx02-yield")
        res = orchestrator.process_turn("what is the yield capacity of citizen cx-02?", state=state)
        self.assertEqual(res["source"], "route:product_spec_attribute")
        self.assertIn("400 prints per roll", res["reply"])
        self.assertIn("CX2.4X6", res["reply"])
        self.assertTrue(len(res["product_cards"]) > 0)

    def test_inquiry_citizen_cy02_roll_capacity(self):
        """Customer asks: 'what is the roll capacity of cy-02?'"""
        state = ConversationState(session_id="test-cy02-cap")
        res = orchestrator.process_turn("what is the roll capacity of cy-02?", state=state)
        self.assertEqual(res["source"], "route:product_spec_attribute")
        self.assertIn("700 prints per roll", res["reply"])
        self.assertIn("CY-MS46", res["reply"])

    def test_inquiry_citizen_cz01_pattern_change(self):
        """Customer asks: 'how does pattern change work on the cz-01?'"""
        state = ConversationState(session_id="test-cz01-pattern")
        res = orchestrator.process_turn("how does pattern change work on the cz-01?", state=state)
        self.assertEqual(res["source"], "route:product_spec_attribute")
        self.assertIn("Partial Matte", res["reply"])
        self.assertIn("Glossy, Matte, and Partial Matte", res["reply"])
        self.assertIn("thermal printhead overcoat", res["reply"])

    def test_inquiry_epson_wfc5890_yield(self):
        """Customer asks: 'what is the page yield of wf-c5890?'"""
        state = ConversationState(session_id="test-c5890-yield")
        res = orchestrator.process_turn("what is the page yield of wf-c5890?", state=state)
        self.assertEqual(res["source"], "route:product_spec_attribute")
        self.assertIn("10,000 pages Black", res["reply"])
        self.assertIn("5,000 pages Colour", res["reply"])

    def test_inquiry_general_yield_and_pattern(self):
        """Customer asks: 'what is eild capacity and pattern change?' with no active product."""
        state = ConversationState(session_id="test-general-pattern")
        res = orchestrator.process_turn("what is eild capacity and pattern change?", state=state)
        self.assertEqual(res["source"], "route:yield_pattern_general")
        self.assertIn("Yield & Capacity", res["reply"])
        self.assertIn("Pattern & Finishing", res["reply"])
        self.assertIn("Thermal Overcoat Patterns", res["reply"])
        self.assertIn("Nozzle Check Diagnostic Pattern", res["reply"])


if __name__ == "__main__":
    unittest.main()
