"""
Targeted Test Suite for Kepler Tech SalesAI Requirement Flow Categories.
Validates the four approved product categories and their colloquial/industry aliases:
1. Office / Business Printers (A3 / A4)
2. Technical Large Format / CAD / Plotters (including 'plottaer')
3. Photo & Fine Art Large Format
4. Dye-Sublimation Printers (SC-F100 & SC-F500, including T-Shirt printing)
"""
import unittest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator
from conversation.normalizer import normalize_category, extract_deterministic_requirements
from catalog.subcategory_resolver import resolve_subcategory
from catalog.catalogue_loader import catalogue_loader


class TestRequirementFlowCategories(unittest.TestCase):

    def setUp(self):
        catalogue_loader.load_and_validate()

    # ── 1. Office / Business / A3 or A4 Printers ─────────────────────────────

    def test_office_business_printer_category_detection(self):
        """'business printer' and 'business printing' must normalize to office_printer."""
        self.assertEqual(normalize_category("I need a business printer"), "office_printer")
        self.assertEqual(normalize_category("Looking for business printing solutions"), "office_printer")
        self.assertEqual(normalize_category("Need a business MFP"), "office_printer")
        self.assertEqual(normalize_category("Show me A3 or A4 printers"), "office_printer")
        self.assertEqual(normalize_category("I need an A4 printer for documents"), "office_printer")

    def test_office_business_qualification_turn(self):
        """'I need a business printer' must prompt for paper size (A4 vs A3)."""
        state = ConversationState(session_id="test-rf-biz-1")
        res = orchestrator.process_turn("I need a business printer", state=state)
        self.assertEqual(state.category, "office_printer")
        self.assertEqual(state.awaiting_field, "paper_size")
        self.assertIn("A4", res.get("reply", ""))
        self.assertIn("A3", res.get("reply", ""))

    def test_business_a4_recommendation_flow(self):
        """'A4 business printer with 200 pages daily volume' returns 4 A4 models."""
        state = ConversationState(session_id="test-rf-biz-a4")
        res = orchestrator.process_turn(
            "I need an A4 business colour multifunction printer with 200 pages daily volume",
            state=state
        )
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 4)
        card_ids = set(c["id"] for c in cards)
        self.assertEqual(card_ids, {"epson-wf-c5890-dwf", "epson-em-c800", "epson-am-c400", "epson-am-c550"})

    # ── 2. Technical / CAD / Plotters ────────────────────────────────────────

    def test_technical_cad_and_plottaer_category_detection(self):
        """'plottaer', 'plotter', and 'cad' must normalize to technical_large_format."""
        self.assertEqual(normalize_category("I need a plottaer"), "technical_large_format")
        self.assertEqual(normalize_category("Looking for a CAD printer"), "technical_large_format")
        self.assertEqual(normalize_category("We need an architectural plotter"), "technical_large_format")
        self.assertEqual(normalize_category("Technical printer for blueprints"), "technical_large_format")

    def test_plottaer_qualification_turn(self):
        """'I need a plottaer' must prompt for print width / size."""
        state = ConversationState(session_id="test-rf-plottaer-1")
        res = orchestrator.process_turn("I need a plottaer", state=state)
        self.assertEqual(state.category, "technical_large_format")
        self.assertEqual(state.awaiting_field, "print_width")
        self.assertIn("24-inch", res.get("reply", ""))

    def test_technical_flow_inches_then_scanner_no_daily_volume(self):
        """Technical flow must first ask inches, then scanner, and classify without asking daily volume."""
        state = ConversationState(session_id="test-rf-tech-flow")
        
        # Turn 1: User asks for CAD printer -> Assistant asks inches (print_width)
        res1 = orchestrator.process_turn("I need a CAD printer", state=state)
        self.assertEqual(state.category, "technical_large_format")
        self.assertEqual(state.awaiting_field, "print_width")
        self.assertIn("24-inch", res1.get("reply", ""))
        self.assertIn("36-inch", res1.get("reply", ""))
        self.assertEqual(len(res1.get("cards", [])), 0)

        # Turn 2: User specifies inches ("36-inch") -> Assistant asks scanner required or not
        res2 = orchestrator.process_turn("36-inch", state=state)
        self.assertEqual(state.awaiting_field, "scanner_required")
        self.assertIn("scanner", res2.get("reply", "").lower())
        self.assertEqual(len(res2.get("cards", [])), 0)

        # Turn 3: User specifies scanner ("Yes, with scanner") -> Classifies immediately to technical_36_multifunction, NO daily volume asked
        res3 = orchestrator.process_turn("Yes, with scanner", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertIsNone(state.awaiting_field)
        self.assertEqual(res3.get("subcategory"), "technical_36_multifunction")
        cards = res3.get("cards", [])
        self.assertEqual(len(cards), 3)
        self.assertEqual(set(c["id"] for c in cards), {"epson-sc-t5100m", "epson-sc-t5400m", "epson-sc-t5700dm"})

    def test_technical_flow_direct_inches_and_scanner_returns_immediately(self):
        """When inches and scanner are provided upfront, returns matching cards immediately without asking volume."""
        state = ConversationState(session_id="test-rf-direct-cad")
        res = orchestrator.process_turn("I need a 44-inch CAD printer without scanner", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(res.get("subcategory"), "technical_44_print_only")
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 2)
        self.assertEqual(set(c["id"] for c in cards), {"epson-sc-t7700d", "epson-sc-t7700dl"})

    # ── 3. Photo & Fine-Art Printers ─────────────────────────────────────────

    def test_photo_fine_art_category_detection(self):
        """'fine art' and 'photo printer' must normalize to photography_large_format."""
        self.assertEqual(normalize_category("I need a fine art printer"), "photography_large_format")
        self.assertEqual(normalize_category("Looking for a professional photo printer"), "photography_large_format")
        self.assertEqual(normalize_category("Fine-art gallery printer"), "photography_large_format")

    def test_fine_art_qualification_turn(self):
        """'I need a photo printer' must prompt for compact vs large format."""
        state = ConversationState(session_id="test-rf-fineart-1")
        res = orchestrator.process_turn("I need a photo printer", state=state)
        self.assertEqual(state.category, "photography_large_format")
        self.assertEqual(state.awaiting_field, "photo_form_factor")
        chips = res.get("suggested_chips", [])
        self.assertIn("Compact (Desktop / Portable)", chips)
        self.assertIn("Large Format (24″ to 64″)", chips)

    def test_photo_large_format_sends_all_large_models(self):
        """Selecting large format returns all 10 large-format Epson models immediately."""
        state = ConversationState(session_id="test-rf-large-all")
        orchestrator.process_turn("I need a photo printer", state=state)
        res = orchestrator.process_turn("Large Format (24″ to 64″)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(res.get("subcategory"), "photo_large_format")
        cards = res.get("cards", [])
        self.assertTrue(len(cards) >= 8)  # 8 grouped cards covering 10 models
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-p6500e", card_ids)
        self.assertIn("epson-sc-p7500", card_ids)
        self.assertIn("epson-sc-p8500d", card_ids)
        self.assertIn("epson-sc-p9500", card_ids)
        self.assertIn("epson-sc-p20500", card_ids)

    def test_photo_compact_epson_recommendation(self):
        """Selecting compact then Epson returns SC-P700, SC-P900, SC-P5300."""
        state = ConversationState(session_id="test-rf-compact-epson")
        orchestrator.process_turn("I need a photo printer", state=state)
        res_compact = orchestrator.process_turn("Compact (Desktop / Portable)", state=state)
        self.assertEqual(state.awaiting_field, "photo_brand")
        res = orchestrator.process_turn("Epson Desktop (Fine Art / A3+ / A2+)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(res.get("subcategory"), "photo_compact_epson")
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 3)
        self.assertEqual(set(c["id"] for c in cards), {"epson-sc-p700", "epson-sc-p900", "epson-sc-p5300"})

    def test_photo_compact_citizen_recommendation(self):
        """Selecting compact then Citizen returns all 4 Citizen models."""
        state = ConversationState(session_id="test-rf-compact-citizen")
        orchestrator.process_turn("I need a photo printer", state=state)
        orchestrator.process_turn("Compact (Desktop / Portable)", state=state)
        res = orchestrator.process_turn("Citizen (Photo Booth / Events)", state=state)
        self.assertTrue(state.qualification_complete)
        self.assertEqual(res.get("subcategory"), "citizen_photo")
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 4)
        self.assertEqual(set(c["id"] for c in cards), {"citizen-cz-01", "citizen-cx-02", "citizen-cy-02", "citizen-cx-02w"})

    # ── 4. Sublimation & T-Shirt Printers (SC-F100 & SC-F500) ────────────────

    def test_sublimation_and_tshirt_category_detection(self):
        """Sublimation, F100, F500, and T-shirt printing must normalize to dye_sublimation."""
        self.assertEqual(normalize_category("I need a sublimation printer"), "dye_sublimation")
        self.assertEqual(normalize_category("Looking for t shirt printing"), "dye_sublimation")
        self.assertEqual(normalize_category("I need a t-shirt printer"), "dye_sublimation")
        self.assertEqual(normalize_category("Do you have the F100?"), "dye_sublimation")
        self.assertEqual(normalize_category("Tell me about the SC-F500"), "dye_sublimation")
        self.assertEqual(normalize_category("Printer for mugs and merchandise"), "dye_sublimation")

    def test_sublimation_qualification_turn(self):
        """'I need a sublimation printer' must prompt for format (A4 desktop vs 24-inch roll)."""
        state = ConversationState(session_id="test-rf-sub-qual")
        res = orchestrator.process_turn("I need a sublimation printer", state=state)
        self.assertEqual(state.category, "dye_sublimation")
        self.assertEqual(state.awaiting_field, "paper_size")
        self.assertIn("SC-F100", res.get("reply", ""))
        self.assertIn("SC-F500", res.get("reply", ""))

    def test_t_shirt_printing_qualification_turn(self):
        """'I need a printer for t shirt printing' must prompt for format with F100 / F500 options."""
        state = ConversationState(session_id="test-rf-tshirt-qual")
        res = orchestrator.process_turn("I need a printer for t shirt printing", state=state)
        self.assertEqual(state.category, "dye_sublimation")
        self.assertEqual(state.awaiting_field, "paper_size")
        chips = res.get("suggested_chips", [])
        self.assertTrue(any("F100" in c for c in chips))
        self.assertTrue(any("F500" in c for c in chips))

    def test_sc_f100_sublimation_recommendation(self):
        """A4 desktop sublimation printer with daily volume returns Epson SureColor SC-F100."""
        state = ConversationState(session_id="test-rf-f100")
        # Turn 1: Specify size and application -> asks daily volume
        res1 = orchestrator.process_turn("I need an A4 desktop sublimation printer for mugs", state=state)
        self.assertEqual(state.awaiting_field, "daily_volume")
        self.assertEqual(len(res1.get("cards", [])), 0)

        # Turn 2: Provide daily volume -> returns F100 card
        res2 = orchestrator.process_turn("50 prints daily", state=state)
        cards = res2.get("cards", [])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "epson-sc-f100")
        self.assertEqual(res2.get("subcategory"), "dye_sublimation_desktop")
        self.assertTrue(state.qualification_complete)

    def test_sc_f500_sublimation_recommendation(self):
        """24-inch sublimation roll inquiry for T-shirts with daily volume returns Epson SureColor SC-F500."""
        state = ConversationState(session_id="test-rf-f500")
        # Turn 1: Specify size and t-shirt apparel application -> asks daily volume
        res1 = orchestrator.process_turn(
            "I need a 24-inch sublimation roll printer for t-shirt and apparel printing",
            state=state
        )
        self.assertEqual(state.awaiting_field, "daily_volume")
        self.assertEqual(len(res1.get("cards", [])), 0)

        # Turn 2: Provide daily volume -> returns F500 card
        res2 = orchestrator.process_turn("40 prints daily", state=state)
        cards = res2.get("cards", [])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "epson-sc-f500")
        self.assertEqual(res2.get("subcategory"), "dye_sublimation_24_inch")
        self.assertTrue(state.qualification_complete)

    def test_direct_f100_inquiry(self):
        """Direct inquiry for F100 returns product card and specifications."""
        state = ConversationState(session_id="test-rf-f100-direct")
        res = orchestrator.process_turn("Tell me about the Epson F100", state=state)
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "epson-sc-f100")

    def test_direct_f500_inquiry(self):
        """Direct inquiry for F500 returns product card and specifications."""
        state = ConversationState(session_id="test-rf-f500-direct")
        res = orchestrator.process_turn("Tell me about the Epson F500", state=state)
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["id"], "epson-sc-f500")

    def test_p900_direct_inquiry_sends_both_configurations(self):
        """Direct inquiry for 'i need p900' sends both with and without roll adapter cards."""
        state = ConversationState(session_id="test-p900-both")
        res = orchestrator.process_turn("i need p900", state=state)
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 2)
        card_ids = [c["id"] for c in cards]
        self.assertEqual(card_ids, ["epson-sc-p900", "epson-sc-p900-roll"])
        self.assertIn("With Roll Adapter", res.get("suggested_chips", []))
        self.assertIn("Without Roll Adapter (Standard)", res.get("suggested_chips", []))

    def test_p900_followup_with_roll_adapter(self):
        """Follow-up 'i need with' after P900 selects the roll adapter configuration."""
        state = ConversationState(session_id="test-p900-with-followup")
        res1 = orchestrator.process_turn("i need p900", state=state)
        self.assertEqual(len(res1.get("cards", [])), 2)

        res2 = orchestrator.process_turn("i need with", state=state)
        cards2 = res2.get("cards", [])
        self.assertEqual(len(cards2), 1)
        self.assertEqual(cards2[0]["id"], "epson-sc-p900-roll")

    def test_p900_followup_without_roll_adapter(self):
        """Follow-up 'without roll adapter' after P900 selects the standard configuration."""
        state = ConversationState(session_id="test-p900-without-followup")
        res1 = orchestrator.process_turn("p900", state=state)
        self.assertEqual(len(res1.get("cards", [])), 2)

        res2 = orchestrator.process_turn("without roll adapter", state=state)
        cards2 = res2.get("cards", [])
        self.assertEqual(len(cards2), 1)
        self.assertEqual(cards2[0]["id"], "epson-sc-p900")

    def test_p900_direct_explicit_configurations(self):
        """Direct queries with explicit configuration return the single matching model."""
        state_roll = ConversationState(session_id="test-p900-dir-roll")
        res_roll = orchestrator.process_turn("i need p900 with roll adapter", state=state_roll)
        cards_roll = res_roll.get("cards", [])
        self.assertEqual(len(cards_roll), 1)
        self.assertEqual(cards_roll[0]["id"], "epson-sc-p900-roll")

        state_std = ConversationState(session_id="test-p900-dir-std")
        res_std = orchestrator.process_turn("i need p900 without roll adapter", state=state_std)
        cards_std = res_std.get("cards", [])
        self.assertEqual(len(cards_std), 1)
        self.assertEqual(cards_std[0]["id"], "epson-sc-p900")


if __name__ == "__main__":
    unittest.main()

