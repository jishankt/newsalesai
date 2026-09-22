"""
Regression tests verifying authentication enforcement across all admin portal routes.
Ensures unauthenticated requests to protected endpoints return 401 Unauthorized.
"""

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ── Public & Exempt Endpoints ────────────────────────────────────────────────
def test_admin_dashboard_shell_is_public(client):
    """The HTML shell /admin and /admin/ must remain accessible without auth."""
    resp1 = client.get("/admin")
    assert resp1.status_code == 200
    assert b"Admin Dashboard" in resp1.data

    resp2 = client.get("/admin/")
    assert resp2.status_code == 200
    assert b"Admin Dashboard" in resp2.data


def test_auth_me_unauthenticated_returns_200_with_logged_in_false(client):
    """Unauthenticated call to /api/admin/auth/me should return 200 with authenticated=False."""
    resp = client.get("/api/admin/auth/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["authenticated"] is False
    assert data["logged_in"] is False
    assert data["agent"] is None


# ── Protected Admin Endpoints (Must Return 401 when Unauthenticated) ─────────
@pytest.mark.parametrize(
    "method,url,payload",
    [
        ("GET", "/api/admin/stats", None),
        ("GET", "/api/admin/sessions", None),
        ("GET", "/api/admin/sessions/test-session-123", None),
        ("GET", "/api/admin/leads", None),
        ("GET", "/api/admin/live-desk/sessions", None),
        ("POST", "/api/admin/live-desk/takeover", {"session_id": "test-session-123"}),
        ("POST", "/api/admin/live-desk/release", {"session_id": "test-session-123"}),
        ("POST", "/api/admin/live-desk/send", {"session_id": "test-session-123", "message": "hello"}),
        ("GET", "/api/admin/live-desk/poll?session_id=test-session-123", None),
        ("GET", "/api/admin/live-desk/notifications", None),
        ("GET", "/api/admin/auth/status", None),
        ("POST", "/api/admin/auth/status", {"status": "busy"}),
        ("GET", "/api/admin/agents", None),
        ("POST", "/api/admin/agents", {"username": "test", "password": "pw", "name": "Test"}),
        ("POST", "/api/admin/auth/logout", None),
    ],
)
def test_protected_admin_routes_enforce_authentication(client, method, url, payload):
    """Every protected admin route must return 401 when no session cookie is provided."""
    if method == "GET":
        resp = client.get(url)
    elif method == "POST":
        resp = client.post(url, json=payload or {})
    else:
        pytest.fail(f"Unsupported method: {method}")

    assert resp.status_code == 401, f"{method} {url} returned {resp.status_code}, expected 401"
    data = resp.get_json()
    assert data is not None, f"Response from {url} was not JSON"
    assert data["success"] is False
    assert "Authentication required" in data.get("error", "")


def test_auth_login_rate_limiting(client):
    """Test that login route enforces strict rate limiting (5 attempts per IP)."""
    from security.rate_limiter import rate_limiter
    rate_limiter.reset()

    # First 5 attempts should return 401 (invalid credentials), not 429
    for i in range(5):
        resp = client.post(
            "/api/admin/auth/login",
            json={"username": "fake_user", "password": "wrong_password"},
            environ_base={"REMOTE_ADDR": "198.51.100.42"}
        )
        assert resp.status_code == 401, f"Attempt {i+1} returned {resp.status_code}, expected 401"

    # 6th attempt from the same IP must be rate limited (429)
    blocked_resp = client.post(
        "/api/admin/auth/login",
        json={"username": "fake_user", "password": "wrong_password"},
        environ_base={"REMOTE_ADDR": "198.51.100.42"}
    )
    assert blocked_resp.status_code == 429
    assert "Retry-After" in blocked_resp.headers
    blocked_data = blocked_resp.get_json()
    assert blocked_data["success"] is False
    assert "Too many requests" in blocked_data["error"]
    assert "Too many login attempts" in blocked_data["message"]

    # Reset after test
    rate_limiter.reset()
