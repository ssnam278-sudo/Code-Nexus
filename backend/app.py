"""Flask API for the BhuSanket prototype monitoring system."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from .risk_engine import calculate_risk
from .simulator import DataStore, SCENARIO_BOOSTS, simulate_zone


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
store = DataStore()
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config.from_mapping(
	JSON_SORT_KEYS=False,
	MAX_CONTENT_LENGTH=10 * 1024 * 1024,
	ENVIRONMENT="prototype",
)


@app.after_request
def add_cors_headers(response: Any) -> Any:
	"""Allow the separately served prototype frontend to call this API."""
	response.headers["Access-Control-Allow-Origin"] = "*"
	response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
	response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
	return response


def _zone_records() -> list[dict[str, Any]]:
	datasets = store.load_all_datasets()
	sensors = {sensor["zone_id"]: sensor for sensor in datasets["sensors"]}
	records = []
	for zone in datasets["zones"]:
		sensor = sensors.get(zone["id"], {})
		records.append({
			**zone,
			"sensor_id": sensor.get("id"),
			"sensor_status": sensor.get("status", "unknown"),
			"rainfall": sensor.get("rainfall", 0),
			"soil_moisture": sensor.get("soil_moisture", 0),
			"temperature": sensor.get("temperature", 0),
			"accumulated_rainfall": sensor.get("accumulated_rainfall", 0),
			"moisture": sensor.get("soil_moisture", 0),
			"accumulated": sensor.get("accumulated_rainfall", 0),
		})
	return records


def _find_zone(zone_id: str) -> dict[str, Any]:
	zone = next((item for item in _zone_records() if item["id"] == zone_id), None)
	if zone is None:
		raise KeyError(zone_id)
	return zone


def _risk_record(zone: dict[str, Any], scenario: str = "Normal") -> dict[str, Any]:
	result = simulate_zone(zone, scenario)
	return {"zone_id": zone["id"], **result}


@app.get("/")
def index() -> Any:
	return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/api/health")
def health() -> Any:
	return jsonify({"status": "ok", "service": "bhusanket-api", "environment": app.config["ENVIRONMENT"], "data_sources": 4, "database": str(store.database_path.name)})


@app.get("/api/zones")
def zones() -> Any:
	return jsonify(_zone_records())


@app.get("/api/sensors")
def sensors() -> Any:
	return jsonify(store.load_dataset("sensors"))


@app.get("/api/history")
def history() -> Any:
	return jsonify(store.load_dataset("history"))


@app.get("/api/infrastructure")
def infrastructure() -> Any:
	return jsonify(store.load_dataset("infrastructure"))


@app.get("/api/risk")
def risk() -> Any:
	zone_id = request.args.get("zone_id")
	scenario = request.args.get("scenario", "Normal")
	if scenario not in SCENARIO_BOOSTS:
		return jsonify({"error": f"unknown scenario: {scenario}"}), 400
	try:
		zone = _find_zone(zone_id) if zone_id else _zone_records()[0]
	except KeyError:
		return jsonify({"error": "zone not found"}), 404
	return jsonify(_risk_record(zone, scenario))


@app.get("/api/alerts")
def alerts() -> Any:
	active = []
	for zone in _zone_records():
		risk_result = _risk_record(zone)
		if risk_result["risk_level"] in {"High", "Critical"}:
			active.append({"zone_id": zone["id"], "level": risk_result["risk_level"], "title": f"{risk_result['risk_level']} risk detected", "reason": risk_result["explanation"], "recommended_action": "Immediate field verification" if risk_result["risk_level"] == "Critical" else "Field inspection", "risk_score": risk_result["risk_score"]})
	return jsonify({"alerts": active, "stored": store.recent("alerts")})


@app.get("/api/sensor-updates")
def sensor_updates() -> Any:
	return jsonify(store.recent("sensor_updates"))


@app.get("/api/risk-history")
def risk_history() -> Any:
	return jsonify(store.recent("risk_history"))


@app.get("/api/reports")
def reports() -> Any:
	return jsonify(store.recent("field_reports"))


@app.get("/api/simulation")
def simulation() -> Any:
	return jsonify({"scenarios": list(SCENARIO_BOOSTS), "events": store.recent("simulation_events")})


@app.post("/api/simulation")
def run_simulation() -> Any:
	payload = request.get_json(silent=True) or {}
	scenario = payload.get("scenario", "Normal")
	if scenario not in SCENARIO_BOOSTS:
		return jsonify({"error": f"unknown scenario: {scenario}"}), 400
	rainfall_boost, moisture_boost = SCENARIO_BOOSTS[scenario]
	store.save_simulation_event({"scenario": scenario, "rainfall_boost": rainfall_boost, "moisture_boost": moisture_boost})
	zone_id = payload.get("zone_id")
	try:
		zones_to_simulate = [_find_zone(zone_id)] if zone_id else _zone_records()
	except KeyError:
		return jsonify({"error": "zone not found"}), 404
	results = [_risk_record(zone, scenario) for zone in zones_to_simulate]
	for result in results:
		store.save_sensor_update({"zone_id": result["zone_id"], "rainfall": result["rainfall"], "soil_moisture": result["moisture"], "temperature": result["temperature"], "accumulated_rainfall": result["accumulated"]})
		store.save_risk_history(result)
		if result["risk_level"] in {"High", "Critical"}:
			store.save_alert({"zone_id": result["zone_id"], "level": result["risk_level"], "title": f"{result['risk_level']} risk detected", "reason": result["explanation"], "recommended_action": "Immediate field verification" if result["risk_level"] == "Critical" else "Field inspection", "risk_score": result["risk_score"]})
	return jsonify({"scenario": scenario, "results": results})


@app.post("/api/reports")
def create_report() -> Any:
	payload = request.get_json(silent=True) or {}
	required = ("zone_id", "location", "observation", "severity")
	missing = [field for field in required if not payload.get(field)]
	if missing:
		return jsonify({"error": "missing required fields", "fields": missing}), 400
	report_id = store.save_field_report(payload)
	return jsonify({"id": report_id, "status": payload.get("status", "Submitted")}), 201


if __name__ == "__main__":
	app.run(debug=True, host="127.0.0.1", port=5000)
