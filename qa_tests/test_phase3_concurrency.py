"""
QA Test Suite - Phase 3: Concurrency, Session Locking, Optimistic Concurrency & Timeout
Tests:
- Two simultaneous requests on the same session are saved in order with none lost (using threads)
- Different sessions do not block each other
- Lock acquire timeout returns HTTP 429 with 'Still working on your previous message, please wait a moment.'
- Idle session locks are cleaned up to prevent memory growth
- Optimistic database locking via 'version' column with automatic history merging on conflict
- LLM call timeout with graceful fallback message
"""

import unittest
import os
import time
import threading
import requests
from unittest.mock import patch, MagicMock
from app import app
from persistence.state_repository import state_repository
from persistence.customer_repository import customer_repository
from domain.state_store import state_manager, session_lock_manager
from domain.conversation_state import ConversationState

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_phase3.db")


class TestPhase3Concurrency(unittest.TestCase):
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
        with session_lock_manager._mutex:
            session_lock_manager._locks.clear()

        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_two_simultaneous_requests_same_session_saved_in_order(self):
        """Two concurrent requests on the same session must both be saved in order with none lost."""
        sid = "sess_concurrent_order"
        results = []
        errors = []

        def send_msg(msg, delay):
            time.sleep(delay)
            try:
                res = self.client.post("/api/chat", json={"session_id": sid, "message": msg})
                results.append((msg, res.status_code, res.get_json()))
            except Exception as e:
                errors.append(e)

        # Mock orchestrator.process_turn to simulate slight execution time
        def fake_process_turn(raw_message, session_id, history, state, model_name=None):
            time.sleep(0.15)
            reply = f"Acknowledged: {raw_message}"
            return {
                "reply": reply,
                "source": "route:test",
                "product_cards": [],
                "consumable_cards": [],
                "suggested_chips": ["Specs"],
                "grounding": {"status": "mock", "is_grounded": True, "notes": []},
                "nlp": {"intent": "TEST", "normalized_text": raw_message},
                "state": state,
                "retrieved_items": [],
                "active_agent": "Front Desk"
            }

        with patch("app.new_orchestrator.process_turn", side_effect=fake_process_turn):
            t1 = threading.Thread(target=send_msg, args=("First message", 0.0))
            t2 = threading.Thread(target=send_msg, args=("Second message", 0.02))

            t1.start()
            t2.start()
            t1.join()
            t2.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 2)
        for _, status, _ in results:
            self.assertEqual(status, 200)

        # Verify history in database contains both turns in order
        persisted = state_repository.get_session(sid)
        self.assertIsNotNone(persisted)
        _, history = persisted

        # 2 turns * 2 messages each = 4 messages
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "First message")
        self.assertEqual(history[1]["content"], "Acknowledged: First message")
        self.assertEqual(history[2]["content"], "Second message")
        self.assertEqual(history[3]["content"], "Acknowledged: Second message")

    def test_different_sessions_do_not_block_each_other(self):
        """Requests on different sessions execute independently without blocking each other."""
        sid_a = "sess_independent_a"
        sid_b = "sess_independent_b"
        start_times = {}
        end_times = {}

        def send_msg(sid, delay_in_turn):
            def mock_turn(*args, **kwargs):
                time.sleep(delay_in_turn)
                return {
                    "reply": f"Reply for {sid}",
                    "source": "route:test",
                    "product_cards": [],
                    "consumable_cards": [],
                    "suggested_chips": [],
                    "grounding": {"status": "ok", "is_grounded": True, "notes": []},
                    "nlp": {"intent": "TEST", "normalized_text": ""},
                    "state": kwargs.get("state") or args[3],
                    "retrieved_items": [],
                    "active_agent": "Front Desk"
                }

            start_times[sid] = time.time()
            with patch("app.new_orchestrator.process_turn", side_effect=mock_turn):
                self.client.post("/api/chat", json={"session_id": sid, "message": "hello"})
            end_times[sid] = time.time()

        # Session A takes 0.3s, Session B takes 0.05s
        t_a = threading.Thread(target=send_msg, args=(sid_a, 0.3))
        t_b = threading.Thread(target=send_msg, args=(sid_b, 0.05))

        t_a.start()
        time.sleep(0.02)
        t_b.start()

        t_b.join()
        # Session B must finish before Session A
        duration_b = end_times[sid_b] - start_times[sid_b]
        self.assertLess(duration_b, 0.2)
        t_a.join()

    def test_session_lock_timeout_returns_429(self):
        """When lock cannot be acquired within timeout, returns 429 with specific message."""
        sid = "sess_timeout_test"

        # Manually hold lock on sid
        session_lock_manager.acquire(sid)

        # Patch default timeout to 0.1s for fast test
        with patch.object(session_lock_manager, "default_timeout", 0.1):
            res = self.client.post("/api/chat", json={"session_id": sid, "message": "hello"})
            self.assertEqual(res.status_code, 429)
            body = res.get_json()
            self.assertIn("Still working on your previous message, please wait a moment.", body.get("error", ""))

        session_lock_manager.release(sid)

    def test_idle_locks_cleaned_up(self):
        """Idle locks not used within max_idle_seconds are automatically cleaned up."""
        session_lock_manager.max_idle_seconds = 0.05
        # Acquire and release 5 sessions
        for i in range(5):
            s_name = f"sess_temp_{i}"
            session_lock_manager.acquire(s_name)
            session_lock_manager.release(s_name)

        self.assertEqual(len(session_lock_manager._locks), 5)
        time.sleep(0.08)

        # Acquiring a new session triggers cleanup of idle locks
        session_lock_manager.acquire("new_active_session")
        session_lock_manager.release("new_active_session")

        # The 5 old sessions must be cleaned up
        for i in range(5):
            self.assertNotIn(f"sess_temp_{i}", session_lock_manager._locks)

    def test_optimistic_locking_conflict_retry_and_history_merge(self):
        """Database optimistic locking detects version conflict and merges history turns without data loss."""
        sid = "sess_optimistic_test"
        state = ConversationState(session_id=sid)

        # 1. Initial save at version 1
        init_history = [{"role": "user", "content": "T1"}, {"role": "assistant", "content": "A1"}]
        saved = state_repository.save_session(sid, state, init_history)
        self.assertTrue(saved)
        self.assertEqual(state._version, 1)

        # 2. Simulate Worker 2 concurrently updating the session to version 2
        worker2_state = ConversationState(session_id=sid)
        worker2_state._version = 1
        worker2_history = [
            {"role": "user", "content": "T1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Worker2 Turn"},
            {"role": "assistant", "content": "Worker2 Reply"},
        ]
        saved2 = state_repository.save_session(sid, worker2_state, worker2_history)
        self.assertTrue(saved2)
        self.assertEqual(worker2_state._version, 2)

        # 3. Worker 1 tries to save with stale version=1 and its own turn
        worker1_history = [
            {"role": "user", "content": "T1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Worker1 Turn"},
            {"role": "assistant", "content": "Worker1 Reply"},
        ]
        # state._version is still 1
        saved1 = state_repository.save_session(sid, state, worker1_history)
        self.assertTrue(saved1)

        # 4. Verify merged result in DB has all turns preserved
        _, final_history = state_repository.get_session(sid)
        contents = [m["content"] for m in final_history]

        self.assertIn("T1", contents)
        self.assertIn("A1", contents)
        self.assertIn("Worker2 Turn", contents)
        self.assertIn("Worker2 Reply", contents)
        self.assertIn("Worker1 Turn", contents)
        self.assertIn("Worker1 Reply", contents)
        self.assertEqual(len(final_history), 6)

    def test_llm_timeout_fallback(self):
        """LLM timeout triggers graceful fallback message and records it in history."""
        sid = "sess_timeout_fallback"

        with patch("app.new_orchestrator.process_turn", side_effect=requests.exceptions.ReadTimeout("Ollama read timed out")):
            res = self.client.post("/api/chat", json={"session_id": sid, "message": "Show me printers"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("I apologize for the delay", data.get("reply", ""))
            self.assertIn("taking longer than expected", data.get("reply", ""))

        # Verify saved in history
        history = state_manager.get_history(sid)
        self.assertEqual(len(history), 2)
        self.assertIn("taking longer than expected", history[1]["content"])


if __name__ == "__main__":
    unittest.main()
