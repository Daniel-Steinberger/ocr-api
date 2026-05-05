from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ocr_api.jobs import JobStore
from ocr_api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.job_store = JobStore()
    # app.state.converter is wired in step 8 (real model loading)
    yield


app = FastAPI(title="ocr-api", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    import torch

    gpu = torch.cuda.is_available()
    device = torch.cuda.get_device_name(0) if gpu else "cpu"
    return {"status": "ok", "gpu": gpu, "device": device}
