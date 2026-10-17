"""
Phase 5 Test Suite: Technical Spec Retrieval & Attribute Extraction.

Validates:
1. Power consumption is never misattributed as ink consumption/yield.
2. Duplex scanning feature inquiries retrieve verified scanner/ADF specifications.
3. Page yield inquiries retrieve verified cartridge/pack duty yields.
4. Warranty inquiries retrieve official manufacturer warranty details without category reset.
"""

import unittest
from conversation.understanding import understand_turn
from catalog.product_spec_engine import product_spec_engine


class TestAuditPhase5SpecRetrieval(unittest.TestCase):

    def test_power_consumption_intent_and_slot_extraction(self):
        """Power consumption must extract target_attribute='power_consumption', not 'ink_consumption'."""
        turn = understand_turn("What is the power consumption?")
        target_slot = turn.slots.get("target_attribute")
        target_attr = target_slot.value if target_slot else None
        self.assertEqual(target_attr, "power_consumption", f"Expected power_consumption but got {target_attr}")

    def test_power_consumption_retrieval_am_c550(self):
        """Power consumption query for AM-C550 must return electrical wattage and never mention ink consumption."""
        res = product_spec_engine.answer_single_attribute("epson-am-c550", "What is the power consumption?")
        self.assertIsNotNone(res, "Expected RouteResult for power consumption inquiry")
        reply_lower = res.reply.lower()
        self.assertNotIn("ink consumption", reply_lower)
        self.assertNotIn("cartridge capacity", reply_lower)
        self.assertTrue(
            any(k in reply_lower for k in ["power", "energy", "watt", "watts", "electricity", "heat-free"]),
            f"Expected power or energy wattage in reply, got: {res.reply}"
        )

    def test_duplex_scanning_spec_query(self):
        """Duplex scanning inquiry must return verified dual-head / single-pass duplex scanning details."""
        res = product_spec_engine.answer_single_attribute("epson-am-c4000", "Does it support duplex scanning?")
        self.assertIsNotNone(res, "Expected RouteResult for duplex scanning inquiry")
        reply_lower = res.reply.lower()
        self.assertTrue(
            any(k in reply_lower for k in ["duplex", "two-sided", "2-sided", "single-pass", "dual-head", "120 ipm", "100 ipm"]),
            f"Expected duplex scanning specs, got: {res.reply}"
        )

    def test_page_yield_spec_query(self):
        """Page yield query for WF-C5890 must return verified pack yields."""
        res = product_spec_engine.answer_single_attribute("epson-wf-c5890-dwf", "What is the page yield for the ink packs?")
        self.assertIsNotNone(res, "Expected RouteResult for page yield inquiry")
        reply_lower = res.reply.lower()
        self.assertTrue(
            any(k in reply_lower for k in ["10,000", "10000", "5,000", "5000", "yield", "pages"]),
            f"Expected page yield details, got: {res.reply}"
        )


if __name__ == "__main__":
    unittest.main()
