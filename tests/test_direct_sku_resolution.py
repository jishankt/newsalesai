"""
Direct SKU and Consumable Part Number Resolution Tests.
Verifies that direct SKU queries (e.g. C13T11C340, C13S210057, CX2.4x6)
are immediately recognized and resolved with the exact consumable card.
"""

import unittest
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


class TestDirectSKUResolution(unittest.TestCase):

    def test_direct_sku_ink_inquiry(self):
        """'i need C13T11C340' must return the magenta ink consumable card directly."""
        state = ConversationState(session_id="test-sku-1")
        res = orchestrator.process_turn("i need C13T11C340", state=state)
        self.assertEqual(res["source"], "route:consumables:direct_sku")
        self.assertEqual(len(res["consumable_cards"]), 1)
        self.assertEqual(res["consumable_cards"][0]["sku"], "C13T11C340")
        self.assertIn("C13T11C340", res["reply"])

    def test_direct_sku_i_want_inquiry(self):
        """'i want C13T11C340' must return the magenta ink consumable card directly."""
        state = ConversationState(session_id="test-sku-2")
        res = orchestrator.process_turn("i want C13T11C340", state=state)
        self.assertEqual(res["source"], "route:consumables:direct_sku")
        self.assertEqual(len(res["consumable_cards"]), 1)
        self.assertEqual(res["consumable_cards"][0]["sku"], "C13T11C340")

    def test_direct_sku_with_ink_keyword(self):
        """'i need this ink C13T11C340' must return the magenta ink consumable card directly."""
        state = ConversationState(session_id="test-sku-3")
        res = orchestrator.process_turn("i need this ink C13T11C340", state=state)
        self.assertEqual(res["source"], "route:consumables:direct_sku")
        self.assertEqual(len(res["consumable_cards"]), 1)
        self.assertEqual(res["consumable_cards"][0]["sku"], "C13T11C340")

    def test_direct_sku_maintenance_box(self):
        """'C13S210057' maintenance box SKU returns genuine maintenance box consumable card."""
        state = ConversationState(session_id="test-sku-4")
        res = orchestrator.process_turn("C13S210057", state=state)
        self.assertEqual(res["source"], "route:consumables:direct_sku")
        self.assertEqual(len(res["consumable_cards"]), 1)
        self.assertEqual(res["consumable_cards"][0]["sku"], "C13S210057")

    def test_direct_sku_citizen_media(self):
        """'CX2.4x6' Citizen media SKU returns Citizen CX-02 media consumable card."""
        state = ConversationState(session_id="test-sku-5")
        res = orchestrator.process_turn("CX2.4x6", state=state)
        self.assertEqual(res["source"], "route:consumables:direct_sku")
        self.assertEqual(len(res["consumable_cards"]), 1)
        self.assertEqual(res["consumable_cards"][0]["sku"], "CX2.4x6")


if __name__ == "__main__":
    unittest.main()
