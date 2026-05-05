from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ocr_api.config import get_settings
from ocr_api.converter import build_default_converter
from ocr_api.jobs import JobStore
from ocr_api.routes import router

logger = logging.getLogger(__name__)


def _should_load_models() -> bool:
    """Models are heavy. Load only when explicitly requested.

    Production sets OCR_API_LOAD_MODELS=1; tests leave it unset so the
    suite stays fast and offline. Set to 1 in docker-compose / deployment.
    """
    return os.environ.get("OCR_API_LOAD_MODELS") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.job_store = JobStore()
    if _should_load_models():
        settings = get_settings()
        logger.info("loading marker models on device=%s", settings.torch_device)
        app.state.converter = build_default_converter(
            max_concurrent=settings.max_concurrent_jobs,
        )
        logger.info("marker models loaded")
    else:
        logger.info("OCR_API_LOAD_MODELS not set — skipping model load")
    yield


app = FastAPI(title="ocr-api", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    import torch

    gpu = torch.cuda.is_available()
    device = torch.cuda.get_device_name(0) if gpu else "cpu"
    return {"status": "ok", "gpu": gpu, "device": device}
