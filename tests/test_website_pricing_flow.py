"""
Unit & Integration Tests for Website Pricing, Product Card Prices, and Support Referral Flows.
"""

import unittest
from catalog.website_price_fetcher import website_price_fetcher
from catalog.price_resolver import price_resolver
from agent.tool_executor import catalog_tool_executor
from catalog.catalogue_loader import catalogue_loader
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState
from guardrails import (
    OFFICIAL_SUPPORT_EMAIL,
    OFFICIAL_SUPPORT_PHONE,
    OFFICIAL_WEBSITE_URL,
    DISCOUNT_REFUSAL,
    is_price_inquiry,
    is_discount_inquiry,
)


from catalog.catalogue_filter import catalogue_filter


class TestWebsitePricingFlow(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()

    def test_website_price_fetcher_cache_loaded(self):
        """Website price cache should contain all 43 catalogue items."""
        self.assertGreaterEqual(len(website_price_fetcher.cache), 43)

    def test_published_models_have_real_prices(self):
        """Direct online purchase models must have exact website AED prices."""
        f100_info = website_price_fetcher.get_price("epson-sc-f100")
        self.assertEqual(f100_info["price"], 1950.0)
        self.assertEqual(f100_info["currency"], "AED")
        self.assertEqual(f100_info["price_str"], "AED 1,950.00")
        self.assertFalse(f100_info["is_request"])
        self.assertEqual(f100_info["status"], "published_on_site")

        cx02_info = website_price_fetcher.get_price("citizen-cx-02")
        self.assertEqual(cx02_info["price"], 4385.0)
        self.assertFalse(cx02_info["is_request"])

        cx02w_info = website_price_fetcher.get_price("citizen-cx-02w")
        self.assertEqual(cx02w_info["price"], 6820.0)
        self.assertEqual(cx02w_info["price_str"], "AED 6,820.00")
        self.assertFalse(cx02w_info["is_request"])

        p900_info = website_price_fetcher.get_price("epson-sc-p900")
        self.assertEqual(p900_info["price"], 4880.0)
        self.assertEqual(p900_info["price_str"], "AED 4,880.00")
        self.assertFalse(p900_info["is_request"])

        p900_roll_info = website_price_fetcher.get_price("epson-sc-p900-roll")
        self.assertEqual(p900_roll_info["price"], 5320.0)
        self.assertEqual(p900_roll_info["price_str"], "AED 5,320.00")
        self.assertFalse(p900_roll_info["is_request"])

        t3100_info = website_price_fetcher.get_price("epson-sc-t3100")
        self.assertEqual(t3100_info["price"], 3880.0)
        self.assertFalse(t3100_info["is_request"])

    def test_quote_only_models_status(self):
        """Enterprise/large-format models not sold via direct checkout must be marked quote_only."""
        p7500_info = website_price_fetcher.get_price("epson-sc-p7500")
        self.assertIsNone(p7500_info["price"])
        self.assertTrue(p7500_info["is_request"])
        self.assertEqual(p7500_info["price_str"], "Price on Request")

        p9500_info = website_price_fetcher.get_price("epson-sc-p9500")
        self.assertIsNone(p9500_info["price"])
        self.assertTrue(p9500_info["is_request"])

    def test_hardware_product_card_formatting(self):
        """Product cards from both catalogue_filter and tool_executor must include price, price_str, vat_note, and is_request."""
        f100 = catalogue_loader.get_by_id("epson-sc-f100")
        card_f100 = catalog_tool_executor.format_card(f100, card_type="hardware")
        self.assertEqual(card_f100["price"], 1950.0)
        self.assertEqual(card_f100["price_formatted"], "AED 1,950.00")
        self.assertEqual(card_f100["vat_note"], "(Excl. VAT)")
        self.assertFalse(card_f100["is_request"])

        # Test catalogue_filter._format_card (used in recommendation & detail cards)
        filter_card_f100 = catalogue_filter._format_card(f100, f100.get("subcategory"), {})
        self.assertEqual(filter_card_f100["price"], 1950.0)
        self.assertEqual(filter_card_f100["price_formatted"], "AED 1,950.00")
        self.assertEqual(filter_card_f100["vat_note"], "(Excl. VAT)")
        self.assertFalse(filter_card_f100["is_request"])

        p700 = catalogue_loader.get_by_id("epson-sc-p700")
        filter_card_p700 = catalogue_filter._format_card(p700, p700.get("subcategory"), {})
        self.assertEqual(filter_card_p700["price"], 3400.0)
        self.assertEqual(filter_card_p700["price_formatted"], "AED 3,400.00")
        self.assertFalse(filter_card_p700["is_request"])

        p7500 = catalogue_loader.get_by_id("epson-sc-p7500")
        card_p7500 = catalog_tool_executor.format_card(p7500, card_type="hardware")
        self.assertIsNone(card_p7500["price"])
        self.assertEqual(card_p7500["price_formatted"], "Price on Request")
        self.assertTrue(card_p7500["is_request"])

        filter_card_p7500 = catalogue_filter._format_card(p7500, p7500.get("subcategory"), {})
        self.assertIsNone(filter_card_p7500["price"])
        self.assertEqual(filter_card_p7500["price_formatted"], "Price on Request")
        self.assertTrue(filter_card_p7500["is_request"])

    def test_orchestrator_answers_price_for_published_model(self):
        """Asking for the price of SC-F100 returns exact price and card with price."""
        state = ConversationState(session_id="test_price_f100")
        resp = self.orchestrator.process_turn("what is the price of sc-f100?", session_id="test_price_f100", state=state)
        
        reply = resp["reply"]
        self.assertIn("1,950.00", reply)
        self.assertIn("AED", reply)
        self.assertIn("Epson SureColor SC-F100", reply)
        self.assertIn("https://www.keplertechllc.com/product/epson-surecolor-sc-f100-printer/", reply)
        self.assertEqual(len(resp["product_cards"]), 1)
        self.assertEqual(resp["product_cards"][0]["price"], 1950.0)

    def test_orchestrator_directs_unpriced_model_to_support_team(self):
        """Asking for the price of SC-P7500 instructs user to contact customer support team."""
        state = ConversationState(session_id="test_price_p7500")
        resp = self.orchestrator.process_turn("what does the sc-p7500 cost?", session_id="test_price_p7500", state=state)

        reply = resp["reply"]
        self.assertIn(OFFICIAL_SUPPORT_EMAIL, reply)
        self.assertIn(OFFICIAL_SUPPORT_PHONE, reply)
        self.assertIn("Epson SureColor SC-P7500", reply)
        self.assertIn("commercial quotation", reply.lower())
        self.assertEqual(len(resp["product_cards"]), 1)
        self.assertTrue(resp["product_cards"][0]["is_request"])

    def test_orchestrator_handles_discount_queries(self):
        """Asking for discounts directs user to official website and support team."""
        queries = [
            "can you give me a discount on sc-f100?",
            "can we negotiate the price?",
            "any discount for bulk order?",
            "what is your best price?",
        ]
        for q in queries:
            state = ConversationState(session_id="test_discount_flow")
            resp = self.orchestrator.process_turn(q, session_id="test_discount_flow", state=state)
            reply = resp["reply"]
            self.assertIn("sales@keplertech.ae", reply)
            self.assertIn("+971 4 323 1008", reply)
            self.assertIn("keplertechllc.com", reply)
            # Ensure no discount was promised
            self.assertNotIn("i can give you", reply.lower())
            self.assertNotIn("we can offer a discount", reply.lower())

    def test_general_price_query(self):
        """Asking generic price query without a specific model directs to website and support."""
        state = ConversationState(session_id="test_gen_price")
        resp = self.orchestrator.process_turn("what are your prices?", session_id="test_gen_price", state=state)
        reply = resp["reply"]
        self.assertIn("keplertechllc.com", reply)
        self.assertIn(OFFICIAL_SUPPORT_EMAIL, reply)
        self.assertIn(OFFICIAL_SUPPORT_PHONE, reply)


if __name__ == "__main__":
    unittest.main()
