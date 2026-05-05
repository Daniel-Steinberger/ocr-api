"""Lifespan integration test — only runs if marker is importable.

Loading the real models pulls ~5GB to disk and several GB to VRAM, so
this test is opt-in via OCR_API_LOAD_MODELS=1 to keep the default test
run fast.
"""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("OCR_API_LOAD_MODELS") != "1",
    reason="set OCR_API_LOAD_MODELS=1 to load real marker models",
)
def test_lifespan_attaches_real_converter():
    pytest.importorskip("marker")
    from fastapi.testclient import TestClient

    from ocr_api.converter import MarkerConverter
    from ocr_api.main import app

    with TestClient(app) as client:
        assert isinstance(app.state.converter, MarkerConverter)
        response = client.get("/health")
        assert response.status_code == 200


def test_lifespan_initializes_job_store_without_models():
    """Without OCR_API_LOAD_MODELS, lifespan must still wire JobStore."""
    from fastapi.testclient import TestClient

    from ocr_api.jobs import JobStore
    from ocr_api.main import app

    with TestClient(app) as _:
        assert isinstance(app.state.job_store, JobStore)
