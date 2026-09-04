"""Live hazard: run the rainfall model over the stored real rainfall series and
project it forward along the forecast to estimate lead time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .live_store import LiveStore
from .rainfall_model import antecedent_index, hazard, storm_exceedance

HORIZONS_H = (6, 24, 48, 72)
PERSIST_H = 3          # a projected crossing must hold this long to "count"
WARN_LEVELS = {"High", "Critical"}


def _now_hour_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")


def _daily_before(precip: Sequence[float], idx: int, days: int) -> list[float]:
    """`days` trailing 24 h buckets ending 24 h before hour `idx` (oldest first)."""
    buckets = [0.0] * days
    for offset in range(24, 24 + days * 24):
        j = idx - offset
        if j < 0:
            break
        buckets[(offset - 24) // 24] += precip[j]
    return list(reversed(buckets))


def zone_live_hazard(store: LiveStore, zone: Mapping[str, Any]) -> dict[str, Any]:
    rows = store.series(zone["id"])
    if not rows:
        return {"zone_id": zone["id"], "name": zone.get("name"), "status": "no_data"}

    times = [r["ts_utc"] for r in rows]
    precip = [float(r["precip_mm"]) for r in rows]
    soil = [r.get("soil_moist") for r in rows]
    prob = [r.get("precip_prob") for r in rows]
    n = len(rows)

    cutoff = _now_hour_iso()
    now_idx = max((i for i, t in enumerate(times) if t <= cutoff), default=n - 1)

    slope = float(zone["slope"]); susc = float(zone["susceptibility"]); hist = float(zone["history"])

    def _sm_frac(idx: int) -> float | None:
        v = soil[idx]
        return None if v is None else max(0.0, min(1.0, float(v) / 0.5))  # m3/m3 -> 0..1

    def at(idx: int) -> dict[str, Any]:
        api = antecedent_index(_daily_before(precip, idx, 15))
        exc = storm_exceedance(precip[: idx + 1])["ratio"]
        return hazard(slope=slope, susceptibility=susc, history=hist,
                      api_mm=api, exceedance_ratio=exc, soil_moisture_frac=_sm_frac(idx))

    now = at(now_idx)
    now.update({
        "rain_1h": round(precip[now_idx], 2),
        "rain_24h": round(sum(precip[max(0, now_idx - 23): now_idx + 1]), 1),
        "soil_moisture_m3m3": (round(soil[now_idx], 3) if soil[now_idx] is not None else None),
        "observed_through": times[now_idx],
    })

    lo = max(0, now_idx - 24)
    hi = min(n - 1, now_idx + max(HORIZONS_H))
    trajectory = []
    for idx in range(lo, hi + 1):
        h = at(idx)
        trajectory.append({
            "time": times[idx] + "Z",
            "risk_score": h["risk_score"],
            "risk_level": h["risk_level"],
            "kind": "observed" if idx <= now_idx else "forecast",
            # per-hour rainfall (mm) — same Open-Meteo series the risk uses;
            # the Situation Room rainfall-timeline animation reads this.
            "rain": round(precip[idx], 2),
        })

    future = [step for step in trajectory if step["kind"] == "forecast"]

    def first_sustained(levels: set[str]) -> int | None:
        for k in range(len(future)):
            if all(future[j]["risk_level"] in levels
                   for j in range(k, min(k + PERSIST_H, len(future)))):
                return k + 1  # hours ahead (future[0] is now+1h)
        return None

    lead_high = 0 if now["risk_level"] in WARN_LEVELS else first_sustained(WARN_LEVELS)
    lead_crit = 0 if now["risk_level"] == "Critical" else first_sustained({"Critical"})

    def _confidence(hours_ahead: int | None) -> int | None:
        """Mean forecast precipitation probability from now to the crossing hour."""
        if not hours_ahead:
            return None
        window = [prob[now_idx + k] for k in range(1, hours_ahead + 1)
                  if now_idx + k < n and prob[now_idx + k] is not None]
        return round(sum(window) / len(window)) if window else None

    peak = max(trajectory, key=lambda s: s["risk_score"]) if trajectory else None
    horizon = []
    for hrs in HORIZONS_H:
        window = [s for s in future[:hrs]]
        if window:
            top = max(window, key=lambda s: s["risk_score"])
            horizon.append({"h": hrs, "risk_score": top["risk_score"], "risk_level": top["risk_level"]})

    return {
        "zone_id": zone["id"],
        "name": zone.get("name"),
        "district": zone.get("district"),
        "coordinates": zone.get("coordinates"),
        "exposure": zone.get("exposure"),
        "now": now,
        "forecast": {
            "projected_peak_score": peak["risk_score"] if peak else now["risk_score"],
            "projected_peak_level": peak["risk_level"] if peak else now["risk_level"],
            "projected_peak_time": peak["time"] if peak else now["observed_through"] + "Z",
            "lead_time_to_high_h": lead_high,
            "lead_time_to_critical_h": lead_crit,
            "lead_confidence_pct": _confidence(lead_high or lead_crit),
            "horizon": horizon,
        },
        "trajectory": trajectory,
    }


def all_live_hazards(store: LiveStore, zones: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    results = []
    for zone in zones:
        try:
            results.append(zone_live_hazard(store, zone))
        except (KeyError, TypeError, ValueError) as exc:
            results.append({"zone_id": zone.get("id"), "status": "error", "error": str(exc)})

    ranked = sorted(
        results,
        key=lambda r: (
            r.get("forecast", {}).get("projected_peak_score", 0)
            if r.get("now") else -1
        ),
        reverse=True,
    )
    warnings = [
        r for r in ranked
        if r.get("now")
        and (r["now"]["risk_level"] in WARN_LEVELS
             or r["forecast"]["lead_time_to_high_h"] is not None)
    ]
    last = store.last_ingest()
    return {
        "generated_at": store.now(),
        "last_ingest": last,
        "zone_count": len(results),
        "warning_count": len(warnings),
        "any_forecast_warning": bool(warnings),
        "zones": ranked,
    }
