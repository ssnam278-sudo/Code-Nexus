"""Real-time rainfall ingestion from Open-Meteo (free, keyless).

One request per zone returns 16 days of past hourly precipitation plus a 7-day
hourly forecast. Past hours are stored as ``observed``, future hours as
``forecast``; the hazard model uses the observed tail for the antecedent state
and the forecast for the projected trajectory / lead time.

Runs as a background thread under a long-lived server (Render), or one cycle at a
time via ``GET /api/tick`` for serverless / cron setups.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .live_store import LiveStore

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 16
FORECAST_DAYS = 7
USER_AGENT = "CodeNexus/1.0 (landslide early warning; contact ops@example.org)"


def _now_hour() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")


def fetch_hourly(latitude: float, longitude: float, *, timeout: float = 30.0) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ("precipitation,precipitation_probability,"
                   "soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm"),
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    })
    request = urllib.request.Request(f"{FORECAST_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    hourly = payload.get("hourly", {})
    times = list(hourly.get("time", []))
    precip = [float(x or 0.0) for x in hourly.get("precipitation", [])]
    if not times or len(times) != len(precip):
        raise RuntimeError("malformed Open-Meteo hourly response")

    prob = hourly.get("precipitation_probability", []) or [None] * len(times)
    sm_layers = [
        hourly.get("soil_moisture_0_to_1cm", []) or [],
        hourly.get("soil_moisture_1_to_3cm", []) or [],
        hourly.get("soil_moisture_3_to_9cm", []) or [],
    ]

    def _soil(i: int):
        vals = [layer[i] for layer in sm_layers if i < len(layer) and layer[i] is not None]
        return sum(vals) / len(vals) if vals else None

    cutoff = _now_hour()
    rows = []
    for i, (t, p) in enumerate(zip(times, precip)):
        rows.append({
            "ts_utc": t,
            "precip_mm": p,
            "kind": "observed" if t <= cutoff else "forecast",
            "soil_moist": _soil(i),
            "precip_prob": (float(prob[i]) if i < len(prob) and prob[i] is not None else None),
        })
    return {"rows": rows, "cutoff": cutoff, "provider": "Open-Meteo"}


def ingest_zone(store: LiveStore, zone: Mapping[str, Any]) -> int:
    lat, lon = zone["coordinates"]
    result = fetch_hourly(lat, lon)
    return store.upsert_hours(zone["id"], result["rows"])


def ingest_all(store: LiveStore, zones: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_hours = 0
    ok, errors = [], []
    for zone in zones:
        try:
            total_hours += ingest_zone(store, zone)
            ok.append(zone["id"])
        except (OSError, RuntimeError, ValueError, KeyError) as exc:  # keep going
            errors.append({"zone": zone.get("id"), "error": str(exc)})
    store.log_ingest(len(ok), total_hours, json.dumps(errors) if errors else "")
    return {"zones_ok": ok, "hours": total_hours, "errors": errors, "ran_at": store.now()}


_thread: threading.Thread | None = None


def start_scheduler(
    store: LiveStore,
    zones_provider: Callable[[], Sequence[Mapping[str, Any]]],
    *,
    interval_seconds: int = 900,
    on_cycle: Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    """Start the ingestion loop once per process. Returns True if it started."""
    global _thread
    if _thread and _thread.is_alive():
        return False

    def _loop() -> None:
        # small stagger so multiple gunicorn workers don't all fire at once
        time.sleep(2)
        while True:
            try:
                summary = ingest_all(store, zones_provider())
                if on_cycle:
                    on_cycle(summary)
            except Exception as exc:  # never let the loop die
                print(f"[live_ingest] cycle failed: {exc}", flush=True)
            time.sleep(max(60, interval_seconds))

    _thread = threading.Thread(target=_loop, name="live-ingest", daemon=True)
    _thread.start()
    return True
