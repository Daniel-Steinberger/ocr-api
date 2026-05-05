from typing import Any, Literal

from pydantic import BaseModel


class ConvertResponse(BaseModel):
    format: Literal["markdown", "json"]
    markdown: str | None = None
    json_blocks: list[Any] | dict | None = None
    metadata: dict | None = None
