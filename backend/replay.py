"""Historical event replay: feed real past rainfall through the hazard model and
measure how many hours of warning it would have produced.

Rainfall is ERA5 reanalysis from the Open-Meteo archive API (no key required).
Responses are cached under ``backend/data/replay_cache`` so the demo and the test
suite run fully offline once the cache is populated (``python -m backend.replay
--refresh``).

ERA5 is a ~25 km reanalysis and under-catches convective monsoon peaks in steep
terrain, so absolute intensities are conservative; the point of the replay is the
*relative* trajectory and the lead time it buys, not a hindcast of the exact mm.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .rainfall_model import antecedent_index, hazard, storm_exceedance

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_DIR = Path(__file__).resolve().parent / "data" / "replay_cache"
WARNING_LEVELS = {"High", "Critical"}
MIN_PERSIST_H = 6   # a crossing only "counts" once it holds this many hours (kills transient spikes)


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    description: str
    latitude: float
    longitude: float
    failure_utc: str | None          # ISO8601 'Z'; None for a no-failure control
    lookback_days: int
    slope: float
    susceptibility: float
    history: float
    source: str
    window_end_utc: str | None = None  # anchor for controls (failure_utc is None)
    static: dict = field(default_factory=dict)


EVENTS: dict[str, Event] = {
    "meghalaya-2022": Event(
        id="meghalaya-2022",
        name="East Khasi Hills (Sohra), Meghalaya",
        description=(
            "Record-breaking rainfall 14-17 Jun 2022 (Cherrapunji ~ its wettest June "
            "in a century) triggered widespread landslides across Meghalaya; dozens "
            "killed, road and rail links to the Barak Valley severed."
        ),
        latitude=25.28, longitude=91.73,
        failure_utc="2022-06-17T00:00:00Z",
        lookback_days=22,
        slope=70, susceptibility=78, history=64,
        source="IMD rainfall bulletins + Meghalaya SDMA, Jun 2022",
    ),
    "sikkim-nh10-2023": Event(
        id="sikkim-nh10-2023",
        name="NH-10 corridor (Rangpo-Singtam), Sikkim",
        description=(
            "A sustained wet spell in mid-Jun 2023 reactivated slides along NH-10, the "
            "lifeline road to Gangtok, closing it to traffic for several days."
        ),
        latitude=27.17, longitude=88.53,
        failure_utc="2023-06-19T06:00:00Z",
        lookback_days=20,
        # NH-10 through the Teesta gorge is among India's most chronically
        # failure-prone road sections -- very steep cut slopes, sheared phyllite,
        # a decades-long slide record.
        slope=74, susceptibility=88, history=84,
        source="Sikkim SDMA / BRO situation notes, Jun 2023",
    ),
    "arunachal-itanagar-2022": Event(
        id="arunachal-itanagar-2022",
        name="Itanagar - Naharlagun, Arunachal Pradesh",
        description=(
            "Prolonged monsoon rain over 14-17 Jun 2022 saturated the hill slopes "
            "around the Arunachal capital; multiple landslides killed several "
            "people, blocked NH-415 and the Hollongi road, and damaged homes "
            "across Itanagar and Naharlagun."
        ),
        latitude=27.10, longitude=93.62,
        failure_utc="2022-06-17T00:00:00Z",
        lookback_days=22,
        # steep, heavily built-up cut slopes on weathered gneiss/schist around
        # the capital; a recurring monsoon landslide record on the town roads.
        slope=64, susceptibility=74, history=55,
        source="Arunachal SDMA / district reports + IMD, Jun 2022",
    ),
    "control-meghalaya-2019": Event(
        id="control-meghalaya-2019",
        name="Sohra - ordinary monsoon week (control)",
        description=(
            "The same slope during a routine wet spell in Jun 2019 with no reported "
            "failure. Checks that the model does not cry wolf on ordinary monsoon rain."
        ),
        latitude=25.28, longitude=91.73,
        failure_utc=None,
        window_end_utc="2019-06-24T00:00:00Z",
        lookback_days=18,
        slope=70, susceptibility=78, history=64,
        source="Control window; no landslide on record",
    ),
}


def _window(event: Event) -> tuple[str, str]:
    anchor = event.failure_utc or event.window_end_utc
    if not anchor:
        raise ValueError(f"{event.id}: needs failure_utc or window_end_utc")
    end = datetime.fromisoformat(anchor.replace("Z", "+00:00")) + timedelta(days=1)
    start = end - timedelta(days=event.lookback_days + 1)
    return start.date().isoformat(), end.date().isoformat()


def _cache_file(event: Event) -> Path:
    return CACHE_DIR / f"{event.id}.json"


def fetch_series(event: Event, *, refresh: bool = False) -> dict[str, list]:
    """Return {'time': [...ISO hourly...], 'precipitation': [mm...]} for the event."""
    cache = _cache_file(event)
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    start, end = _window(event)
    query = urllib.parse.urlencode({
        "latitude": event.latitude,
        "longitude": event.longitude,
        "start_date": start,
        "end_date": end,
        "hourly": "precipitation",
        "timezone": "UTC",
    })
    with urllib.request.urlopen(f"{ARCHIVE_URL}?{query}", timeout=60) as resp:
        payload = json.load(resp)
    hourly = payload.get("hourly", {})
    series = {
        "time": list(hourly.get("time", [])),
        "precipitation": [float(x or 0.0) for x in hourly.get("precipitation", [])],
        "source": "Open-Meteo ERA5 archive",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not series["time"]:
        raise RuntimeError(f"empty rainfall series for {event.id}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(series), encoding="utf-8")
    return series


def _daily_totals_before(times: list[str], rain: list[float], upto: int, days: int) -> list[float]:
    """`days` trailing 24 h buckets ending 24 h before hour `upto` (the antecedent
    period), oldest first."""
    buckets = [0.0] * days
    for offset in range(24, 24 + days * 24):
        idx = upto - offset
        if idx < 0:
            break
        bucket = (offset - 24) // 24
        buckets[bucket] += rain[idx]
    return list(reversed(buckets))


def run_replay(event_id: str, *, refresh: bool = False, warmup_h: int = 24 * 6) -> dict[str, Any]:
    if event_id not in EVENTS:
        raise KeyError(event_id)
    event = EVENTS[event_id]
    series = fetch_series(event, refresh=refresh)
    times, rain = series["time"], series["precipitation"]
    n = len(times)

    steps: list[dict[str, Any]] = []
    for i in range(warmup_h, n):
        api = antecedent_index(_daily_totals_before(times, rain, i, 15))
        exc = storm_exceedance(rain[: i + 1])
        h = hazard(
            slope=event.slope, susceptibility=event.susceptibility, history=event.history,
            api_mm=api, exceedance_ratio=exc["ratio"],
        )
        steps.append({
            "time": times[i] + "Z" if not times[i].endswith("Z") else times[i],
            "risk_score": h["risk_score"],
            "risk_level": h["risk_level"],
            "api_mm": h["api_mm"],
            "exceedance_ratio": h["exceedance_ratio"],
            "storm_duration_h": exc["duration_h"],
            "rain_1h": round(rain[i], 2),
            "rain_24h": round(sum(rain[max(0, i - 23): i + 1]), 1),
        })

    failure_idx = None
    if event.failure_utc:
        target = datetime.fromisoformat(event.failure_utc.replace("Z", "+00:00"))
        failure_idx = min(
            range(len(steps)),
            key=lambda k: abs(
                datetime.fromisoformat(steps[k]["time"].replace("Z", "+00:00")) - target
            ),
        )

    def first_cross(levels: set[str]) -> int | None:
        """First step that enters ``levels`` and *stays* there >= MIN_PERSIST_H hours,
        so a lone spike that immediately relaxes does not count as the warning."""
        limit = failure_idx if failure_idx is not None else len(steps) - 1
        for k in range(limit + 1):
            if all(steps[j]["risk_level"] in levels
                   for j in range(k, min(k + MIN_PERSIST_H, len(steps)))):
                return k
        return None

    warn_idx = first_cross(WARNING_LEVELS)
    crit_idx = first_cross({"Critical"})

    def lead(idx: int | None) -> float | None:
        if idx is None or failure_idx is None:
            return None
        return round(failure_idx - idx, 1)   # 1 step == 1 hour

    return {
        "event": {
            "id": event.id, "name": event.name, "description": event.description,
            "failure_utc": event.failure_utc, "latitude": event.latitude,
            "longitude": event.longitude, "source": event.source,
            "terrain": {"slope": event.slope, "susceptibility": event.susceptibility,
                        "history": event.history},
        },
        "rainfall_source": series.get("source", "Open-Meteo ERA5 archive"),
        "steps": steps,
        "failure_index": failure_idx,
        "warning_index": warn_idx,
        "critical_index": crit_idx,
        "lead_time_hours": lead(warn_idx),
        "critical_lead_time_hours": lead(crit_idx),
        "peak_score": max((s["risk_score"] for s in steps), default=0),
        "fired": warn_idx is not None,
    }


def summary_line(result: dict[str, Any]) -> str:
    ev = result["event"]
    if result["lead_time_hours"] is not None:
        verdict = (
            f"warning at High {result['lead_time_hours']:.0f} h before failure"
            + (f", Critical {result['critical_lead_time_hours']:.0f} h before"
               if result["critical_lead_time_hours"] is not None else "")
        )
    elif ev["failure_utc"]:
        verdict = "NO warning issued before failure"
    else:
        verdict = f"stayed calm (peak score {result['peak_score']}) - no false alarm"
    return f"{ev['name']}: {verdict}"


def _main() -> None:
    parser = argparse.ArgumentParser(description="Replay a historical rainfall event.")
    parser.add_argument("event", nargs="?", choices=sorted(EVENTS), help="event id (default: all)")
    parser.add_argument("--refresh", action="store_true", help="re-fetch rainfall from Open-Meteo")
    args = parser.parse_args()
    ids = [args.event] if args.event else sorted(EVENTS)
    for eid in ids:
        result = run_replay(eid, refresh=args.refresh)
        print(summary_line(result))
        if result["warning_index"] is not None:
            w = result["steps"][result["warning_index"]]
            print(f"    first warning {w['time']}  score={w['risk_score']} "
                  f"API={w['api_mm']}mm  ID-exceedance={w['exceedance_ratio']}")


if __name__ == "__main__":
    _main()
