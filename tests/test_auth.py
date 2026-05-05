import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ocr_api.auth import require_api_key
from ocr_api.config import Settings, get_settings


@pytest.fixture
def app_with_protected_route():
    test_app = FastAPI()

    @test_app.get("/protected")
    def protected(_: None = Depends(require_api_key)):
        return {"ok": True}

    test_app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    return test_app


def test_protected_route_rejects_missing_header(app_with_protected_route):
    client = TestClient(app_with_protected_route)
    assert client.get("/protected").status_code == 401


def test_protected_route_rejects_wrong_key(app_with_protected_route):
    client = TestClient(app_with_protected_route)
    response = client.get("/protected", headers={"X-API-Key": "nope"})
    assert response.status_code == 403


def test_protected_route_accepts_correct_key(app_with_protected_route):
    client = TestClient(app_with_protected_route)
    response = client.get("/protected", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unset_api_key_disables_protection():
    test_app = FastAPI()

    @test_app.get("/protected")
    def protected(_: None = Depends(require_api_key)):
        return {"ok": True}

    test_app.dependency_overrides[get_settings] = lambda: Settings(api_key=None)
    client = TestClient(test_app)
    assert client.get("/protected").status_code == 503
