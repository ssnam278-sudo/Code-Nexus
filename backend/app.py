"""Flask API for the BhuSanket prototype monitoring system."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from .alerts import ALERT_STATES, build_alert, priority_queue
from .simulator import DataStore, SCENARIO_BOOSTS, simulate_zone


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

store = DataStore()

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="",
)

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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    return response


def _zone_records() -> list[dict[str, Any]]:
    datasets = store.load_all_datasets()

    sensors = {
        sensor["zone_id"]: sensor
        for sensor in datasets["sensors"]
    }

    records = []

    for zone in datasets["zones"]:
        sensor = sensors.get(zone["id"], {})

        records.append(
            {
                **zone,
                "sensor_id": sensor.get("id"),
                "sensor_status": sensor.get("status", "unknown"),
                "rainfall": sensor.get("rainfall", 0),
                "soil_moisture": sensor.get("soil_moisture", 0),
                "temperature": sensor.get("temperature", 0),
                "accumulated_rainfall": sensor.get(
                    "accumulated_rainfall", 0
                ),
                "moisture": sensor.get("soil_moisture", 0),
                "accumulated": sensor.get(
                    "accumulated_rainfall", 0
                ),
            }
        )

    return records


def _find_zone(zone_id: str) -> dict[str, Any]:
    zone = next(
        (
            item
            for item in _zone_records()
            if item["id"] == zone_id
        ),
        None,
    )

    if zone is None:
        raise KeyError(zone_id)

    return zone


def _risk_record(
    zone: dict[str, Any],
    scenario: str = "Normal",
) -> dict[str, Any]:
    result = simulate_zone(zone, scenario)

    return {
        "zone_id": zone["id"],
        **result,
    }


def _circle_polygon(
    latitude: float,
    longitude: float,
    radius_km: float,
    points: int = 32,
) -> list[list[float]]:
    """Create a prototype GeoJSON polygon around a zone center."""

    coordinates = []

    for index in range(points + 1):
        angle = 2 * math.pi * index / points

        lat = (
            latitude
            + (radius_km / 111.0)
            * math.sin(angle)
        )

        lon = (
            longitude
            + (
                radius_km
                / (
                    111.0
                    * max(
                        math.cos(math.radians(latitude)),
                        0.1,
                    )
                )
            )
            * math.cos(angle)
        )

        coordinates.append(
            [
                round(lon, 6),
                round(lat, 6),
            ]
        )

    return coordinates


def _exposure_geojson(
    zone_id: str | None = None,
) -> dict[str, Any]:

    datasets = store.load_all_datasets()

    zones = {
        zone["id"]: zone
        for zone in _zone_records()
    }

    assets = datasets["infrastructure"]

    if zone_id:
        if zone_id not in zones:
            raise KeyError(zone_id)

        assets = [
            asset
            for asset in assets
            if asset["zone_id"] == zone_id
        ]

    features: list[dict[str, Any]] = []

    for zone in zones.values():

        if zone_id and zone["id"] != zone_id:
            continue

        latitude, longitude = zone["coordinates"]

        risk = _risk_record(zone)

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        _circle_polygon(
                            latitude,
                            longitude,
                            6.0,
                        )
                    ],
                },
                "properties": {
                    "feature_type": "zone_boundary",
                    "zone_id": zone["id"],
                    "name": zone["name"],
                    "risk_score": risk["risk_score"],
                    "risk_level": risk["risk_level"],
                },
            }
        )

        impact_radius = (
            2.5 + risk["risk_score"] * 0.065
        )

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        _circle_polygon(
                            latitude,
                            longitude,
                            impact_radius,
                        )
                    ],
                },
                "properties": {
                    "feature_type": "probable_impact_area",
                    "zone_id": zone["id"],
                    "name": zone["name"],
                    "radius_km": round(
                        impact_radius,
                        1,
                    ),
                    "assistance": (
                        "Assistance may be needed here"
                    ),
                },
            }
        )

        source = [
            longitude - 0.055,
            latitude + 0.045,
        ]

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": source,
                },
                "properties": {
                    "feature_type": "hazard_source",
                    "zone_id": zone["id"],
                    "name": "Potential landslide source",
                    "description": (
                        "Steep terrain instability detected"
                    ),
                },
            }
        )

    for index, asset in enumerate(assets):

        zone = zones.get(asset["zone_id"])

        if not zone:
            continue

        latitude, longitude = zone["coordinates"]

        asset_coordinates = [
            round(
                longitude
                + 0.018 * ((index % 3) - 1),
                6,
            ),
            round(
                latitude
                - 0.016 * ((index % 2) + 1),
                6,
            ),
        ]

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": asset_coordinates,
                },
                "properties": {
                    **asset,
                    "feature_type": "infrastructure",
                    "zone_id": zone["id"],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@app.get("/")
def index() -> Any:
    return send_from_directory(
        FRONTEND_DIR,
        "index.html",
    )


@app.get("/api/health")
def health() -> Any:
    return jsonify(
        {
            "status": "ok",
            "service": "bhusanket-api",
            "environment": app.config["ENVIRONMENT"],
            "data_sources": 4,
            "database": str(
                store.database_path.name
            ),
        }
    )


@app.get("/api/zones")
def zones() -> Any:
    return jsonify(_zone_records())


@app.get("/api/sensors")
def sensors() -> Any:
    return jsonify(
        store.load_dataset("sensors")
    )


@app.get("/api/history")
def history() -> Any:
    return jsonify(
        store.load_dataset("history")
    )


@app.get("/api/infrastructure")
def infrastructure() -> Any:
    return jsonify(
        store.load_dataset("infrastructure")
    )


@app.get("/api/exposure")
def exposure() -> Any:
    try:
        return jsonify(
            _exposure_geojson(
                request.args.get("zone_id")
            )
        )

    except KeyError:
        return jsonify(
            {"error": "zone not found"}
        ), 404


@app.get("/api/risk")
def risk() -> Any:

    zone_id = request.args.get("zone_id")
    scenario = request.args.get(
        "scenario",
        "Normal",
    )

    if scenario not in SCENARIO_BOOSTS:
        return jsonify(
            {
                "error": (
                    f"unknown scenario: {scenario}"
                )
            }
        ), 400

    try:
        zone = (
            _find_zone(zone_id)
            if zone_id
            else _zone_records()[0]
        )

    except KeyError:
        return jsonify(
            {"error": "zone not found"}
        ), 404

    return jsonify(
        _risk_record(zone, scenario)
    )


@app.get("/api/alerts")
def alerts() -> Any:

    zones = _zone_records()

    risks = [
        _risk_record(zone)
        for zone in zones
    ]

    active = [
        build_alert(zone, risk)
        for zone, risk in zip(zones, risks)
        if risk["risk_level"] in ALERT_STATES
    ]

    return jsonify(
        {
            "alerts": active,
            "priority_queue": priority_queue(
                zones,
                risks,
            ),
            "stored": store.recent("alerts"),
        }
    )


@app.get("/api/sensor-updates")
def sensor_updates() -> Any:
    return jsonify(
        store.recent("sensor_updates")
    )


@app.get("/api/risk-history")
def risk_history() -> Any:
    return jsonify(
        store.recent("risk_history")
    )


@app.get("/api/reports")
def reports() -> Any:

    reports = store.recent(
        "field_reports"
    )

    zones = {
        zone["id"]: zone
        for zone in _zone_records()
    }

    for report in reports:

        zone = zones.get(
            report["zone_id"]
        )

        if zone:

            risk_result = _risk_record(zone)

            report["current_risk"] = {
                "score": risk_result["risk_score"],
                "level": risk_result["risk_level"],
            }

    return jsonify(reports)


@app.get("/api/simulation")
def simulation() -> Any:

    return jsonify(
        {
            "scenarios": list(
                SCENARIO_BOOSTS
            ),
            "events": store.recent(
                "simulation_events"
            ),
        }
    )


@app.post("/api/simulation")
def run_simulation() -> Any:

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    scenario = payload.get(
        "scenario",
        "Normal",
    )

    if scenario not in SCENARIO_BOOSTS:
        return jsonify(
            {
                "error": (
                    f"unknown scenario: {scenario}"
                )
            }
        ), 400

    rainfall_boost, moisture_boost = (
        SCENARIO_BOOSTS[scenario]
    )

    store.save_simulation_event(
        {
            "scenario": scenario,
            "rainfall_boost": rainfall_boost,
            "moisture_boost": moisture_boost,
        }
    )

    zone_id = payload.get("zone_id")

    try:
        zones_to_simulate = (
            [_find_zone(zone_id)]
            if zone_id
            else _zone_records()
        )

    except KeyError:
        return jsonify(
            {"error": "zone not found"}
        ), 404

    results = [
        _risk_record(
            zone,
            scenario,
        )
        for zone in zones_to_simulate
    ]

    alerts = []

    for result in results:

        zone = next(
            zone
            for zone in zones_to_simulate
            if zone["id"]
            == result["zone_id"]
        )

        alert = build_alert(
            zone,
            result,
        )

        store.save_sensor_update(
            {
                "zone_id": result["zone_id"],
                "rainfall": result["rainfall"],
                "soil_moisture": result["moisture"],
                "temperature": result["temperature"],
                "accumulated_rainfall": result["accumulated"],
            }
        )

        store.save_risk_history(result)

        alerts.append(alert)

        store.save_alert(alert)

    return jsonify(
        {
            "scenario": scenario,
            "results": results,
            "alerts": alerts,
            "priority_queue": priority_queue(
                zones_to_simulate,
                results,
            ),
        }
    )


@app.post("/api/reports")
def create_report() -> Any:

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    required = (
        "zone_id",
        "location",
        "observation",
        "severity",
    )

    missing = [
        field
        for field in required
        if not payload.get(field)
    ]

    if missing:
        return jsonify(
            {
                "error": "missing required fields",
                "fields": missing,
            }
        ), 400

    if payload.get(
        "status",
        "Submitted",
    ) not in {
        "Submitted",
        "Under review",
        "Verified",
        "Rejected",
    }:
        return jsonify(
            {
                "error": "invalid report status"
            }
        ), 400

    try:
        _find_zone(
            payload["zone_id"]
        )

    except KeyError:
        return jsonify(
            {"error": "zone not found"}
        ), 404

    report_id = store.save_field_report(
        payload
    )

    return jsonify(
        {
            "id": report_id,
            "status": payload.get(
                "status",
                "Submitted",
            ),
        }
    ), 201


@app.patch("/api/reports/<int:report_id>")
def update_report(
    report_id: int,
) -> Any:

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    status = payload.get("status")

    if status not in {
        "Submitted",
        "Under review",
        "Verified",
        "Rejected",
    }:
        return jsonify(
            {
                "error": "invalid report status"
            }
        ), 400

    if not store.update_field_report_status(
        report_id,
        status,
    ):
        return jsonify(
            {"error": "report not found"}
        ), 404

    return jsonify(
        {
            "id": report_id,
            "status": status,
        }
    )


if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000,
    )