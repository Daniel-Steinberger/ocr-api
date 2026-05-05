from fastapi.testclient import TestClient

from ocr_api.main import app


def test_health_returns_gpu_status():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["gpu"], bool)
    assert isinstance(data["device"], str)
