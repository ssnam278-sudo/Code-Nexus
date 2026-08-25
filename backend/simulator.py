"""Scenario input transformations for the standalone risk engine."""

from __future__ import annotations

from typing import Any, Mapping

try:
	from .risk_engine import calculate_risk
except ImportError:
	from risk_engine import calculate_risk


SCENARIO_BOOSTS = {
	"Normal": (0.0, 0.0),
	"Heavy Rain": (18.0, 9.0),
	"Extreme Rain": (42.0, 18.0),
	"Recovery": (-8.0, -6.0),
}


def simulate_zone(zone: Mapping[str, Any], scenario: str = "Normal") -> dict[str, Any]:
	"""Apply a scenario to zone inputs, then calculate its resulting risk."""
	if scenario not in SCENARIO_BOOSTS:
		raise ValueError(f"unknown scenario: {scenario}")
	rainfall_boost, moisture_boost = SCENARIO_BOOSTS[scenario]
	simulated = dict(zone)
	simulated["rainfall"] = max(0.0, float(zone["rainfall"]) + rainfall_boost)
	simulated["accumulated"] = max(0.0, float(zone["accumulated"]) + rainfall_boost * 1.7)
	simulated["moisture"] = max(0.0, min(100.0, float(zone["moisture"]) + moisture_boost))
	return {**simulated, **calculate_risk(simulated)}
