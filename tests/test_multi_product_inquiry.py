import unittest
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


class TestMultiProductInquiry(unittest.TestCase):
    def test_i_need_f100_and_f500_returns_both_products(self):
        state = ConversationState(session_id="test_multi_f100_f500")
        res = orchestrator.process_turn("i need f100 and f500", session_id="test_multi_f100_f500", state=state)
        
        self.assertEqual(res.get("source"), "route:comparison")
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 2)
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-f100", card_ids)
        self.assertIn("epson-sc-f500", card_ids)
        
        reply = res.get("reply", "")
        self.assertIn("Epson SureColor SC-F100", reply)
        self.assertIn("Epson SureColor SC-F500", reply)

    def test_multi_product_without_compare_keyword(self):
        state = ConversationState(session_id="test_multi_t3100_t5100")
        res = orchestrator.process_turn("tell me about t3100 and t5100", session_id="test_multi_t3100_t5100", state=state)
        
        self.assertEqual(res.get("source"), "route:comparison")
        cards = res.get("cards", [])
        self.assertEqual(len(cards), 2)
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-t3100", card_ids)
        self.assertIn("epson-sc-t5100", card_ids)

    def test_price_followup_after_multi_product_comparison(self):
        state = ConversationState(session_id="test_price_followup_cmp")
        res1 = orchestrator.process_turn("i need f100 and f500", session_id="test_price_followup_cmp", state=state)
        self.assertEqual(res1.get("source"), "route:comparison")
        
        res2 = orchestrator.process_turn("i need price?", session_id="test_price_followup_cmp", state=state)
        self.assertEqual(res2.get("source"), "route:product_price_inquiry")
        cards = res2.get("cards", [])
        self.assertEqual(len(cards), 2)
        card_ids = [c["id"] for c in cards]
        self.assertIn("epson-sc-f100", card_ids)
        self.assertIn("epson-sc-f500", card_ids)
        
        reply = res2.get("reply", "")
        self.assertIn("Epson SureColor SC-F100", reply)
        self.assertIn("Epson SureColor SC-F500", reply)
        self.assertIn("1,950.00", reply)
        self.assertIn("Price on Request", reply)


if __name__ == "__main__":
    unittest.main()
