"""
QA Automated Test Suite - Section C: Concurrency
Tests:
- Concurrent requests sent to the same session from threads
- Verification of no crashes (no SQLite database locks)
- Verification that both messages are saved, no duplicate rows, and replies are valid
"""

import unittest
import os
import uuid
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_isolated.db")


class TestSectionCConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True

    def setUp(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        customer_repository.db_path = TEST_DB_PATH
        customer_repository._init_db()
        state_repository.db_path = TEST_DB_PATH
        state_repository._init_db()

        with state_manager._lock:
            state_manager._store.clear()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_c1_concurrent_messages_same_session(self):
        """Send two messages to the same session simultaneously in parallel threads."""
        session_id = f"sess_concurrent_{uuid.uuid4().hex[:8]}"

        def post_message(msg):
            # Each thread gets its own test_client
            client = app.test_client()
            resp = client.post("/api/chat", json={
                "session_id": session_id,
                "message": msg
            })
            return resp.status_code, resp.get_json()

        queries = [
            "What is the print speed of the Epson SureColor SC-T3100?",
            "Does the Epson SureColor SC-T3100 support Wi-Fi connectivity?"
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(post_message, q) for q in queries]
            results = [f.result() for f in futures]

        # 1. Both calls must succeed without crash or database lock error
        for status_code, body in results:
            self.assertEqual(status_code, 200, f"Concurrent call failed: {body}")
            self.assertTrue(body.get("success"), f"Success flag False: {body}")
            self.assertTrue(len(body.get("reply", "")) > 10)

        # 2. Check history in StateManager / SQLite
        history = state_manager.get_history(session_id)

        # There should be turns for both messages (user + assistant for each query)
        user_messages = [m.get("content") for m in history if m.get("role") == "user"]
        self.assertGreaterEqual(len(user_messages), 2, f"Expected at least 2 user messages, found: {user_messages}")

        # Check for duplicate consecutive messages
        for i in range(len(history) - 1):
            curr_content = history[i].get("content")
            next_content = history[i+1].get("content")
            if history[i].get("role") == history[i+1].get("role"):
                self.assertNotEqual(
                    curr_content, next_content,
                    f"Found identical consecutive duplicate message in history: {curr_content}"
                )

    def test_c2_concurrent_sessions_under_load(self):
        """Send 6 messages across 3 distinct sessions in parallel."""
        sessions = [f"sess_load_{i}_{uuid.uuid4().hex[:6]}" for i in range(3)]
        tasks = []
        for i, sid in enumerate(sessions):
            tasks.append((sid, f"Query 1 for session {i}: Epson P900 resolution"))
            tasks.append((sid, f"Query 2 for session {i}: Citizen CX-02 print speed"))

        def run_task(item):
            sid, msg = item
            client = app.test_client()
            resp = client.post("/api/chat", json={"session_id": sid, "message": msg})
            return sid, resp.status_code, resp.get_json()

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(run_task, tasks))

        for sid, status, body in results:
            self.assertEqual(status, 200, f"Session {sid} failed under load: {body}")
            self.assertTrue(body.get("success"))


if __name__ == "__main__":
    unittest.main()
