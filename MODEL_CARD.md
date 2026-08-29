# Model card — Code Nexus rainfall-triggered landslide hazard

## Summary

Code Nexus estimates **rainfall-triggered landslide hazard** for a monitored
slope as a bounded 0–100 score with four operational levels
(Monitoring / Advisory / High / Critical). It is an **explainable, physically
motivated heuristic**, not a machine-learned classifier — every term is a named
quantity with a citation.

### The score — one formula, everywhere

`backend/risk_engine.py` `calculate_risk()` is the **single** risk formula in
the product. The Situation Room, Zone Intelligence, Alerts and Live Forecast
pages all display the value it returns (served bundled in `/api/zones`); the
offline browser build (`frontend/js/app.js` `CodeNexusRisk`) is a line-for-line
port, so it produces the same number.

```
risk = 0.35·rainfall_pressure
     + 0.25·soil_saturation
     + 0.25·terrain_susceptibility
     + 0.15·historical_susceptibility          Σ weights = 1.00
```

Each term is normalised to 0–100; `risk` is 0–100 with bands **35 / 55 / 75**
= Advisory / High / Critical.

| Term | Inputs → xᵢ (0–100) |
| --- | --- |
| `rainfall_pressure` | `100 · clamp(0.6·(mm_hr / 50) + 0.4·(accum_24h / 200), 0..1)` |
| `soil_saturation` | soil moisture %, as-is |
| `terrain_susceptibility` | `0.5·slope + 0.5·susceptibility` |
| `historical_susceptibility` | `history` index, as-is |

`50 mm/hr` (torrential single hour) and `200 mm/24h` (≈ IMD "extremely heavy"
day) are the top-of-scale references. **Exposure is not in the hazard score** —
it belongs to consequence, and is used only in the response-priority ranking
(`priority = 0.65·risk + 0.35·exposure`).

`backend/rainfall_model.py` (Antecedent Precip Index + Caine ID + Mora-Vahrson)
is a **separate** physical model, used only for the Event Replay validation and
the forward trajectory / lead-time on the Live Forecast page — never for the
current-risk number.

### Confidence

`confidence` is **not** a fixed number. `risk_engine.derive_confidence()`
computes it from real signals and returns an itemised `confidence_basis`:

| Driver | Effect |
| --- | --- |
| Live Open-Meteo rainfall, fresh (< 90 min) | +14 |
| Live rainfall, 1.5–3 h old / > 3 h old | +7 / +2 |
| Simulated rainfall (no live feed) | +0 |
| Soil moisture from NASA POWER / Open-Meteo / simulated | +6 / +4 / −6 |
| Rainfall pressure and soil saturation agree | +7 |
| Heavy rain not yet reflected in soil moisture | −11 |
| All inputs present and in range | +4 |
| Corroborating field report (added in `apply_ground_truth`) | +6…+12 |

Base 72, clamped to 40–97.

## Inputs

| Input | Source now | Source in production |
| --- | --- | --- |
| Rainfall (now + 24 h accumulation) | **LIVE** — Open-Meteo forecast API, keyless | IMD AWS, GPM-IMERG, local tipping-bucket gauges |
| Soil moisture | **LIVE** — NASA POWER `GWETTOP` (daily, ~2–5 day lag), Open-Meteo 0–7 cm as cross-check | NASA SMAP L3/L4, in-situ probes |
| Slope | Prepared — SRTM DEM-derived per zone (`zone_profile_cache`) | SRTM / Cartosat DEM, per pixel |
| Terrain susceptibility | Prepared — GSI-style susceptibility baseline per zone | GSI Landslide Susceptibility Zonation |
| Historical vulnerability | Per-zone constant (0–100) | GSI landslide inventory, NASA Global Landslide Catalog |

## Method

1. **Antecedent Precipitation Index** `API_t = k·API_{t-1} + P_t`
   (k = 0.88 daily recession). Maps to a 0–1 *wetness* via
   `1 − exp(−API / 130 mm)`. — Kohler & Linsley 1951; Glade et al. 2000.
2. **Intensity–Duration threshold** — Caine (1980) global line
   `I_crit = 14.82·D^−0.39` (mm/h, h). The storm's mean intensity over
   trailing 3/6/12/24/48/72 h windows is compared to the line; the largest
   exceedance ratio is the acute signal.
3. **Trigger index** — wetness and the *wetness-gated* acute term combined 50/50.
   An intense burst on dry ground is down-weighted (floor 0.30) so isolated
   cloudbursts do not raise a full alert.
4. **Composition** — Mora & Vahrson (1994) style:
   `hazard = 100 · predisposition^0.6 · (0.18 + 0.82·trigger)`, where
   `predisposition = 0.40·slope + 0.35·susceptibility + 0.25·history` (0–1).

## Calibration & validation (prototype)

Constants were hand-tuned against a **3-case mini-inventory** with real ERA5
rainfall (`python -m backend.replay`):

| Case | Real outcome | Model |
| --- | --- | --- |
| East Khasi Hills, Meghalaya — 14–17 Jun 2022 | Fatal landslides, road/rail cut | **High 63 h** before, **Critical 26 h** before |
| NH-10 Rangpo–Singtam, Sikkim — 19 Jun 2023 | NH-10 closed for days | **High 60 h** before |
| Sohra, Jun 2019 — ordinary wet week (control) | No failure | Peak "Advisory"; **no alert** |

This is a **sanity check, not a validation**. Before operational use the ID
constants and weights must be fitted on the full GSI / NASA landslide inventory
for the Northeastern Region and evaluated on held-out events with ROC / PR and a
Brier score, per district.

## Limitations

- **ERA5 under-catches convective peaks** in steep terrain (~25 km grid); replay
  intensities are conservative. Absolute mm are not a hindcast — the *trajectory*
  and *lead time* are the signal.
- Slope / susceptibility / history are per-zone constants in the prototype, not
  per-pixel DEM/GSI layers.
- No earthquake trigger, no snowmelt, no anthropogenic cut-slope / drainage
  factors, no run-out modelling.
- Thresholds are life-safety decisions; the system **surfaces** hazard for a
  human duty officer and must never auto-issue a public alert unattended.

## Ethical / operational notes

- CAP output (`backend/cap.py`) is emitted with `status = Exercise` and is
  unsigned. A registered SACHET sender id, XML signature, and an authorised
  issuing officer are required before any message reaches the public.
- False negatives (missed events) and false positives (evacuation fatigue) both
  cost lives; the four-level design exists so response can be graduated.
