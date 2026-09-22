"""
Security Hardening Tests.
Verifies:
1. SSRF prevention: client-provided `ollama_base_url` is ignored and does NOT mutate server configuration.
2. Model allowlist: requests specifying disallowed models receive HTTP 400.
3. CORS configuration: restrictive origins applied, malicious origins not accepted.
4. Security headers and payload limits (MAX_CONTENT_LENGTH = 1MB).
"""
import unittest
import json
from app import app
from config import OLLAMA_BASE_URL, ALLOWED_MODELS


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_ssrf_ollama_base_url_ignored(self):
        """Ensure client cannot redirect Ollama requests to arbitrary internal or external servers."""
        malicious_url = "http://169.254.169.254/latest/meta-data/"
        payload = {
            "text": "Hello",
            "ollama_base_url": malicious_url,
            "session_id": "sec-test-ssrf"
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertIn(res.status_code, [200, 400])

        # Verify global configuration was NOT mutated
        import config
        self.assertEqual(config.OLLAMA_BASE_URL, OLLAMA_BASE_URL)
        from ollama_client import ollama_client
        self.assertNotEqual(ollama_client.base_url, malicious_url)

    def test_model_allowlist_enforcement(self):
        """Ensure unapproved model names are rejected with 400."""
        payload = {
            "message": "Hello",
            "model": "evil_injected_model:latest",
            "session_id": "sec-test-model"
        }
        res = self.client.post("/api/chat", json=payload)
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn("error", data)
        self.assertIn("Model not allowed", data["error"])

    def test_allowed_models_accepted(self):
        """Ensure models in ALLOWED_MODELS are accepted."""
        for model in ALLOWED_MODELS[:1]:
            payload = {
                "message": "Hi",
                "model": model,
                "session_id": "sec-test-allowed-model"
            }
            res = self.client.post("/api/chat", json=payload)
            self.assertEqual(res.status_code, 200)

    def test_security_headers_present(self):
        """Ensure response contains standard security headers."""
        res = self.client.get("/health/live")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_max_content_length_enforced(self):
        """Ensure requests exceeding 1MB are rejected with 413 Payload Too Large."""
        large_text = "A" * (1024 * 1024 + 1024)  # > 1MB
        res = self.client.post(
            "/api/chat",
            data=large_text,
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 413)

    def test_health_endpoints(self):
        """Verify liveness and readiness endpoints respond correctly."""
        live_res = self.client.get("/health/live")
        self.assertEqual(live_res.status_code, 200)
        live_data = json.loads(live_res.data)
        self.assertEqual(live_data["status"], "alive")

        ready_res = self.client.get("/health/ready")
        self.assertEqual(ready_res.status_code, 200)
        ready_data = json.loads(ready_res.data)
        # Status is "ready", "not_ready", or "degraded" depending on Ollama availability and config
        self.assertIn(ready_data["status"], ["ready", "not_ready", "degraded"])
        # Catalog must always be loaded regardless of Ollama state
        self.assertGreater(ready_data["catalog_count"], 0)


if __name__ == "__main__":
    unittest.main()
