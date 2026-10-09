"""
Test suite for the live n8n-style agent execution dashboard and workflow APIs.
Verifies authentication enforcement, trace retrieval, event pagination/filtering,
health metrics, SSE streaming integration, and end-to-end pipeline trace recording.
"""

import time
import pytest
from app import app
from agent.orchestrator import orchestrator
from domain.conversation_state import ConversationState
from persistence.trace_repository import trace_repository, trace_broadcaster
from persistence.models import AgentExecutionTrace, AgentExecutionEvent


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_client(client):
    """Test client authenticated as agent-admin-01."""
    with client.session_transaction() as sess:
        sess["agent_id"] = "agent-admin-01"
        sess["admin_logged_in"] = True
    return client


# ── 1. Authentication Enforcement on Workflow Endpoints ─────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "/api/admin/workflow/executions",
        "/api/admin/workflow/executions/test-exec-id",
        "/api/admin/workflow/executions/test-exec-id/events",
        "/api/admin/workflow/health",
        "/api/admin/workflow/stream",
    ],
)
def test_workflow_endpoints_require_admin_authentication(client, url):
    """Unauthenticated calls to workflow endpoints must return 401 Unauthorized."""
    resp = client.get(url)
    assert resp.status_code == 401
    data = resp.get_json()
    if data:
        assert data["success"] is False
        assert "Authentication required" in data.get("error", "")


# ── 2. Workflow Health API ───────────────────────────────────────────────────
def test_workflow_health_authenticated(auth_client):
    """Authenticated calls to workflow health endpoint return operational metrics."""
    resp = auth_client.get("/api/admin/workflow/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["status"] in ("healthy", "ok")
    assert "total_executions" in data
    assert data["service"] == "salesai_execution_tracer"


# ── 3. Trace Querying and Filtering ─────────────────────────────────────────
def test_workflow_executions_list_and_filter(auth_client):
    """Workflow executions can be listed, filtered by status, and searched."""
    # Seed a test trace directly
    test_id = f"test-trace-{int(time.time() * 1000)}"
    trace = AgentExecutionTrace(
        execution_id=test_id,
        conversation_id="conv-test-wf",
        session_id="sess-test-wf",
        status="completed",
        summary="Customer inquired about Epson L3250 printer",
        input_preview="How much is Epson L3250?",
        output_preview="Epson L3250 is available for AED 599.",
        final_action="recommend",
        total_duration_ms=45.2,
    )
    trace_repository.save_trace(trace)

    # List all executions
    resp = auth_client.get("/api/admin/workflow/executions?limit=50")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert any(x["execution_id"] == test_id for x in data["executions"])

    # Search filter
    resp_search = auth_client.get(f"/api/admin/workflow/executions?search={test_id}")
    assert resp_search.status_code == 200
    data_search = resp_search.get_json()
    assert len(data_search["executions"]) == 1
    assert data_search["executions"][0]["execution_id"] == test_id

    # Status filter
    resp_status = auth_client.get("/api/admin/workflow/executions?status=completed")
    assert resp_status.status_code == 200
    data_st = resp_status.get_json()
    assert any(x["execution_id"] == test_id for x in data_st["executions"])


# ── 4. Workflow Execution Detail & Events ────────────────────────────────────
def test_workflow_execution_detail_and_events(auth_client):
    """Fetching a specific trace returns the full trace object and its ordered events."""
    test_id = f"test-exec-detail-{int(time.time() * 1000)}"
    trace = AgentExecutionTrace(
        execution_id=test_id,
        conversation_id="conv-detail",
        session_id="sess-detail",
        status="completed",
        summary="Detailed test execution",
        input_preview="Show me Zebra barcode scanners",
        output_preview="Here are Zebra scanners...",
        final_action="search",
        total_duration_ms=120.5,
    )
    trace_repository.save_trace(trace)

    # Add 2 events
    ev1 = AgentExecutionEvent(
        event_id=f"ev1-{test_id}",
        execution_id=test_id,
        node_id="node_receive",
        node_type="TRIGGER",
        event_type="node_completed",
        duration_ms=1.2,
        status="completed",
        input_summary="Inbound query received",
        output_summary="Parsed payload",
    )
    ev2 = AgentExecutionEvent(
        event_id=f"ev2-{test_id}",
        execution_id=test_id,
        node_id="node_tool",
        node_type="TOOL",
        event_type="node_completed",
        duration_ms=45.0,
        status="completed",
        tool_name="search",
        input_summary="Searching for Zebra scanners",
        output_summary="Found 3 models",
    )
    trace_repository.record_event(ev1)
    trace_repository.record_event(ev2)

    # Query detail endpoint
    resp = auth_client.get(f"/api/admin/workflow/executions/{test_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["execution"]["execution_id"] == test_id
    assert len(data["events"]) == 2
    assert data["events"][0]["node_id"] == "node_receive"
    assert data["events"][1]["node_id"] == "node_tool"

    # Query events endpoint
    resp_ev = auth_client.get(f"/api/admin/workflow/executions/{test_id}/events")
    assert resp_ev.status_code == 200
    data_ev = resp_ev.get_json()
    assert data_ev["success"] is True
    assert len(data_ev["events"]) == 2


# ── 5. End-to-End Orchestrator Pipeline Instrumentation ─────────────────────
def test_live_turn_creates_trace_with_all_nodes(auth_client):
    """Running a live customer turn through the canonical orchestrator creates an execution trace with events."""
    session_id = f"test-live-trace-turn-{int(time.time() * 1000)}"
    state = ConversationState(session_id=session_id)

    # Execute a turn asking for product recommendations
    res = orchestrator.process_turn(
        raw_message="I need a barcode scanner for a retail store in Dubai",
        session_id=session_id,
        state=state,
    )

    # Response should have execution metadata
    exec_id = res.get("execution_id")
    assert exec_id is not None
    assert "node_receive" in res.get("ascii_trace", "")

    # Trace must exist in the database
    db_trace = trace_repository.get_trace(exec_id)
    assert db_trace is not None
    assert db_trace.status in ("completed", "handed_off")
    assert db_trace.total_duration_ms > 0

    # Events must cover the pipeline nodes
    events = trace_repository.get_events(exec_id)
    assert len(events) >= 5
    node_ids = [e.node_id for e in events]
    assert "node_receive" in node_ids
    assert "node_understand" in node_ids
    assert "node_reconcile" in node_ids
    assert "node_plan" in node_ids
    assert "node_deliver" in node_ids

    # The trace must be queryable via the admin API
    resp = auth_client.get(f"/api/admin/workflow/executions/{exec_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["execution"]["execution_id"] == exec_id
    assert len(data["events"]) >= 5


# ── 6. SSE Event Broadcaster Pub-Sub ─────────────────────────────────────────
def test_trace_event_broadcaster_pubsub():
    """TraceEventBroadcaster correctly delivers published events to subscriber queues."""
    sub_queue = trace_broadcaster.subscribe()
    try:
        test_payload = {
            "execution_id": "test-sub-123",
            "node_id": "node_plan",
            "status": "completed",
        }
        trace_broadcaster.broadcast("node_event", test_payload)

        # Queue should receive the message
        received = sub_queue.get(timeout=2.0)
        assert received["event"] == "node_event"
        assert received["data"]["execution_id"] == "test-sub-123"
        assert received["data"]["node_id"] == "node_plan"
    finally:
        trace_broadcaster.unsubscribe(sub_queue)


def test_workflow_stream_endpoint_headers(auth_client):
    """The SSE stream endpoint responds with text/event-stream content type and initial handshake."""
    resp = auth_client.get("/api/admin/workflow/stream", buffered=False)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")
    assert "no-cache" in resp.headers.get("Cache-Control", "")

    # Read the first event yielded by the generator
    first_chunk = next(resp.response)
    assert b"event: connected" in first_chunk
    resp.close()
