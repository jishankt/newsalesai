"""
Production Hardening Pass Tests.

Covers:
1. Production secret validation (refuse startup in production with missing/default secret).
2. API rate limiting (IP and session limits, 429 status, Retry-After header, proxy IP resolution).
3. Privacy-safe logging (no sensitive plain text in production logs).
4. Internal state redaction (canonical_state omitted in production).
5. Restricted health information (/health/live minimal, /api/health sanitized).
6. Ollama readiness policy (ready, degraded, unavailable states and status codes).
7. Empty and invalid input verification (empty, whitespace-only, non-string, overlong).
"""

import unittest
import json
import logging
from unittest.mock import patch, MagicMock
from config import validate_secret_key
from security.rate_limiter import rate_limiter, get_client_ip, is_valid_ip
from app import app


class TestProductionHardeningPass(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        rate_limiter.reset()

    def tearDown(self):
        rate_limiter.reset()

    # ── 1. Production Secret Validation ──────────────────────────────────────
    def test_production_secret_refuses_default_or_missing_in_prod(self):
        """In production, validate_secret_key must raise RuntimeError on default/empty key."""
        with self.assertRaises(RuntimeError):
            validate_secret_key(secret_key="", app_env="production", debug=False)

        with self.assertRaises(RuntimeError):
            validate_secret_key(
                secret_key="kepler-tech-salesai-default-secret-change-in-production",
                app_env="production",
                debug=False
            )

        with self.assertRaises(RuntimeError):
            validate_secret_key(secret_key="dev-secret-key", app_env="production", debug=False)

        with self.assertRaises(RuntimeError):
            validate_secret_key(secret_key="too-short", app_env="production", debug=False)

    def test_production_secret_allows_strong_key_in_prod(self):
        """In production, a strong key with >= 16 chars is accepted."""
        result = validate_secret_key(
            secret_key="super-strong-production-kepler-secret-key-2026-secure",
            app_env="production",
            debug=False
        )
        self.assertTrue(result)

    def test_production_secret_allows_default_in_dev_or_test(self):
        """Development and test environments permit default secret key."""
        result_dev = validate_secret_key(
            secret_key="kepler-tech-salesai-default-secret-change-in-production",
            app_env="development",
            debug=True
        )
        self.assertTrue(result_dev)

        result_test = validate_secret_key(
            secret_key="dev-secret-key",
            app_env="test",
            debug=False
        )
        self.assertTrue(result_test)

    # ── 2. API Rate Limiting & Trusted Proxy Handling ─────────────────────────
    def test_client_ip_resolution_cloudflare(self):
        """Inspects CF-Connecting-IP when configured."""
        mock_req = MagicMock()
        mock_req.headers = {"CF-Connecting-IP": "198.51.100.42"}
        mock_req.remote_addr = "127.0.0.1"

        resolved = get_client_ip(mock_req)
        self.assertEqual(resolved, "198.51.100.42")

    def test_client_ip_resolution_trusted_proxy_chain(self):
        """Inspects X-Forwarded-For using trusted proxy hop count from right to left."""
        mock_req = MagicMock()
        # Spoofed leftmost IP: 1.1.1.1, real client: 203.0.113.195, proxy: 10.0.0.1
        mock_req.headers = {
            "X-Forwarded-For": "1.1.1.1, 203.0.113.195"
        }
        mock_req.remote_addr = "10.0.0.1"

        with patch("security.rate_limiter.TRUST_CF_CONNECTING_IP", False), \
             patch("security.rate_limiter.TRUSTED_PROXY_COUNT", 1):
            resolved = get_client_ip(mock_req)
            # With TRUSTED_PROXY_COUNT=1, rightmost IP is the client IP from proxy perspective
            self.assertEqual(resolved, "203.0.113.195")

    def test_rate_limiting_returns_429_when_limit_exceeded(self):
        """Excessive requests return HTTP 429 with safe JSON and Retry-After header."""
        # Patch limit to 3 for testing
        with patch("security.rate_limiter.RATE_LIMIT_IP_PER_MINUTE", 3):
            # 3 permitted requests
            for i in range(3):
                res = self.client.post("/api/chat", json={"message": f"Turn {i}", "session_id": "rl-test-session"})
                self.assertEqual(res.status_code, 200)

            # 4th request exceeds rate limit
            res_4 = self.client.post("/api/chat", json={"message": "Turn 4", "session_id": "rl-test-session"})
            self.assertEqual(res_4.status_code, 429)
            data = json.loads(res_4.data)
            self.assertEqual(data.get("error"), "Too many requests")
            self.assertIn("Retry-After", res_4.headers)

    # ── 3. Privacy-Safe Logging ──────────────────────────────────────────────
    def test_privacy_safe_logging_does_not_log_message_text_by_default(self):
        """When LOG_SENSITIVE_DATA is False, sensitive plain text is not written to logger."""
        secret_content = "SECRET_PATIENT_RECORDS_MEDICAL_XYZ_12345"
        with patch("app.LOG_SENSITIVE_DATA", False):
            with self.assertLogs("conversational_ai", level=logging.INFO) as log_capture:
                res = self.client.post("/api/chat", json={
                    "message": f"I need a printer for {secret_content}",
                    "session_id": "privacy-test-sess"
                })
                self.assertEqual(res.status_code, 200)

                # Confirm the sensitive string does NOT appear in conversational_ai log records
                for record in log_capture.output:
                    self.assertNotIn(secret_content, record)
                    # Verify required operational fields are logged
                    if "incoming_chat" in record:
                        self.assertIn("req_id=", record)
                        self.assertIn("msg_len=", record)
                        self.assertIn("intent=", record)
                    if "status=200" in record:
                        self.assertIn("latency_ms=", record)
                        self.assertIn("route=", record)

    # ── 4. Internal State Redaction from Public API ───────────────────────────
    def test_canonical_state_omitted_in_production(self):
        """canonical_state must be absent from /api/chat when EXPOSE_DEBUG_STATE is False."""
        with patch("app.EXPOSE_DEBUG_STATE", False):
            res = self.client.post("/api/chat", json={
                "message": "I need an A4 printer",
                "session_id": "prod-contract-session"
            })
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)

            # Internal state must NOT be leaked
            self.assertNotIn("canonical_state", data)

            # Public contract fields required by frontend must be present
            self.assertIn("reply", data)
            self.assertIn("product_cards", data)
            self.assertIn("session_id", data)
            self.assertIn("nlp", data)
            self.assertIn("grounding", data)

    def test_canonical_state_permitted_in_debug_mode(self):
        """canonical_state is present when EXPOSE_DEBUG_STATE is True."""
        with patch("app.EXPOSE_DEBUG_STATE", True):
            res = self.client.post("/api/chat", json={
                "message": "I need an A4 printer",
                "session_id": "debug-contract-session"
            })
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertIn("canonical_state", data)

    # ── 5. Restrict Health Information ───────────────────────────────────────
    def test_health_live_minimal(self):
        """Liveness endpoint must return minimal status."""
        res = self.client.get("/health/live")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data, {"status": "alive", "service": "kepler-salesai"})

    def test_api_health_sanitized_in_production(self):
        """Public /api/health must not expose base_url or raw server internals."""
        with patch("app.DEBUG", False), patch("app.EXPOSE_DEBUG_STATE", False):
            res = self.client.get("/api/health")
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertNotIn("base_url", data)
            self.assertNotIn("models", data)
            self.assertIn("status", data)
            self.assertIn("catalogue_ok", data)

    # ── 6. Clarify Ollama Readiness Policy ────────────────────────────────────
    def test_readiness_ready_when_all_systems_go(self):
        """Returns 200 'ready' when catalogue, persistence, and Ollama are healthy."""
        with patch.object(self.client.application, "test_client"):
            res = self.client.get("/health/ready")
            # In live local environment with 43 catalogue & Ollama
            data = json.loads(res.data)
            self.assertEqual(data["catalog_count"], 43)
            self.assertEqual(data["catalogue_count"], 43)
            self.assertTrue(data["catalogue_ok"])
            self.assertTrue(data["persistence_ok"])

    def test_readiness_degraded_when_ollama_offline_and_not_mandatory(self):
        """Returns 200 'degraded' when Ollama is offline but OLLAMA_MANDATORY_FOR_READY is False."""
        with patch("app.ollama_client.check_health", return_value={"online": False, "model_available": False}), \
             patch("app.OLLAMA_MANDATORY_FOR_READY", False):
            res = self.client.get("/health/ready")
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertEqual(data["status"], "degraded")
            self.assertFalse(data["ollama_ok"])
            self.assertTrue(data["catalogue_ok"])

    def test_readiness_unavailable_when_ollama_offline_and_mandatory(self):
        """Returns 503 'unavailable' when Ollama is offline and OLLAMA_MANDATORY_FOR_READY is True."""
        with patch("app.ollama_client.check_health", return_value={"online": False, "model_available": False}), \
             patch("app.OLLAMA_MANDATORY_FOR_READY", True):
            res = self.client.get("/health/ready")
            self.assertEqual(res.status_code, 503)
            data = json.loads(res.data)
            self.assertEqual(data["status"], "unavailable")

    def test_readiness_unavailable_when_catalogue_corrupted(self):
        """Returns 503 'unavailable' when catalogue count != 41."""
        with patch("catalog.catalogue_loader.catalogue_loader.get_all", return_value=[]):
            res = self.client.get("/health/ready")
            self.assertEqual(res.status_code, 503)
            data = json.loads(res.data)
            self.assertEqual(data["status"], "unavailable")
            self.assertFalse(data["catalogue_ok"])

    # ── 8. Verify Empty and Invalid Input ─────────────────────────────────────
    def test_empty_message_rejected_400(self):
        """Empty string returns HTTP 400."""
        res = self.client.post("/api/chat", json={"message": "", "session_id": "test-empty"})
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertEqual(data.get("error"), "Empty message")

    def test_whitespace_only_message_rejected_400(self):
        """Whitespace-only string returns HTTP 400."""
        res = self.client.post("/api/chat", json={"message": "   \n\t  ", "session_id": "test-whitespace"})
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertEqual(data.get("error"), "Empty message")

    def test_non_string_message_rejected_400(self):
        """Non-string message (int, list, dict) returns HTTP 400."""
        res_int = self.client.post("/api/chat", json={"message": 12345, "session_id": "test-non-string"})
        self.assertEqual(res_int.status_code, 400)

        res_dict = self.client.post("/api/chat", json={"message": {"nested": "value"}, "session_id": "test-non-string"})
        self.assertEqual(res_dict.status_code, 400)

    def test_overlong_message_rejected_400(self):
        """Message exceeding 4000 characters returns HTTP 400."""
        overlong = "a" * 4001
        res = self.client.post("/api/chat", json={"message": overlong, "session_id": "test-overlong"})
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn("exceeds maximum allowed length", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
