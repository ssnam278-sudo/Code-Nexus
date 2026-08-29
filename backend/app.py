"""Flask API for the Code Nexus prototype monitoring system."""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from .alerts import ALERT_STATES, build_alert, priority_queue
from .alert_dispatch import (
    dispatch as dispatch_alert,
    ist_stamp,
    send_telegram_message,
    telegram_configured,
    webhook_configured,
)
from .cap import build_cap_alert, to_xml as cap_to_xml
from .data_connectors import source_register
from .live_hazard import all_live_hazards, zone_live_hazard
from .live_ingest import ingest_all, start_scheduler
from .live_store import LiveStore
from .open_meteo import fetch_current
from .realtime import publish, stream, subscribe, unsubscribe
from .replay import EVENTS as REPLAY_EVENTS, run_replay
from .simulator import DataStore, SCENARIO_BOOSTS, apply_ground_truth, simulate_zone
from .thresholds import operational_level, threshold_for


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

store = DataStore()
live_store = LiveStore(store.database_path)
_open_meteo_last_sync = 0.0
_open_meteo_sync_seconds = float(os.getenv("OPEN_METEO_SYNC_SECONDS", "600"))

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="",
)

app.config.from_mapping(
    JSON_SORT_KEYS=False,
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    ENVIRONMENT="prototype",
    INGEST_API_KEY=os.getenv("INGEST_API_KEY", ""),
)


@app.after_request
def add_cors_headers(response: Any) -> Any:
    """Allow the separately served prototype frontend to call this API."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    return response


def _seconds_since(iso_timestamp: str | None) -> float | None:
    """Whole seconds between an ISO8601 timestamp and now (UTC). None if unparseable."""
    if not iso_timestamp:
        return None
    try:
        when = datetime.fromisoformat(str(iso_timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - when).total_seconds())


# DEM + inventory derived terrain/history, loaded once from the committed cache.
_PROFILES: dict[str, dict[str, Any]] = {}


def _load_profiles() -> None:
    from .zone_profile import _cache as _profile_cache  # local import; avoids cycle at import time
    _PROFILES.clear()
    for zone in store.load_dataset("zones"):
        path = _profile_cache(zone["id"])
        if path.exists():
            try:
                _PROFILES[zone["id"]] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass


def _zone_records() -> list[dict[str, Any]]:
    datasets = store.load_all_datasets()

    # sensors.json is the simulated fallback; current_sensors holds anything that
    # actually arrived live (Open-Meteo sync or POST /api/ingest/telemetry).
    simulated_sensors = {
        sensor["zone_id"]: sensor
        for sensor in datasets["sensors"]
    }
    live_sensors = store.current_sensors()

    records = []

    for zone in datasets["zones"]:
        is_live = zone["id"] in live_sensors
        sensor = live_sensors.get(zone["id"]) or simulated_sensors.get(zone["id"], {})
        profile = _PROFILES.get(zone["id"], {})

        observed_at = sensor.get("recorded_at") if is_live else None
        feed_age = _seconds_since(observed_at) if observed_at else None

        records.append(
            {
                **zone,
                # DEM + inventory derived, when available (see /api/terrain)
                "slope": profile.get("slope", zone.get("slope")),
                "susceptibility": profile.get("susceptibility", zone.get("susceptibility")),
                "history": profile.get("history", zone.get("history")),
                "terrain_source": "dem+inventory" if profile else "static",
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
                # provenance for the UI real-vs-simulated labelling + confidence
                "data_source": "open-meteo" if is_live else "simulated",
                "observed_at": observed_at,
                "feed_age_seconds": feed_age,
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
    meta = {
        "data_source": zone.get("data_source"),
        "feed_age_seconds": zone.get("feed_age_seconds"),
    }
    result = simulate_zone(zone, scenario, meta)

    # A recent High/Critical field report is ground truth: it bumps (or, when
    # verified critical, overrides) the model score for this zone.
    ground_truth = apply_ground_truth(result, store.latest_field_report(zone["id"]))

    record = {
        "zone_id": zone["id"],
        "operational_level": operational_level(result["risk_score"], zone.get("district")),
        "data_source": zone.get("data_source", "simulated"),
        "observed_at": zone.get("observed_at"),
        "feed_age_seconds": zone.get("feed_age_seconds"),
        **result,
    }
    if ground_truth:
        record["ground_truth"] = ground_truth
    return record


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
    records = _zone_records()
    live = sum(1 for zone in records if zone.get("data_source") == "open-meteo")
    return jsonify(
        {
            "status": "ok",
            "service": "code-nexus-api",
            "environment": app.config["ENVIRONMENT"],
            "data_sources": 4,
            "database": str(
                store.database_path.name
            ),
            "rainfall_feed": {
                "provider": "Open-Meteo",
                "zones_live": live,
                "zones_total": len(records),
                "zones_simulated": len(records) - live,
            },
            "alert_dispatch": {
                "telegram_configured": telegram_configured(),
                "webhook_configured": webhook_configured(),
            },
        }
    )


@app.get("/api/zones")
def zones() -> Any:
    records = []
    for zone in _zone_records():
        risk = _risk_record(zone)
        records.append({
            **zone,
            "risk_score": risk["risk_score"],
            "risk_level": risk["risk_level"],
            "confidence": risk.get("confidence", 95),
            "confidence_basis": risk.get("confidence_basis", []),
            "ground_truth": risk.get("ground_truth"),
        })
    return jsonify(records)


@app.get("/api/sensors")
def sensors() -> Any:
    readings = {sensor["zone_id"]: sensor for sensor in store.load_dataset("sensors")}
    readings.update(store.current_sensors())
    return jsonify(list(readings.values()))


@app.post("/api/live/open-meteo")
def sync_open_meteo() -> Any:
    global _open_meteo_last_sync
    force = request.args.get("force", "false").lower() == "true"
    if not force and time.monotonic() - _open_meteo_last_sync < _open_meteo_sync_seconds:
        return jsonify({"status": "cached", "provider": "Open-Meteo", "next_sync_seconds": round(_open_meteo_sync_seconds - (time.monotonic() - _open_meteo_last_sync))})
    readings = []
    for zone in _zone_records():
        try:
            reading = fetch_current(zone)
            store.upsert_current_sensor(reading)
            store.save_sensor_update(reading)
            publish("telemetry", reading)
            readings.append(reading)
        except (KeyError, TypeError, ValueError, OSError) as error:
            return jsonify({"error": "Open-Meteo sync failed", "detail": str(error), "completed": len(readings)}), 502
    _open_meteo_last_sync = time.monotonic()
    return jsonify({"status": "updated", "provider": "Open-Meteo", "readings": readings, "recorded_at": store.timestamp()})


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


@app.get("/api/sources")
def sources() -> Any:
    return jsonify(source_register())


@app.get("/api/thresholds")
def thresholds() -> Any:
    return jsonify({"levels": ["Normal", "Watch", "Advisory", "Warning", "Critical", "Evacuation Recommended"], "districts": {"default": threshold_for()}})


@app.post("/api/ml/compare")
def ml_compare() -> Any:
    payload = request.get_json(silent=True) or {}
    try:
        from .ml_model import compare_risk
        result = compare_risk(payload)
    except ImportError:
        return jsonify({"error": "ML comparison model is not available in this deployment"}), 503
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result)


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


@app.get("/api/terrain")
def terrain_all() -> Any:
    profiles = []
    for zone in store.load_dataset("zones"):
        p = _PROFILES.get(zone["id"])
        profiles.append(p or {"zone_id": zone["id"], "status": "not_resolved"})
    return jsonify({"zones": profiles, "count": len(profiles)})


@app.get("/api/terrain/<zone_id>")
def terrain_zone(zone_id: str) -> Any:
    p = _PROFILES.get(zone_id)
    if not p:
        return jsonify({"error": "no terrain profile", "zone_id": zone_id}), 404
    return jsonify(p)


@app.post("/api/terrain/refresh")
def terrain_refresh() -> Any:
    from .zone_profile import resolve_profile
    done, errors = [], []
    for zone in store.load_dataset("zones"):
        try:
            resolve_profile(zone, refresh=True)
            done.append(zone["id"])
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append({"zone": zone["id"], "error": str(exc)})
    _load_profiles()
    return jsonify({"refreshed": done, "errors": errors})


@app.get("/api/replay/events")
def replay_events() -> Any:
    return jsonify([
        {
            "id": e.id,
            "name": e.name,
            "description": e.description,
            "failure_utc": e.failure_utc,
            "is_control": e.failure_utc is None,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "source": e.source,
        }
        for e in REPLAY_EVENTS.values()
    ])


@app.get("/api/replay")
def replay() -> Any:
    event_id = request.args.get("event", "")
    refresh = request.args.get("refresh", "false").lower() == "true"
    try:
        return jsonify(run_replay(event_id, refresh=refresh))
    except KeyError:
        return jsonify({"error": "unknown event", "events": sorted(REPLAY_EVENTS)}), 404
    except (OSError, RuntimeError, ValueError) as error:
        return jsonify({"error": "replay unavailable", "detail": str(error)}), 502


@app.get("/api/cap")
def cap_alert() -> Any:
    zone_id = request.args.get("zone_id")
    scenario = request.args.get("scenario", "Normal")
    if scenario not in SCENARIO_BOOSTS:
        return jsonify({"error": f"unknown scenario: {scenario}"}), 400
    try:
        zone = _find_zone(zone_id) if zone_id else _zone_records()[0]
    except KeyError:
        return jsonify({"error": "zone not found"}), 404

    risk = _risk_record(zone, scenario)
    alert = build_alert(zone, risk)
    payload = {**risk, "explanation": risk.get("explanation"), "recommended_action": alert["recommended_action"]}
    cap = build_cap_alert(zone, payload)

    if request.args.get("format", "json").lower() == "xml":
        return app.response_class(cap_to_xml(cap), mimetype="application/xml")
    return jsonify(cap)


def _live_zones() -> list[dict[str, Any]]:
    """Zone records with the static terrain fields the hazard model needs."""
    return [
        z for z in _zone_records()
        if all(k in z for k in ("slope", "susceptibility", "history", "coordinates"))
    ]


def _dispatch_on_escalation(zone: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any] | None:
    """Send a real alert when a simulated result crosses into High/Critical.

    Shares the ``live_alert_state`` dedupe table with the live cycle, so the
    "Run escalation demo" button fires each channel exactly once per crossing.
    Set ``CODENEXUS_ALERT_ON_SIM=0`` to disable.
    """
    if os.getenv("CODENEXUS_ALERT_ON_SIM", "1").lower() not in {"1", "true", "yes"}:
        return None
    hz = {
        "now": {
            "risk_level": risk["risk_level"],
            "risk_score": int(risk["risk_score"]),
            "method": risk.get("explanation", "Weighted risk engine (scenario)"),
        },
        "forecast": {},
    }
    try:
        result = dispatch_alert(live_store, zone, hz)
        return result if result.get("dispatched") else None
    except (KeyError, TypeError, ValueError, OSError) as exc:  # pragma: no cover - defensive
        print(f"[alert_dispatch] sim escalation failed for {zone.get('id')}: {exc}", flush=True)
        return None


def _run_live_cycle(refresh: bool = True) -> dict[str, Any]:
    """One real-time step: pull rainfall, recompute hazard, dispatch escalations."""
    zones = _live_zones()
    ingest_summary = ingest_all(live_store, zones) if refresh else {"skipped": True}
    dispatched = []
    for zone in zones:
        try:
            hz = zone_live_hazard(live_store, zone)
            if hz.get("now"):
                result = dispatch_alert(live_store, zone, hz)
                if result.get("dispatched"):
                    dispatched.append(result)
        except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
            dispatched.append({"zone": zone.get("id"), "error": str(exc)})
    return {"ingest": ingest_summary, "alerts_dispatched": dispatched}


@app.get("/api/live/hazard")
def live_hazard() -> Any:
    zones = _live_zones()
    if not live_store.has_data():
        try:
            ingest_all(live_store, zones)
        except (OSError, RuntimeError) as error:
            return jsonify({"status": "warming_up", "detail": str(error), "zones": []}), 200
    return jsonify(all_live_hazards(live_store, zones))


@app.get("/api/live/hazard/<zone_id>")
def live_hazard_zone(zone_id: str) -> Any:
    try:
        zone = _find_zone(zone_id)
    except KeyError:
        return jsonify({"error": "zone not found"}), 404
    return jsonify(zone_live_hazard(live_store, zone))


@app.get("/api/tick")
@app.post("/api/tick")
def live_tick() -> Any:
    """Run one ingestion + hazard + dispatch cycle. For cron / serverless setups."""
    try:
        return jsonify(_run_live_cycle(refresh=True))
    except (OSError, RuntimeError) as error:
        return jsonify({"error": "tick failed", "detail": str(error)}), 502


@app.post("/api/alerts/dispatch-test")
def dispatch_test() -> Any:
    """Send a sample Telegram alert so operators can verify the wiring.

    Honours ``INGEST_API_KEY`` (header ``X-Ingest-Key``) when it is configured.
    """
    configured_key = app.config["INGEST_API_KEY"]
    if configured_key and request.headers.get("X-Ingest-Key") != configured_key:
        return jsonify({"error": "invalid ingestion key"}), 401
    text = (
        "\U0001f9ea <b>Code Nexus - test alert</b>\n"
        "Telegram dispatch is wired correctly. No landslide risk is implied.\n"
        f"<i>{ist_stamp()}</i>"
    )
    delivered = send_telegram_message(text)
    if delivered is None:
        return jsonify({
            "telegram": "skipped",
            "reason": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set",
        })
    return jsonify({"telegram": "sent" if delivered else "failed"}), (200 if delivered else 502)


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

        _dispatch_on_escalation(zone, result)

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
        zone = _find_zone(
            payload["zone_id"]
        )

    except KeyError:
        return jsonify(
            {"error": "zone not found"}
        ), 404

    report_id = store.save_field_report(
        payload
    )

    ground_truth = None
    severity = str(payload.get("severity") or "")
    if severity in {"High", "Critical"}:
        # Log the ground-truth verification as an audit row so it shows up in
        # GET /api/alerts alongside model-generated alerts.
        risk_after = _risk_record(zone)
        ground_truth = risk_after.get("ground_truth")
        store.save_alert(
            {
                "zone_id": zone["id"],
                "level": "GroundTruth",
                "title": "Field verification",
                "reason": (
                    f"{severity} field report from {payload.get('location', zone['id'])}: "
                    f"{payload.get('observation', '')}"[:280]
                ),
                "recommended_action": "Review against model; adjust response posture.",
                "risk_score": int(risk_after.get("risk_score", 0)),
                "status": "Logged",
            }
        )

    return jsonify(
        {
            "id": report_id,
            "status": payload.get(
                "status",
                "Submitted",
            ),
            "ground_truth": ground_truth,
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


@app.get("/api/events")
def events() -> Any:
    queue = subscribe()
    response = app.response_class(stream(queue), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.post("/api/ingest/telemetry")
def ingest_telemetry() -> Any:
    configured_key = app.config["INGEST_API_KEY"]
    if configured_key and request.headers.get("X-Ingest-Key") != configured_key:
        return jsonify({"error": "invalid ingestion key"}), 401
    payload = request.get_json(silent=True) or {}
    required = ("zone_id", "sensor_id", "rainfall", "soil_moisture", "temperature", "accumulated_rainfall")
    missing = [field for field in required if field not in payload]
    if missing:
        return jsonify({"error": "missing required fields", "fields": missing}), 400
    try:
        reading = {"zone_id": str(payload["zone_id"]), "sensor_id": str(payload["sensor_id"]), "rainfall": float(payload["rainfall"]), "soil_moisture": float(payload["soil_moisture"]), "temperature": float(payload["temperature"]), "accumulated_rainfall": float(payload["accumulated_rainfall"]), "status": str(payload.get("status", "healthy")), "recorded_at": str(payload.get("recorded_at", store.timestamp()))}
        _find_zone(reading["zone_id"])
        if reading["rainfall"] < 0 or reading["accumulated_rainfall"] < 0 or not 0 <= reading["soil_moisture"] <= 100:
            raise ValueError("invalid telemetry range")
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    store.upsert_current_sensor(reading)
    store.save_sensor_update(reading)
    publish("telemetry", reading)
    return jsonify({"status": "accepted", "reading": reading}), 202


def maybe_start_live_ingest() -> None:
    """Start the background rainfall loop when explicitly enabled (Render sets this).

    Off by default so imports in tests / local dev never spawn a network thread;
    serverless deployments use GET /api/tick on a cron instead.
    """
    if os.getenv("CODENEXUS_LIVE_INGEST", "0").lower() not in {"1", "true", "yes"}:
        return
    interval = int(os.getenv("CODENEXUS_LIVE_INGEST_SECONDS", "900"))

    def _on_cycle(_summary: Any) -> None:
        for zone in _live_zones():
            try:
                hz = zone_live_hazard(live_store, zone)
                if hz.get("now"):
                    dispatch_alert(live_store, zone, hz)
            except (KeyError, TypeError, ValueError):
                pass

    started = start_scheduler(
        live_store, _live_zones, interval_seconds=interval, on_cycle=_on_cycle
    )
    if started:
        print(f"[live_ingest] scheduler started (every {interval}s)", flush=True)


_load_profiles()
maybe_start_live_ingest()


if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000,
    )