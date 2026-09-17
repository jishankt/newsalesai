"""
Regression tests for conversational AI fixes from session 15a3bf97:
1. Turn 15: 'which one will do this job' with 'single paper roll' recommends Citizen CX-02, not consumables inquiry.
2. Turn 23: 'DNPrx1' competitor brand refusal and redirection to Citizen/Epson.
3. Turn 28-29: Active product context synchronization - 'media for this printer' returns Citizen CX-02W media, not Epson C5000 inks, plus pricing guidance.
4. Turn 31: 'media and its cost' returns media SKU and official pricing guidance.
5. Turn 33: 'CAN I PRINT 2X6 STRIP IN THIS PRINTER?' answers capability factually and recommends Citizen CX-02.
6. Turn 35: 'which photo printer printers 6x2 with out media loss' recommends Citizen CX-02.
7. Turn 37: 'how you offer against my request' does NOT trigger discount refusal guardrail.
"""

import unittest
from agent.orchestrator import Orchestrator
from domain.conversation_state import ConversationState
from guardrails import is_discount_inquiry, DISCOUNT_REFUSAL


class TestSessionMistakesRegression(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()

    def test_turn15_single_paper_roll_printer_recommendation(self):
        """User asking 'which one will do this job' for 6x8 and 6x4 on single paper roll must recommend Citizen CX-02, NOT ask for consumable model."""
        state = ConversationState(session_id="reg_turn15")
        # Pre-seed category as citizen_photo (as happened in Turn 13)
        state.category = "citizen_photo"
        state.requirements = {"product_line": "citizen"}

        resp = self.orchestrator.process_turn(
            "i need to print 6X8 and 6X4 in single paper roll, which one will do this job?",
            session_id="reg_turn15",
            state=state
        )

        reply = resp["reply"]
        self.assertNotIn("Which printer or scanner model do you need consumables for", reply)
        self.assertIn("Citizen CX-02", reply)
        self.assertTrue(len(resp["product_cards"]) >= 1)
        self.assertEqual(resp["product_cards"][0]["id"], "citizen-cx-02")

    def test_turn23_dnp_rx1_competitor_detection(self):
        """User asking for competitor model DNPrx1 photo printer must trigger unapproved model refusal."""
        state = ConversationState(session_id="reg_turn23")
        resp = self.orchestrator.process_turn(
            "i am looking for DNPrx1 photo printer",
            session_id="reg_turn23",
            state=state
        )

        reply = resp["reply"]
        self.assertIn("not present in our approved catalogue", reply.lower())
        self.assertIn("authorized kepler tech distributor", reply.lower())
        self.assertIn("citizen photo", reply.lower())

    def test_turn28_and_29_active_printer_media_context_sync(self):
        """Recommending Citizen CX-02W and then asking for 'media for this printer' must return CX-02W media, NOT stale Epson C5000 inks."""
        state = ConversationState(session_id="reg_turn28_29")
        state.category = "citizen_photo"
        state.requirements = {"product_line": "citizen"}
        # Simulate earlier Turn 17 where user inquired about C5000 inks
        state.active_printer_for_consumables = "Epson WorkForce Enterprise AM-C5000"

        # Turn 27/28: User narrows to 8x12 inches -> CX-02W recommended
        resp28 = self.orchestrator.process_turn(
            "i need to print only 8x12 inches",
            session_id="reg_turn28_29",
            state=state
        )
        self.assertEqual(len(resp28["product_cards"]), 1)
        self.assertEqual(resp28["product_cards"][0]["id"], "citizen-cx-02w")
        self.assertIn("Citizen CX-02W", state.active_printer_for_consumables)

        # Turn 29: User asks for media for this printer cost and cost per print
        resp29 = self.orchestrator.process_turn(
            "can i have the media for this printer cost and cost per print too?",
            session_id="reg_turn28_29",
            state=state
        )
        reply29 = resp29["reply"]
        # Must return Citizen CX-02W media, NOT Epson AM-C5000 inks
        self.assertNotIn("AM-C5000", reply29)
        self.assertNotIn("Black Ink", reply29)
        self.assertIn("Citizen CX-02W", reply29)
        self.assertIn("CX2W 812", reply29)
        # Must include pricing / quotation guidance
        self.assertTrue(any(w in reply29.lower() for w in ["pricing", "cost-per-print", "quote", "sales@keplertech.ae"]))

    def test_turn31_cx02w_media_and_cost(self):
        """User asking 'i AM TALKING ABOUT CX-02W PRINT MEDIA AND ITS COST' returns CX-02W media and pricing guidance."""
        state = ConversationState(session_id="reg_turn31")
        resp = self.orchestrator.process_turn(
            "i AM TALKING ABOUT CX-02W PRINT MEDIA AND ITS COST",
            session_id="reg_turn31",
            state=state
        )
        reply = resp["reply"]
        self.assertIn("Citizen CX-02W", reply)
        self.assertIn("CX2W 812", reply)
        self.assertTrue(any(w in reply.lower() for w in ["pricing", "cost-per-print", "quote", "sales@keplertech.ae"]))

    def test_turn33_capability_query_2x6_strip_on_cx02w(self):
        """User asking 'CAN I PRINT 2X6 STRIP IN THIS PRINTER?' when CX-02W is active must answer accurately and recommend Citizen CX-02."""
        state = ConversationState(session_id="reg_turn33")
        cx02w = {"id": "citizen-cx-02w", "display_name": "Citizen CX-02W", "name": "Citizen CX-02W"}
        state.active_product = cx02w
        state.active_product_id = "citizen-cx-02w"

        resp = self.orchestrator.process_turn(
            "CAN I PRINT 2X6 STRIP IN THIS PRINTER?",
            session_id="reg_turn33",
            state=state
        )
        reply = resp["reply"]
        # Must explain that CX-02W does not support 2x6 and recommend CX-02
        self.assertIn("Citizen CX-02W", reply)
        self.assertIn("Citizen CX-02", reply)
        self.assertIn("2x6", reply)
        self.assertTrue(len(resp["product_cards"]) >= 1)
        self.assertEqual(resp["product_cards"][0]["id"], "citizen-cx-02")

    def test_turn35_photo_printer_6x2_without_media_loss(self):
        """User asking 'which photo printer printers 6x2 with out media loss' must recommend Citizen CX-02."""
        state = ConversationState(session_id="reg_turn35")
        resp = self.orchestrator.process_turn(
            "which photo printer printers 6x2 with out media loss",
            session_id="reg_turn35",
            state=state
        )
        reply = resp["reply"]
        self.assertIn("Citizen CX-02", reply)
        self.assertTrue(len(resp["product_cards"]) >= 1)
        self.assertEqual(resp["product_cards"][0]["id"], "citizen-cx-02")

    def test_turn37_how_you_offer_does_not_trigger_discount_guardrail(self):
        """Phrase 'how you offer against my request to print 6x2?' must NOT trigger discount refusal."""
        query = "its only print 8x12 and how you offer against my request to print 6x2?"
        self.assertFalse(is_discount_inquiry(query))

        state = ConversationState(session_id="reg_turn37")
        state.category = "citizen_photo"
        resp = self.orchestrator.process_turn(
            query,
            session_id="reg_turn37",
            state=state
        )
        reply = resp["reply"]
        # Must NOT be the commercial discount refusal
        self.assertNotIn("For pricing details, special discounts, bulk promotions, or commercial offers", reply)
        # Must address model recommendation and propose CX-02
        self.assertIn("CX-02", reply)

    def test_how_can_i_buy_this_consumable(self):
        """When a consumable is active and user asks 'how can i buy this', bot must return purchase instructions for that consumable, not recommend a printer."""
        state = ConversationState(session_id="test_buy_consumable")
        r1 = self.orchestrator.process_turn("c13t49n400", session_id="test_buy_consumable", state=state)
        self.assertTrue(len(r1.get("consumable_cards", [])) >= 1)

        r2 = self.orchestrator.process_turn("how can i buy this", session_id="test_buy_consumable", state=state)
        reply = r2["reply"]
        self.assertEqual(r2.get("source"), "route:purchase:consumable")
        self.assertIn("Epson Dye Sublimation Yellow Ink", reply)
        self.assertIn("https://www.keplertechllc.com/product/c13t49n400-epson-dye-sublimation-yellow-ink/", reply)
        self.assertIn("sales@keplertech.ae", reply)
        self.assertNotIn("matching catalogue printer", reply.lower())
        self.assertEqual(len(r2.get("product_cards", [])), 0)
        self.assertTrue(len(r2.get("consumable_cards", [])) >= 1)

    def test_how_can_i_buy_this_hardware(self):
        """When a printer is active and user asks 'how can i buy this', bot must return purchase instructions for the printer."""
        state = ConversationState(session_id="test_buy_hw")
        r1 = self.orchestrator.process_turn("tell me about epson sc-t3100", session_id="test_buy_hw", state=state)
        self.assertTrue(len(r1.get("product_cards", [])) >= 1)

        r2 = self.orchestrator.process_turn("how can i buy this", session_id="test_buy_hw", state=state)
        reply = r2["reply"]
        self.assertEqual(r2.get("source"), "route:purchase:hardware")
        self.assertIn("Epson SureColor SC-T3100", reply)
        self.assertIn("AED 3,880.00", reply)
        self.assertIn("sales@keplertech.ae", reply)
        self.assertTrue(len(r2.get("product_cards", [])) >= 1)

    def test_how_much_is_this_consumable(self):
        """When a consumable is active and user asks 'how much is this', bot must return the official consumable price."""
        state = ConversationState(session_id="test_price_consumable")
        self.orchestrator.process_turn("c13t49n400", session_id="test_price_consumable", state=state)

        r2 = self.orchestrator.process_turn("how much is this", session_id="test_price_consumable", state=state)
        reply = r2["reply"]
        self.assertEqual(r2.get("source"), "route:consumable_price_inquiry")
        self.assertIn("AED 110.00", reply)
        self.assertIn("Epson Dye Sublimation Yellow Ink", reply)


if __name__ == "__main__":
    unittest.main()
