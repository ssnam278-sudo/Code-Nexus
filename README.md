# BhuSanket

BhuSanket is a landslide intelligence prototype for monitoring environmental conditions, estimating zone-level risk, and prioritising field verification across the North Eastern Region of India.

The repository currently contains two complementary implementations:

- A browser-based situation room in `frontend/` with simulated telemetry, an interactive Leaflet map, escalation scenarios, alerts, zone intelligence, and field reports.
- A standalone, deterministic Python risk engine in `backend/` with unit tests in `tests/`.

The prototype uses local and simulated inputs. It is not a live warning service and must not be used as the sole basis for evacuation, route closure, or emergency response decisions.

## Features

### Situation room

- Regional risk score and active-alert summary
- Risk, rainfall, terrain, exposure, and road map layers
- Monitored locations with selectable incident details
- Environmental telemetry for rainfall, soil moisture, temperature, and accumulated rain
- Exposure snapshot covering people, roads, villages, and critical infrastructure
- Priority queue for field verification

### Simulation and workflow

- Normal, Heavy Rain, and Extreme Rain scenarios in the dashboard
- Automatic telemetry variation during normal simulation mode
- Zone intelligence view with contributing factors and explanations
- Alerts and response-priority views
- Local field-report submission and verification log
- Data-source register showing which inputs are simulated or prepared

### Python risk engine

The Python engine calculates a bounded score from seven inputs:

| Input | Weight |
| --- | ---: |
| Current rainfall | 16% |
| Accumulated rainfall | 12% |
| Soil moisture | 20% |
| Slope | 16% |
| Terrain susceptibility | 16% |
| Historical vulnerability | 12% |
| Exposure | 8% |

Scores are classified as:

| Score | Level |
| ---: | --- |
| 0-34 | Monitoring |
| 35-54 | Advisory |
| 55-74 | High |
| 75-100 | Critical |

## Project structure

```text
.
├── backend/
│   ├── alerts.py              # Placeholder for alert-generation logic
│   ├── app.py                 # Placeholder for a future backend API
│   ├── risk_engine.py         # Deterministic risk calculation
│   ├── simulator.py           # Scenario transformations
│   └── data/                  # Reserved for future data integrations
├── frontend/
│   ├── index.html              # Dashboard shell and views
│   ├── css/style.css           # Dashboard styling and responsive layout
│   └── js/
│       ├── app.js              # State, mock data, simulation, and navigation
│       ├── dashboard.js         # Dashboard rendering and interactions
│       └── map.js               # Leaflet map and map layers
├── tests/
│   └── test_risk_engine.py     # Risk engine and simulator tests
├── requirements.txt
└── README.md
```

## Run the dashboard

The frontend is static and does not currently require a backend server or Python packages.

From the repository root:

```bash
cd frontend
python3 -m http.server 8000
```

Open [http://localhost:8000](http://localhost:8000) in a browser.

The map uses Leaflet and external tile/font resources loaded from CDNs, so those resources require network access. The dashboard still loads without the map tile services, but the map background and some map controls will be unavailable.

## Run the Python tests

The project uses Python's standard-library `unittest` framework. Run the suite from the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The current tests cover validation, deterministic and bounded scores, risk thresholds, scenario escalation, and recovery behavior.

### ML comparison model

The repository also includes `backend/ml_model.py`, a deterministic Random Forest classifier trained from the clearly labeled prototype dataset in `backend/data/historical_training.json`. It compares the learned risk level with the explainable baseline, reports model confidence, and identifies the three strongest learned drivers.

This training file is synthetic prototype data, not a validated historical disaster record. Replace it with reviewed event history and evaluate it on held-out data before using model output operationally. The protected API endpoint is:

```text
POST /api/ml/compare
```

It accepts the same seven numeric zone inputs as the baseline and returns `baseline`, `model`, and `comparison` objects. A disagreement is intentionally surfaced for human review rather than silently overriding the baseline.

## Use the risk engine

The engine accepts a mapping with the required numeric fields and returns a risk score, level, confidence, explanation, and contributing factors.

```python
from backend.risk_engine import calculate_risk
from backend.simulator import simulate_zone

zone = {
	"rainfall": 42.6,
	"accumulated": 184,
	"moisture": 76,
	"slope": 72,
	"susceptibility": 82,
	"history": 68,
	"exposure": 86,
}

normal = calculate_risk(zone)
extreme = simulate_zone(zone, "Extreme Rain")

print(normal["risk_score"], normal["risk_level"])
print(extreme["risk_score"], extreme["risk_level"])
```

Accepted simulator scenarios are `Normal`, `Heavy Rain`, `Extreme Rain`, and `Recovery`. Rainfall and accumulated rainfall must be non-negative. Moisture, slope, susceptibility, historical vulnerability, and exposure must be between 0 and 100.

## Current status and next steps

This is a prototype rather than a production monitoring system. The browser dashboard currently uses its own in-memory mock data, while the Python engine is a separate library and is not connected to the dashboard. Authentication and protected API foundations are present, but the repository does not yet include durable operational data persistence, live sensor ingestion, or production alert delivery.

Natural next steps are to connect the dashboard to an API backed by `risk_engine.py`, populate the data contracts in `backend/data/`, add durable report storage, and integrate validated environmental, terrain, historical, and exposure feeds.

## Configure authentication

The authentication foundation uses Supabase Auth. It runs in demo mode while credentials are blank, so the existing dashboard can still be explored locally.

### 1. Create a Supabase project

Create a project at [supabase.com](https://supabase.com), then open **Project Settings > API**. Copy the project URL and the public anon key into `frontend/js/config.js`:

```js
window.BHUSANKET_CONFIG = {
	supabaseUrl: 'https://your-project.supabase.co',
	supabaseAnonKey: 'your-public-anon-key',
	apiBaseUrl: 'http://localhost:8001'
};
```

The anon key is intended for browser use. Never put a Supabase service-role key in `frontend/` or commit it to Git.

### 2. Create the database tables

Open the Supabase **SQL Editor**, paste the contents of [`backend/supabase_schema.sql`](backend/supabase_schema.sql), and run it. New users default to the `Citizen` role.

### 3. Enable sign-in providers

In **Authentication > Providers**:

- Enable Email for password sign-in and magic links.
- Enable Google for Google login.
- Add the local callback URL `http://localhost:8000/` under the allowed redirect URLs.

Google login also requires a Google Cloud OAuth client. Add the Supabase callback URL shown in the Google provider settings to the OAuth client's authorised redirect URIs. Keep the Google client secret inside Supabase, not in this repository.

### 4. Run the API

Install dependencies and copy the environment template:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Set `SUPABASE_URL` in `.env`, then start the API from the repository root:

```bash
uvicorn backend.app:app --reload --port 8001 --env-file .env
```

The API accepts Supabase access tokens as `Authorization: Bearer <token>`. `GET /api/me` is protected for any signed-in user, while `GET /api/admin/users` is restricted to users whose Supabase `app_metadata.role` is `Admin`.

### 5. Assign roles

For security, users cannot promote themselves. Create the first admin through the Supabase dashboard or a server-side admin script, then set the role in both the `profiles` record and the user's Supabase `app_metadata`. Keep role changes behind an Admin-only server route in production.

## License

See [LICENSE](LICENSE).
