from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "done", "failed"]


class ConvertResponse(BaseModel):
    format: Literal["markdown", "json", "html"]
    markdown: str | None = None
    html: str | None = None
    json_blocks: list[Any] | dict | None = None
    metadata: dict | None = None


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: ConvertResponse | dict | None = None
    error: str | None = None
    created_at: datetime
