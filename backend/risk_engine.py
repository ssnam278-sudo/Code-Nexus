"""Single source of truth for a zone's landslide risk score.

Four factors, one transparent weighted sum:

    risk = 0.35·rainfall_pressure
         + 0.25·soil_saturation
         + 0.25·terrain_susceptibility
         + 0.15·historical_susceptibility

Every term is normalised to 0–100, so ``risk`` is 0–100 with bands
35 / 55 / 75 = Advisory / High / Critical.

`calculate_risk` here is the ONLY risk formula in the product. The Situation
Room, Zone Intelligence, Alerts and Live Forecast pages all display the value it
produces (served via `/api/zones` and `/api/risk`); the offline browser build
uses a byte-for-byte JS port of the same math. `backend/rainfall_model.py` is a
*separate* physical model kept only for the Event Replay validation and the
forward trajectory / lead-time on the Live Forecast page — never for the
"current risk" number.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


# rainfall_pressure needs current intensity + 24 h accumulation; the rest are
# already 0–100 indices on the zone record.
_REQUIRED_FIELDS = (
	"rainfall",
	"accumulated",
	"moisture",
	"slope",
	"susceptibility",
	"history",
)

# Weights sum to 1.00. Public (not underscore-private) so /api responses, tests
# and the UI can publish the exact table the score is built from.
WEIGHTS = {
	"Rainfall pressure": 0.35,
	"Soil saturation": 0.25,
	"Terrain susceptibility": 0.25,
	"Historical susceptibility": 0.15,
}
_WEIGHTS = WEIGHTS  # backwards-compatible alias

# Top-of-scale references for the rainfall term (see MODEL_CARD.md).
RAINFALL_INTENSITY_REF_MM_H = 50.0     # a torrential single hour
RAINFALL_ACCUM_REF_MM_24H = 200.0      # ~ IMD "extremely heavy" day

FORMULA = (
	"risk = 0.35·rainfall_pressure + 0.25·soil_saturation "
	"+ 0.25·terrain_susceptibility + 0.15·historical_susceptibility  "
	"(each term normalised to 0–100)"
)

# factor name -> (primary raw zone field, unit label) for the UI breakdown
_FACTOR_INPUTS = {
	"Rainfall pressure": ("rainfall", "mm/hr + 24h accum"),
	"Soil saturation": ("moisture", "%"),
	"Terrain susceptibility": ("slope", "slope+suscept index"),
	"Historical susceptibility": ("history", "index"),
}


def _number(data: Mapping[str, Any], field: str) -> float:
	value = data.get(field)
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise ValueError(f"{field} must be a finite number")
	if not isfinite(float(value)):
		raise ValueError(f"{field} must be a finite number")
	return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
	return max(low, min(high, value))


def _validate_zone(zone: Mapping[str, Any]) -> dict[str, float]:
	if not isinstance(zone, Mapping):
		raise ValueError("zone must be a mapping of environmental values")
	values = {field: _number(zone, field) for field in _REQUIRED_FIELDS}
	if values["rainfall"] < 0 or values["accumulated"] < 0:
		raise ValueError("rainfall values cannot be negative")
	for field in ("moisture", "slope", "susceptibility", "history"):
		if not 0 <= values[field] <= 100:
			raise ValueError(f"{field} must be between 0 and 100")
	return values


def normalised_factors(values: Mapping[str, float]) -> dict[str, float]:
	"""The four factor inputs, each mapped to 0–100."""
	rainfall_pressure = 100.0 * _clamp(
		0.6 * (values["rainfall"] / RAINFALL_INTENSITY_REF_MM_H)
		+ 0.4 * (values["accumulated"] / RAINFALL_ACCUM_REF_MM_24H),
		0.0,
		1.0,
	)
	terrain = 0.5 * values["slope"] + 0.5 * values["susceptibility"]
	return {
		"Rainfall pressure": round(rainfall_pressure, 1),
		"Soil saturation": round(_clamp(values["moisture"]), 1),
		"Terrain susceptibility": round(_clamp(terrain), 1),
		"Historical susceptibility": round(_clamp(values["history"]), 1),
	}


def _level(score: int) -> str:
	if score >= 75:
		return "Critical"
	if score >= 55:
		return "High"
	if score >= 35:
		return "Advisory"
	return "Monitoring"


def _impact(value: float) -> str:
	if value >= 70:
		return "high"
	if value >= 35:
		return "moderate"
	return "low"


def _explanation(level: str, factors: list[dict[str, Any]]) -> str:
	ranked = sorted(factors, key=lambda factor: factor["contribution"], reverse=True)
	names = [factor["name"].lower() for factor in ranked if factor["value"] >= 45][:2]
	if level == "Critical":
		return "Extreme rainfall and near-saturated soil are combining with highly susceptible terrain, creating critical landslide conditions."
	if level == "High":
		primary = " and ".join(names) or "elevated environmental conditions"
		return f"Elevated {primary} are raising risk on steep, susceptible terrain."
	if level == "Advisory":
		primary = " and ".join(names) or "several factors"
		return f"Advisory conditions reflect increasing {primary}; continued monitoring is warranted."
	if names:
		return f"Conditions remain below the high-risk threshold while {names[0]} is monitored."
	return "Conditions remain below the high-risk threshold; terrain susceptibility is moderate."


def derive_confidence(
	normalized: Mapping[str, float],
	meta: Mapping[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
	"""Model confidence (%) from real signals, with an itemised basis.

	Drivers: rainfall-feed freshness, soil-moisture source, agreement between the
	rainfall and soil signals, and input ranges. Deterministic. Base 72, clamped
	to 40–97.
	"""
	meta = meta or {}
	basis: list[dict[str, Any]] = []
	score = 72.0

	rain_source = str(meta.get("data_source") or "simulated").lower()
	age = meta.get("feed_age_seconds")
	if rain_source == "open-meteo" and isinstance(age, (int, float)):
		if age <= 5400:
			delta, label = 14, f"live Open-Meteo rainfall, {round(age / 60)} min old"
		elif age <= 10800:
			delta, label = 7, f"live Open-Meteo rainfall, {round(age / 3600, 1)} h old"
		else:
			delta, label = 2, f"Open-Meteo rainfall feed is stale ({round(age / 3600)} h)"
	elif rain_source == "open-meteo":
		delta, label = 10, "live Open-Meteo rainfall"
	else:
		delta, label = 0, "simulated rainfall (no live feed)"
	score += delta
	basis.append({"factor": label, "effect": delta})

	soil_source = str(meta.get("soil_data_source") or meta.get("soil_source") or "simulated").lower()
	if soil_source == "nasa-power":
		score += 6
		basis.append({"factor": "soil moisture from NASA POWER", "effect": 6})
	elif soil_source == "open-meteo":
		score += 4
		basis.append({"factor": "soil moisture from Open-Meteo", "effect": 4})
	else:
		score -= 6
		basis.append({"factor": "soil moisture simulated", "effect": -6})

	rain_n = float(normalized.get("Rainfall pressure", 0.0))
	soil_n = float(normalized.get("Soil saturation", 0.0))
	if (rain_n >= 55 and soil_n >= 55) or (rain_n <= 35 and soil_n <= 35):
		score += 7
		basis.append({"factor": "rainfall pressure and soil saturation agree", "effect": 7})
	elif rain_n >= 60 and soil_n <= 40:
		score -= 11
		basis.append({"factor": "heavy rain not yet reflected in soil moisture", "effect": -11})
	else:
		score += 2
		basis.append({"factor": "rain / soil signals partially aligned", "effect": 2})

	score += 4
	basis.append({"factor": "all inputs present and within expected range", "effect": 4})

	return int(round(_clamp(score, 40.0, 97.0))), basis


def calculate_risk(
	zone: Mapping[str, Any],
	meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""The single risk formula. ``meta`` carries feed provenance for the
	confidence model, e.g. ``{"data_source": "open-meteo", "feed_age_seconds":
	640, "soil_data_source": "nasa-power"}``.
	"""
	values = _validate_zone(zone)
	normalized = normalised_factors(values)

	factors = []
	for name, factor_value in normalized.items():
		weight = _WEIGHTS[name]
		raw_field, unit = _FACTOR_INPUTS[name]
		factor = {
			"name": name,
			"value": factor_value,
			"weight": weight,
			"contribution": round(factor_value * weight, 2),
			"impact": _impact(factor_value),
			"input": round(values[raw_field], 1),
			"input_field": raw_field,
			"input_unit": unit,
		}
		if name == "Rainfall pressure":
			factor["input_detail"] = (
				f"{round(values['rainfall'], 1)} mm/hr now, "
				f"{round(values['accumulated'], 0):.0f} mm/24h"
			)
		elif name == "Terrain susceptibility":
			factor["input_detail"] = (
				f"slope {round(values['slope'], 0):.0f}, susceptibility {round(values['susceptibility'], 0):.0f}"
			)
		factors.append(factor)

	score = int(_clamp(round(sum(factor["contribution"] for factor in factors))))
	risk_level = _level(score)
	confidence, confidence_basis = derive_confidence(normalized, meta)
	return {
		"risk_score": score,
		"risk_level": risk_level,
		"confidence": confidence,
		"confidence_basis": confidence_basis,
		"explanation": _explanation(risk_level, factors),
		"contributing_factors": factors,
		"formula": FORMULA,
		"weights": dict(_WEIGHTS),
	}
