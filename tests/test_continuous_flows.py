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

        # Turn 4: Answer scanner -> Yes, with Scanner (streamlined flow resolves immediately)
        r4 = orchestrator.process_turn("Yes, with Scanner", state=state)
        self.assertIs(state.requirements.get("scanner_required"), True)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("type"), "product_list")
        self.assertEqual(r4.get("subcategory"), "technical_36_multifunction")
        cards = r4.get("cards", [])
        self.assertTrue(len(cards) > 0)
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-t5100m", card_ids)
        self.assertIn("epson-sc-t5400m", card_ids)
        self.assertNotIn("epson-sc-t5100", card_ids)

    def test_flow_2_cad_24_inch_print_only(self):
        """Vague -> CAD -> 24-inch -> completes qualification immediately (all 24-inch CAD models are print-only) -> SC-T3100, SC-T3700E/D/DE."""
        state = ConversationState(session_id="flow-2-cad-24-print")

        # Turn 1
        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        # Turn 2: CAD
        r2 = orchestrator.process_turn("CAD Drawings", state=state)
        self.assertEqual(state.category, "technical_large_format")
        self.assertEqual(state.awaiting_field, "print_width")

        # Turn 3: 24-inch (A1) -> completes qualification
        r3 = orchestrator.process_turn("24-inch (A1)", state=state)
        self.assertEqual(state.requirements.get("print_width"), 24)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r3.get("subcategory"), "technical_24_print_only")
        card_ids = [c["id"] for c in r3.get("cards", [])]
        self.assertIn("epson-sc-t3100", card_ids)
        self.assertIn("epson-sc-t3700d", card_ids)

    def test_flow_3_cad_44_inch_print_only(self):
        """Vague -> CAD -> 44-inch -> print only -> SC-T7700D."""
        state = ConversationState(session_id="flow-3-cad-44-print")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        r2 = orchestrator.process_turn("CAD Drawings", state=state)
        r3 = orchestrator.process_turn("44-inch Wide", state=state)
        r4 = orchestrator.process_turn("No, Print Only", state=state)

        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "technical_44_print_only")
        card_ids = [c["id"] for c in r4.get("cards", [])]
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

    def test_flow_7_photo_compact_epson(self):
        """Vague -> Photo -> Compact -> Epson -> SC-P700, SC-P900, SC-P5300."""
        state = ConversationState(session_id="flow-7-photo-compact-epson")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        self.assertEqual(state.category, "photography_large_format")
        self.assertEqual(state.awaiting_field, "photo_form_factor")

        r3 = orchestrator.process_turn("Compact (Desktop / Portable)", state=state)
        self.assertEqual(state.awaiting_field, "photo_brand")

        r4 = orchestrator.process_turn("Epson Desktop (Fine Art / A3+ / A2+)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "photo_compact_epson")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertIn("epson-sc-p700", card_ids)
        self.assertIn("epson-sc-p900", card_ids)
        self.assertIn("epson-sc-p5300", card_ids)

    def test_flow_8_photo_compact_citizen(self):
        """Vague -> Photo -> Compact -> Citizen -> CZ-01, CX-02, CY-02, CX-02W."""
        state = ConversationState(session_id="flow-8-photo-compact-citizen")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        self.assertEqual(state.category, "photography_large_format")
        self.assertEqual(state.awaiting_field, "photo_form_factor")

        r3 = orchestrator.process_turn("Compact (Desktop / Portable)", state=state)
        self.assertEqual(state.awaiting_field, "photo_brand")

        r4 = orchestrator.process_turn("Citizen (Photo Booth / Events)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r4.get("subcategory"), "citizen_photo")
        card_ids = [c["id"] for c in r4.get("cards", [])]
        self.assertEqual(len(card_ids), 4)
        self.assertIn("citizen-cx-02", card_ids)
        self.assertIn("citizen-cz-01", card_ids)

    def test_flow_9_photo_large_format_send_all(self):
        """Vague -> Photo -> Large Format -> All 10 Epson large-format models returned immediately."""
        state = ConversationState(session_id="flow-9-photo-large")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Professional Photographs", state=state)
        self.assertEqual(state.category, "photography_large_format")
        self.assertEqual(state.awaiting_field, "photo_form_factor")

        r3 = orchestrator.process_turn("Large Format (24″ to 64″)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(r3.get("subcategory"), "photo_large_format")
        card_ids = [c["id"] for c in r3.get("cards", [])]
        self.assertTrue(len(card_ids) >= 8)
        self.assertIn("epson-sc-p6500e", card_ids)
        self.assertIn("epson-sc-p7500", card_ids)
        self.assertIn("epson-sc-p8500d", card_ids)
        self.assertIn("epson-sc-p9500", card_ids)
        self.assertIn("epson-sc-p20500", card_ids)

    def test_flow_10_citizen_photo_6_inch(self):
        """Vague -> Citizen Event -> 4x6 & 6x8 -> volume -> CX-02, CY-02, CZ-01."""
        state = ConversationState(session_id="flow-10-citizen-6")

        r1 = orchestrator.process_turn("I need a printer", state=state)
        self.assertEqual(state.awaiting_field, "category")

        r2 = orchestrator.process_turn("Event Photos (Photo Booth)", state=state)
        self.assertEqual(state.category, "citizen_photo")
        self.assertTrue(state.qualification_complete)
        self.assertEqual(len(r2.get("cards", [])), 4)

        r3 = orchestrator.process_turn("Standard 4x6 & 6x8", state=state)
        self.assertIn("4x6", state.requirements.get("print_sizes", []))

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


    def test_flow_photo_bare_13_and_17(self):
        """Typing bare '13' or '17' directly answers photo printer width without repeating question."""
        # Test bare 13 -> SC-P700
        state13 = ConversationState(session_id="bare-13-test")
        r1 = orchestrator.process_turn("i need a photo printer", state=state13)
        self.assertIn("compact", r1.get("reply", "").lower())
        r2 = orchestrator.process_turn("13", state=state13)
        card_ids_13 = [c["id"] for c in r2.get("product_cards", [])]
        self.assertEqual(card_ids_13, ["epson-sc-p700"])

        # Test bare 17 -> SC-P900 & SC-P5300
        state17 = ConversationState(session_id="bare-17-test")
        orchestrator.process_turn("i need a photo printer", state=state17)
        r4 = orchestrator.process_turn("17", state=state17)
        card_ids_17 = [c["id"] for c in r4.get("product_cards", [])]
        self.assertIn("epson-sc-p900", card_ids_17)
        self.assertIn("epson-sc-p5300", card_ids_17)

    def test_flow_photo_bare_large(self):
        """Typing bare 'large' answers photo printer form factor and returns all 8 large-format photo models."""
        state = ConversationState(session_id="bare-large-test")
        orchestrator.process_turn("i need a photo printer", state=state)
        res = orchestrator.process_turn("large", state=state)
        card_ids = [c["id"] for c in res.get("product_cards", [])]
        self.assertTrue(len(card_ids) >= 8)
        self.assertIn("epson-sc-p6500e", card_ids)
    def test_flow_cad_bare_24(self):
        """Typing bare '24' completes qualification directly since all 24-inch CAD models are print-only."""
        state_24 = ConversationState(session_id="cad-24-test")
        orchestrator.process_turn("I need a CAD printer", state=state_24)
        r2 = orchestrator.process_turn("24", state=state_24)
        self.assertTrue(state_24.qualification_complete)
        card_ids = [c["id"] for c in r2.get("cards", []) or r2.get("product_cards", [])]
        self.assertIn("epson-sc-t3100", card_ids)
        self.assertIn("epson-sc-t3700d", card_ids)

    def test_flow_model_switch_and_media_consumables_isolation(self):
        """User compares Citizen, asks for media for cy02, then asks for SC-P700, then ink.
        Must isolate consumables to SC-P700 and not bleed Citizen CY-02."""
        state = ConversationState(session_id="model-switch-consumables-test")

        # Turn 1: Compare Citizen models
        r1 = orchestrator.process_turn("Compare Citizen CX-02 and Citizen CY-02", state=state)
        self.assertEqual(r1.get("source"), "route:comparison")

        # Turn 2: Media for cy02 -> must route to consumables, not hardware specs
        r2 = orchestrator.process_turn("media for cy02?", state=state)
        self.assertEqual(r2.get("source"), "route:consumables")
        self.assertIn("CY-02", r2.get("reply", ""))
        self.assertIn("CY-MS46", r2.get("reply", ""))
        self.assertEqual(len(r2.get("consumable_cards", [])), 2)

        # Turn 3: User inquires about SC-P700
        r3 = orchestrator.process_turn("i need scp700", state=state)
        self.assertEqual(r3.get("source"), "route:model_detail")
        self.assertEqual(state.active_product_id, "epson-sc-p700")

        # Turn 4: User asks for ink -> MUST return SC-P700 UltraChrome Pro10 inks, NOT Citizen
        r4 = orchestrator.process_turn("ink?", state=state)
        self.assertEqual(r4.get("source"), "route:consumables")
        self.assertIn("SC-P700", r4.get("reply", ""))
        self.assertNotIn("CY-02", r4.get("reply", ""))
        card_skus = [c.get("sku") for c in r4.get("consumable_cards", [])]
        self.assertIn("C13T46S100", card_skus)

    def test_flow_em_c800_consumables_typo_query(self):
        """User inquiry 'check the consubales for em c800' must return genuine EM-C800R inks."""
        state = ConversationState(session_id="test-flow-em-c800")
        res = orchestrator.process_turn("check the consubales for em c800", state=state)
        self.assertEqual(res.get("source"), "route:consumables")
        self.assertIn("EM-C800", res.get("reply", ""))
        self.assertIn("C13T11N140", res.get("reply", ""))
        card_skus = [c.get("sku") for c in res.get("consumable_cards", [])]
        self.assertIn("C13T11N140", card_skus)
        self.assertIn("C12C938211", card_skus)


if __name__ == "__main__":
    unittest.main()

