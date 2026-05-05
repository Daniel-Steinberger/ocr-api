from pathlib import Path

from fastapi.testclient import TestClient


def _upload(
    client: TestClient,
    pdf: Path,
    *,
    format: str = "markdown",
    api_key: str | None = "secret",
):
    headers = {"X-API-Key": api_key} if api_key else {}
    with pdf.open("rb") as fh:
        return client.post(
            "/convert",
            files={"file": (pdf.name, fh, "application/pdf")},
            params={"format": format},
            headers=headers,
        )


def test_convert_markdown(client: TestClient, sample_pdf: Path, fake_converter):
    response = _upload(client, sample_pdf, format="markdown")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "markdown"
    assert body["markdown"].startswith("# Converted")
    assert body.get("metadata") == {"page_count": 1}
    assert len(fake_converter.calls) == 1


def test_convert_requires_api_key(client: TestClient, sample_pdf: Path):
    response = _upload(client, sample_pdf, format="markdown", api_key=None)
    assert response.status_code == 401


def test_convert_rejects_non_pdf(client: TestClient, tmp_path: Path):
    txt = tmp_path / "note.txt"
    txt.write_bytes(b"hi")
    with txt.open("rb") as fh:
        response = client.post(
            "/convert",
            files={"file": (txt.name, fh, "text/plain")},
            params={"format": "markdown"},
            headers={"X-API-Key": "secret"},
        )
    assert response.status_code == 415
