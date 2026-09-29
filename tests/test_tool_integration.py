from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tool_health_endpoint():
    response = client.get("/api/tools/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 9
    assert any(item["name"] == "run_project_startup" and item["permission"] == "confirmation_required" for item in payload["tools"])


def test_health_advertises_registry():
    assert "secure_tool_registry" in client.get("/api/health").json()["capabilities"]
