"""
Automated Test Suite for Ollama Connectivity, Health Checks,
Error Logging, and Priority Routing (Online and Offline conditions).
"""

import unittest
from unittest.mock import patch, MagicMock
import requests
import json

from config import DEFAULT_MODEL, OLLAMA_BASE_URL
from ollama_client import (
    OllamaClient,
    OllamaErrorKind,
    classify_ollama_exception,
    is_model_installed,
)
from domain.conversation_state import ConversationState
from domain.conversation_types import Intent, RouteName
from agent.orchestrator import Orchestrator


class OllamaConnectivityTestCase(unittest.TestCase):
    def setUp(self):
        self.online_client = OllamaClient(base_url=OLLAMA_BASE_URL, default_model=DEFAULT_MODEL)
        self.offline_client = OllamaClient(base_url="http://192.168.0.110:11434", default_model="qwen2.5:32b")

    # ── 1. Online / Offline Health Checks ────────────────────────────────

    def test_startup_health_check_online(self):
        """Verify startup health check against the local running Ollama instance."""
        res = self.online_client.startup_health_check(test_inference=False)
        self.assertTrue(res["server_connected"])
        self.assertTrue(res["model_available"])
        self.assertIn(DEFAULT_MODEL, res["models"])
        self.assertIsNone(res["error_kind"])

    def test_startup_health_check_offline(self):
        """Verify startup health check properly categorizes unreachable server."""
        res = self.offline_client.startup_health_check(test_inference=False)
        self.assertFalse(res["online"])
        self.assertFalse(res["server_connected"])
        self.assertFalse(res["model_available"])
        self.assertIn(res["error_kind"], [OllamaErrorKind.SERVER_UNAVAILABLE.value, OllamaErrorKind.CONNECTION_TIMEOUT.value])

    def test_error_categorization_helper(self):
        """Verify error classification distinguishes connection timeout, server down, and parse error."""
        kind, msg = classify_ollama_exception(requests.exceptions.ConnectTimeout("Connect timeout"))
        self.assertEqual(kind, OllamaErrorKind.CONNECTION_TIMEOUT)

        kind, msg = classify_ollama_exception(requests.exceptions.ConnectionError("Connection refused"))
        self.assertEqual(kind, OllamaErrorKind.SERVER_UNAVAILABLE)

        kind, msg = classify_ollama_exception(requests.exceptions.ReadTimeout("Read timeout"))
        self.assertEqual(kind, OllamaErrorKind.READ_TIMEOUT)

        kind, msg = classify_ollama_exception(json.JSONDecodeError("Expecting value", "doc", 0))
        self.assertEqual(kind, OllamaErrorKind.JSON_PARSE_FAILURE)

    def test_model_not_installed_detection(self):
        """Verify health check detects when requested model is missing from server."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}, {"name": "nomic-embed:latest"}]}
            mock_get.return_value = mock_resp

            client = OllamaClient(base_url="http://mock-ollama:11434", default_model="non_existent_model:99b")
            res = client.startup_health_check(test_inference=False)
            self.assertTrue(res["server_connected"])
            self.assertFalse(res["model_available"])
            self.assertEqual(res["error_kind"], OllamaErrorKind.MODEL_NOT_INSTALLED.value)

    # ── 2. Fallback Logging & Classify Resilience ───────────────────────

    def test_classify_offline_returns_fallback_with_error_kind(self):
        """Verify classify() on offline server logs and returns structured fallback with error_kind."""
        client = OllamaClient(base_url="http://127.0.0.1:9999", default_model="qwen2.5:32b")
        res = client.classify(messages=[{"role": "user", "content": "test"}], schema={})
        self.assertFalse(res["success"])
        self.assertTrue(res["fallback_used"])
        self.assertEqual(res["error_kind"], OllamaErrorKind.SERVER_UNAVAILABLE.value)
        self.assertIn("fallback_reason", res)

    # ── 3. Priority Routing: Direct Attributes & Comparisons Bypass Qualification ─

    def test_fastest_printer_bypasses_qualification_offline(self):
        """
        Critical Requirement:
        'Which Citizen printer is the fastest?' must bypass qualification even when Ollama is offline.
        Must answer with verified facts (Citizen CY-02 at 12.4s vs CX-02 at 13.8s) and not ask for print size.
        """
        orch = Orchestrator(ollama_client=self.offline_client)
        state = ConversationState(session_id="test_fastest_offline")

        res = orch.process_turn("Which Citizen printer is the fastest?", "test_fastest_offline", [], state)
        self.assertEqual(state.active_route, RouteName.COMPARISON.value)
        self.assertIn("Citizen CY-02 is the fastest", res["reply"])
        self.assertIn("12.4 seconds", res["reply"])
        self.assertIn("13.8 seconds", res["reply"])
        # Must not ask qualification question about size
        self.assertNotIn("What print size", res["reply"])
        self.assertNotIn("What maximum drawing", res["reply"])
        # Product cards attached
        card_names = [c.get("name") for c in res.get("product_cards", [])]
        self.assertTrue(any("CX" in n or "CX02" in n for n in card_names))
        self.assertTrue(any("CY" in n or "CY02" in n for n in card_names))

    def test_fastest_printer_bypasses_qualification_online(self):
        """'Which Citizen printer is the fastest?' under online client."""
        orch = Orchestrator(ollama_client=self.online_client)
        state = ConversationState(session_id="test_fastest_online")

        res = orch.process_turn("Which Citizen printer is the fastest?", "test_fastest_online", [], state)
        self.assertEqual(state.active_route, RouteName.COMPARISON.value)
        self.assertIn("CY-02", res["reply"])
        self.assertIn("12.4 seconds", res["reply"])

    def test_compare_models_bypasses_qualification(self):
        """Direct comparison between models must bypass qualification."""
        orch = Orchestrator(ollama_client=self.offline_client)
        state = ConversationState(session_id="test_compare_bypass")

        res = orch.process_turn("Compare Epson SureColor T3100 vs T5100", "test_compare_bypass", [], state)
        self.assertEqual(state.active_route, RouteName.COMPARISON.value)
        self.assertIn("T3100", res["reply"])
        self.assertIn("T5100", res["reply"])

    def test_direct_spec_attribute_question_bypasses_qualification(self):
        """Direct attribute question about specific model must route to PRODUCT, not QUALIFICATION."""
        orch = Orchestrator(ollama_client=self.offline_client)
        state = ConversationState(session_id="test_spec_bypass")

        res = orch.process_turn("What is the print speed of the Citizen CX-02?", "test_spec_bypass", [], state)
        self.assertEqual(state.active_route, RouteName.PRODUCT.value)
        self.assertNotIn("What print size do you need?", res["reply"])

    def test_recommendation_requests_route_to_qualification(self):
        """
        Preserve routing priority:
        Consultative requests ('I need a plotter for CAD drawings') must still route to qualification.
        """
        orch = Orchestrator(ollama_client=self.offline_client)
        state = ConversationState(session_id="test_rec_qualification")

        res = orch.process_turn("I need a printer for CAD drawings.", "test_rec_qualification", [], state)
        self.assertEqual(state.active_route, RouteName.QUALIFICATION.value)
        self.assertIn("?", res["reply"])


if __name__ == "__main__":
    unittest.main()
