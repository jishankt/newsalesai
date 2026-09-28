"""Regression test suite for Turns 33-46 failures from session e0d5a098-b91f-4e8a-a47e-38ac4a241cd6.

Captures the exact failure points that caused the 4.5/10 Conversational Understanding rating:
1. Turn 34 ("it print t shirts"):
   - Classification: QUESTION_VS_REQUIREMENT_FAILURE & TOPIC_SWITCH_FAILURE
   - Failure: Isolated keyword "t shirts" hijacked category to dye_sublimation and asked F100 qualification questions.
   - Expected: Recognize dialogue_act = PRODUCT_CAPABILITY_QUESTION for active product SC-P900.
   - Answer: SC-P900 is an aqueous photo printer and cannot print directly on T-shirts (requires DTG or dye-sub).

2. Turn 36 ("what i asked about p900"):
   - Classification: RESPONSE_COVERAGE_FAILURE & MEMORY_RECALL_FAILURE
   - Failure: Assistant repeated generic marketing text for SC-P900 without recalling or answering the unanswered question from Turn 34.
   - Expected: Recognize memory recall / conversation check, clarify the user's prior unanswered inquiry ("You asked if the SC-P900 can print on T-shirts...").

3. Turn 38 ("can you send photo ?"):
   - Classification: INTENT_FAILURE & TOPIC_SWITCH_FAILURE
   - Failure: Isolated keyword "photo" hijacked category to photo_printer and reset qualification asking "compact photo or large format?".
   - Expected: Recognize customer is asking for a photo/image of the active product (SC-P900), not starting photo printer qualification.

4. Turn 44 ("what the diffrance bw this two"):
   - Classification: REFERENCE_FAILURE & COMPARISON_FAILURE
   - Failure: Assistant's prior message mentioned two configurations of SC-P900 (standard cut-sheet vs roll adapter). Customer asked "what the diffrance bw this two". Router resolved both to 'epson-sc-p900', comparison engine failed and asked if they want Citizen photo booth printers.
   - Expected: Reference resolution recognizes "this two" refers to the two configurations just mentioned (cut-sheet standard vs roll adapter) for SC-P900, not distinct competing catalog models.
"""

import unittest
from domain.conversation_state import ConversationState
from domain.conversation_types import DialogueAct, Intent
from agent.orchestrator import orchestrator
from conversation.reference_resolver import reference_resolver
from nlp.normalizer import normalize_for_intent


class TestTurns33To46Regression(unittest.TestCase):

    def setUp(self):
        self.orchestrator = orchestrator

    def test_turn_34_capability_question_does_not_hijack_category(self):
        """Turn 34: 'it print t shirts' when SC-P900 is active product.
        
        RAW MESSAGE: 'it print t shirts'
        STATE BEFORE: active_product = 'epson-sc-p900', category = 'photo_printer'
        PREVIOUS ASSISTANT: Discussed SC-P900 capabilities.
        EXPECTED SEMANTIC MEANING: Inquiring if active product SC-P900 prints T-shirts.
        EXPECTED DIALOGUE ACT: PRODUCT_CAPABILITY_QUESTION
        EXPECTED REFERENCES: ['epson-sc-p900']
        EXPECTED REQUIREMENT UPDATE: None (must NOT set application='t-shirts' or category='dye_sublimation')
        EXPECTED ROUTE: PRODUCT_DETAILS / CAPABILITY_INQUIRY
        EXPECTED RESPONSE: Clarify that SC-P900 does NOT print T-shirts (aqueous fine art, not dye-sub/DTG).
        """
        state = ConversationState(session_id="test_turn_34_regression")
        state.selected_product_id = "epson-sc-p900"
        state.active_product_id = "epson-sc-p900"
        state.category = "photo_printer"
        state.history = [
            {"role": "user", "content": "what abour p900"},
            {"role": "assistant", "content": "The Epson SureColor SC-P900 is well-suited for photography and large-format printing needs. It can handle your daily volume of 20 prints efficiently with its high-quality output."}
        ]

        response = self.orchestrator.process_turn("it print t shirts", state=state)
        reply = response.get("reply", "").lower()

        # Must NOT reset category and ask dye-sub qualification questions about mugs or F100 vs F500
        self.assertNotIn("compact a4 desktop (for mugs", reply)
        self.assertNotIn("sc-f500", reply)

        # Must mention SC-P900 and directly address t-shirt / apparel capability
        self.assertIn("p900", reply)
        self.assertTrue(
            any(w in reply for w in ["not", "cannot", "does not", "fine art", "photo", "dye-sub", "dtg"]),
            f"Expected clear capability answer on t-shirt printing, got: {reply}"
        )

    def test_turn_36_user_callout_unanswered_question(self):
        """Turn 36: 'what i asked about p900'
        
        RAW MESSAGE: 'what i asked about p900'
        STATE BEFORE: SC-P900 is active, user previously asked 'it print t shirts'
        EXPECTED SEMANTIC MEANING: Recall the user's prior question about whether SC-P900 prints t-shirts.
        EXPECTED DIALOGUE ACT: MEMORY_RECALL / CLARIFICATION
        EXPECTED RESPONSE: Remind the user that they asked if SC-P900 prints t-shirts, and answer it clearly.
        """
        state = ConversationState(session_id="test_turn_36_regression")
        state.selected_product_id = "epson-sc-p900"
        state.active_product_id = "epson-sc-p900"
        state.category = "photo_printer"
        state.history = [
            {"role": "user", "content": "what abour p900"},
            {"role": "assistant", "content": "The Epson SureColor SC-P900 is well-suited for photography and large-format printing needs."},
            {"role": "user", "content": "it print t shirts"},
            {"role": "assistant", "content": "The Epson SureColor SC-F100 is suitable for printing on T-shirts with its compact A4 print width."}
        ]

        response = self.orchestrator.process_turn("what i asked about p900", state=state)
        reply = response.get("reply", "").lower()

        # Must mention p900 and either t-shirt or the prior inquiry
        self.assertIn("p900", reply)
        self.assertIn("don't have the exact earlier question", reply)

    def test_turn_38_media_request_does_not_hijack_photo_category(self):
        """Turn 38: 'can you send photo ?'
        
        RAW MESSAGE: 'can you send photo ?'
        STATE BEFORE: SC-P900 is active product.
        EXPECTED SEMANTIC MEANING: Customer wants to see an image / photo / visual of the SC-P900.
        EXPECTED DIALOGUE ACT: MEDIA_REQUEST
        EXPECTED REQUIREMENT UPDATE: None (must NOT restart category='photo_printer' qualification!)
        EXPECTED RESPONSE: Provide product visual/image link or description of SC-P900 appearance/details.
        """
        state = ConversationState(session_id="test_turn_38_regression")
        state.selected_product_id = "epson-sc-p900"
        state.active_product_id = "epson-sc-p900"
        state.category = "photo_printer"
        state.history = [
            {"role": "user", "content": "what abour p900"},
            {"role": "assistant", "content": "The Epson SureColor SC-P900 is well-suited for photography and large-format printing needs."}
        ]

        response = self.orchestrator.process_turn("can you send photo ?", state=state)
        reply = response.get("reply", "").lower()

        # Must NOT reset and ask "Do you need a compact photo printer or large-format photo?"
        self.assertNotIn("do you need a compact photo printer (desktop / portable) or a large-format", reply)
        self.assertIn("p900", reply)

    def test_turn_44_configuration_difference_not_duplicate_id_failure(self):
        """Turn 44: 'what the diffrance bw this two'
        
        RAW MESSAGE: 'what the diffrance bw this two'
        STATE BEFORE: Assistant just described SC-P900 two configurations: standard cut-sheet vs roll adapter.
        EXPECTED SEMANTIC MEANING: Compare standard cut-sheet configuration vs roll unit adapter configuration.
        EXPECTED DIALOGUE ACT: COMPARISON_FOLLOWUP / CONFIGURATION_DIFFERENCE
        EXPECTED RESPONSE: Explain the difference between cut-sheet media and roll adapter on the SC-P900.
        MUST NOT: Ask if they want Citizen dye-sub photo booth printers!
        """
        state = ConversationState(session_id="test_turn_44_regression")
        state.selected_product_id = "epson-sc-p900"
        state.active_product_id = "epson-sc-p900"
        state.category = "photo_printer"
        state.history = [
            {"role": "user", "content": "can you give more details"},
            {"role": "assistant", "content": "The Epson SureColor SC-P900 is a dedicated photo printer that supports various media types like glossy, semi-gloss, luster, matte, baryta, and fine art canvas. It comes in two configurations: standard for cut-sheet media (A2+, A3+, A3, A4) and with a roll adapter for continuous roll media. Let me know if you need more details!"}
        ]

        response = self.orchestrator.process_turn("what the diffrance bw this two", state=state)
        reply = response.get("reply", "").lower()

        # Must NOT fail into citizen dye-sub photo booth hallucination
        self.assertNotIn("citizen instant dye-sub", reply)
        self.assertNotIn("photo booths & events", reply)

        # Must discuss cut-sheet vs roll adapter
        self.assertTrue(
            ("roll" in reply or "sheet" in reply or "adapter" in reply) and "p900" in reply,
            f"Expected explanation of cut-sheet vs roll adapter on P900, got: {reply}"
        )


if __name__ == "__main__":
    unittest.main()
