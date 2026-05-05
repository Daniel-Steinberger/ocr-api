from fastapi import FastAPI

app = FastAPI(title="ocr-api", version="0.1.0")


@app.get("/health")
def health() -> dict:
    import torch

    gpu = torch.cuda.is_available()
    device = torch.cuda.get_device_name(0) if gpu else "cpu"
    return {"status": "ok", "gpu": gpu, "device": device}
