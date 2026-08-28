# Architecture — Code Nexus

## Pipeline

```mermaid
flowchart LR
  subgraph Ingest
    A2[Open-Meteo<br/>16-day obs + 7-day forecast<br/>+ ERA5 archive]:::live
    A6[live_ingest.py<br/>scheduler / GET /api/tick<br/>every 15 min]:::live
    A1[IMD AWS / GPM-IMERG<br/>rainfall]:::future
    A3[Local tipping-bucket<br/>gauges / IoT]:::future
    A4[SRTM / Cartosat DEM<br/>-> slope]:::future
    A5[GSI susceptibility +<br/>landslide inventory]:::future
  end

  A2 --> A6 --> RH[(rainfall_hourly<br/>observed + forecast)]
  A1 & A3 --> Q[Ingestion API<br/>POST /api/ingest/telemetry]
  A4 & A5 --> S[(Static terrain<br/>layers per zone)]
  RH --> M

  Q --> DB[(SQLite / Postgres<br/>readings, alerts, reports)]
  Q --> RT[Event broker<br/>SSE /api/events]

  DB --> M[Hazard model<br/>rainfall_model.py<br/>API + Caine-ID + Mora-Vahrson]
  S --> M
  M --> AL[Alert engine<br/>alerts.py<br/>level + priority queue]
  AL --> CAP[CAP 1.2 emitter<br/>cap.py]
  AL --> RT

  CAP --> OUT1[SACHET / State SDMA]:::future
  CAP --> OUT2[Cell broadcast / SMS / siren]:::future
  RT --> UI[Situation room<br/>frontend/ dashboard + map]
  M --> REP[Historical replay<br/>replay.py -> lead-time evidence]

  UI --> FR[Field reports<br/>geotagged ground truth] --> DB

  classDef live fill:#1f7a5c,color:#fff,stroke:#0d3;
  classDef future fill:#5a3b1f,color:#fff,stroke:#a63,stroke-dasharray:4 3;
```

Green = wired in the prototype. Dashed brown = contracted but stubbed
(`backend/data_connectors.py` lists connection status per source).

## Components

| Module | Responsibility |
| --- | --- |
| `backend/app.py` | Flask API + serves the dashboard |
| `backend/rainfall_model.py` | Antecedent index, Caine ID threshold, hazard composition |
| `backend/risk_engine.py` | Older flat weighted baseline (kept for comparison) |
| `backend/replay.py` | Fetch real past rainfall (ERA5) → risk trajectory → lead time |
| `backend/alerts.py` | Level mapping, recommended action, risk×exposure priority queue |
| `backend/cap.py` | CAP 1.2 (SACHET-compatible) alert output |
| `backend/simulator.py` | Scenario boosts + SQLite persistence |
| `backend/realtime.py` | In-process pub/sub for Server-Sent Events |
| `backend/open_meteo.py` | Live weather adapter |
| `frontend/` | Situation room: map, zone intelligence, alerts, field reports, replay |

## Data / control flow at runtime

1. A rainfall reading arrives (`POST /api/ingest/telemetry`) or the Open-Meteo
   sync runs.
2. It is validated, persisted, and published to connected dashboards over SSE.
3. On request (`/api/risk`, `/api/alerts`) the hazard model combines the reading's
   antecedent + intensity signal with the zone's static terrain layers.
4. The alert engine assigns a level and orders zones by risk × exposure.
5. High/Critical zones produce a CAP message for downstream dissemination.
6. Field reports feed geotagged ground truth back into the store.

## Scaling & deployment

- **Stateless API** behind a WSGI server (gunicorn); horizontal scale for read
  load. Move persistence to managed Postgres; move SSE to Redis pub/sub or a
  managed broker.
- **Offline-first dashboard** — Northeastern connectivity is intermittent; the
  frontend already runs from cached state and a polling fallback. Target: a PWA
  that a district officer can open with no signal and sync when back online.
- **Cost envelope (order-of-magnitude, one district):** Open-Meteo + ERA5 are
  free; GPM-IMERG is free; a small always-on API instance + managed DB is a few
  US$/month. The dominant real cost is field gauges and their telemetry, not
  compute.
- **Rollout:** one validated pilot corridor → district → state, adding real DEM
  and GSI layers per area as calibration data accrues.
