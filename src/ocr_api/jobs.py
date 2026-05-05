from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ocr_api.converter import MarkerConverter

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass
class Job:
    id: str
    status: JobStatus = "queued"
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobStore:
    """In-memory async-safe job store. Lost on restart by design."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> Job:
        async with self._lock:
            job = Job(id=uuid.uuid4().hex)
            self._jobs[job.id] = job
            return job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)

    async def delete(self, job_id: str) -> bool:
        async with self._lock:
            return self._jobs.pop(job_id, None) is not None


async def run_job(
    *,
    store: JobStore,
    job_id: str,
    pdf_path: Path,
    output_format: str,
    converter: MarkerConverter,
) -> None:
    """Background task body. Updates the job's status as it progresses."""
    await store.update(job_id, status="running")
    try:
        result = await converter.convert(pdf_path, output_format=output_format)  # type: ignore[arg-type]
        payload = {
            "format": output_format,
            "markdown": result.markdown,
            "json_blocks": result.json,
            "metadata": result.metadata,
        }
        await store.update(job_id, status="done", result=payload)
    except Exception as exc:
        await store.update(job_id, status="failed", error=str(exc))
    finally:
        pdf_path.unlink(missing_ok=True)
