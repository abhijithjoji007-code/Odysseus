from fastapi.testclient import TestClient

from app.main import app


def test_assistant_request_rejects_invalid_session_id():
    response = TestClient(app).post(
        "/api/assistant",
        json={"message": "help", "session_id": "contains spaces"},
    )
    assert response.status_code == 422


def test_assistant_request_accepts_session_id():
    response = TestClient(app).post(
        "/api/assistant",
        json={"message": "help", "session_id": "browser_123"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "help"
