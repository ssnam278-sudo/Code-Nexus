"""Rainfall-triggered landslide hazard model for Code Nexus.

This module replaces the flat weighted-sum heuristic with a physically motivated,
citable structure:

1. Antecedent Precipitation Index (API) -- a decayed running sum of prior daily
   rainfall that represents how wet (and therefore how primed) the slope already
   is.  API_t = k * API_(t-1) + P_t  (Kohler & Linsley, 1951; widely used in
   landslide early warning, e.g. Glade et al., 2000).

2. Rainfall Intensity-Duration (ID) threshold -- the classic empirical trigger
   line.  We use the global reference curve of Caine (1980):
       I_crit(D) = 14.82 * D**-0.39     (I in mm/h, D in h, 0.17 h <= D <= 500 h)
   The storm's mean intensity is compared against this line over several trailing
   windows; the largest exceedance ratio is the acute trigger signal.
   NOTE: Caine's line is global.  A regional line calibrated on a Northeast-India
   landslide inventory (GSI / NASA Global Landslide Catalog) should replace the
   two constants below before operational use -- they are isolated here for that
   reason.

3. Composition -- following the Mora & Vahrson (1994) idea that hazard is a
   *predisposition* (static terrain) modulated by a *trigger* (rainfall):
       hazard = 100 * predisposition**0.7 * (BASELINE + (1-BASELINE)*trigger)

All tunables are module constants with a comment on where the number comes from.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

# --- 1. Antecedent Precipitation Index -------------------------------------------------
API_DECAY_K = 0.88          # daily recession; 0.85-0.92 typical for monsoon soils
API_REFERENCE_MM = 130.0    # API value treated as "fully saturated" (-> wetness 1.0)

# --- 2. Intensity-Duration threshold (Caine 1980, global) ----------------------------
ID_COEFFICIENT = 14.82      # replace with regional calibration
ID_EXPONENT = -0.39
ID_DURATIONS_H = (3, 6, 12, 24, 48, 72)   # trailing windows scored for a "storm"

# --- 3. Composition ------------------------------------------------------------------
PREDISPOSITION_WEIGHTS = {"slope": 0.40, "susceptibility": 0.35, "history": 0.25}
PREDISPOSITION_EXPONENT = 0.60
TRIGGER_BASELINE = 0.18     # a very unstable slope still reads 18% of its ceiling dry
TRIGGER_MIX = {"wetness": 0.50, "acute": 0.50}
ACUTE_SATURATION = 1.3      # exceedance ratio at which the acute term maxes out
ACUTE_DRY_FLOOR = 0.30      # weight of the intensity term when the ground is bone dry

LEVELS = ((75, "Critical"), (55, "High"), (35, "Advisory"), (0, "Monitoring"))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def antecedent_index(daily_rainfall_mm: Sequence[float], decay_k: float = API_DECAY_K) -> float:
    """API for the day *after* the supplied series (oldest day first)."""
    api = 0.0
    for day in daily_rainfall_mm:
        if day < 0:
            raise ValueError("daily rainfall cannot be negative")
        api = decay_k * api + float(day)
    return round(api, 2)


def wetness_index(api_mm: float) -> float:
    """API in mm -> 0..1 saturation fraction (exponential approach to 1)."""
    return round(_clamp(1.0 - math.exp(-max(0.0, api_mm) / API_REFERENCE_MM)), 4)


def id_critical_intensity(duration_h: float) -> float:
    """Caine (1980) critical mean intensity (mm/h) for a storm of the given duration."""
    if duration_h <= 0:
        raise ValueError("duration must be positive")
    return ID_COEFFICIENT * duration_h ** ID_EXPONENT


def storm_exceedance(hourly_rainfall_mm: Sequence[float], durations_h: Iterable[int] = ID_DURATIONS_H) -> dict:
    """Largest (mean-intensity / Caine-threshold) ratio across trailing windows.

    ``hourly_rainfall_mm`` is ordered oldest -> newest; the most recent hour is
    the "now" the storm is evaluated at.
    """
    series = [max(0.0, float(x)) for x in hourly_rainfall_mm]
    best = {"ratio": 0.0, "duration_h": 0, "intensity_mm_h": 0.0, "critical_mm_h": 0.0}
    for d in durations_h:
        window = series[-d:]
        if len(window) < d:
            continue
        intensity = sum(window) / d
        critical = id_critical_intensity(d)
        ratio = intensity / critical if critical else 0.0
        if ratio > best["ratio"]:
            best = {
                "ratio": round(ratio, 3),
                "duration_h": d,
                "intensity_mm_h": round(intensity, 2),
                "critical_mm_h": round(critical, 2),
            }
    return best


def trigger_index(api_mm: float, exceedance_ratio: float) -> float:
    """Combine chronic wetness and the acute storm signal into 0..1.

    The acute (intensity) term is *gated* by wetness: an intense burst on dry,
    unsaturated ground is far less likely to mobilise a slope than the same burst
    after days of rain, so its weight scales from ACUTE_DRY_FLOOR (dry) up to full
    (saturated).  This is what stops the model crying wolf on isolated cloudbursts.
    """
    wet = wetness_index(api_mm)
    acute = _clamp(exceedance_ratio / ACUTE_SATURATION)
    acute_gated = acute * (ACUTE_DRY_FLOOR + (1.0 - ACUTE_DRY_FLOOR) * wet)
    return round(_clamp(TRIGGER_MIX["wetness"] * wet + TRIGGER_MIX["acute"] * acute_gated), 4)


def predisposition_index(slope: float, susceptibility: float, history: float) -> float:
    """Static terrain instability, 0..1, from the existing 0-100 zone fields."""
    for name, value in (("slope", slope), ("susceptibility", susceptibility), ("history", history)):
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
    w = PREDISPOSITION_WEIGHTS
    return round(
        (w["slope"] * slope + w["susceptibility"] * susceptibility + w["history"] * history) / 100.0,
        4,
    )


def classify(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "Monitoring"


def hazard(
    *,
    slope: float,
    susceptibility: float,
    history: float,
    api_mm: float,
    exceedance_ratio: float,
) -> dict:
    """Full rainfall-triggered hazard result for one point in time."""
    predisp = predisposition_index(slope, susceptibility, history)
    trig = trigger_index(api_mm, exceedance_ratio)
    score = 100.0 * (predisp ** PREDISPOSITION_EXPONENT) * (
        TRIGGER_BASELINE + (1.0 - TRIGGER_BASELINE) * trig
    )
    score = int(round(_clamp(score, 0.0, 100.0)))
    return {
        "risk_score": score,
        "risk_level": classify(score),
        "predisposition": predisp,
        "trigger_index": trig,
        "wetness_index": wetness_index(api_mm),
        "api_mm": round(api_mm, 1),
        "exceedance_ratio": round(exceedance_ratio, 3),
        "method": "API + Caine(1980) ID threshold, Mora-Vahrson composition",
    }
