# Data sources — Code Nexus

Every input the model uses, where it comes from, and the authoritative dataset to
swap in for operational use. All "live now" sources are **free and keyless**.

---

## 1. Rainfall — now + forecast  (primary trigger)

| | |
| --- | --- |
| **Used in** | `backend/live_ingest.py`, `backend/open_meteo.py`, `frontend/js/weather.js` (browser) |
| **Provider** | Open-Meteo Forecast API |
| **Endpoint** | `https://api.open-meteo.com/v1/forecast` |
| **Params** | `hourly=precipitation,precipitation_probability` · `past_days=16` · `forecast_days=7` · `timezone=UTC` (live-ingest); `current=temperature_2m,precipitation,rain,relative_humidity_2m,soil_moisture_0_to_7cm` (`open_meteo.py`) |
| **Extracts** | hourly precipitation (mm), precipitation probability (%) — 16 days observed + 7 days forecast, per zone lat/lon |
| **Live vs simulated** | `/api/zones` and `/api/risk` tag every zone `data_source: "open-meteo" \| "simulated"` with `observed_at` + `feed_age_seconds`; the dashboard shows a `LIVE`/`SIM` badge per telemetry value and drives the confidence model. A zone is `simulated` until a real reading lands in `current_sensors` (Open-Meteo sync or `POST /api/ingest/telemetry`). |
| **Docs** | https://open-meteo.com/en/docs |
| **Licence** | CC-BY 4.0, no API key |
| **Underlying models** | ECMWF IFS + DWD ICON + NOAA GFS blend |

**Authoritative replacement (India):**
- IMD (India Meteorological Department) — https://mausam.imd.gov.in/ · gridded daily rainfall (0.25°): https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html
- NASA GPM IMERG (half-hourly, 0.1°) — https://gpm.nasa.gov/data/imerg · access: https://disc.gsfc.nasa.gov/datasets?keywords=IMERG
- CHIRPS (daily rainfall, 0.05°) — https://www.chc.ucsb.edu/data/chirps

---

## 2. Rainfall — historical  (event replay / validation)

| | |
| --- | --- |
| **Used in** | `backend/replay.py` (cached under `backend/data/replay_cache/`) |
| **Provider** | Open-Meteo Historical Weather API (ERA5 reanalysis) |
| **Endpoint** | `https://archive-api.open-meteo.com/v1/archive` |
| **Params** | `hourly=precipitation` · `start_date` / `end_date` · `timezone=UTC` |
| **Extracts** | hourly precipitation (mm) for a real past window around each landslide event |
| **Docs** | https://open-meteo.com/en/docs/historical-weather-api |
| **Underlying dataset** | ECMWF **ERA5** / ERA5-Land reanalysis (~25 km / ~9 km) |
| **ERA5 primary source** | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels |

---

## 3. Soil moisture  (wetness cross-check)

| | |
| --- | --- |
| **Used in** | `backend/live_ingest.py` (→ `backend/rainfall_model.py` `effective_wetness`) |
| **Provider** | Open-Meteo Forecast API (same call as #1) |
| **Params** | `hourly=soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm` |
| **Extracts** | volumetric soil water content (m³/m³) at 3 near-surface layers, hourly, observed + forecast |
| **Underlying model** | ECMWF land-surface scheme |

**Authoritative replacement:** NASA SMAP L3/L4 soil moisture — https://smap.jpl.nasa.gov/data/ · ESA CCI Soil Moisture — https://climate.esa.int/en/projects/soil-moisture/

---

## 4. Terrain — slope, local relief, roughness, profile curvature  (predisposition)

| | |
| --- | --- |
| **Used in** | `backend/terrain.py` (cached under `backend/data/terrain_cache/`) |
| **Provider** | Open-Meteo Elevation API |
| **Endpoint** | `https://api.open-meteo.com/v1/elevation` |
| **Method** | 9×9 sample grid (~9 km window, ~1.1 km spacing) per zone → central-difference slope (p88 of grid), elevation range, std-dev, Laplacian curvature |
| **Docs** | https://open-meteo.com/en/docs/elevation-api |
| **Underlying DEM** | Copernicus **GLO-90** / NASA **SRTM** (~90 m) |
| **Alt. tested** | OpenTopoData SRTM 30 m — https://www.opentopodata.org/datasets/srtm/ |

**Authoritative replacement (higher-res DEM):**
- Copernicus DEM (GLO-30, 30 m) — https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model
- NASADEM (30 m) — https://lpdaac.usgs.gov/products/nasadem_hgtv001/
- ISRO CartoDEM (10 m, India) — https://bhuvan.nrsc.gov.in/ (Elevation → CartoDEM)
- ALOS AW3D30 (30 m) — https://www.eorc.jaxa.jp/ALOS/en/dataset/aw3d30/aw3d30_e.htm

---

## 5. Terrain susceptibility zonation  (predisposition — production layer)

| | |
| --- | --- |
| **Used in** | prototype derives it from #4; production layer not yet wired |
| **Authoritative** | GSI **National Landslide Susceptibility Mapping** (1:50,000) — https://bhukosh.gsi.gov.in/ (Bhukosh portal, GSI) |
| | NRSC/ISRO **Bhuvan – Landslide Hazard Zonation** — https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=landslide |
| | GSI main site — https://www.gsi.gov.in/ |

---

## 6. Historical landslide inventory  (historical-vulnerability factor)

| | |
| --- | --- |
| **Used in** | `backend/landslide_inventory.py` — 15 curated, dated NE-India events; `history_index` = distance + recency decayed density |
| **Authoritative replacements** | |
| GSI Landslide Inventory | https://bhukosh.gsi.gov.in/Bhukosh/Public (layer: Geohazards → Landslide) |
| NASA **Global Landslide Catalog** (GLC) / COOLR | https://gpm.nasa.gov/landslides/ · data export: https://data.nasa.gov/dataset/global-landslide-catalog-export |
| NASA COOLR viewer | https://maps.nccs.nasa.gov/arcgis/apps/webappviewer/index.html?id=824ea5864ec8423fb985b33ee6bc05b7 |
| NRSC landslide inventory (India) | https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=landslide |

---

## 7. Map context — basemap, roads, settlements

| | |
| --- | --- |
| **Used in** | `frontend/js/map.js` (deployed) and baked-in tiles in `code-nexus.html` |
| **Sources** | OpenStreetMap tiles `https://tile.openstreetmap.org/{z}/{x}/{y}.png` · OpenTopoMap `https://{s}.tile.opentopomap.org/...` · Esri World Imagery `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/...` |
| **Bulk OSM data** | https://download.geofabrik.de/asia/india.html (roads, buildings, places) |
| **Admin boundaries** | Survey of India / Bhuvan — https://bhuvan.nrsc.gov.in/ · GADM — https://gadm.org/download_country.html (IND) |
| **Licence** | OSM: ODbL |

---

## 8. Exposure — population, roads, villages, critical assets

| | |
| --- | --- |
| **Used in** | `backend/data/infrastructure.json` (prototype, hand-entered) |
| **Authoritative replacements** | |
| WorldPop (100 m population) | https://www.worldpop.org/ |
| Meta / CIESIN High-Resolution Population Density | https://data.humdata.org/dataset/highresolutionpopulationdensitymaps |
| Census of India (village/town, PCA) | https://censusindia.gov.in/ |
| OSM roads + `population_served` from admin data | Geofabrik (see #7) |

---

## 9. Roadmap connectors (declared, stubbed in `backend/data_connectors.py`)

| id | Provider | Link |
| --- | --- | --- |
| `imd` | India Meteorological Department | https://mausam.imd.gov.in/ |
| `gpm-chirps` | NASA GPM IMERG / UCSB CHIRPS | https://gpm.nasa.gov/data/imerg · https://www.chc.ucsb.edu/data/chirps |
| `sentinel` | Copernicus Sentinel-1 (SAR) / Sentinel-2 (optical) | https://dataspace.copernicus.eu/ |
| `dem` | SRTM / Copernicus DEM | see #4 |
| `soil-moisture` | NASA SMAP / local sensors | https://smap.jpl.nasa.gov/data/ |

---

## 10. Output standard — alerts

| | |
| --- | --- |
| **Used in** | `backend/cap.py` |
| **Standard** | OASIS **Common Alerting Protocol (CAP) 1.2** — http://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.html |
| **India platform** | NDMA **SACHET** / CAP-India — https://sachet.ndma.gov.in/ |

---

## 11. Real alert dispatch — Telegram

| | |
| --- | --- |
| **Used in** | `backend/alert_dispatch.py` (`send_telegram_message`), fired from `backend/app.py` `_run_live_cycle` / `_dispatch_on_escalation` |
| **Provider** | Telegram Bot API |
| **Endpoint** | `https://api.telegram.org/bot<token>/sendMessage` |
| **Secrets** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — environment variables only, never in the repo. Setup: `TELEGRAM_SETUP.md` |
| **Licence / cost** | Free, no card. Bot created via `@BotFather` |
| **Trigger** | first upward crossing of a zone into High/Critical (de-duped via the `live_alert_state` table); also `POST /api/alerts/dispatch-test` |
| **Alt.** | `ALERT_WEBHOOK_URL` — generic JSON webhook (Slack / Discord / any endpoint) |

---

## Method references (not datasets)

- **Antecedent Precipitation Index** — Kohler & Linsley (1951); Glade, Crozier & Smith (2000), *Pure Appl. Geophys.* 157:1059-1079.
- **Rainfall Intensity–Duration threshold** — Caine, N. (1980), *Geografiska Annaler* 62A: 23-27. `I = 14.82·D^-0.39`.
- **Hazard = predisposition × trigger** — Mora, S. & Vahrson, W. (1994), *Bull. Assoc. Eng. Geol.* 31(1): 49-58.
- **Landslide susceptibility zonation practice (India)** — BIS IS 14496 (Part 2); GSI *Manual on Landslide Hazard Zonation*.
