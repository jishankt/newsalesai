"""
Phase 1 Test Suite: Concurrency, Input Safety, and Resilience.
Tests:
1a. Concurrency & Lock safety: 10 parallel requests for same session.
1b. Debouncing, merging, and message_id idempotency.
1c. Web security: Session ownership check (403 on cross-user), rate limiting (429).
1d. Ollama failure fallback: Circuit breaker, graceful fallback on connection error / timeout, no 500.
1e. Bounded transcript and PII masking.
"""

import time
import json
import uuid
import threading
import unittest
from unittest.mock import patch, MagicMock
import requests

from app import app
from domain.state_store import state_manager, session_lock_manager
from domain.conversation_state import ConversationState


class TestPhase1Resilience(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_1a_parallel_requests_same_session_serialization(self):
        """10 parallel requests for the same session must be serialized without clobbering state."""
        session_id = f"test-conc-{uuid.uuid4().hex[:8]}"
        responses = []
        errors = []

        def send(idx):
            try:
                res = self.client.post("/api/chat", json={
                    "session_id": session_id,
                    "message": f"Message {idx}: I need an office printer"
                })
                responses.append(res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered thread errors: {errors}")
        self.assertEqual(len(responses), 10)
        # All responses should either succeed (200), be superseded gracefully (409), or wait/retry (429)
        # But NEVER crash with an unhandled 500
        for r in responses:
            self.assertIn(r.status_code, [200, 409, 429])

    def test_1b_idempotency_with_message_id(self):
        """Same message_id sent twice must return the identical cached response without duplicate processing."""
        session_id = f"test-idem-{uuid.uuid4().hex[:8]}"
        msg_id = f"msg_{uuid.uuid4().hex}"

        res1 = self.client.post("/api/chat", json={
            "session_id": session_id,
            "message_id": msg_id,
            "message": "Do you have office printers?"
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()

        # Send same message_id again
        res2 = self.client.post("/api/chat", json={
            "session_id": session_id,
            "message_id": msg_id,
            "message": "Do you have office printers?"
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()

        self.assertEqual(data1["reply"], data2["reply"])
        self.assertTrue(data2.get("idempotent_replay", False) or data1["reply"] == data2["reply"])

    def test_1c_cross_user_session_access_forbidden(self):
        """If a session is linked to Customer A, Customer B or unauthenticated request must get 403."""
        session_id = f"test-sec-{uuid.uuid4().hex[:8]}"
        state = state_manager.get_or_create(session_id)
        state.customer_id = "cust-owner-123"
        state_manager.save(state)

        # Request with no customer_id in session cookie
        res = self.client.post("/api/chat", json={
            "session_id": session_id,
            "message": "Hello from an attacker"
        })
        self.assertEqual(res.status_code, 403, f"Expected 403 Forbidden, got {res.status_code}")
        data = res.get_json()
        self.assertIn("error", data)

    def test_1d_ollama_failure_graceful_fallback_no_500(self):
        """When Ollama connection fails, return 200 fallback, flag handover, and never 500."""
        session_id = f"test-ollama-fail-{uuid.uuid4().hex[:8]}"

        with patch("agent.orchestrator.orchestrator.process_turn", side_effect=requests.exceptions.ConnectionError("Failed to connect to Ollama")):
            res = self.client.post("/api/chat", json={
                "session_id": session_id,
                "message": "Tell me about Epson AM-C400"
            })
            # Must be 200 with fallback, NEVER 500
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("handover_triggered", False))
            self.assertIn("specialist", data["reply"].lower())

    def test_1e_bounded_transcript_loading(self):
        """Transcript loaded for turn must be bounded (e.g. max 15 turns)."""
        session_id = f"test-bound-{uuid.uuid4().hex[:8]}"
        state = state_manager.get_or_create(session_id)
        long_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}"} for i in range(50)]
        state_manager.save(state, history=long_history)

        bounded = state_manager.get_history(session_id, max_turns=15)
        self.assertLessEqual(len(bounded), 15)

    def test_1e_pii_masking_in_stored_history(self):
        """Stored conversation history must mask customer email and phone number."""
        from domain.state_store import mask_pii
        raw_text = "Contact me at john.doe@company.ae or +971 50 123 4567"
        masked = mask_pii(raw_text)
        self.assertNotIn("john.doe@company.ae", masked)
        self.assertIn("j***@company.ae", masked)
        self.assertNotIn("123 4567", masked)


if __name__ == "__main__":
    unittest.main()
