"""
Continuous Conversation Flow Test Suite for Kepler Tech SalesAI.
Tests the full conversational journey starting from a vague request ("I need a printer")
through step-by-step qualification to final product card delivery for every approved subcategory.
"""

import unittest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


class TestContinuousFlows(unittest.TestCase):

    def test_flow_1_cad_36_inch_with_scanner(self):
        """Vague -> CAD -> 36-inch -> with scanner -> volume -> SC-T5100M, SC-T5400M."""
        state = ConversationState(session_id="flow-1-cad-36-mfp")

        # Turn 1: Vague initial prompt
        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")
        self.assertFalse(state.qualification_complete)
        self.assertEqual(len(r1.get("cards", [])), 0)
        self.assertIn("primarily print", r1["message"])

        # Turn 2: Answer category -> CAD
        r2 = orchestrator.process_turn("Technical CAD Plotters", state=state)
        self.assertEqual(state.category, "technical_large_format")
        self.assertEqual(state.awaiting_field, "print_width")
        self.assertIn("width", r2["message"].lower())

        # Turn 3: Answer width -> 36-inch (A0)
        r3 = orchestrator.process_turn("36-inch (A0)", state=state)
        self.assertEqual(state.requirements.get("print_width"), 36)
        self.assertEqual(state.awaiting_field, "scanner_required")
        self.assertIn("scanner", r3["message"].lower())

        # Turn 4: Answer scanner -> Yes, with Scanner
        r4 = orchestrator.process_turn("Yes, with Scanner", state=state)
        self.assertIs(state.requirements.get("scanner_required"), True)
        self.assertEqual(state.awaiting_field, "daily_volume")
        self.assertIn("daily", r4["message"].lower())

        # Turn 5: Answer daily volume -> 20 to 30
        r5 = orchestrator.process_turn("20 to 30", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r5.get("type"), "product_list")
        self.assertEqual(r5.get("subcategory"), "technical_36_multifunction")
        cards = r5.get("cards", [])
        self.assertTrue(len(cards) > 0)
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-t5100m", card_ids)
        self.assertIn("epson-sc-t5400m", card_ids)
        self.assertNotIn("epson-sc-t5100", card_ids)

    def test_flow_2_cad_24_inch_print_only(self):
        """Vague -> CAD -> 24-inch (scanner skipped as all 24-inch CAD are print-only) -> volume -> SC-T3100, SC-T3700E/D/DE."""
        state = ConversationState(session_id="flow-2-cad-24-print")

        # Turn 1
        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        # Turn 2: CAD
        r2 = orchestrator.process_turn("CAD Drawings", state=state)
        self.assertEqual(state.category, "technical_large_format")
        self.assertEqual(state.awaiting_field, "print_width")

        # Turn 3: 24-inch (A1) -> scanner is skipped automatically
        r3 = orchestrator.process_turn("24-inch (A1)", state=state)
        self.assertEqual(state.requirements.get("print_width"), 24)
        self.assertEqual(state.awaiting_field, "daily_volume")

        # Turn 4: 10
        r4 = orchestrator.process_turn("10", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "technical_24_print_only")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-sc-t3100", card_ids)
        self.assertIn("epson-sc-t3700d", card_ids)

    def test_flow_3_cad_44_inch_print_only(self):
        """Vague -> CAD -> 44-inch -> print only -> volume -> SC-T7700D."""
        state = ConversationState(session_id="flow-3-cad-44-print")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("CAD Drawings", state=state)
        r3 = orchestrator.process_turn("44-inch Wide", state=state)
        r4 = orchestrator.process_turn("No, Print Only", state=state)
        r5 = orchestrator.process_turn("25", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r5.get("subcategory"), "technical_44_print_only")
        card_ids = [c["id"] for c in r5.get("cards", [])]
        self.assertIn("epson-sc-t7700d", card_ids)

    def test_flow_4_office_a4_colour_multifunction(self):
        """Vague -> Office -> A4 -> (colour & multifunction auto-satisfied) -> volume -> A4 Colour MFP."""
        state = ConversationState(session_id="flow-4-office-a4-mfp")

        # Turn 1
        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        # Turn 2: Office
        r2 = orchestrator.process_turn("Office Enterprise Documents", state=state)
        self.assertEqual(state.category, "office_printer")
        self.assertEqual(state.awaiting_field, "paper_size")

        # Turn 3: A4 -> colour_mode & functions are auto-satisfied (all 10 office are colour MFP)
        r3 = orchestrator.process_turn("A4 Standard", state=state)
        self.assertEqual(state.requirements.get("paper_size"), "a4")
        self.assertEqual(state.awaiting_field, "daily_volume")

        # Turn 4: 150
        r4 = orchestrator.process_turn("150", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "a4_colour_multifunction")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-wf-c5890-dwf", card_ids)
        self.assertIn("epson-am-c400", card_ids)

    def test_flow_5_office_a3_workforce_pro(self):
        """Vague -> Office -> A3 -> Low/Mid volume (80) -> WF-C878R/C879R."""
        state = ConversationState(session_id="flow-5-office-a3-wfpro")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Office Enterprise Documents", state=state)
        r3 = orchestrator.process_turn("A3 Large Format", state=state)
        self.assertEqual(state.awaiting_field, "daily_volume")
        r4 = orchestrator.process_turn("80", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "a3_workforce_pro_multifunction")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-wf-c878r-dwf", card_ids)
        self.assertIn("epson-wf-c879r-dwf", card_ids)

    def test_flow_6_office_a3_enterprise(self):
        """Vague -> Office -> A3 -> High volume (500) -> AM-C4000/C5000/C6000."""
        state = ConversationState(session_id="flow-6-office-a3-enterprise")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Office Enterprise Documents", state=state)
        r3 = orchestrator.process_turn("A3 Large Format", state=state)
        self.assertEqual(state.awaiting_field, "daily_volume")
        r4 = orchestrator.process_turn("500", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "a3_enterprise_multifunction")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-am-c4000", card_ids)
        self.assertIn("epson-am-c5000", card_ids)
        self.assertIn("epson-am-c6000", card_ids)

    def test_flow_correction_sorry_its_200(self):
        """Office A4 -> initial volume 50 (WorkForce Pro ranked first) -> 'sorry its 200' -> WorkForce Enterprise AM-C550/C400 ranked first."""
        state = ConversationState(session_id="flow-correction-200")

        r1 = orchestrator.process_turn("I need an A4 colour printer for office", state=state)
        r2 = orchestrator.process_turn("50", state=state)
        self.assertTrue(state.qualification_complete)
        card_ids_r2 = [c["id"] for c in r2.get("cards", [])]
        # At 50 pages/day, WorkForce Pro models are prioritized
        self.assertIn(card_ids_r2[0], ["epson-wf-c5890-dwf", "epson-em-c800"])

        # Customer corrects/updates volume: "sorry its 200"
        r3 = orchestrator.process_turn("sorry its 200", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertIn("updated your daily volume to 200", r3["message"].lower())
        self.assertIn("am-c400", r3["message"].lower())
        card_ids_r3 = [c["id"] for c in r3.get("cards", [])]
        # At 200 pages/day, WorkForce Enterprise line-head models (AM-C550 and AM-C400) MUST be ranked ahead of WorkForce Pro
        self.assertEqual(card_ids_r3[0], "epson-am-c550")
        self.assertEqual(card_ids_r3[1], "epson-am-c400")

    def test_flow_7_photo_13_inch_desktop(self):
        """Vague -> Photo -> 13-inch -> volume -> SC-P700."""
        state = ConversationState(session_id="flow-7-photo-13")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        self.assertEqual(state.category, "photography_large_format")
        self.assertEqual(state.awaiting_field, "print_width")

        r3 = orchestrator.process_turn("13-inch (A3+)", state=state)
        self.assertEqual(state.requirements.get("print_width"), 13)
        self.assertEqual(state.awaiting_field, "daily_volume")

        r4 = orchestrator.process_turn("10", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "photo_13_desktop")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertEqual(card_ids, ["epson-sc-p700"])

    def test_flow_8_photo_17_inch_desktop(self):
        """Vague -> Photo -> 17-inch -> volume -> SC-P900 (grouped config)."""
        state = ConversationState(session_id="flow-8-photo-17")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        r3 = orchestrator.process_turn("17-inch (A2+)", state=state)
        r4 = orchestrator.process_turn("20", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "photo_17_desktop")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-sc-p900", card_ids)
        p900 = next(c for c in r4["cards"] if c["id"] == "epson-sc-p900")
        self.assertTrue(len(p900.get("available_configurations", [])) >= 1)

    def test_flow_9_photo_44_inch_fine_art(self):
        """Vague -> Photo -> 44-inch -> volume -> SC-P8500D, SC-P9500."""
        state = ConversationState(session_id="flow-9-photo-44")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        r3 = orchestrator.process_turn("44-inch Fine Art", state=state)
        r4 = orchestrator.process_turn("15", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "photo_44_professional")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-sc-p8500d", card_ids)
        self.assertIn("epson-sc-p9500", card_ids)

    def test_flow_10_citizen_photo_6_inch(self):
        """Vague -> Citizen Event -> 4x6 & 6x8 -> volume -> CX-02, CY-02, CZ-01."""
        state = ConversationState(session_id="flow-10-citizen-6")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Event Photos (Photo Booth)", state=state)
        self.assertEqual(state.category, "citizen_photo")
        self.assertEqual(state.awaiting_field, "print_sizes")

        r3 = orchestrator.process_turn("Standard 4x6 & 6x8", state=state)
        self.assertIn("4x6", state.requirements.get("print_sizes", []))
        self.assertEqual(state.awaiting_field, "daily_volume")

        r4 = orchestrator.process_turn("300 prints", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "citizen_6_inch")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("citizen-cx-02", card_ids)
        self.assertIn("citizen-cy-02", card_ids)
        self.assertNotIn("citizen-cz-01", card_ids)
        self.assertNotIn("citizen-cx-02w", card_ids)

    def test_flow_11_citizen_photo_8_inch_wide(self):
        """Vague -> Citizen Event -> 8x10 & 8x12 -> volume -> CX-02W."""
        state = ConversationState(session_id="flow-11-citizen-8")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Event Photos (Photo Booth)", state=state)
        r3 = orchestrator.process_turn("Large 8x10 & 8x12", state=state)
        r4 = orchestrator.process_turn("100 prints", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "citizen_8_inch")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertEqual(card_ids, ["citizen-cx-02w"])

    def test_flow_12_citizen_photo_4_inch_compact(self):
        """Vague -> Citizen Event -> 4x4 / 4.5x8 -> volume -> CZ-01."""
        state = ConversationState(session_id="flow-12-citizen-4")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("Event Photos (Photo Booth)", state=state)
        r3 = orchestrator.process_turn("Compact 4x4 / 4.5x8", state=state)
        r4 = orchestrator.process_turn("50 prints", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "citizen_4_inch")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertEqual(card_ids, ["citizen-cz-01"])

    def test_flow_13_a3_print_only_relaxation_flow(self):
        """Office A3 print-only query must offer helpful relaxation and prevent false consumable routing."""
        state = ConversationState(session_id="flow-13-a3-print-only")

        r1 = orchestrator.process_turn("hello", state=state)
        r2 = orchestrator.process_turn("i need a printer", state=state)
        r3 = orchestrator.process_turn("i need a office printer", state=state)
        r4 = orchestrator.process_turn("i want a3", state=state)
        r5 = orchestrator.process_turn("print only", state=state)
        r6 = orchestrator.process_turn("i think its 30", state=state)

        # Confirm turn 6 does not false-trigger consumables via 'think'
        self.assertNotEqual(r6.get("source"), "route:consumables")
        self.assertEqual(r6.get("source"), "recommendation:no_match")
        self.assertIn("multifunction", r6.get("reply", "").lower())
        self.assertEqual(len(r6.get("product_cards", [])), 0)

        # Follow-up: relax multifunction requirement
        r7 = orchestrator.process_turn("yes multifunction a3 is fine", state=state)
        self.assertEqual(r7.get("source"), "recommendation:catalogue_list")
        card_ids = [c["id"] for c in r7.get("product_cards", [])]
        self.assertEqual(card_ids, ["epson-wf-c878r-dwf", "epson-wf-c879r-dwf"])

    def test_spaceless_model_detail_query(self):
        """Models typed without spaces/hyphens like WF-C5890DWF resolve to model detail."""
        state = ConversationState(session_id="spaceless-model-test")
        r = orchestrator.process_turn("ineeed WF-C5890DWF", state=state)
        self.assertEqual(r.get("source"), "route:model_detail")
        self.assertEqual(len(r.get("product_cards", [])), 1)
        self.assertEqual(r["product_cards"][0]["id"], "epson-wf-c5890-dwf")


if __name__ == "__main__":
    unittest.main()

