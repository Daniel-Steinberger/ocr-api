import time
from pathlib import Path

from fastapi.testclient import TestClient


def _post_job(client: TestClient, pdf: Path, format: str = "markdown"):
    with pdf.open("rb") as fh:
        return client.post(
            "/jobs",
            files={"file": (pdf.name, fh, "application/pdf")},
            params={"format": format},
            headers={"X-API-Key": "secret"},
        )


def _wait_done(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": "secret"})
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_post_jobs_returns_job_id(client: TestClient, sample_pdf: Path):
    response = _post_job(client, sample_pdf)
    assert response.status_code == 202
    body = response.json()
    assert "job_id" in body
    assert body["status"] in ("queued", "running", "done")


def test_get_job_eventually_done(client: TestClient, sample_pdf: Path):
    job_id = _post_job(client, sample_pdf).json()["job_id"]
    body = _wait_done(client, job_id)
    assert body["status"] == "done"
    assert body["result"]["format"] == "markdown"
    assert body["result"]["markdown"].startswith("# Converted")


def test_get_job_unknown_returns_404(client: TestClient):
    response = client.get("/jobs/no-such-id", headers={"X-API-Key": "secret"})
    assert response.status_code == 404


def test_jobs_require_api_key(client: TestClient, sample_pdf: Path):
    with sample_pdf.open("rb") as fh:
        r = client.post("/jobs", files={"file": (sample_pdf.name, fh, "application/pdf")})
    assert r.status_code == 401


def test_delete_job(client: TestClient, sample_pdf: Path):
    job_id = _post_job(client, sample_pdf).json()["job_id"]
    _wait_done(client, job_id)

    delete = client.delete(f"/jobs/{job_id}", headers={"X-API-Key": "secret"})
    assert delete.status_code == 204

    after = client.get(f"/jobs/{job_id}", headers={"X-API-Key": "secret"})
    assert after.status_code == 404


def test_delete_unknown_job_returns_404(client: TestClient):
    r = client.delete("/jobs/no-such-id", headers={"X-API-Key": "secret"})
    assert r.status_code == 404
