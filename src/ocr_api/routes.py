from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from ocr_api.auth import require_api_key
from ocr_api.converter import MarkerConverter
from ocr_api.jobs import JobStore, run_job
from ocr_api.schemas import ConvertResponse, JobCreatedResponse, JobStatusResponse

router = APIRouter()


def _get_converter_dependency(request: Request) -> MarkerConverter:
    converter = getattr(request.app.state, "converter", None)
    if converter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="converter not initialized",
        )
    return converter


def _get_job_store_dependency(request: Request) -> JobStore:
    store = getattr(request.app.state, "job_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="job store not initialized",
        )
    return store


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
    format: Literal["markdown", "json", "html"] = Query("markdown"),
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
        html=result.html,
        json_blocks=result.json,
        metadata=result.metadata,
    )


@router.post(
    "/jobs",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    format: Literal["markdown", "json", "html"] = Query("markdown"),
    converter: MarkerConverter = Depends(_get_converter_dependency),
    store: JobStore = Depends(_get_job_store_dependency),
) -> JobCreatedResponse:
    pdf_path = await _save_upload(file)
    job = await store.create()
    background_tasks.add_task(
        run_job,
        store=store,
        job_id=job.id,
        pdf_path=pdf_path,
        output_format=format,
        converter=converter,
    )
    return JobCreatedResponse(job_id=job.id, status=job.status)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_job(
    job_id: str,
    store: JobStore = Depends(_get_job_store_dependency),
) -> JobStatusResponse:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
async def delete_job(
    job_id: str,
    store: JobStore = Depends(_get_job_store_dependency),
) -> None:
    if not await store.delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
