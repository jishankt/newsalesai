"""
Unit & Integration Tests for Professional Scanners Catalogue & 3-Way Categorization.
Tests:
- Integrity enforcement for all 72 catalogue models (43 printers + 29 scanners).
- Strict subcategory partitioning:
    * photo_scanners (2 models)
    * hybrid_scanners (10 models - 'both can do': flatbed + ADF)
    * business_scanners (17 models - high-speed, sheetfed, mobile)
- Subcategory resolution from user natural language intent.
- Qualification flow and category prompting for scanners.
- Filtering and ranking for each scanner subcategory.
- Direct model lookup and side-by-side comparisons.
- Non-regression: printer MFP queries ("printer with scanner") still route to office_printer.
"""

import unittest
from catalog.catalogue_loader import catalogue_loader, EXPECTED_CATALOGUE_COUNT
from catalog.subcategory_resolver import resolve_subcategory
from catalog.catalogue_filter import catalogue_filter
from catalog.catalogue_resolver import find_mentioned_catalogue_products, build_approved_comparison_response
from conversation.normalizer import normalize_category, extract_deterministic_requirements
from conversation.qualification_schema import get_missing_mandatory_fields, get_next_question
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState


class TestScannersCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = Orchestrator()
        cls.all_products = catalogue_loader.get_all()
        cls.scanners = [p for p in cls.all_products if p.get("catalogue") == "scanners"]

    def test_01_catalogue_integrity_total_count(self):
        """Must load exactly 72 verified catalogue products (43 printers + 29 scanners)."""
        self.assertEqual(len(self.all_products), 72)
        self.assertEqual(EXPECTED_CATALOGUE_COUNT, 72)
        self.assertEqual(len(self.scanners), 29)

    def test_02_scanner_subcategories_partitioning(self):
        """Scanners must partition into exactly 3 subcategories: photo, hybrid (both), and business."""
        photo = [p for p in self.scanners if p.get("subcategory") == "photo_scanners"]
        hybrid = [p for p in self.scanners if p.get("subcategory") == "hybrid_scanners"]
        business = [p for p in self.scanners if p.get("subcategory") == "business_scanners"]

        # Exactly 2 photo scanners (12000XL and 12000XL Pro)
        self.assertEqual(len(photo), 2)
        photo_ids = {p["id"] for p in photo}
        self.assertIn("epson-expression-12000xl", photo_ids)
        self.assertIn("epson-expression-12000xl-pro", photo_ids)

        # Exactly 10 hybrid scanners (both can do: flatbed platen + ADF)
        self.assertEqual(len(hybrid), 10)
        hybrid_ids = {p["id"] for p in hybrid}
        self.assertTrue({"epson-workforce-ds-1630", "epson-workforce-ds-1660w"}.issubset(hybrid_ids))
        self.assertTrue({"epson-workforce-ds-6500", "epson-workforce-ds-6500n"}.issubset(hybrid_ids))
        self.assertTrue({"epson-workforce-ds-7500", "epson-workforce-ds-7500n"}.issubset(hybrid_ids))
        self.assertTrue({"epson-workforce-ds-60000", "epson-workforce-ds-60000n"}.issubset(hybrid_ids))
        self.assertTrue({"epson-workforce-ds-70000", "epson-workforce-ds-70000n"}.issubset(hybrid_ids))

        # Exactly 17 business scanners (sheetfed, desktop, mobile)
        self.assertEqual(len(business), 17)
        biz_ids = {p["id"] for p in business}
        self.assertTrue({"epson-workforce-ds-900wn", "epson-workforce-ds-800wn"}.issubset(biz_ids))
        self.assertTrue({"epson-workforce-es-580w", "epson-workforce-es-500wii"}.issubset(biz_ids))
        self.assertTrue({"epson-workforce-ds-970", "epson-workforce-ds-870", "epson-workforce-ds-790wn"}.issubset(biz_ids))
        self.assertTrue({"epson-workforce-ds-770ii", "epson-workforce-ds-730n", "epson-workforce-ds-530ii", "epson-workforce-ds-410"}.issubset(biz_ids))
        self.assertTrue({"epson-workforce-ds-30000", "epson-workforce-ds-32000"}.issubset(biz_ids))
        self.assertTrue({"epson-workforce-ds-70", "epson-workforce-ds-80w", "epson-workforce-ds-310", "epson-workforce-ds-360w"}.issubset(biz_ids))

        # Total matches 29
        self.assertEqual(len(photo) + len(hybrid) + len(business), 29)

    def test_03_category_normalization(self):
        """Scanner inquiries must normalize to 'scanners', while printer MFP queries stay 'office_printer'."""
        self.assertEqual(normalize_category("I need a scanner"), "scanners")
        self.assertEqual(normalize_category("Looking for professional scanners"), "scanners")
        self.assertEqual(normalize_category("Show me business document scanners"), "scanners")
        self.assertEqual(normalize_category("I need a photo scanner for film"), "scanners")
        self.assertEqual(normalize_category("Do you have DS-900WN?"), "scanners")
        self.assertEqual(normalize_category("Tell me about Expression 12000XL"), "scanners")

        # Crucial disambiguation: printer with scanner must remain office_printer or technical
        self.assertEqual(normalize_category("I need an A4 printer with a scanner"), "office_printer")
        self.assertEqual(normalize_category("Looking for a business printer that can print and scan"), "office_printer")

    def test_04_subcategory_resolution(self):
        """Requirements must deterministically resolve to the 3 subcategories."""
        # 1. Photo Scanners
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "photo"}),
            "photo_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"application": "fine_art_scanning"}),
            "photo_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"model": "12000xl"}),
            "photo_scanners"
        )

        # 2. Hybrid Scanners ("Both can do")
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "both"}),
            "hybrid_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "hybrid"}),
            "hybrid_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "flatbed and adf"}),
            "hybrid_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"application": "books and documents"}),
            "hybrid_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"model": "ds-1630"}),
            "hybrid_scanners"
        )

        # 3. Business Scanners
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "business"}),
            "business_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "documents"}),
            "business_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"model": "ds-900wn"}),
            "business_scanners"
        )
        self.assertEqual(
            resolve_subcategory("scanners", {"scanner_intent": "portable"}),
            "business_scanners"
        )

    def test_05_qualification_flow(self):
        """When user asks for a generic scanner, mandatory qualification asks for scanner intent."""
        missing = get_missing_mandatory_fields("scanners", {})
        self.assertEqual(missing, ["scanner_intent"])

        q = get_next_question("scanners", missing)
        self.assertEqual(q["field"], "scanner_intent")
        self.assertIn("high-speed business document scanner", q["question"])
        self.assertIn("Business Documents", q["pills"])
        self.assertIn("Photo & Film (High-Res)", q["pills"])
        self.assertIn("Both (Flatbed + ADF)", q["pills"])

        # When intent is provided, no mandatory questions remain
        missing_answered = get_missing_mandatory_fields("scanners", {"scanner_intent": "business"})
        self.assertEqual(missing_answered, [])

    def test_06_catalogue_filter_by_subcategories(self):
        """Filtering by each subcategory returns the expected certified models."""
        # Photo
        photo_cards, _ = catalogue_filter.filter_and_rank("scanners", "photo_scanners", {})
        self.assertEqual(len(photo_cards), 2)
        card_names = {c["name"] for c in photo_cards}
        self.assertTrue(any("12000XL Pro" in name for name in card_names))
        self.assertTrue(any("12000XL Photo" in name for name in card_names))

        # Hybrid ("Both can do")
        hybrid_cards, _ = catalogue_filter.filter_and_rank("scanners", "hybrid_scanners", {})
        self.assertEqual(len(hybrid_cards), 10)

        # Business
        biz_cards, _ = catalogue_filter.filter_and_rank("scanners", "business_scanners", {})
        self.assertEqual(len(biz_cards), 17)

    def test_07_paper_size_filtering_for_scanners(self):
        """A3 filter on business scanners returns the production A3 sheetfed models (DS-30000, DS-32000)."""
        a3_biz_cards, _ = catalogue_filter.filter_and_rank("scanners", "business_scanners", {"paper_size": "a3"})
        self.assertEqual(len(a3_biz_cards), 2)
        a3_ids = {c["id"] for c in a3_biz_cards}
        self.assertEqual(a3_ids, {"epson-workforce-ds-30000", "epson-workforce-ds-32000"})

    def test_08_direct_model_lookup(self):
        """Direct mentions of scanner models must be identified accurately."""
        prods = find_mentioned_catalogue_products("Tell me about the Epson WorkForce DS-900WN")
        self.assertEqual(len(prods), 1)
        self.assertEqual(prods[0]["id"], "epson-workforce-ds-900wn")

        prods_photo = find_mentioned_catalogue_products("What is the resolution of Expression 12000XL Pro?")
        self.assertEqual(len(prods_photo), 1)
        self.assertEqual(prods_photo[0]["id"], "epson-expression-12000xl-pro")

    def test_09_scanner_comparison(self):
        """Side-by-side comparison between scanner models builds verified comparison tables."""
        prods = find_mentioned_catalogue_products("Compare DS-900WN and DS-800WN")
        self.assertEqual(len(prods), 2)
        intro, cards, data = build_approved_comparison_response(prods)
        self.assertIn("DS-900WN", intro)
        self.assertIn("140", intro)
        self.assertIn("100", intro)
        self.assertIn("11,000", intro)
        self.assertIn("8,000", intro)

    def test_10_end_to_end_conversation_turn(self):
        """Full orchestrator turn for photo scanners returns cards and tailored response."""
        state = ConversationState(session_id="test-scanners-photo")
        res = self.orchestrator.process_turn("I need a photo scanner for scanning high-resolution photos and film", state=state)
        self.assertEqual(state.category, "scanners")
        cards = res.get("product_cards", [])
        self.assertEqual(len(cards), 2)
        pids = {c["id"] for c in cards}
        self.assertEqual(pids, {"epson-expression-12000xl", "epson-expression-12000xl-pro"})


if __name__ == "__main__":
    unittest.main()
