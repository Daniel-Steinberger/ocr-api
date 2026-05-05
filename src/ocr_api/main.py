from __future__ import annotations

from fastapi import FastAPI

from ocr_api.routes import router

app = FastAPI(title="ocr-api", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health() -> dict:
    import torch

    gpu = torch.cuda.is_available()
    device = torch.cuda.get_device_name(0) if gpu else "cpu"
    return {"status": "ok", "gpu": gpu, "device": device}
