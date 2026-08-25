"""Deterministic, explainable baseline risk engine for BhuSanket zones."""

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

_WEIGHTS = {
	"Current rainfall": 0.16,
	"Accumulated rainfall": 0.12,
	"Soil moisture": 0.20,
	"Slope": 0.16,
	"Terrain susceptibility": 0.16,
	"Historical vulnerability": 0.12,
	"Exposure": 0.08,
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


def calculate_risk(zone: Mapping[str, Any]) -> dict[str, Any]:
	"""Calculate a deterministic risk result from an existing BhuSanket zone."""
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
	factors = [
		{
			"name": name,
			"value": round(value, 1),
			"weight": weight,
			"contribution": round(value * weight, 2),
			"impact": _impact(value),
		}
		for name, value in normalized.items()
		for weight in [_WEIGHTS[name]]
	]
	score = max(0, min(100, round(sum(factor["contribution"] for factor in factors))))
	confidence = 95
	risk_level = _level(score)
	return {
		"risk_score": score,
		"risk_level": risk_level,
		"confidence": confidence,
		"explanation": _explanation(risk_level, factors),
		"contributing_factors": factors,
	}
