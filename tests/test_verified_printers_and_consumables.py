"""
Comprehensive Test Suite for Verified Printers, Consumables, and Running Costs.

Tests:
1. Citizen CY-02 verified specifications (speed, sizes, capacity, weight, dimensions).
2. Authoritative removal of unsupported 5×7″ format and 19.9s speed claim from CY-02.
3. Accurate Citizen CX-02, CX-02W, and CZ-01 specifications and pack yields.
4. Auditable Cost-Per-Print calculations (pack price ÷ usable prints from sold box).
5. Consumable isolation (ink only without maintenance/paper; media only without ink).
6. Multi-attribute query responses with clearly labelled bullets.
7. Verification of weights and dimensions across all approved printer families.
8. Continuous multi-turn conversation switching between CY-02, CX-02, and CX-02W without cross-contamination.
"""

import unittest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState
from catalog.repository import catalog_repository
from catalog.consumable_registry import consumable_registry
from catalog.cost_per_print_calculator import cost_per_print_calculator
from catalog.product_spec_engine import product_spec_engine


class TestVerifiedPrintersAndConsumables(unittest.TestCase):

    def setUp(self):
        self.orchestrator = Orchestrator()

    # ── 1. Citizen CY-02 Verification ────────────────────────────────────────

    def test_cy02_verified_speeds(self):
        """CY-02 prints 4x6 in 12.4s and 6x8 in 21.9s. 5x7 is unsupported."""
        # 4x6 speed query
        res_46 = product_spec_engine.answer_single_attribute("citizen-cy-02", "What is the 4x6 print speed of CY-02?")
        self.assertIsNotNone(res_46)
        self.assertIn("12.4", res_46.reply)
        self.assertNotIn("19.9", res_46.reply)

        # 6x8 speed query
        res_68 = product_spec_engine.answer_single_attribute("citizen-cy-02", "How fast does CY-02 print 6x8?")
        self.assertIsNotNone(res_68)
        self.assertIn("21.9", res_68.reply)
        self.assertNotIn("19.9", res_68.reply)

        # 5x7 speed query -> must state unsupported
        res_57 = product_spec_engine.answer_single_attribute("citizen-cy-02", "What is the 5x7 print speed of CY-02?")
        self.assertIsNotNone(res_57)
        self.assertTrue("not support" in res_57.reply.lower() or "unsupported" in res_57.reply.lower())

    def test_cy02_supported_sizes_and_width(self):
        """CY-02 supports 4x6 and 6x8 with 6-inch max width. 5x7 and 6x9 are unsupported."""
        res_sizes = product_spec_engine.answer_single_attribute("citizen-cy-02", "What paper sizes does CY-02 support?")
        self.assertIsNotNone(res_sizes)
        self.assertIn("4×6", res_sizes.reply)
        self.assertIn("6×8", res_sizes.reply)
        self.assertIn("not supported", res_sizes.reply.lower())

        # Check repository product data directly
        prod = catalog_repository.get_by_id("citizen-cy-02")
        self.assertIsNotNone(prod)
        self.assertIn("4x6", prod.supported_print_sizes)
        self.assertIn("6x8", prod.supported_print_sizes)
        self.assertNotIn("5x7", prod.supported_print_sizes)
        self.assertNotIn("6x9", prod.supported_print_sizes)

    def test_cy02_weight_and_dimensions(self):
        """CY-02 net weight is 13.8 kg (excluding media) and package shipping weight is 16.5 kg."""
        res_wt = product_spec_engine.answer_single_attribute("citizen-cy-02", "What is the weight and dimensions of the CY-02?")
        self.assertIsNotNone(res_wt)
        self.assertIn("13.8", res_wt.reply)
        self.assertIn("16.5", res_wt.reply)
        self.assertIn("32.2 × 35.1 × 28.1", res_wt.reply)

    def test_cy02_capacity_per_roll_and_box(self):
        """CY-02 yields 700 prints/roll (1,400/box) for 4x6 and 350 prints/roll (700/box) for 6x8."""
        res_cap = product_spec_engine.answer_single_attribute("citizen-cy-02", "What is the roll capacity of the Citizen CY-02?")
        self.assertIsNotNone(res_cap)
        self.assertIn("700", res_cap.reply)
        self.assertIn("1,400", res_cap.reply)
        self.assertIn("350", res_cap.reply)
        self.assertIn("700", res_cap.reply)
        self.assertNotIn("5×7", res_cap.reply.split("*(Note")[0])

    # ── 2. Cost-Per-Print Calculations ───────────────────────────────────────

    def test_cy02_cost_per_print_arithmetic(self):
        """CY-02 4x6 media (CY-MS46) costs 625 AED for 1,400 prints = 0.45 AED/print."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cy-02", print_format="4x6")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.package_yield_prints, 1400)
        self.assertEqual(res.package_price_aed, 625.0)
        self.assertEqual(res.cost_per_print_aed, 0.45)
        self.assertEqual(res.consumable_sku, "CY-MS46")

    def test_cy02_6x8_cost_per_print_arithmetic(self):
        """CY-02 6x8 media (CY-MS68) costs 685 AED for 700 prints = 0.98 AED/print."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cy-02", print_format="6x8")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.package_yield_prints, 700)
        self.assertEqual(res.package_price_aed, 685.0)
        self.assertEqual(res.cost_per_print_aed, 0.98)
        self.assertEqual(res.consumable_sku, "CY-MS68")

    def test_cy02_5x7_cost_per_print_fails_cleanly(self):
        """CY-02 5x7 cost per print returns unsupported format because CY-02 does not print 5x7."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cy-02", print_format="5x7")
        self.assertEqual(res.status, "unsupported_format")
        self.assertIn("does not support", res.explanation.lower())

    def test_cx02_cost_per_print_arithmetic(self):
        """CX-02 4x6 media (CX2.4x6) costs 490 AED for 800 prints = 0.61 AED/print."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cx-02", print_format="4x6")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.package_yield_prints, 800)
        self.assertEqual(res.package_price_aed, 490.0)
        self.assertEqual(res.cost_per_print_aed, 0.61)

    def test_cx02w_cost_per_print_arithmetic(self):
        """CX-02W 8x12 media (CX2W 812) costs 975 AED for 220 prints = 4.43 AED/print."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cx-02w", print_format="8x12")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.package_yield_prints, 220)
        self.assertEqual(res.package_price_aed, 975.0)
        self.assertEqual(res.cost_per_print_aed, 4.43)

    def test_cz01_cost_per_print_arithmetic(self):
        """CZ-01 4x6 media (CZ-MS46) costs 295 AED for 300 prints = 0.98 AED/print."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cz-01", print_format="4x6")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.package_yield_prints, 300)
        self.assertEqual(res.package_price_aed, 295.0)
        self.assertEqual(res.cost_per_print_aed, 0.98)

    def test_inkjet_insufficient_data_status(self):
        """For inkjets without full photo ink coverage data (e.g. SC-P900), cost per print states insufficient verified data."""
        res = cost_per_print_calculator.calculate_cost_per_print("epson-sc-p900", print_format="8x10")
        self.assertEqual(res.status, "insufficient_verified_data")
        self.assertIn("cannot be verified from the available data", res.explanation)

    # ── 3. Consumable Registry & Compatibility ───────────────────────────────

    def test_consumable_registry_isolation(self):
        """CY-MS46 is compatible only with CY-02; CX-02 media is incompatible with CY-02."""
        # CY-MS46 on CY-02 -> yes
        stat1, exp1 = consumable_registry.check_sku_compatibility("CY-MS46", "citizen-cy-02")
        self.assertEqual(stat1, "yes")

        # CY-MS46 on CX-02 -> no
        stat2, exp2 = consumable_registry.check_sku_compatibility("CY-MS46", "citizen-cx-02")
        self.assertEqual(stat2, "no")

        # CX2.4x6 on CY-02 -> no
        stat3, exp3 = consumable_registry.check_sku_compatibility("CX2.4X6", "citizen-cy-02")
        self.assertEqual(stat3, "no")

        # CX2W 812 on CZ-01 -> no
        stat4, exp4 = consumable_registry.check_sku_compatibility("CX2W 812", "citizen-cz-01")
        self.assertEqual(stat4, "no")

        # Unknown SKU -> unverified
        stat5, exp5 = consumable_registry.check_sku_compatibility("UNKNOWN-SKU-999", "citizen-cy-02")
        self.assertEqual(stat5, "unverified")

    def test_consumable_filtering_ink_only(self):
        """'Show only ink cartridges, no paper or maintenance boxes' returns only ink cartridges."""
        state = ConversationState(session_id="test-ink-isolation")
        turn = self.orchestrator.process_turn(
            "Show only ink cartridges for Epson SC-P900, no paper or maintenance boxes",
            state=state
        )
        c_cards = turn.get("consumable_cards", [])
        self.assertTrue(len(c_cards) > 0)
        for card in c_cards:
            cat = str(card.get("category", "")).lower()
            title = (card.get("title", "") + " " + card.get("name", "")).lower()
            self.assertIn("ink", cat)
            self.assertNotIn("maintenance", cat)
            self.assertNotIn("maintenance", title)
            self.assertNotIn("paper", cat)
            self.assertNotIn("roll", title)

    # ── 4. Multi-Attribute Query Handling ────────────────────────────────────

    def test_multi_attribute_weight_and_speed(self):
        """Asking for weight and print speed produces labelled bullets for each."""
        state = ConversationState(session_id="test-multi-attr")
        turn = self.orchestrator.process_turn(
            "What is the print speed and weight of the Citizen CY-02?",
            state=state
        )
        reply = turn.get("reply", "")
        self.assertIn("Print Speed:", reply)
        self.assertIn("12.4 seconds", reply)
        self.assertIn("Weight:", reply)
        self.assertIn("13.8 kg", reply)
        self.assertNotIn("19.9 seconds", reply)

    def test_all_catalog_printers_have_verified_weights(self):
        """All approved hardware printers have non-null, non-empty verified weights."""
        all_prods = [p for p in catalog_repository.get_all() if p.entity_type == "printer"]
        self.assertGreaterEqual(len(all_prods), 35)
        for p in all_prods:
            weight = p.verified.weight
            self.assertIsNotNone(weight, f"Product {p.id} must have verified weight")
            self.assertTrue(len(str(weight).strip()) > 0, f"Product {p.id} weight must not be empty")

    # ── 5. Continuous Photo-Booth Multi-Turn Session ─────────────────────────

    def test_continuous_photobooth_switching_session(self):
        """Continuous multi-turn conversation switching among CY-02, CX-02, and CX-02W without cross-contamination."""
        state = ConversationState(session_id="test-continuous-pb")

        # Turn 1: Inquire about high-capacity photo booth printer
        t1 = self.orchestrator.process_turn("I need a high-capacity photo booth printer for heavy event volume. What fits?", state=state)
        p_cards1 = t1.get("product_cards", [])
        reply1 = t1.get("reply", "")
        self.assertTrue(any("cy-02" in (c.get("id") or "").lower() for c in p_cards1) or "CY-02" in reply1)

        # Turn 2: Ask specifically about CY-02 weight and print sizes
        t2 = self.orchestrator.process_turn("What is the weight and supported print sizes for the CY-02?", state=state)
        reply2 = t2.get("reply", "")
        self.assertIn("13.8 kg", reply2)
        self.assertIn("4×6", reply2)
        self.assertIn("6×8", reply2)
        self.assertNotIn("5×7", reply2.split("Note")[0])

        # Turn 3: Ask for CY-02 cost per print
        t3 = self.orchestrator.process_turn("What is the per print cost for 4x6 photos on the CY-02?", state=state)
        reply3 = t3.get("reply", "")
        self.assertIn("0.45", reply3)
        self.assertIn("CY-MS46", reply3)
        self.assertIn("1,400", reply3)
        # Verify no printer selling price leaked
        self.assertNotIn("AED 3,400", reply3)

        # Turn 4: Switch to CX-02 for portability
        t4 = self.orchestrator.process_turn("What if I need something lighter for travel? How does the CX-02 compare in weight and speed?", state=state)
        reply4 = t4.get("reply", "")
        self.assertIn("12", reply4)  # 12.0 kg
        self.assertTrue("8.4" in reply4 or "9.8" in reply4)

        # Turn 5: Ask CX-02 media compatibility with CY-02
        t5 = self.orchestrator.process_turn("Can I use the CY-MS46 media roll in the CX-02?", state=state)
        reply5 = t5.get("reply", "")
        self.assertTrue("no" in reply5.lower() or "not compatible" in reply5.lower())

        # Turn 6: Switch to CX-02W for large prints
        t6 = self.orchestrator.process_turn("Can either of those print 8x12 photos? Does the CX-02W handle that?", state=state)
        reply6 = t6.get("reply", "")
        self.assertTrue("CX-02W" in reply6 or "cx-02w" in reply6.lower())
        self.assertIn("8×12", reply6)

        # Turn 7: Check CX-02W pack yield and per print cost
        t7 = self.orchestrator.process_turn("What is the per print cost and pack yield for 8x12 on the CX-02W?", state=state)
        reply7 = t7.get("reply", "")
        self.assertIn("4.43", reply7)
        self.assertIn("220", reply7)
        self.assertIn("CX2W 812", reply7)


if __name__ == "__main__":
    unittest.main()
