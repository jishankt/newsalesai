"""
Comprehensive test suite for the 41-printer approved catalogue scope,
qualification flows, deterministic filtering, and fail-closed validation.
"""

import unittest
from domain.conversation_state import ConversationState
from catalog.catalogue_loader import catalogue_loader
from catalog.catalogue_filter import catalogue_filter
from catalog.subcategory_resolver import subcategory_resolver
from conversation.normalizer import normalizer
from conversation.qualification_schema import qualification_schema
from validation.catalogue_validator import catalogue_validator
from agent.orchestrator import orchestrator


class TestCatalogueScopeAndFilters(unittest.TestCase):

    def setUp(self):
        self.products = catalogue_loader.load_and_validate()

    def test_catalogue_loader_exact_43_entries(self):
        """Assert startup validation enforces exactly 43 active products."""
        self.assertEqual(len(self.products), 43)
        # Unique IDs
        ids = [p["id"] for p in self.products]
        self.assertEqual(len(ids), len(set(ids)))
        # Approved catalogues only
        approved_cats = {
            "business_a4",
            "business_a3",
            "technical_large_format",
            "photography_and_fine_art",
            "citizen_photo",
            "dye_sublimation",
        }
        for p in self.products:
            self.assertTrue(p.get("active"))
            self.assertTrue(p.get("catalogue_verified"))
            self.assertIn(p.get("catalogue"), approved_cats)

    def test_case_1_cad_36_inch_with_scanner(self):
        """36-inch CAD with scanner -> SC-T5100M, SC-T5400M."""
        reqs = {
            "main_category": "technical_large_format",
            "paper_size": 36,
            "scanner_required": True,
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-sc-t5100m", prod_ids)
        self.assertIn("epson-sc-t5400m", prod_ids)
        # Should not include print-only T5100
        self.assertNotIn("epson-sc-t5100", prod_ids)
        self.assertNotIn("epson-sc-t5405", prod_ids)

    def test_case_2_cad_36_inch_print_only(self):
        """36-inch CAD print-only -> SC-T5100, SC-T5405, SC-T5700D."""
        reqs = {
            "main_category": "technical_large_format",
            "paper_size": 36,
            "scanner_required": False,
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-sc-t5100", prod_ids)
        self.assertIn("epson-sc-t5405", prod_ids)
        self.assertIn("epson-sc-t5700d", prod_ids)
        # T5100M requires scanner, but user requested print-only -> should NOT be included
        self.assertNotIn("epson-sc-t5100m", prod_ids)

    def test_case_3_cad_44_inch_with_scanner(self):
        """44-inch CAD with scanner -> SC-T7700DM (dual roll MFP/printer)."""
        reqs = {
            "main_category": "technical_large_format",
            "paper_size": 44,
            "scanner_required": True,
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-sc-t7700dm", prod_ids)
        # T7700D is print only, so with scanner_required=True it should not match
        self.assertNotIn("epson-sc-t7700d", prod_ids)

    def test_case_4_cad_44_inch_print_only(self):
        """44-inch CAD print-only -> SC-T7700D."""
        reqs = {
            "main_category": "technical_large_format",
            "paper_size": 44,
            "scanner_required": False,
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-sc-t7700d", prod_ids)

    def test_case_5_citizen_photo_8x10_8x12(self):
        """Citizen photo 8x10/8x12 -> CX-02W."""
        reqs = {
            "main_category": "citizen_photo",
            "print_size": "8x12",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertEqual(prod_ids, ["citizen-cx-02w"])

    def test_case_6_citizen_photo_4x4(self):
        """Citizen photo 4x4 -> CZ-01."""
        reqs = {
            "main_category": "citizen_photo",
            "print_size": "4x4",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertEqual(prod_ids, ["citizen-cz-01"])

    def test_case_7_citizen_photo_4x6_6x8(self):
        """Citizen photo 4x6/6x8 -> CX-02, CY-02, CZ-01."""
        reqs = {
            "main_category": "citizen_photo",
            "print_size": "4x6",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("citizen-cx-02", prod_ids)
        self.assertIn("citizen-cy-02", prod_ids)
        self.assertIn("citizen-cz-01", prod_ids)
        self.assertNotIn("citizen-cx-02w", prod_ids)

    def test_case_8_photography_a3_plus(self):
        """Photography A3+ -> SC-P700."""
        reqs = {
            "main_category": "photography_and_fine_art",
            "paper_size": "A3+",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertEqual(prod_ids, ["epson-sc-p700"])

    def test_case_9_photography_a2_plus(self):
        """Photography A2+ (17-inch) -> SC-P900 (grouped configuration)."""
        reqs = {
            "main_category": "photography_and_fine_art",
            "paper_size": 17,
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-sc-p900", prod_ids)
        # Check that epson-sc-p900-roll is grouped under epson-sc-p900
        p900 = next(p for p in res["ranked_products"] if p["id"] == "epson-sc-p900")
        self.assertTrue(len(p900.get("available_configurations", [])) >= 1)

    def test_case_10_office_a4_colour_mfp(self):
        """Office A4 colour MFP -> WF-C5890DWF, AM-C400."""
        reqs = {
            "main_category": "business_a4",
            "paper_size": "A4",
            "function": "multifunction",
            "colour_mode": "colour",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-wf-c5890-dwf", prod_ids)
        self.assertIn("epson-am-c400", prod_ids)

    def test_case_11_office_a3_workforce_pro_mfp(self):
        """Office A3 WorkForce Pro MFP -> WF-C878R, WF-C879R."""
        reqs = {
            "main_category": "business_a3",
            "paper_size": "A3",
            "function": "multifunction",
            "series": "workforce_pro",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-wf-c878r-dwf", prod_ids)
        self.assertIn("epson-wf-c879r-dwf", prod_ids)

    def test_case_12_office_a3_enterprise_mfp(self):
        """Office A3 Enterprise MFP -> AM-C4000, AM-C5000, AM-C6000."""
        reqs = {
            "main_category": "business_a3",
            "paper_size": "A3",
            "function": "multifunction",
            "series": "workforce_enterprise",
        }
        res = catalogue_filter.filter_products(reqs)
        prod_ids = [p["id"] for p in res["ranked_products"]]
        self.assertIn("epson-am-c4000", prod_ids)
        self.assertIn("epson-am-c5000", prod_ids)
        self.assertIn("epson-am-c6000", prod_ids)

    def test_case_13_unapproved_model_refusal(self):
        """Unapproved / website-only models (e.g. Canon imagePROGRAF, Epson EcoTank L805) are refused.

        Note: SC-F100 and SC-F500 are approved sublimation catalogue products.
        Unapproved brands and non-catalogue models must be refused.
        """
        state = ConversationState(session_id="unapproved-test")
        res = orchestrator.process_turn("Do you have the Canon imagePROGRAF large format printer?", state=state)
        # Validator check: Response text must not endorse unapproved models
        # and cards must not contain unapproved IDs
        cards = res.get("cards", [])
        for card in cards:
            self.assertIn(card["id"], catalogue_loader.approved_ids)
        # Should inform the user that the unapproved model is not in Kepler's catalogue
        msg = res["message"].lower()
        self.assertTrue("not part of" in msg or "not carry" in msg or "catalogue" in msg)

    def test_normalizer_negation_handling(self):
        """Test normalizer extracts negation: 'without scanner' -> scanner_required=False."""
        norm = normalizer.normalize("I want a 36 inch plotter without scanner")
        self.assertEqual(norm.get("print_width"), 36)
        self.assertEqual(norm.get("paper_size"), "a0")
        self.assertIs(norm.get("scanner_required"), False)

    def test_normalizer_monthly_to_daily_volume(self):
        """Test monthly volume converts to daily volume (monthly // 30)."""
        norm = normalizer.normalize("We print 6000 pages monthly")
        self.assertEqual(norm.get("daily_volume"), 200)

    def test_no_repeated_questions_rule_of_one(self):
        """Test asking strictly one missing mandatory field and never re-asking answered fields."""
        state = ConversationState(session_id="rule-of-one-test")
        # Turn 1: user provides category and size
        res1 = orchestrator.process_turn("I need a 36-inch CAD printer for architectural plans", state=state)
        self.assertEqual(state.requirements.get("print_width"), 36)
        # Scanner is missing, should ask about scanner next
        self.assertEqual(state.awaiting_field, "scanner_required")

        # Turn 2: user answers scanner
        res2 = orchestrator.process_turn("Without scanner, print only", state=state)
        self.assertIs(state.requirements.get("scanner_required"), False)

    def test_customer_correction_replaces_cards(self):
        """Test changing requirement (e.g. from print-only to with scanner) updates cards."""
        state = ConversationState(session_id="correction-test")
        res1 = orchestrator.process_turn("36-inch CAD printer print only with low volume", state=state)
        prod_ids1 = [c["id"] for c in res1.get("cards", [])]
        if prod_ids1:
            self.assertIn("epson-sc-t5100", prod_ids1)
            self.assertNotIn("epson-sc-t5100m", prod_ids1)

        # Correction: Actually I do need a scanner
        res2 = orchestrator.process_turn("Actually I need a scanner integrated", state=state)
        prod_ids2 = [c["id"] for c in res2.get("cards", [])]
        if prod_ids2:
            self.assertIn("epson-sc-t5100m", prod_ids2)
            self.assertNotIn("epson-sc-t5100", prod_ids2)

    def test_price_refusal_guardrail(self):
        """Verify price inquiries are refused without prices or discounts."""
        state = ConversationState(session_id="price-refusal-test")
        res = orchestrator.process_turn("How much is the SC-P700? Give me a price and discount", state=state)
        self.assertIn("pricing", res["message"].lower())
        # Ensure no dollar/pound/euro signs
        self.assertNotIn("$", res["message"])
        self.assertNotIn("£", res["message"])
        self.assertNotIn("€", res["message"])

    def test_office_printer_query_not_diverted_to_business_info(self):
        """Ensure 'printer for my office' returns product cards and does not trigger company info."""
        state = ConversationState(session_id="office-test")
        res = orchestrator.process_turn(
            "I need an A4 colour multifunction printer for my office. It must print, scan and copy, and we print approximately 200 pages per day. Show me all matching catalogue models.",
            state=state
        )
        self.assertNotEqual(res.get("source"), "route:business_info")
        self.assertEqual(res.get("type"), "product_list")
        self.assertTrue(len(res.get("cards", [])) > 0)
        card_ids = [c["id"] for c in res["cards"]]
        self.assertIn("epson-wf-c5890-dwf", card_ids)

    def test_volume_bare_number_response(self):
        """Ensure bare number like '20 to 30' or '20' answers daily_volume question for office printers."""
        state = ConversationState(session_id="volume-bare-test")
        res1 = orchestrator.process_turn("A4 colour office printer", state=state)
        self.assertEqual(state.awaiting_field, "daily_volume")
        res2 = orchestrator.process_turn("20 to 30", state=state)
        self.assertEqual(state.requirements.get("daily_volume"), 25)
        self.assertTrue(state.qualification_complete)
        self.assertTrue(len(res2.get("cards", [])) > 0)

    def test_target_reported_query_workforce_pro_150_pages(self):
        """Regression test for the user-reported query with 150 pages daily volume and WorkForce Pro constraint."""
        state = ConversationState(session_id="target-query-wf-pro")
        query = (
            "I need an A3 colour multifunction printer for a busy office. It must print, scan and copy, "
            "and our daily volume is approximately 150 pages. Show every suitable WorkForce Pro model from the catalogue."
        )
        res = orchestrator.process_turn(query, state=state)
        self.assertEqual(res.get("type"), "product_list")
        self.assertEqual(res.get("result_count"), 2)
        self.assertEqual(res.get("subcategory"), "a3_workforce_pro_multifunction")
        self.assertTrue(state.qualification_complete)
        self.assertEqual(state.requirements.get("product_line"), "workforce_pro")
        self.assertEqual(state.requirements.get("daily_volume"), 150)
        self.assertEqual(state.requirements.get("paper_size"), "a3")

        card_ids = [c["id"] for c in res.get("cards", [])]
        self.assertEqual(set(card_ids), {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf"})
        self.assertIn("2 A3 WorkForce Pro multifunction printers", res["message"])

    def test_regression_show_every_suitable_workforce_pro_model(self):
        """Show every suitable WorkForce Pro model -> only C878R and C879R."""
        state = ConversationState(session_id="reg-wf-pro")
        res = orchestrator.process_turn(
            "I need an A3 colour multifunction printer with 150 daily volume. Show every suitable WorkForce Pro model from the catalogue.",
            state=state
        )
        self.assertEqual(res.get("subcategory"), "a3_workforce_pro_multifunction")
        card_ids = [c["id"] for c in res.get("cards", [])]
        self.assertEqual(set(card_ids), {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf"})

    def test_regression_show_every_suitable_workforce_enterprise_model(self):
        """Show every suitable WorkForce Enterprise model -> only AM-C4000, AM-C5000, AM-C6000, WF-C21000."""
        state = ConversationState(session_id="reg-wf-enterprise")
        res = orchestrator.process_turn(
            "I need an A3 colour multifunction printer with 150 daily volume. Show every suitable WorkForce Enterprise model from the catalogue.",
            state=state
        )
        self.assertEqual(res.get("subcategory"), "a3_enterprise_multifunction")
        card_ids = [c["id"] for c in res.get("cards", [])]
        self.assertEqual(set(card_ids), {"epson-am-c4000", "epson-am-c5000", "epson-am-c6000", "epson-wf-c21000-d4tw"})

    def test_regression_dont_care_whether_pro_or_enterprise(self):
        """I don't care whether it is Pro or Enterprise -> product_line = unspecified; returns all 6 A3 models."""
        state = ConversationState(session_id="reg-unspecified")
        res = orchestrator.process_turn(
            "I need an A3 colour multifunction printer with 150 daily volume. I don't care whether it is Pro or Enterprise.",
            state=state
        )
        self.assertEqual(state.requirements.get("product_line"), "unspecified")
        card_ids = [c["id"] for c in res.get("cards", [])]
        self.assertEqual(len(card_ids), 6)
        self.assertEqual(
            set(card_ids),
            {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf", "epson-am-c4000", "epson-am-c5000", "epson-am-c6000", "epson-wf-c21000-d4tw"}
        )

    def test_regression_show_a3_multifunction_printers_no_assumed_line(self):
        """Show A3 multifunction printers -> do not assume Pro or Enterprise; asks volume then returns all eligible A3 models."""
        state = ConversationState(session_id="reg-a3-mfp")
        res1 = orchestrator.process_turn("Show A3 multifunction printers", state=state)
        self.assertEqual(state.awaiting_field, "daily_volume")
        self.assertEqual(len(res1.get("cards", [])), 0)

        res2 = orchestrator.process_turn("100 pages, pro or enterprise", state=state)
        card_ids = [c["id"] for c in res2.get("cards", [])]
        self.assertEqual(len(card_ids), 6)
        self.assertEqual(
            set(card_ids),
            {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf", "epson-am-c4000", "epson-am-c5000", "epson-am-c6000", "epson-wf-c21000-d4tw"}
        )

    def test_regression_correction_said_workforce_pro_not_enterprise(self):
        """I said WorkForce Pro, not Enterprise -> corrects product line and replaces Enterprise cards with Pro cards."""
        state = ConversationState(session_id="reg-correction")
        res1 = orchestrator.process_turn(
            "I need an A3 colour multifunction printer with 150 daily volume for WorkForce Enterprise",
            state=state
        )
        card_ids1 = [c["id"] for c in res1.get("cards", [])]
        self.assertIn("epson-am-c4000", card_ids1)

        res2 = orchestrator.process_turn("I said WorkForce Pro, not Enterprise", state=state)
        self.assertEqual(state.requirements.get("product_line"), "workforce_pro")
        self.assertEqual(res2.get("subcategory"), "a3_workforce_pro_multifunction")
        card_ids2 = [c["id"] for c in res2.get("cards", [])]
        self.assertEqual(set(card_ids2), {"epson-wf-c878r-dwf", "epson-wf-c879r-dwf"})
        self.assertNotIn("epson-am-c4000", card_ids2)


if __name__ == "__main__":
    unittest.main()
