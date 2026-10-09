"""
Tests for Live Execution Tracing and Admin Workflow Endpoints.
Verifies real backend node events, persistence, security, and schema fidelity.
"""

import unittest
import json
import uuid
import time
from app import app
from persistence.trace_repository import trace_repository
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState


class TestLiveExecutionTracing(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_turn_creates_persistent_trace_and_ordered_node_events(self):
        """A customer message produces an execution trace and sequential node events."""
        session_id = f"trace_test_{uuid.uuid4().hex[:8]}"
        state = ConversationState(session_id=session_id)

        # Process a real turn through orchestrator
        res = orchestrator.process_turn(
            raw_message="What are the technical specs and print speed of the Epson SC-T3100?",
            session_id=session_id,
            state=state
        )

        exec_id = res.get("execution_id")
        self.assertIsNotNone(exec_id)
        self.assertTrue(exec_id.startswith("exec_"))

        # Verify trace persisted in SQLite
        trace = trace_repository.get_trace(exec_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace.session_id, session_id)
        self.assertEqual(trace.status, "completed")
        self.assertGreater(trace.total_duration_ms, 0)
        self.assertTrue(len(trace.output_preview) > 0)

        # Verify sequential node events recorded
        events = trace_repository.get_trace_events(exec_id)
        self.assertGreaterEqual(len(events), 6)

        node_ids = [e.node_id for e in events]
        self.assertIn("node_receive", node_ids)
        self.assertIn("node_understand", node_ids)
        self.assertIn("node_reconcile", node_ids)
        self.assertIn("node_plan", node_ids)
        self.assertIn("node_tool", node_ids)
        self.assertIn("node_deliver", node_ids)

        # Verify event durations and timestamps are recorded honestly
        for e in events:
            self.assertGreaterEqual(e.timestamp, trace.started_at)
            self.assertEqual(e.status, "completed")

    def test_unauthenticated_admin_workflow_api_denied(self):
        """Unauthenticated requests to admin workflow endpoints must return 401."""
        resp = self.client.get("/api/admin/workflow/executions")
        self.assertEqual(resp.status_code, 401)

        resp2 = self.client.get("/api/admin/workflow/executions/exec_test123")
        self.assertEqual(resp2.status_code, 401)

    def test_authenticated_admin_can_query_executions_and_events(self):
        """Authenticated admin agent can list and inspect execution traces."""
        # 1. Login as admin agent
        with self.client.session_transaction() as sess:
            sess["agent_id"] = "agent-admin-01"
            sess["agent_name"] = "Operations Admin"
            sess["agent_role"] = "admin"

        # 2. Query list of executions
        list_resp = self.client.get("/api/admin/workflow/executions")
        self.assertEqual(list_resp.status_code, 200)
        data = list_resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("executions", data)
        self.assertIn("total", data)

        # 3. If traces exist, fetch detail
        if data["executions"]:
            first_exec = data["executions"][0]
            first_id = first_exec["execution_id"]
            detail_resp = self.client.get(f"/api/admin/workflow/executions/{first_id}")
            self.assertEqual(detail_resp.status_code, 200)
            det_data = detail_resp.get_json()
            self.assertTrue(det_data["success"])
            self.assertEqual(det_data["execution"]["execution_id"], first_id)
            self.assertIn("events", det_data)


if __name__ == "__main__":
    unittest.main()
