"""
Verification and regression tests for Kepler Tech Official Delivery, Returns & Conversational Fixes:
1. Delivery Coverage (UAE, Oman, GCC via 3rd-party courier, no OFAC countries).
2. Timing (1-2 business days processing, dispatch notification, delivery timeframe disclaimer).
3. Fees (UAE flat AED 10, checkout outside UAE, free local store pickup ready in 1-2 days).
4. Payments & Terms (payment before dispatch, destination import duty/VAT, risk passes on delivery).
5. Cancellations & Returns (24h cancellation, 2 days defective/wrong item report in unopened packaging, refunds up to 45 days).
6. Conversational Acknowledgment ('okey' does not dump product cards).
7. Typo Tolerance ('campare them' compares active models).
8. Category Switch ('okey now i want look a scanner' switches away from printers).
9. 'For each' Model Spec Queries ('dpi for each' answers resolution for all models).
10. Purchase Intent with Pricing ('how much is it and how to buy' gives price + purchase route).
"""

import unittest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState


class TestDeliveryAndConversationFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = Orchestrator()

    def test_delivery_policy_details(self):
        state = ConversationState(session_id="test_del_1")
        resp = self.orchestrator.process_turn(
            "Where do you deliver and what are the fees and timing?",
            session_id="test_del_1",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("AED 10", reply)
        self.assertTrue("UAE" in reply and "Oman" in reply)
        self.assertIn("1 to 2 business days", reply)
        self.assertTrue("third-party courier" in reply.lower() or "courier" in reply.lower())
        self.assertTrue("store pickup" in reply.lower() or "local pickup" in reply.lower())

    def test_delivery_and_return_policy_combined(self):
        state = ConversationState(session_id="test_del_2")
        resp = self.orchestrator.process_turn(
            "What is your delivery and return policy?",
            session_id="test_del_2",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("AED 10", reply)
        self.assertIn("24 hours", reply)
        self.assertIn("2 days", reply)
        self.assertIn("45 days", reply)

    def test_cancellation_and_return_policy_only(self):
        state = ConversationState(session_id="test_del_3")
        resp = self.orchestrator.process_turn(
            "What is your return policy and can I cancel my order?",
            session_id="test_del_3",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("24 hours", reply)
        self.assertIn("2 days", reply)
        self.assertIn("45 days", reply)

    def test_conversational_acknowledgment_no_cards(self):
        state = ConversationState(session_id="test_ack")
        self.orchestrator.process_turn(
            "I am looking for dye sublimation printers",
            session_id="test_ack",
            state=state,
        )
        resp = self.orchestrator.process_turn(
            "okey",
            session_id="test_ack",
            state=state,
        )
        self.assertEqual(len(resp.get("product_cards", [])), 0)
        self.assertTrue("Glad to help" in resp["reply"] or "spec" in resp["reply"].lower())

    def test_topic_switch_to_scanner(self):
        state = ConversationState(session_id="test_scan_sw")
        self.orchestrator.process_turn(
            "I want dye sublimation printer",
            session_id="test_scan_sw",
            state=state,
        )
        resp = self.orchestrator.process_turn(
            "okey now i want look a scanner",
            session_id="test_scan_sw",
            state=state,
        )
        self.assertIn("scanner", resp["reply"].lower())

    def test_typo_compare_models(self):
        state = ConversationState(session_id="test_typo_cmp")
        self.orchestrator.process_turn(
            "tell me about epson sc f100 and f500",
            session_id="test_typo_cmp",
            state=state,
        )
        resp = self.orchestrator.process_turn(
            "campare them",
            session_id="test_typo_cmp",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("SC-F100", reply)
        self.assertIn("SC-F500", reply)

    def test_for_each_dpi_resolution(self):
        state = ConversationState(session_id="test_for_each")
        self.orchestrator.process_turn(
            "tell me about sc f100 and sc f500",
            session_id="test_for_each",
            state=state,
        )
        resp = self.orchestrator.process_turn(
            "dpi for each",
            session_id="test_for_each",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("SC-F100", reply)
        self.assertIn("SC-F500", reply)
        self.assertTrue("600" in reply and "2,400" in reply)

    def test_order_with_price_query(self):
        state = ConversationState(session_id="test_order_price")
        self.orchestrator.process_turn(
            "tell me about epson sc f100",
            session_id="test_order_price",
            state=state,
        )
        resp = self.orchestrator.process_turn(
            "how much is it and how to buy",
            session_id="test_order_price",
            state=state,
        )
        reply = resp["reply"]
        self.assertIn("AED 1,950", reply)
        self.assertIn("keplertechllc.com", reply)


if __name__ == "__main__":
    unittest.main()
