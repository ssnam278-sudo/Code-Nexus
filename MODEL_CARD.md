# Model card — Code Nexus rainfall-triggered landslide hazard

## Summary

Code Nexus estimates **rainfall-triggered landslide hazard** for a monitored
slope as a bounded 0–100 score with four operational levels
(Monitoring / Advisory / High / Critical). It is an **explainable, physically
motivated heuristic**, not a machine-learned classifier — every term is a named
quantity with a citation.

`backend/rainfall_model.py` is the model. `backend/risk_engine.py` keeps the
older flat weighted-sum as a labelled baseline for comparison.

## Inputs

| Input | Source in prototype | Source in production |
| --- | --- | --- |
| Hourly rainfall (now + antecedent) | Open-Meteo forecast / ERA5 archive | IMD AWS, GPM-IMERG, local tipping-bucket gauges |
| Slope | Per-zone constant (0–100) | SRTM / Cartosat DEM, per pixel |
| Terrain susceptibility | Per-zone constant (0–100) | GSI Landslide Susceptibility Zonation |
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
