"""
Phase 7 & 8 Tests: Production Hardening, Circuit Breakers, Security, Metamorphic Testing & DoD.
"""

import unittest
import time
import sqlite3
import threading
from unittest.mock import patch, MagicMock

from security.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenException
from persistence.db_pool import SQLiteConnectionPool
from app import app
from conversation.understanding import understand_turn
from conversation.dialogue_state import DialogueState
from agent.orchestrator import orchestrator as new_orchestrator


class TestPhase7And8ProductionAndDoD(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    # ── 1. Circuit Breaker State Machine ────────────────────────────────────

    def test_01_circuit_breaker_closed_to_open_transition(self):
        """Verifies circuit breaker trips to OPEN after failure threshold reached."""
        cb = CircuitBreaker(name="test_service", failure_threshold=3, recovery_timeout=0.2)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

        # Failures 1 and 2: remain CLOSED
        cb.record_failure("Err 1")
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure("Err 2")
        self.assertEqual(cb.state, CircuitState.CLOSED)

        # Failure 3: trips to OPEN
        cb.record_failure("Err 3")
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())
        self.assertFalse(cb.is_available())

    def test_02_circuit_breaker_half_open_recovery_probe(self):
        """Verifies circuit breaker allows single trial in HALF_OPEN after cooldown."""
        cb = CircuitBreaker(name="test_service", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("Err 1")
        cb.record_failure("Err 2")
        self.assertEqual(cb.state, CircuitState.OPEN)

        # Before cooldown
        self.assertFalse(cb.allow_request())

        # Wait for cooldown
        time.sleep(0.12)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request())

        # Successful probe resets to CLOSED
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.get_status()["failure_count"], 0)

    def test_03_circuit_breaker_half_open_failure_reopens(self):
        """Verifies failed probe in HALF_OPEN immediately re-opens the circuit."""
        cb = CircuitBreaker(name="test_service", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure("Err 1")
        cb.record_failure("Err 2")
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.12)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Failed probe
        cb.record_failure("Probe failed")
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    # ── 2. SQLite WAL Mode, Busy Timeout & Concurrency ──────────────────────

    def test_04_sqlite_wal_mode_and_busy_timeout(self):
        """Verifies SQLite connection pool enables WAL journal mode and busy timeout."""
        db_path = "/tmp/test_salesai_wal.db"
        try:
            conn = SQLiteConnectionPool.get_connection(db_path)
            cur = conn.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0].lower()
            self.assertEqual(journal_mode, "wal")

            cur = conn.execute("PRAGMA busy_timeout;")
            busy_timeout = cur.fetchone()[0]
            self.assertGreaterEqual(busy_timeout, 5000)
        finally:
            SQLiteConnectionPool.close_all()

    def test_05_sqlite_concurrent_multithreaded_access(self):
        """Verifies multithreaded readers/writers operate concurrently without locking."""
        db_path = "/tmp/test_salesai_concurrency.db"
        errors = []

        def worker(thread_id: int):
            try:
                conn = SQLiteConnectionPool.get_connection(db_path)
                with conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS test_data (id INT, val TEXT);")
                    conn.execute("INSERT INTO test_data VALUES (?, ?);", (thread_id, f"val_{thread_id}"))
                cur = conn.execute("SELECT COUNT(*) FROM test_data;")
                _ = cur.fetchone()[0]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        SQLiteConnectionPool.close_all()
        self.assertEqual(errors, [], f"Encountered concurrent DB errors: {errors}")

    # ── 3. Production Security Headers & Readiness Endpoint ─────────────────

    def test_06_security_headers_present_on_endpoints(self):
        """Verifies CSP, HSTS, X-Content-Type-Options, and X-Frame-Options are set."""
        resp = self.client.get("/api/health")
        self.assertIn("Content-Security-Policy", resp.headers)
        self.assertIn("Strict-Transport-Security", resp.headers)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_07_readiness_probe_exposes_circuit_breaker(self):
        """Verifies /health/ready returns status and circuit breaker diagnostic payload."""
        resp = self.client.get("/health/ready")
        self.assertIn(resp.status_code, [200, 503])
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertIn("circuit_breaker", data)
        self.assertTrue(data["catalogue_ok"])

    # ── 4. Metamorphic Testing (Input Invariance & Resiliency) ──────────────

    def test_08_metamorphic_model_name_variations(self):
        """Verifies case variations, hyphens, and shorthand resolve to identical model."""
        variants = [
            "epson surecolor sc-t3100",
            "EPSON SURECOLOR SC-T3100",
            "sc-t3100",
            "t3100",
            "SC T3100",
        ]
        resolved_entities = set()
        for query in variants:
            resolved = understand_turn(query)
            matched_names = {e.normalised_id for e in resolved.entities}
            resolved_entities.add("epson-sc-t3100" in matched_names)

        self.assertTrue(all(resolved_entities), "All name variants must resolve to epson-sc-t3100")

    def test_09_metamorphic_multilingual_greeting_resilience(self):
        """Verifies Arabic greetings and conversational mixed inputs are understood cleanly."""
        multilingual_inputs = [
            "Marhaba, I need a printer for CAD drawings",
            "Salam, what are your showroom hours in Dubai?",
            "Hello, do you deliver to Abu Dhabi?",
        ]
        for query in multilingual_inputs:
            resolved = understand_turn(query)
            self.assertIsNotNone(resolved.intent)

    # ── 5. Persona Simulator Tests ──────────────────────────────────────────

    def test_10_persona_terse_user(self):
        """Terse one-word input triggers helpful categorization chips."""
        from domain.conversation_state import ConversationState
        sid = "test_persona_terse"
        state = ConversationState(session_id=sid)
        resp = new_orchestrator.process_turn("plotter", session_id=sid, state=state)
        chips = resp.get("chips") or []
        bot_text = resp.get("reply") or resp.get("response") or ""
        self.assertGreater(len(chips), 0, "Terse user should receive category/spec options")
        self.assertNotIn("Certainly!", bot_text)

    def test_11_persona_indecisive_user(self):
        """Indecisive user receives comparative choices."""
        from domain.conversation_state import ConversationState
        sid = "test_persona_indecisive"
        state = ConversationState(session_id=sid)
        resp = new_orchestrator.process_turn("I am not sure whether to get 24 inch or 36 inch", session_id=sid, state=state)
        chips = resp.get("chips") or []
        cards = resp.get("cards") or resp.get("product_cards") or []
        bot_text = resp.get("reply") or resp.get("response") or ""
        self.assertTrue(len(chips) > 0 or len(cards) > 0)
        self.assertNotIn("Certainly!", bot_text)

    def test_12_persona_frustrated_user(self):
        """Frustrated user receives empathetic de-escalation with specialist contact."""
        from domain.conversation_state import ConversationState
        sid = "test_persona_frustrated"
        state = ConversationState(session_id=sid)
        resp = new_orchestrator.process_turn("this is useless", session_id=sid, state=state)
        bot_text = resp.get("reply") or resp.get("response") or ""
        text_lower = bot_text.lower()
        self.assertTrue(
            "sales@keplertech.ae" in text_lower or "specialist" in text_lower or "apologize" in text_lower,
            f"Frustrated user must receive escalation assistance, got: {bot_text}"
        )


if __name__ == "__main__":
    unittest.main()
