"""
Comprehensive test suite for Live Sales Desk & Human Agent Takeover.
Tests:
1. StateManager takeover, release, and message queuing.
2. /api/chat bypass when human agent is active.
3. Live desk API endpoints: sessions, takeover, release, send, poll.
4. Client-side polling endpoint /api/chat/poll.
5. Automatic escalation triggers for human agent requests.
"""

import json
import unittest
import time
from app import app
from domain.state_store import state_manager


class TestLiveSalesDesk(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.session_id = f"test-desk-{int(time.time() * 1000)}"

    def tearDown(self):
        state_manager.delete(self.session_id)

    def test_01_state_manager_takeover_and_release(self):
        """Verify state transitions when an agent takes over and releases a session."""
        state = state_manager.set_agent_takeover(
            session_id=self.session_id,
            agent_name="Sarah - Technical Advisor",
            reason="manual_takeover"
        )
        self.assertTrue(state.human_agent_active)
        self.assertEqual(state.human_agent_name, "Sarah - Technical Advisor")
        self.assertTrue(state.handover_triggered)
        self.assertEqual(state.handover_reason, "manual_takeover")

        history = state_manager.get_history(self.session_id)
        self.assertGreater(len(history), 0)
        self.assertEqual(history[-1].get("event"), "agent_takeover")

        # Release
        released_state = state_manager.release_agent_takeover(self.session_id)
        self.assertFalse(released_state.human_agent_active)
        history_after = state_manager.get_history(self.session_id)
        self.assertEqual(history_after[-1].get("event"), "agent_released")

    def test_02_add_agent_message_and_poll(self):
        """Verify sales agent messages are appended to history and retrieved via poll."""
        state_manager.set_agent_takeover(self.session_id, agent_name="Ahmed")
        msg = state_manager.add_agent_message(
            session_id=self.session_id,
            message="Hello! I can arrange an on-site demo of the SC-T5405 for you.",
            agent_name="Ahmed"
        )
        self.assertEqual(msg["sender"], "agent")
        self.assertEqual(msg["agent_name"], "Ahmed")

        poll_res = state_manager.get_poll_data(self.session_id, last_count=0)
        self.assertTrue(poll_res["human_agent_active"])
        self.assertGreater(len(poll_res["new_messages"]), 0)
        agent_msgs = [m for m in poll_res["new_messages"] if m.get("sender") == "agent"]
        self.assertEqual(len(agent_msgs), 1)
        self.assertIn("SC-T5405", agent_msgs[0]["content"])

    def test_03_chat_endpoint_bypasses_ai_when_agent_active(self):
        """When human_agent_active is True, /api/chat routes to agent queue without calling LLM."""
        state_manager.set_agent_takeover(self.session_id, agent_name="Sarah Specialist")

        payload = {
            "session_id": self.session_id,
            "message": "Can you offer me 15% discount on 3 units of AM-C4000?"
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["source"], "human_agent_queue")
        self.assertTrue(data["human_agent_active"])
        self.assertIn("Sarah Specialist", data["reply"])

        # Customer message should be stored in history for agent to read
        history = state_manager.get_history(self.session_id)
        user_msgs = [m for m in history if m.get("role") == "user"]
        self.assertGreater(len(user_msgs), 0)
        self.assertIn("15% discount", user_msgs[-1]["content"])

    def test_04_live_desk_api_endpoints(self):
        """Test the REST endpoints: takeover, send, poll, release, sessions."""
        # 1. Takeover
        takeover_res = self.client.post("/api/admin/live-desk/takeover", json={
            "session_id": self.session_id,
            "agent_name": "Tariq Sales",
            "reason": "customer_support"
        })
        self.assertEqual(takeover_res.status_code, 200)
        self.assertTrue(takeover_res.get_json()["state"]["human_agent_active"])

        # 2. Agent Send
        send_res = self.client.post("/api/admin/live-desk/send", json={
            "session_id": self.session_id,
            "message": "Official quotation has been prepared.",
            "agent_name": "Tariq Sales"
        })
        self.assertEqual(send_res.status_code, 200)
        self.assertEqual(send_res.get_json()["sent_message"]["sender"], "agent")

        # 3. Admin Poll
        poll_res = self.client.get(f"/api/admin/live-desk/poll?session_id={self.session_id}&last_count=0")
        self.assertEqual(poll_res.status_code, 200)
        p_data = poll_res.get_json()
        self.assertTrue(p_data["human_agent_active"])
        self.assertEqual(p_data["human_agent_name"], "Tariq Sales")

        # 4. Client Poll
        client_poll = self.client.get(f"/api/chat/poll?session_id={self.session_id}&last_count=0")
        self.assertEqual(client_poll.status_code, 200)
        cp_data = client_poll.get_json()
        self.assertTrue(cp_data["human_agent_active"])
        self.assertGreater(len(cp_data["new_messages"]), 0)

        # 5. Live Desk Sessions queue
        queue_res = self.client.get("/api/admin/live-desk/sessions?filter=all")
        self.assertEqual(queue_res.status_code, 200)
        q_data = queue_res.get_json()
        self.assertTrue(any(s["session_id"] == self.session_id for s in q_data["sessions"]))

        # 6. Release
        release_res = self.client.post("/api/admin/live-desk/release", json={
            "session_id": self.session_id
        })
        self.assertEqual(release_res.status_code, 200)
        self.assertFalse(release_res.get_json()["state"]["human_agent_active"])

    def test_05_escalation_triggers_for_human_agent_request(self):
        """Explicit customer request for human assistance sets handover_triggered flag."""
        payload = {
            "session_id": self.session_id,
            "message": "I would like to speak to a human agent please"
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 200)

        state = state_manager.get(self.session_id)
        self.assertIsNotNone(state)
        self.assertTrue(state.handover_triggered)
        self.assertEqual(state.handover_reason, "customer_requested_human")

        # Must appear in live desk sessions under attention
        queue_res = self.client.get("/api/admin/live-desk/sessions?filter=attention")
        self.assertEqual(queue_res.status_code, 200)
        q_data = queue_res.get_json()
        session_entry = next((s for s in q_data["sessions"] if s["session_id"] == self.session_id), None)
        self.assertIsNotNone(session_entry)
        self.assertEqual(session_entry["priority"], 1)


if __name__ == "__main__":
    unittest.main()
