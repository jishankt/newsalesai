"""
Regression Test Suite for Session b3e67673 Failure Modes.

Validates fixes for:
1. Turn 1: Canvas printer with 'upto 40"' width correctly routes to 44" photo large format.
2. Turns 11-14: Inquiring about consumables for an unapproved printer (D1000) does not loop.
3. Turn 15: Inquiring about canvas for pigment inks returns verified media information and does not loop.
4. Turn 17: 'do have F100?' routes to the printer hardware, not ink cartridges.
5. Turn 20: F100 inquiries do not trigger false relaxation error due to leftover requirements.
6. Turns 23-28: Asking 'does it print a3?' on the SC-F100 answers factually and recommends the SC-F500.
"""

import unittest
from domain.conversation_state import ConversationState
from agent.orchestrator import orchestrator


class TestSessionB3e67673Regression(unittest.TestCase):

    def test_turn1_canvas_40_inch_routes_to_photo_large_format(self):
        """'i need a canvas printer which can print upto 40"' must route to 44-inch photo large format."""
        state = ConversationState(session_id="test-b3e-turn1")
        res = orchestrator.process_turn("i need a canvas printer which can print upto 40\"", state=state)
        
        # Must detect photography_large_format
        self.assertEqual(state.category, "photography_large_format")
        # 40" requirement maps to 44-inch roll width
        self.assertEqual(state.requirements.get("print_width"), 44)
        self.assertEqual(state.requirements.get("application"), "canvas")
        # Must not ask generic open category question
        reply = res.get("reply", "")
        self.assertNotIn("What will you primarily print", reply)
        self.assertNotIn("sublimation merchandise (mugs & T-shirts)", reply)

    def test_turns11_to_14_unapproved_model_consumables_does_not_loop(self):
        """Inquiring about consumables for D1000 must not repeat the question indefinitely."""
        state = ConversationState(session_id="test-b3e-d1000-ink")
        
        # Turn 1: Unapproved printer query
        orchestrator.process_turn("do you sell D1000 printer?", state=state)
        
        # Turn 2: Ink inquiry
        res2 = orchestrator.process_turn("do you have ink for this?", state=state)
        self.assertEqual(state.awaiting_field, "printer_model")
        
        # Turn 3: User answers D1000
        res3 = orchestrator.process_turn("D1000", state=state)
        reply3 = res3.get("reply", "")
        
        # Must explain D1000 consumables are not carried, and MUST NOT repeat the prompt
        self.assertIn("D1000", reply3)
        self.assertNotIn("Which printer or scanner model do you need consumables for?", reply3)
        self.assertIsNone(state.awaiting_field)

    def test_turn15_canvas_media_query_returns_media_details(self):
        """'do you sell canvas for pigment inks' returns fine art canvas media details without looping."""
        state = ConversationState(session_id="test-b3e-canvas-media")
        res = orchestrator.process_turn("do you sell canvas for pigment inks", state=state)
        reply = res.get("reply", "")
        
        self.assertIn("Exhibition Canvas", reply)
        self.assertIn("pigment", reply.lower())
        self.assertNotIn("Which printer or scanner model do you need consumables for?", reply)
        self.assertIsNone(state.awaiting_field)

    def test_turn17_do_have_f100_recommends_printer_not_inks(self):
        """'do have F100?' must display the Epson SureColor SC-F100 printer, not consumable ink cartridges."""
        state = ConversationState(session_id="test-b3e-f100-hw")
        # Put state into awaiting printer model first (as happened after turn 16)
        state.awaiting_field = "printer_model"
        state.category = "consumable"
        
        res = orchestrator.process_turn("do have F100?", state=state)
        cards = res.get("cards", [])
        
        self.assertEqual(state.category, "dye_sublimation")
        # Must return hardware card for F100 or hardware specs, not ink bottles
        self.assertTrue(len(cards) > 0)
        self.assertEqual(cards[0]["id"], "epson-sc-f100")
        self.assertNotIn("C13T49N100", res.get("reply", ""))

    def test_turn20_f100_inquiry_does_not_trigger_false_relaxation(self):
        """Switching from large-format to F100 must not trigger false relaxation error."""
        state = ConversationState(session_id="test-b3e-no-false-relax")
        # Simulate earlier large format state
        state.category = "photography_large_format"
        state.requirements = {"photo_form_factor": "large", "print_width": 44}
        
        # User asks for F100
        res = orchestrator.process_turn("how bout F100 printer,do you have stokck?", state=state)
        reply = res.get("reply", "")
        
        self.assertNotIn("I couldn’t find a catalogue printer matching all those requirements", reply)
        self.assertNotIn("relaxing the size", reply)
        self.assertEqual(state.category, "dye_sublimation")

    def test_turns23_and_27_f100_a3_capability_inquiry(self):
        """Asking 'does it print a3?' on the SC-F100 explains it is A4 and recommends the SC-F500."""
        state = ConversationState(session_id="test-b3e-f100-a3")
        # Turn 1: Inquire about F100
        orchestrator.process_turn("Tell me about the Epson F100", state=state)
        self.assertEqual(state.active_product_id, "epson-sc-f100")
        
        # Turn 2: User asks technical question
        res2 = orchestrator.process_turn("does it print a3?", state=state)
        reply2 = res2.get("reply", "")
        
        # Must answer factually about A4 and recommend SC-F500
        self.assertIn("A4", reply2)
        self.assertIn("SC-F500", reply2)
        self.assertNotIn("Approximately how many items, prints, or transfers", reply2)
        self.assertNotIn("I couldn’t find a catalogue printer matching all those requirements", reply2)
        
        # Cards should include the recommended SC-F500
        cards = res2.get("cards", [])
        self.assertTrue(any("f500" in c["id"] for c in cards))


if __name__ == "__main__":
    unittest.main()
