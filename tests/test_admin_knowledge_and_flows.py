import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["agent_id"] = "agent-admin-01"
            sess["agent_name"] = "Operations Admin"
            sess["agent_role"] = "admin"
        yield client


def test_admin_endpoints_require_auth(client):
    endpoints = [
        "/api/admin/catalog/workflows",
        "/api/admin/catalog/consumables-matrix",
        "/api/admin/personas",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 401, f"{ep} did not enforce auth"

    resp_post = client.post("/api/admin/rag/test-query", json={"query": "Citizen CZ-01"})
    assert resp_post.status_code == 401


def test_catalog_workflows_structure(auth_client):
    resp = auth_client.get("/api/admin/catalog/workflows")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total_catalog_products"] >= 72
    assert "categories" in data
    cats = data["categories"]
    assert "office" in cats
    assert "technical_large_format" in cats
    assert "citizen_photo" in cats
    assert "dye_sublimation" in cats
    assert "scanner" in cats

    # Check citizen photo subcategories
    citizen_cat = cats["citizen_photo"]
    subcat_ids = [s["id"] for s in citizen_cat["subcategories"]]
    assert "citizen_4_inch" in subcat_ids
    assert "citizen_6_inch" in subcat_ids
    assert "citizen_8_inch" in subcat_ids


def test_consumables_matrix(auth_client):
    resp = auth_client.get("/api/admin/catalog/consumables-matrix")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total_printers"] >= 72
    assert len(data["matrix"]) >= 72

    # Check item structure
    first = data["matrix"][0]
    assert "product_id" in first
    assert "product_name" in first
    assert "consumables" in first


def test_rag_query_studio(auth_client):
    resp = auth_client.post(
        "/api/admin/rag/test-query",
        json={"query": "Citizen CZ-01 4-inch photo booth", "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total_matches"] > 0
    assert len(data["results"]) > 0
    top = data["results"][0]
    assert "name" in top
    assert "score" in top


def test_personas_studio(auth_client):
    resp = auth_client.get("/api/admin/personas")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total_personas"] == 4
    roles = [p["id"] for p in data["personas"]]
    assert "receptionist" in roles
    assert "product_specialist" in roles
    assert "technical_rag" in roles
    assert "sales_lead" in roles
