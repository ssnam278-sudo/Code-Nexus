"""Deterministic, explainable baseline risk engine for Code Nexus zones.

The score is a transparent weighted sum:

    risk = Σ ( weightᵢ × inputᵢ )      inputᵢ normalised to 0–100,  Σ weightᵢ = 1.00

Every weight is a module constant (``WEIGHTS``) and every factor's normalised
input, weight and point contribution is returned in ``contributing_factors`` so
the dashboard can show exactly how the number was reached. ``confidence`` is
derived from real signals (feed freshness, internal agreement, input ranges),
not a fixed number.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


_REQUIRED_FIELDS = (
	"rainfall",
	"accumulated",
	"moisture",
	"slope",
	"susceptibility",
	"history",
	"exposure",
)

# Weights sum to 1.00. Exposed here (not underscore-private) so callers/tests and
# the /api responses can publish the exact table the score is built from.
WEIGHTS = {
	"Current rainfall": 0.16,
	"Accumulated rainfall": 0.12,
	"Soil moisture": 0.20,
	"Slope": 0.16,
	"Terrain susceptibility": 0.16,
	"Historical vulnerability": 0.12,
	"Exposure": 0.08,
}
_WEIGHTS = WEIGHTS  # backwards-compatible alias

FORMULA = "risk = Σ (weightᵢ × inputᵢ),  each inputᵢ normalised to 0–100,  Σ weights = 1.00"

# name -> (raw zone field, human unit) so the UI can show the real input value
# beside each normalised factor.
_FACTOR_INPUTS = {
	"Current rainfall": ("rainfall", "mm/hr"),
	"Accumulated rainfall": ("accumulated", "mm/24h"),
	"Soil moisture": ("moisture", "%"),
	"Slope": ("slope", "index"),
	"Terrain susceptibility": ("susceptibility", "index"),
	"Historical vulnerability": ("history", "index"),
	"Exposure": ("exposure", "index"),
}


def _number(data: Mapping[str, Any], field: str) -> float:
	value = data.get(field)
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise ValueError(f"{field} must be a finite number")
	if not isfinite(float(value)):
		raise ValueError(f"{field} must be a finite number")
	return float(value)


def _validate_zone(zone: Mapping[str, Any]) -> dict[str, float]:
	if not isinstance(zone, Mapping):
		raise ValueError("zone must be a mapping of environmental values")
	values = {field: _number(zone, field) for field in _REQUIRED_FIELDS}
	if values["rainfall"] < 0 or values["accumulated"] < 0:
		raise ValueError("rainfall values cannot be negative")
	for field in ("moisture", "slope", "susceptibility", "history", "exposure"):
		if not 0 <= values[field] <= 100:
			raise ValueError(f"{field} must be between 0 and 100")
	return values


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
	names = [factor["name"] for factor in ranked if factor["value"] >= 45][:3]
	if level == "Critical":
		return "Extreme rainfall and high soil saturation are combining with highly susceptible terrain, creating critical landslide conditions."
	if level == "High":
		primary = " and ".join(name.lower() for name in names[:2]) or "elevated environmental conditions"
		return f"Elevated {primary} are increasing risk on steep, susceptible terrain."
	if level == "Advisory":
		primary = " and ".join(name.lower() for name in names[:2]) or "several environmental factors"
		return f"Advisory conditions reflect increasing {primary}; continued monitoring is warranted."
	if names:
		return f"Environmental conditions remain relatively stable while {names[0].lower()} is monitored."
	return "Environmental conditions remain relatively stable and terrain susceptibility is moderate."


def derive_confidence(
	normalized: Mapping[str, float],
	meta: Mapping[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
	"""Model confidence (%) from real signals, with an itemised basis.

	Drivers:
	  * feed freshness   -- live Open-Meteo vs simulated inputs, and how old
	  * internal agreement -- do current rainfall, 24 h accumulation and soil
	    moisture tell the same story?
	  * input ranges     -- all seven inputs validated and within expected bounds
	Deterministic; returns (confidence, [{"factor", "effect"}...]).
	"""
	meta = meta or {}
	basis: list[dict[str, Any]] = []
	score = 72.0

	source = str(meta.get("data_source") or "simulated").lower()
	age = meta.get("feed_age_seconds")
	if source == "open-meteo" and isinstance(age, (int, float)):
		if age <= 5400:
			delta = 18
			label = f"live Open-Meteo feed, {round(age / 60)} min old"
		elif age <= 10800:
			delta = 9
			label = f"live Open-Meteo feed, {round(age / 3600, 1)} h old"
		else:
			delta = 2
			label = f"live feed is stale ({round(age / 3600)} h old)"
	elif source == "open-meteo":
		delta = 12
		label = "live Open-Meteo feed"
	else:
		delta = 0
		label = "simulated inputs (no live feed connected)"
	score += delta
	basis.append({"factor": label, "effect": delta})

	rain_n = float(normalized.get("Current rainfall", 0.0))
	acc_n = float(normalized.get("Accumulated rainfall", 0.0))
	soil_n = float(normalized.get("Soil moisture", 0.0))
	signals = (rain_n, acc_n, soil_n)
	if all(v >= 55 for v in signals) or all(v <= 35 for v in signals):
		score += 7
		basis.append({"factor": "current rainfall, 24 h accumulation and soil moisture agree", "effect": 7})
	elif rain_n >= 60 and acc_n <= 30 and soil_n <= 40:
		score -= 11
		basis.append({"factor": "rainfall spike not yet reflected in soil moisture / accumulation", "effect": -11})
	else:
		score += 2
		basis.append({"factor": "wetness signals only partially aligned", "effect": 2})

	score += 4
	basis.append({"factor": "all seven inputs present and within expected range", "effect": 4})

	return int(round(max(40.0, min(97.0, score)))), basis


def calculate_risk(
	zone: Mapping[str, Any],
	meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""Calculate a deterministic risk result from an existing Code Nexus zone.

	``meta`` (optional) carries provenance for the confidence model, e.g.
	``{"data_source": "open-meteo", "feed_age_seconds": 640}``.
	"""
	values = _validate_zone(zone)
	normalized = {
		"Current rainfall": min(100.0, values["rainfall"] / 60 * 100),
		"Accumulated rainfall": min(100.0, values["accumulated"] / 300 * 100),
		"Soil moisture": values["moisture"],
		"Slope": values["slope"],
		"Terrain susceptibility": values["susceptibility"],
		"Historical vulnerability": values["history"],
		"Exposure": values["exposure"],
	}
	factors = []
	for name, value in normalized.items():
		weight = _WEIGHTS[name]
		raw_field, unit = _FACTOR_INPUTS[name]
		factors.append(
			{
				"name": name,
				"value": round(value, 1),
				"weight": weight,
				"contribution": round(value * weight, 2),
				"impact": _impact(value),
				"input": round(values[raw_field], 1),
				"input_field": raw_field,
				"input_unit": unit,
			}
		)
	score = max(0, min(100, round(sum(factor["contribution"] for factor in factors))))
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
