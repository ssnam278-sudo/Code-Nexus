"""Alert state and response-priority rules for BhuSanket."""

from __future__ import annotations

from typing import Any, Mapping


ALERT_STATES = ("Monitoring", "Advisory", "High", "Critical")


def alert_state(risk_score: int) -> str:
	"""Map a risk score to the operator-facing alert state."""
	if risk_score >= 75:
		return "Critical"
	if risk_score >= 55:
		return "High"
	if risk_score >= 35:
		return "Advisory"
	return "Monitoring"


def recommended_action(state: str) -> str:
	"""Return the least disruptive action appropriate for an alert state."""
	actions = {
		"Monitoring": "Continue monitoring",
		"Advisory": "Review conditions and prepare field inspection",
		"High": "Field inspection recommended",
		"Critical": "Immediate field verification and response coordination",
	}
	try:
		return actions[state]
	except KeyError as error:
		raise ValueError(f"unknown alert state: {state}") from error


def response_priority(risk_score: int, exposure: float) -> int:
	"""Rank a zone using both hazard severity and exposed population/assets."""
	if not 0 <= risk_score <= 100:
		raise ValueError("risk_score must be between 0 and 100")
	if not 0 <= exposure <= 100:
		raise ValueError("exposure must be between 0 and 100")
	return round(risk_score * 0.65 + exposure * 0.35)


def build_alert(zone: Mapping[str, Any], risk: Mapping[str, Any]) -> dict[str, Any]:
	"""Build a complete alert record from a zone and risk-engine result."""
	state = alert_state(int(risk["risk_score"]))
	priority = response_priority(int(risk["risk_score"]), float(zone["exposure"]))
	return {
		"zone_id": zone["id"],
		"level": state,
		"title": f"{state} risk detected",
		"reason": risk["explanation"],
		"recommended_action": recommended_action(state),
		"priority": priority,
		"risk_score": int(risk["risk_score"]),
		"exposure": float(zone["exposure"]),
		"status": "Active",
	}


def priority_queue(zones: list[Mapping[str, Any]], risks: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
	"""Return zones ordered from highest response priority to lowest."""
	by_id = {risk["zone_id"]: risk for risk in risks}
	queue = []
	for zone in zones:
		risk = by_id[zone["id"]]
		alert = build_alert(zone, risk)
		queue.append({**alert, "location": zone["name"]})
	return sorted(queue, key=lambda item: item["priority"], reverse=True)
