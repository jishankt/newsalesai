import unittest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


class TestConsumableOrProductDisambiguation(unittest.TestCase):
    """
    Test that when a customer asks for the next product following a consumables inquiry,
    the assistant asks whether they want the printer itself or its consumables,
    and then accurately delivers the chosen item.
    """

    def test_next_product_disambiguation_flow_consumables(self):
        state = ConversationState(session_id="test-disambig-flow-1")

        # Turn 1: User asks for consumables for F100
        r1 = orchestrator.process_turn("i need consumable for f100", state=state)
        self.assertIn("SC-F100", r1["reply"])
        self.assertGreater(len(r1["consumable_cards"]), 0)

        # Turn 2: User asks for next product ambiguously ("i want p900")
        r2 = orchestrator.process_turn("i want p900", state=state)
        self.assertEqual(state.awaiting_field, "product_or_consumable")
        self.assertEqual(state.pending_disambiguation_model, "epson-sc-p900")
        self.assertIn("printer itself", r2["reply"].lower())
        self.assertIn("consumables", r2["reply"].lower())
        self.assertIn("SC-P900 Printer", r2["suggested_chips"])
        self.assertIn("SC-P900 Consumables", r2["suggested_chips"])
        self.assertEqual(len(r2["product_cards"]), 0)
        self.assertEqual(len(r2["consumable_cards"]), 0)

        # Turn 3: User selects consumables
        r3 = orchestrator.process_turn("SC-P900 Consumables", state=state)
        self.assertIsNone(state.awaiting_field)
        self.assertIn("SC-P900", r3["reply"])
        self.assertGreater(len(r3["consumable_cards"]), 0)
        self.assertEqual(len(r3["product_cards"]), 0)

    def test_next_product_disambiguation_flow_printer(self):
        state = ConversationState(session_id="test-disambig-flow-2")

        # Turn 1: User asks for consumables for F100
        orchestrator.process_turn("i need consumable for f100", state=state)

        # Turn 2: User asks for next product ambiguously ("what about p900")
        r2 = orchestrator.process_turn("what about p900", state=state)
        self.assertEqual(state.awaiting_field, "product_or_consumable")

        # Turn 3: User selects printer
        r3 = orchestrator.process_turn("printer", state=state)
        self.assertIsNone(state.awaiting_field)
        self.assertIn("SC-P900", r3["reply"])
        self.assertGreater(len(r3["product_cards"]), 0)
        self.assertEqual(len(r3["consumable_cards"]), 0)

    def test_explicit_printer_request_does_not_disambiguate(self):
        state = ConversationState(session_id="test-disambig-explicit-printer")
        orchestrator.process_turn("i need consumable for f100", state=state)

        # User explicitly says "i want p900 printer"
        r2 = orchestrator.process_turn("i want p900 printer", state=state)
        self.assertIsNone(state.awaiting_field)
        self.assertGreater(len(r2["product_cards"]), 0)

    def test_explicit_consumable_request_does_not_disambiguate(self):
        state = ConversationState(session_id="test-disambig-explicit-ink")
        orchestrator.process_turn("i need consumable for f100", state=state)

        # User explicitly says "i want p900 ink"
        r2 = orchestrator.process_turn("i want p900 ink", state=state)
        self.assertIsNone(state.awaiting_field)
        self.assertGreater(len(r2["consumable_cards"]), 0)


if __name__ == "__main__":
    unittest.main()
