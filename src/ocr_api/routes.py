from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from ocr_api.auth import require_api_key
from ocr_api.converter import MarkerConverter
from ocr_api.schemas import ConvertResponse

router = APIRouter()


def _get_converter_dependency(request: Request) -> MarkerConverter:
    converter = getattr(request.app.state, "converter", None)
    if converter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="converter not initialized",
        )
    return converter


async def _save_upload(file: UploadFile) -> Path:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"only PDFs are supported, got {file.content_type}",
        )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        while chunk := await file.read(1 << 20):
            tmp.write(chunk)
        return Path(tmp.name)


@router.post(
    "/convert",
    response_model=ConvertResponse,
    dependencies=[Depends(require_api_key)],
)
async def convert(
    file: UploadFile = File(...),
    format: Literal["markdown", "json"] = Query("markdown"),
    converter: MarkerConverter = Depends(_get_converter_dependency),
) -> ConvertResponse:
    pdf_path = await _save_upload(file)
    try:
        result = await converter.convert(pdf_path, output_format=format)
    finally:
        pdf_path.unlink(missing_ok=True)

    return ConvertResponse(
        format=format,
        markdown=result.markdown,
        json_blocks=result.json,
        metadata=result.metadata,
    )
