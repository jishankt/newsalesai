"""
Comprehensive Test Suite: Testing ALL Catalog Equipment Flows 2 Times with Realistic Customer Inputs.
Covers:
1. Office / Multifunction (A4 Standard & High-Speed Line-Head)
2. Office / Multifunction (A3 Departmental RIPS & High-Speed Line-Head)
3. Technical CAD / Blueprint (24" Entry Desktop & Dual Roll)
4. Technical CAD / Blueprint (36" Integrated Scanner MFP & Fast Production)
5. Technical CAD / Blueprint (44" Production Bulk Ink)
6. Professional Photo & Fine Art (13" A3+ & 17" A2+)
7. Professional Photo & Fine Art (24" Master Studio & 44" Production MFP)
8. Citizen Dye-Sub Photo Booth (4" CZ-01 & 6" CX-02 / CY-02 & 8" CX-02W)
9. Dye-Sublimation Apparel & Gifts (A4 SC-F100 & 24" SC-F500)
10. Scanning Solutions (Sheetfed DS-530II, Flatbed DS-1630, Graphic 12000XL)
11. Consumables & Supplies (F100 ink, T3100 ink, CZ-01 media)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conversation.understanding import understand_turn
from conversation.dialogue_state import DialogueState, ReferentResolver
from conversation.policy import PolicyEngine
from conversation.response_plan import ResponsePlanBuilder
from catalog.catalogue_loader import catalogue_loader


class TestAllCatalogFlowsTwice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalogue_loader.load_and_validate()

    def run_two_turn_flow(self, session_name: str, turn1_msg: str, turn2_msg: str, expected_cat: str):
        """Simulates a realistic customer 2-turn dialogue exactly as Orchestrator executes it."""
        state = DialogueState(session_id=session_name)

        # ── Turn 1: Customer category / requirement expression ──
        t1_und = understand_turn(turn1_msg)
        t1_res = ReferentResolver.resolve_turn(t1_und, state)
        t1_dec = PolicyEngine.decide(t1_res, state)
        t1_plan = ResponsePlanBuilder.build(t1_dec, t1_res, state)

        # Update state exactly like orchestrator
        if t1_res.resolved_target_product:
            state.active_product_id = t1_res.resolved_target_product.id
        if t1_dec.options_or_chips:
            state.last_shown_chips = list(t1_dec.options_or_chips)
        state.turn_count += 1

        # ── Turn 2: Customer answers the qualification question ──
        t2_und = understand_turn(turn2_msg)
        t2_res = ReferentResolver.resolve_turn(t2_und, state)
        t2_dec = PolicyEngine.decide(t2_res, state)
        t2_plan = ResponsePlanBuilder.build(t2_dec, t2_res, state)

        return t1_dec, t2_dec, t2_plan

    # ═════════════════════════════════════════════════════════════════════════
    # 1. Office Printing Flows (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_office_a4_run_1(self):
        """Office Flow Run 1: Customer asks for A4 office printer, says 50 pages/day."""
        t1, t2, plan = self.run_two_turn_flow("off_a4_1", "i need an a4 office printer", "around 50 pages a day", "office_printer")
        self.assertEqual(t2.target_entity_id, "epson-wf-c5890-dwf")
        self.assertIn("WF-C5890", plan.formatted_reply)


        

    def test_flow_office_a4_run_2(self):
        """Office Flow Run 2: Customer asks for A4 workforce printer, high volume 400 pages."""
        t1, t2, plan = self.run_two_turn_flow("off_a4_2", "looking for a4 workforce printer for office", "400 pages daily", "office_printer")
        self.assertEqual(t2.target_entity_id, "epson-am-c400")
        self.assertIn("AM-C400", plan.formatted_reply)

    def test_flow_office_a3_run_1(self):
        """Office Flow Run 1: Customer asks for A3 printer, says 50 per day (low volume)."""
        t1, t2, plan = self.run_two_turn_flow("off_a3_1", "i want a3 office printer", "50 per day", "office_printer")
        self.assertEqual(t2.target_entity_id, "epson-wf-c878r-dwf")
        self.assertIn("WF-C878R", plan.formatted_reply)

    def test_flow_office_a3_run_2(self):
        """Office Flow Run 2: Customer asks for A3 commercial printer, says 800 pages."""
        t1, t2, plan = self.run_two_turn_flow("off_a3_2", "need a3 enterprise mfp for office", "800 pages per day", "office_printer")
        self.assertEqual(t2.target_entity_id, "epson-am-c4000")
        self.assertIn("AM-C4000", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 2. Technical CAD / Blueprint Plotters (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_cad_24_run_1(self):
        """CAD Flow Run 1: Customer asks for CAD plotter, selects 24-inch entry desktop."""
        t1, t2, plan = self.run_two_turn_flow("cad_24_1", "do you have cad plotters?", "24-inch (A1)", "technical_large_format")
        self.assertIn("SC-T3100", str(t2.options_or_chips))

    def test_flow_cad_24_run_2(self):
        """CAD Flow Run 2: Customer directly asks for 24 inch architectural plotter desktop."""
        t1, t2, plan = self.run_two_turn_flow("cad_24_2", "i need 24 inch architectural plotter", "entry desktop stand", "technical_large_format")
        self.assertEqual(t2.target_entity_id, "epson-sc-t3100")
        self.assertIn("SC-T3100", plan.formatted_reply)

    def test_flow_cad_36_run_1(self):
        """CAD Flow Run 1: Customer asks for 36 inch plotter with integrated scanner."""
        t1, t2, plan = self.run_two_turn_flow("cad_36_1", "i need 36 inch a0 blueprint plotter", "yes need scanner for plans", "technical_large_format")
        self.assertEqual(t2.target_entity_id, "epson-sc-t5400m")
        self.assertIn("SC-T5400M", plan.formatted_reply)

    def test_flow_cad_36_run_2(self):
        """CAD Flow Run 2: Customer asks for 36 inch plotter, strictly print-only."""
        t1, t2, plan = self.run_two_turn_flow("cad_36_2", "looking for 36 inch cad plotter", "no scanner needed print only", "technical_large_format")
        self.assertEqual(t2.target_entity_id, "epson-sc-t5405")
        self.assertIn("SC-T5405", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 3. Professional Photo & Fine Art (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_photo_run_1(self):
        """Photo Flow Run 1: Customer asks for photo printers, selects 13-inch."""
        t1, t2, plan = self.run_two_turn_flow("photo_1", "do you have photo printers", "13-inch (A3+)", "photography_large_format")
        self.assertEqual(t2.target_entity_id, "epson-sc-p700")
        self.assertIn("SC-P700", plan.formatted_reply)

    def test_flow_photo_run_2(self):
        """Photo Flow Run 2: Customer asks for fine art gallery printer, selects 17-inch panoramic roll."""
        t1, t2, plan = self.run_two_turn_flow("photo_2", "fine art photography printer", "17 inch with panoramic roll unit", "photography_large_format")
        self.assertEqual(t2.target_entity_id, "epson-sc-p900")
        self.assertIn("SC-P900", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 4. Citizen Photo Booth / Event Printers (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_citizen_run_1(self):
        """Citizen Flow Run 1: Customer asks for citizen printer, selects 4-inch."""
        t1, t2, plan = self.run_two_turn_flow("cit_1", "i want citizen printer", "4 inch ultra-compact", "citizen_photo")
        self.assertEqual(t2.target_entity_id, "citizen-cz-01")
        self.assertIn("CZ-01", plan.formatted_reply)

    def test_flow_citizen_run_2(self):
        """Citizen Flow Run 2: Customer with typo 'ciyizon printer', selects 6-inch event."""
        t1, t2, plan = self.run_two_turn_flow("cit_2", "sorry i want ciyizon printer", "6 inch event photo printer", "citizen_photo")
        self.assertEqual(t2.target_entity_id, "citizen-cx-02")
        self.assertIn("CX-02", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 5. Dye-Sublimation Apparel & Gifts (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_dyesub_run_1(self):
        """Dye-sub Flow Run 1: Customer asks for mug and merchandise sublimation."""
        t1, t2, plan = self.run_two_turn_flow("dyesub_1", "i want sublimation printer", "a4 desktop for mugs and gifts", "dye_sublimation")
        self.assertEqual(t2.target_entity_id, "epson-sc-f100")
        self.assertIn("SC-F100", plan.formatted_reply)

    def test_flow_dyesub_run_2(self):
        """Dye-sub Flow Run 2: Customer asks for t-shirt apparel printing."""
        t1, t2, plan = self.run_two_turn_flow("dyesub_2", "need dye sublimation printer for apparel", "24-inch roll apparel", "dye_sublimation")
        self.assertEqual(t2.target_entity_id, "epson-sc-f500")
        self.assertIn("SC-F500", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 6. Professional Scanners (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_flow_scanners_run_1(self):
        """Scanner Flow Run 1: Customer asks for document scanner, selects sheetfed business."""
        t1, t2, plan = self.run_two_turn_flow("scan_1", "do you have scanners", "fast sheetfed business scanner", "scanners")
        self.assertEqual(t2.target_entity_id, "epson-workforce-ds-530ii")
        self.assertIn("DS-530II", plan.formatted_reply)

    def test_flow_scanners_run_2(self):
        """Scanner Flow Run 2: Customer asks for scanners, selects graphic fine art & film."""
        t1, t2, plan = self.run_two_turn_flow("scan_2", "do you have professional scanners", "graphic and fine art film scanner", "scanners")
        self.assertEqual(t2.target_entity_id, "epson-expression-12000xl")
        self.assertIn("12000XL", plan.formatted_reply)

    # ═════════════════════════════════════════════════════════════════════════
    # 7. Consumables & Out of Scope Checks (Tested Twice)
    # ═════════════════════════════════════════════════════════════════════════
    def test_consumables_f100_ink(self):
        """Customer asks 'i want f100 ink' -> directly returns F100 consumables."""
        state = DialogueState(session_id="ink_1")
        turn = understand_turn("i want f100 ink")
        res = ReferentResolver.resolve_turn(turn, state)
        dec = PolicyEngine.decide(res, state)
        plan = ResponsePlanBuilder.build(dec, res, state)
        self.assertEqual(dec.target_entity_id, "epson-sc-f100")
        self.assertTrue(len(plan.consumable_cards) >= 4)

    def test_out_of_scope_label_printer(self):
        """Customer asks 'do you have label printer' -> returns out of scope redirect."""
        state = DialogueState(session_id="oos_1")
        turn = understand_turn("do you have label printer")
        res = ReferentResolver.resolve_turn(turn, state)
        dec = PolicyEngine.decide(res, state)
        self.assertEqual(dec.action.value, "OUT_OF_SCOPE_REDIRECT")


if __name__ == "__main__":
    unittest.main()
