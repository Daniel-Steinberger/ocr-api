from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

OutputFormat = Literal["markdown", "json", "html"]

# Each output format is produced by a distinct marker renderer. The renderers
# return different output objects (MarkdownOutput.markdown, HTMLOutput.html,
# JSONOutput.children), so a converter must be wired to the matching renderer.
RENDERER_CLASSES: dict[str, str] = {
    "markdown": "marker.renderers.markdown.MarkdownRenderer",
    "json": "marker.renderers.json.JSONRenderer",
    "html": "marker.renderers.html.HTMLRenderer",
}


class PdfConverterProtocol(Protocol):
    def __call__(self, filepath: str) -> Any: ...


@dataclass
class ConvertResult:
    markdown: str | None = None
    html: str | None = None
    json: list | dict | None = None
    metadata: dict | None = None


class MarkerConverter:
    """Async-friendly wrapper around marker's PdfConverter.

    Holds one marker PdfConverter per output format, each wired to the
    matching renderer; the heavy model weights are shared between them, so
    the extra converters cost no additional VRAM. Bounds GPU concurrency via
    a Semaphore and offloads the blocking PdfConverter call to a worker
    thread so the event loop stays responsive.
    """

    def __init__(
        self,
        pdf_converters: PdfConverterProtocol | dict[str, PdfConverterProtocol],
        max_concurrent: int = 1,
    ):
        # A bare callable is applied to every format — keeps test fakes (one
        # object exposing markdown/html/children at once) simple to wire up.
        if not isinstance(pdf_converters, dict):
            pdf_converters = dict.fromkeys(RENDERER_CLASSES, pdf_converters)
        self._converters = pdf_converters
        self._sem = asyncio.Semaphore(max_concurrent)

    async def convert(self, pdf_path: Path, output_format: OutputFormat) -> ConvertResult:
        converter = self._converters.get(output_format)
        if converter is None:
            raise ValueError(f"unsupported output_format: {output_format!r}")

        async with self._sem:
            rendered = await asyncio.to_thread(converter, str(pdf_path))

        metadata = getattr(rendered, "metadata", None)
        if output_format == "markdown":
            return ConvertResult(markdown=rendered.markdown, metadata=metadata)
        if output_format == "html":
            return ConvertResult(html=rendered.html, metadata=metadata)
        return ConvertResult(json=rendered.children, metadata=metadata)


def mute_progress_bars() -> None:
    """Silence tqdm + HuggingFace + transformers progress bars.

    Must run before marker / surya / transformers are imported so the env
    vars take effect at module load time.
    """
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"


def build_default_converter(
    max_concurrent: int = 1,
    disable_progress_bars: bool = False,
) -> MarkerConverter:
    """Build a MarkerConverter backed by a real marker PdfConverter.

    Reads TORCH_DEVICE from the environment (marker honors it). Loads heavy
    model weights — call once at app startup. When disable_progress_bars is
    set, mutes tqdm globally and passes ``disable_tqdm=True`` to marker.
    """
    os.environ.setdefault("TORCH_DEVICE", "cuda")
    if disable_progress_bars:
        mute_progress_bars()

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    config = {"disable_tqdm": True} if disable_progress_bars else None
    # Build one converter per format, all sharing the same model weights.
    artifact_dict = create_model_dict()
    pdf_converters = {
        fmt: PdfConverter(artifact_dict=artifact_dict, renderer=renderer, config=config)
        for fmt, renderer in RENDERER_CLASSES.items()
    }
    return MarkerConverter(pdf_converters=pdf_converters, max_concurrent=max_concurrent)
