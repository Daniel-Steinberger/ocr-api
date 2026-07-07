from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocr_api.config import Settings, get_settings
from ocr_api.converter import ConvertResult, MarkerConverter
from ocr_api.main import app
from ocr_api.routes import _get_converter_dependency


class FakeMarkerConverter(MarkerConverter):
    """In-process MarkerConverter substitute that returns canned output."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    async def convert(self, pdf_path: Path, output_format: str) -> ConvertResult:
        self.calls.append((pdf_path, output_format))
        if output_format == "markdown":
            return ConvertResult(
                markdown=f"# Converted {pdf_path.name}",
                metadata={"page_count": 1},
            )
        if output_format == "json":
            return ConvertResult(
                json=[{"block_type": "Page", "id": "/page/0"}],
                metadata={"page_count": 1},
            )
        if output_format == "html":
            return ConvertResult(
                html=f"<h1>Converted {pdf_path.name}</h1>",
                metadata={"page_count": 1},
            )
        raise ValueError(f"unsupported format: {output_format}")


@pytest.fixture
def fake_converter() -> FakeMarkerConverter:
    return FakeMarkerConverter()


@pytest.fixture
def client(fake_converter: FakeMarkerConverter) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    app.dependency_overrides[_get_converter_dependency] = lambda: fake_converter
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return pdf
