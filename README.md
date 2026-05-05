# ocr-api

FastAPI service that converts PDFs to Markdown or structured JSON using
[`marker-pdf`](https://github.com/datalab-to/marker) on a CUDA GPU.

## Quickstart (lokal)

```bash
# 1. Voraussetzungen: NVIDIA-Treiber + CUDA-fähige GPU, uv installiert
uv sync                                    # installiert Python 3.12, torch+cu128, marker, FastAPI ...

# 2. .env anlegen (siehe .env.example)
cp .env.example .env
# API_KEY in .env auf einen geheimen Wert setzen

# 3. Server starten — beim ersten Request lädt marker seine Modelle (~5 GB Download
#    aus dem HuggingFace-Hub, danach im Cache)
OCR_API_LOAD_MODELS=1 uv run uvicorn ocr_api.main:app --host 0.0.0.0 --port 8000

# 4. Health-Check
curl http://localhost:8000/health
# → {"status":"ok","gpu":true,"device":"NVIDIA GeForce RTX 4070 SUPER"}
```

## Quickstart (Docker)

```bash
echo "API_KEY=$(openssl rand -hex 16)" > .env
docker compose up --build
# Erster Start dauert lange: Image baut + marker lädt seine Modelle in
# das Volume hf-cache (persistent zwischen Restarts).
```

Voraussetzung: NVIDIA Container Toolkit (`nvidia-ctk runtime configure --runtime=docker`).

## Endpoints

Alle Endpunkte außer `/health` brauchen den Header `X-API-Key: <wert>`.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Liveness + GPU-Status |
| POST | `/convert?format=markdown\|json` | **Synchron** — blockt bis fertig, gibt Ergebnis direkt zurück |
| POST | `/jobs?format=markdown\|json` | **Asynchron** — gibt `job_id` zurück, Konvertierung läuft im Hintergrund |
| GET | `/jobs/{id}` | Status eines Jobs (`queued` / `running` / `done` / `failed`) inkl. Ergebnis |
| DELETE | `/jobs/{id}` | Job-Eintrag aus dem In-Memory-Store entfernen |

### Beispiele

Synchron, kleine PDF:
```bash
curl -H "X-API-Key: $API_KEY" \
     -F file=@invoice.pdf \
     "http://localhost:8000/convert?format=markdown"
```

Synchron, JSON-Block-Tree:
```bash
curl -H "X-API-Key: $API_KEY" \
     -F file=@report.pdf \
     "http://localhost:8000/convert?format=json"
```

Asynchron mit Polling (für PDFs >20 Seiten empfohlen):
```bash
JOB=$(curl -s -H "X-API-Key: $API_KEY" -F file=@huge.pdf \
      "http://localhost:8000/jobs?format=markdown" | jq -r .job_id)

while :; do
  STATUS=$(curl -s -H "X-API-Key: $API_KEY" \
                "http://localhost:8000/jobs/$JOB" | jq -r .status)
  echo "$STATUS"
  [ "$STATUS" = "done" ] && break
  [ "$STATUS" = "failed" ] && exit 1
  sleep 2
done

curl -s -H "X-API-Key: $API_KEY" \
     "http://localhost:8000/jobs/$JOB" | jq .result.markdown
```

Eingebettete OpenAPI-Doku unter `http://localhost:8000/docs`.

## Architektur-Entscheidungen

**Sync- *und* Async-Endpunkt** — `POST /convert` ist bequem für kurze
PDFs (<50 Seiten), blockt aber den HTTP-Request bis zum Ende. `POST /jobs`
gibt sofort eine `job_id` zurück; die Konvertierung läuft als
`BackgroundTask` weiter, der Status wird über `GET /jobs/{id}` gepollt.

**In-Memory-Job-Store** — `JobStore` ist ein asyncio-locked Dict.
Bewusste Vereinfachung: kein Redis, keine DB. Beim Restart sind alle
Jobs weg. Geeignet für interne / single-instance-Deployments — wenn das
Service horizontal skalieren oder Restart-resilient werden soll, muss
der Store gegen Redis o. ä. getauscht werden.

**Modell-Lifecycle** — `marker.models.create_model_dict()` ist teuer
(mehrere Modelle in VRAM). Ein einziges `MarkerConverter`-Objekt wird in
der FastAPI-`lifespan` gebaut und an `app.state.converter` gehängt; alle
Requests teilen sich dieses Modell. Geladen wird nur, wenn
`OCR_API_LOAD_MODELS=1` gesetzt ist — so bleiben pytest-Läufe schnell und
offline.

**Concurrency-Schutz** — `MarkerConverter` umschließt jeden
`PdfConverter`-Aufruf mit einem `asyncio.Semaphore(MAX_CONCURRENT_JOBS)`
und führt ihn via `asyncio.to_thread` aus, damit der Event-Loop
während der mehreren Sekunden dauernden GPU-Operation reaktiv bleibt.
Default `MAX_CONCURRENT_JOBS=1` ist konservativ; auf einer 12-GB-GPU
(RTX 4070) sind 2 parallele Jobs erfahrungsgemäß sicher (`marker`
nennt 5 GB peak, 3.5 GB avg pro Worker).

**API-Key-Auth über `X-API-Key`** — statischer Vergleich gegen die
Env-Variable `API_KEY`. Reicht für interne Services hinter Reverse-
Proxy. Für öffentliche Deployments OAuth/JWT vorlagern.

**uv mit explizitem PyTorch-CUDA-Index** — `pyproject.toml` zeigt
`torch` und `torchvision` auf den `cu128`-Index der PyTorch-Foundation,
damit `uv sync` die GPU-Wheels auflöst. Andere Pakete kommen weiterhin
von PyPI.

## Tests

```bash
uv run pytest                              # 21 Tests, ohne Modell-Load (~1.5 s)
OCR_API_LOAD_MODELS=1 uv run pytest        # zusätzlich Lifespan-Test mit echten Modellen
uv run ruff check src tests                # Linting
```

Die Test-Fixtures (`tests/conftest.py`) injizieren einen
`FakeMarkerConverter` über `app.dependency_overrides`, deshalb läuft die
Suite ohne GPU und ohne Modell-Download.

## Projektstruktur

```
src/ocr_api/
├── main.py        # FastAPI-App + Lifespan (lädt JobStore + optional Modelle)
├── config.py      # pydantic-settings: API_KEY, TORCH_DEVICE, MAX_CONCURRENT_JOBS
├── auth.py        # require_api_key Depends
├── converter.py   # MarkerConverter (Semaphore + to_thread) + build_default_converter
├── jobs.py        # In-Memory-JobStore + run_job-BackgroundTask
├── routes.py      # /convert (sync), /jobs (async), DELETE-Cleanup
└── schemas.py     # Pydantic-Response-Modelle
```

## Bekannte Einschränkungen

- **Kein Persistence**: Jobs verlieren ihren Zustand beim Restart.
- **Single-Instance**: keine horizontale Skalierung im aktuellen Setup.
- **Kein Auto-Cleanup**: erledigte Jobs bleiben im Speicher, bis der
  Client `DELETE /jobs/{id}` ruft. Für Production ggf. TTL ergänzen.
- **Keine Streaming-Uploads für große PDFs**: das gesamte File wird in
  einer Tempdatei gepuffert. Reicht für PDFs bis ~200 MB problemlos.
