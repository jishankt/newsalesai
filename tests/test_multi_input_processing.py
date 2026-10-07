import unittest
from app import app
from conversation.normalizer import normalize_category
from domain.state_store import state_manager


class TestMultiInputProcessing(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_normalize_category_multi_input_correction(self):
        """Tests that when a user sends multiple inputs or lines with a correction, the latest intent prevails."""
        # Exact scenario from user: sent photo booth first, then corrected to photo printer
        cat = normalize_category("i need a printer for photo booth\nsorry i want photo printer")
        self.assertEqual(cat, "photography_large_format")

        # Reversed order: sent photo printer first, then clarified photo booth
        cat2 = normalize_category("i want a photo printer\nactually for photo booth events")
        self.assertEqual(cat2, "citizen_photo")

        # Complementary lines: technical plotter followed by A0 size specification
        cat3 = normalize_category("technical plotter\nA0 blueprints")
        self.assertEqual(cat3, "technical_large_format")

    def test_api_chat_accepts_messages_array(self):
        """Tests that /api/chat accepts multiple inputs under 'messages' array and answers with one coherent output."""
        session_id = "test-multi-input-session-1"
        state_manager.reset(session_id)

        response = self.client.post("/api/chat", json={
            "session_id": session_id,
            "messages": [
                "i need a printer for photo booth",
                "sorry i want photo printer"
            ]
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        reply = data.get("reply", "")
        self.assertTrue(len(reply) > 0)

        # Inspect history to ensure all user inputs were recorded along with exactly ONE assistant reply
        history = state_manager.get_history(session_id)
        user_turns = [t for t in history if t.get("role") == "user"]
        assistant_turns = [t for t in history if t.get("role") == "assistant"]

        self.assertEqual(len(user_turns), 2)
        self.assertEqual(user_turns[0]["content"], "i need a printer for photo booth")
        self.assertEqual(user_turns[1]["content"], "sorry i want photo printer")
        self.assertEqual(len(assistant_turns), 1)

    def test_api_chat_cancel_endpoint(self):
        """Tests that /api/chat/cancel properly sets invalidation token for superseded turns."""
        response = self.client.post("/api/chat/cancel", json={"session_id": "sess-cancel-test"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))


if __name__ == "__main__":
    unittest.main()
