# Deploying Code Nexus to a permanent URL

The full prototype (Flask API + risk engine + live Open‑Meteo weather + browser
situation room) is unchanged. Only deployment glue was added:

| File | Purpose |
| --- | --- |
| `render.yaml` | One‑click Render blueprint (recommended – runs the whole app live) |
| `pyproject.toml` | `[tool.vercel] entrypoint = "backend.app:app"` – Vercel serves the Flask WSGI app directly |
| `backend/__init__.py` | Make `backend` an explicit package for serverless bundlers |
| `CODENEXUS_DB` env var | Point SQLite at a writable path; the app auto‑uses `/tmp` when `VERCEL` is set |

The dashboard auto‑detects its API: when served from the same origin as the API
(Render / Vercel) it just works, with no `frontend/js/config.js` change needed.

---

## Option A — Render  (recommended: everything works, including SSE + ML + live weather)

1. Push this repo to your own GitHub account.
2. Go to <https://dashboard.render.com> → **New +** → **Blueprint**.
3. Select the repo. Render reads `render.yaml` and creates the web service.
4. Deploy. Your permanent URL is `https://<name>.onrender.com`.

Free instances sleep after 15 min idle and cold‑start in ~30 s. That is the only
limitation; every feature runs.

Local equivalent:

```bash
pip install -r requirements.txt
gunicorn backend.app:app --bind 0.0.0.0:8000       # or: python -m backend.app
```

---

## Option B — Vercel  (deploy from this folder, no GitHub needed)

**From the Vercel dashboard (recommended):** <https://vercel.com/new> → Import
this repo → **Framework Preset: Other / Flask** → Deploy. `pyproject.toml` tells
Vercel the entrypoint is `backend.app:app`; it installs `requirements.txt` and
serves the Flask app (frontend + API). Redeploys on every push.

**Or from this folder:**

```bash
npx vercel login
npx vercel --prod         # → https://<project>.vercel.app
```

**Two serverless limitations** (the app handles both automatically):

- **Server‑Sent Events** (`/api/events`) can't stay open on serverless, so the
  dashboard falls back to 7‑second polling.
- **scikit‑learn** may exceed Vercel Hobby's 250 MB Python bundle. If the build
  fails on size, delete the `scikit-learn` line from `requirements.txt` and
  redeploy — `/api/ml/compare` then returns `503` and the UI shows
  "AI comparison unavailable. Baseline remains active." Everything else
  (risk engine, scenarios, priority queue, live Open‑Meteo sync, field reports,
  Leaflet map) runs normally.
- Field reports on Vercel persist in `/tmp` only for the warm lifetime of the
  instance. Use Option A for durable storage.

---

## Option C — Cloudflare Pages / Netlify  (static front‑end only)

These host static files, not Python. The dashboard still runs fully in its
built‑in **offline prototype mode** (simulated telemetry, real Leaflet map,
scenarios, local reports) but without the Flask risk engine or persistence.

- **Build command:** *(none)*
- **Output / publish directory:** `frontend`

For a live backend, pair this with Option A/B and set `apiBaseUrl` in
`frontend/js/config.js` to that API URL.

---

## Environment variables (all optional)

| Var | Default | Notes |
| --- | --- | --- |
| `OPEN_METEO_SYNC_SECONDS` | `600` | Min seconds between live weather pulls |
| `INGEST_API_KEY` | *(unset)* | If set, `POST /api/ingest/telemetry` requires header `X-Ingest-Key` |
| `CODENEXUS_DB` | `backend/code_nexus.db` locally, `/tmp/code_nexus.db` when `VERCEL` is set | Override to use a specific path (e.g. a mounted volume) |
