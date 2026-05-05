import asyncio
from pathlib import Path

import pytest

from ocr_api.converter import ConvertResult, MarkerConverter


class FakePdfConverter:
    """Stand-in for marker.converters.pdf.PdfConverter."""

    def __init__(self, markdown: str = "# hello", json_blocks: list | None = None):
        self.markdown = markdown
        self.json_blocks = json_blocks or [{"block_type": "Page", "id": "/page/0"}]
        self.calls: list[str] = []

    def __call__(self, filepath: str):
        self.calls.append(filepath)

        class _Rendered:
            pass

        rendered = _Rendered()
        rendered.markdown = self.markdown
        rendered.children = self.json_blocks
        rendered.metadata = {"page_count": 1}
        rendered.images = {}
        return rendered


async def test_convert_markdown(tmp_path: Path):
    fake = FakePdfConverter(markdown="# hi")
    converter = MarkerConverter(pdf_converter=fake, max_concurrent=2)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    result = await converter.convert(pdf, output_format="markdown")

    assert isinstance(result, ConvertResult)
    assert result.markdown == "# hi"
    assert result.json is None
    assert fake.calls == [str(pdf)]


async def test_convert_json(tmp_path: Path):
    fake = FakePdfConverter(json_blocks=[{"block_type": "Page", "id": "/page/0"}])
    converter = MarkerConverter(pdf_converter=fake, max_concurrent=1)
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    result = await converter.convert(pdf, output_format="json")

    assert result.json == [{"block_type": "Page", "id": "/page/0"}]
    assert result.markdown is None


async def test_convert_rejects_unknown_format(tmp_path: Path):
    converter = MarkerConverter(pdf_converter=FakePdfConverter(), max_concurrent=1)
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ValueError):
        await converter.convert(pdf, output_format="xml")


async def test_semaphore_limits_concurrency(tmp_path: Path):
    """With max_concurrent=1, two simultaneous converts must run serially."""
    import threading
    import time

    lock = threading.Lock()
    state = {"in_flight": 0, "peak": 0}

    class SlowFake:
        def __call__(self, filepath: str):
            with lock:
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
            time.sleep(0.05)
            with lock:
                state["in_flight"] -= 1

            class R:
                markdown = "x"
                children = []
                metadata = {}
                images = {}

            return R()

    converter = MarkerConverter(pdf_converter=SlowFake(), max_concurrent=1)
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    await asyncio.gather(
        converter.convert(pdf, output_format="markdown"),
        converter.convert(pdf, output_format="markdown"),
        converter.convert(pdf, output_format="markdown"),
    )
    assert state["peak"] == 1
