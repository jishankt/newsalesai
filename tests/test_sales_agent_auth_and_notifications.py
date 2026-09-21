"""
Tests for Salesman Agent Login, Admin Management, and Live Escalation Notifications.
"""

import json
import pytest
from app import app
from persistence.agent_repository import agent_repository
from persistence.state_repository import state_repository
from domain.conversation_state import ConversationState


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def init_test_db():
    agent_repository._init_db()


def test_auth_login_failure(client):
    """Test login with incorrect password returns 401."""
    resp = client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "admin", "password": "wrongpassword"}),
        content_type="application/json",
    )
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["success"] is False
    assert "Invalid" in data["error"]


def test_auth_login_and_me_success(client):
    """Test login succeeds for default salesman and sets session cookie."""
    resp = client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "sales", "password": "sales123"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["agent"]["username"] == "sales"
    assert data["agent"]["role"] == "salesman"

    # Test /api/admin/auth/me returns authenticated salesman
    me_resp = client.get("/api/admin/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.get_json()
    assert me_data["authenticated"] is True
    assert me_data["agent"]["username"] == "sales"

    # Test status change
    st_resp = client.post(
        "/api/admin/auth/status",
        data=json.dumps({"status": "busy"}),
        content_type="application/json",
    )
    assert st_resp.status_code == 200
    assert st_resp.get_json()["status"] == "busy"

    # Test logout
    lo_resp = client.post("/api/admin/auth/logout")
    assert lo_resp.status_code == 200

    # Verify session destroyed
    me_after = client.get("/api/admin/auth/me")
    assert me_after.get_json()["authenticated"] is False


def test_admin_agent_crud(client):
    """Test creating, listing, updating, and deleting sales agents."""
    # Login as admin
    client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "admin", "password": "admin123"}),
        content_type="application/json",
    )

    # List agents
    resp = client.get("/api/admin/agents")
    assert resp.status_code == 200
    agents = resp.get_json()["agents"]
    initial_count = len(agents)

    # Create new salesman
    new_agent_payload = {
        "name": "Rashid - Commercial Specialist",
        "username": "rashid_test",
        "email": "rashid.test@keplertech.ae",
        "password": "Password123!",
        "role": "salesman",
    }
    create_resp = client.post(
        "/api/admin/agents",
        data=json.dumps(new_agent_payload),
        content_type="application/json",
    )
    assert create_resp.status_code == 201
    created_data = create_resp.get_json()
    assert created_data["success"] is True
    agent_id = created_data["agent"]["agent_id"]

    # Duplicate rejection
    dup_resp = client.post(
        "/api/admin/agents",
        data=json.dumps(new_agent_payload),
        content_type="application/json",
    )
    assert dup_resp.status_code == 400

    # Verify created agent can log in
    client.post("/api/admin/auth/logout")
    login_new = client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "rashid_test", "password": "Password123!"}),
        content_type="application/json",
    )
    assert login_new.status_code == 200
    assert login_new.get_json()["agent"]["name"] == "Rashid - Commercial Specialist"

    # Salesman cannot delete or create agents (admin only)
    forbidden_resp = client.post(
        "/api/admin/agents",
        data=json.dumps({"name": "X", "username": "x", "password": "p", "role": "salesman"}),
        content_type="application/json",
    )
    assert forbidden_resp.status_code == 403

    # Switch back to admin to delete created agent
    client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "admin", "password": "admin123"}),
        content_type="application/json",
    )

    del_resp = client.delete(f"/api/admin/agents/{agent_id}")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["success"] is True


def test_live_desk_notifications_feed(client):
    """Test that customer escalation triggers appear in notification feed and disappear once taken over."""
    session_id = "test_escalation_sess_101"
    initial_state = ConversationState(session_id=session_id)
    initial_state.handover_triggered = True
    initial_state.human_agent_active = False
    initial_state.handover_reason = "Customer requested human advisor"
    initial_state.customer_name = "Hamdan Bin Zayed"

    state_repository.save_session(
        session_id=session_id,
        state=initial_state,
        history=[
            {"role": "user", "content": "I need to talk to a human salesman for a bulk quote."}
        ],
    )

    # Query notifications
    notif_resp = client.get("/api/admin/live-desk/notifications")
    assert notif_resp.status_code == 200
    notifs = notif_resp.get_json()["notifications"]
    matched = [n for n in notifs if n["session_id"] == session_id]
    assert len(matched) == 1
    assert matched[0]["customer_name"] == "Hamdan Bin Zayed"
    assert matched[0]["reason"] == "Customer requested human advisor"
    assert "bulk quote" in matched[0]["last_message"]

    # Now simulate salesman taking over the session
    takeover_resp = client.post(
        "/api/admin/live-desk/takeover",
        data=json.dumps({
            "session_id": session_id,
            "agent_name": "Tariq - Senior Sales Specialist",
            "reason": "manual_takeover",
        }),
        content_type="application/json",
    )
    assert takeover_resp.status_code == 200

    # After takeover, this session should no longer be in the unhandled notification feed
    after_resp = client.get("/api/admin/live-desk/notifications")
    after_notifs = after_resp.get_json()["notifications"]
    after_matched = [n for n in after_notifs if n["session_id"] == session_id]
    assert len(after_matched) == 0


def test_takeover_auto_binds_authenticated_salesman_name(client):
    """Test that live-desk takeover defaults to the logged-in salesman's name if omitted."""
    # Log in as salesman
    client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "sales", "password": "sales123"}),
        content_type="application/json",
    )

    session_id = "test_autobind_sess_202"
    initial_state = ConversationState(session_id=session_id)
    initial_state.handover_triggered = True
    initial_state.human_agent_active = False

    state_repository.save_session(
        session_id=session_id,
        state=initial_state,
        history=[{"role": "user", "content": "Can someone help me choose between TM-300 and TX-3100?"}],
    )

    # Perform takeover WITHOUT specifying agent_name
    takeover_resp = client.post(
        "/api/admin/live-desk/takeover",
        data=json.dumps({"session_id": session_id}),
        content_type="application/json",
    )
    assert takeover_resp.status_code == 200
    takeover_data = takeover_resp.get_json()
    assert takeover_data["success"] is True
    # The default seed salesman's name is "Sales Specialist"
    assert "Sales Specialist" in takeover_data["agent_name"]

    # Verify session detail reflects this salesman name
    detail_resp = client.get(f"/api/admin/sessions/{session_id}")
    detail_data = detail_resp.get_json()
    assert detail_data["state"]["human_agent_active"] is True
    assert "Sales Specialist" in detail_data["state"]["human_agent_name"]


def test_admin_patch_agent_status(client):
    """Test admin updating agent status via PATCH."""
    # Login as admin
    client.post(
        "/api/admin/auth/login",
        data=json.dumps({"username": "admin", "password": "admin123"}),
        content_type="application/json",
    )

    # Find the salesman's agent_id
    agents = client.get("/api/admin/agents").get_json()["agents"]
    sales_agent = next(a for a in agents if a["username"] == "sales")

    patch_resp = client.patch(
        f"/api/admin/agents/{sales_agent['agent_id']}",
        data=json.dumps({"status": "busy"}),
        content_type="application/json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["agent"]["status"] == "busy"

