"""
Comprehensive Unit & Integration Test Suite for Product Pricing.
Tests every single product in Kepler Tech's catalog (all 43 models),
consumables, media, hardware aliases, and end-to-end price inquiries.
"""

import unittest
from catalog.catalogue_loader import catalogue_loader
from catalog.catalogue_filter import catalogue_filter
from catalog.price_resolver import price_resolver
from catalog.website_price_fetcher import website_price_fetcher
from agent.tool_executor import catalog_tool_executor
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState


# Ground-truth verified rates on Kepler Tech LLC official website
EXPECTED_HARDWARE_PRICES = {
    "epson-sc-f100": 1950.0,
    "citizen-cx-02": 4385.0,
    "citizen-cx-02w": 6820.0,
    "citizen-cy-02": 3400.0,
    "citizen-cz-01": 3200.0,
    "epson-sc-t3100": 3880.0,
    "epson-sc-t5100": 9700.0,
    "epson-sc-p700": 3400.0,
    "epson-sc-p900": 4880.0,
    "epson-sc-p900-roll": 5320.0,
    "epson-wf-c5890-dwf": 1656.0,
    "epson-am-c550": 9000.0,
    "epson-wf-c878r-dwf": 6500.0,
    "epson-wf-c879r-dwf": 7600.0,
}

EXPECTED_CONSUMABLES_PRICES = {
    "cx2w 812": 975.0,
    "cx2w-812": 975.0,
    "cy-ms46": 625.0,
    "cy-ms68": 685.0,
    "9797": 490.0,
    "19048": 500.0,
    "9795": 500.0,
    "9790": 190.0,
    "9781": 325.0,
    "c12c935711": 155.0,
    "c13t47a100": 198.0,
    "c13t05a400": 695.0,
    "c13t08h400": 883.0,
    "c13t01d100": 690.0,
    "c13t41f340": 575.0,
}


class TestAllProductPrices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = Orchestrator()
        cls.all_products = catalogue_loader.get_all()

    def test_total_catalogue_products_count(self):
        """Must have exactly 43 catalogue products loaded."""
        self.assertEqual(len(self.all_products), 43)

    def test_every_catalogue_product_price_and_cards(self):
        """Every single product in the catalogue must resolve to its exact verified price or quote_only."""
        for p in self.all_products:
            pid = p["id"]
            expected_price = EXPECTED_HARDWARE_PRICES.get(pid, None)

            # 1. Test PriceResolver directly
            price_info = price_resolver.get_price_info(identifier=pid, prod=p)
            self.assertEqual(
                price_info.get("price"),
                expected_price,
                f"PriceResolver price mismatch for {pid}: got {price_info.get('price')} expected {expected_price}"
            )
            self.assertEqual(price_info.get("currency"), "AED")

            if expected_price is not None:
                self.assertFalse(price_info.get("is_request"), f"{pid} should NOT be request only")
                self.assertEqual(price_info.get("price_str"), f"AED {expected_price:,.2f}")
                self.assertEqual(price_info.get("vat_note"), "(Excl. VAT)")
            else:
                self.assertTrue(price_info.get("is_request"), f"{pid} should be request only")
                self.assertEqual(price_info.get("price_str"), "Price on Request")

            # 2. Test CatalogueFilter card formatting
            filter_card = catalogue_filter._format_card(p, p.get("subcategory"), {})
            self.assertEqual(filter_card.get("price"), expected_price)
            if expected_price is not None:
                self.assertEqual(filter_card.get("price_formatted"), f"AED {expected_price:,.2f}")
                self.assertFalse(filter_card.get("is_request"))
            else:
                self.assertEqual(filter_card.get("price_formatted"), "Price on Request")
                self.assertTrue(filter_card.get("is_request"))

            # 3. Test ToolExecutor card formatting
            tool_card = catalog_tool_executor.format_card(p, card_type="hardware")
            self.assertEqual(tool_card.get("price"), expected_price)
            if expected_price is not None:
                self.assertEqual(tool_card.get("price_formatted"), f"AED {expected_price:,.2f}")
                self.assertFalse(tool_card.get("is_request"))
            else:
                self.assertEqual(tool_card.get("price_formatted"), "Price on Request")
                self.assertTrue(tool_card.get("is_request"))

    def test_citizen_cx02w_price_is_corrected(self):
        """Citizen CX-02W must be 6,820 AED (not 4,385 AED)."""
        info = price_resolver.get_price_info("citizen-cx-02w")
        self.assertEqual(info["price"], 6820.0)
        self.assertEqual(info["price_str"], "AED 6,820.00")
        self.assertFalse(info["is_request"])

    def test_epson_p900_prices_are_corrected(self):
        """Epson SC-P900 standard must be 4,880 AED and roll adapter version must be 5,320 AED."""
        p900_std = price_resolver.get_price_info("epson-sc-p900")
        self.assertEqual(p900_std["price"], 4880.0)
        self.assertEqual(p900_std["price_str"], "AED 4,880.00")

        p900_roll = price_resolver.get_price_info("epson-sc-p900-roll")
        self.assertEqual(p900_roll["price"], 5320.0)
        self.assertEqual(p900_roll["price_str"], "AED 5,320.00")

    def test_prefix_and_alias_resolution(self):
        """Models must resolve identically whether queried with or without 'sc-' prefix or by SKU."""
        alias_pairs = [
            ("epson-sc-p900", "epson-p900", 4880.0),
            ("epson-sc-p700", "epson-p700", 3400.0),
            ("epson-sc-t3100", "epson-t3100", 3880.0),
            ("epson-sc-t5100", "epson-t5100", 9700.0),
            ("epson-sc-f100", "epson-f100", 1950.0),
            ("epson-wf-c5890-dwf", "epson-wf-c5890", 1656.0),
            ("epson-wf-c878r-dwf", "epson-wf-c878r", 6500.0),
            ("epson-wf-c879r-dwf", "epson-wf-c879r", 7600.0),
        ]
        for id1, id2, expected_price in alias_pairs:
            info1 = price_resolver.get_price_info(id1)
            info2 = price_resolver.get_price_info(id2)
            self.assertEqual(info1["price"], expected_price, f"{id1} price mismatch")
            self.assertEqual(info2["price"], expected_price, f"{id2} price mismatch")

        # SKUs
        self.assertEqual(price_resolver.get_price_info("C11CH37402DA")["price"], 4880.0)
        self.assertEqual(price_resolver.get_price_info("C11CH37402DR")["price"], 5320.0)
        self.assertEqual(price_resolver.get_price_info("C11CH38402DA")["price"], 3400.0)
        self.assertEqual(price_resolver.get_price_info("C11CF11302A1")["price"], 3880.0)
        self.assertEqual(price_resolver.get_price_info("C11CF12301A1")["price"], 9700.0)
        self.assertEqual(price_resolver.get_price_info("CX-02W")["price"], 6820.0)
        self.assertEqual(price_resolver.get_price_info("CX-02")["price"], 4385.0)

    def test_verified_consumables_and_media(self):
        """Verified consumables and media must return their exact catalog prices."""
        for item_key, expected_price in EXPECTED_CONSUMABLES_PRICES.items():
            info = price_resolver.get_price_info(item_key)
            self.assertEqual(
                info.get("price"),
                expected_price,
                f"Consumable price mismatch for {item_key}: got {info.get('price')} expected {expected_price}"
            )
            self.assertFalse(info.get("is_request"), f"{item_key} should have a verified price")

    def test_orchestrator_price_inquiry_answers(self):
        """Conversational orchestrator must accurately answer price questions for corrected models."""
        queries = [
            ("what is the price of citizen cx-02w?", "6,820.00", 6820.0),
            ("how much is the epson sc-p900?", "4,880.00", 4880.0),
            ("what is the cost of epson t5100?", "9,700.00", 9700.0),
            ("price of epson t3100", "3,880.00", 3880.0),
            ("what is the price of citizen cx-02?", "4,385.00", 4385.0),
            ("what is the price of epson sc-f100?", "1,950.00", 1950.0),
        ]

        for query, expected_snippet, expected_price in queries:
            session_id = f"test_query_{abs(hash(query))}"
            state = ConversationState(session_id=session_id)
            resp = self.orchestrator.process_turn(query, session_id=session_id, state=state)
            
            reply = resp["reply"]
            self.assertIn(expected_snippet, reply, f"Did not find {expected_snippet} in reply: {reply}")
            self.assertIn("AED", reply)
            self.assertGreaterEqual(len(resp["product_cards"]), 1)
            self.assertEqual(resp["product_cards"][0]["price"], expected_price)


if __name__ == "__main__":
    unittest.main()
