"""Scenario simulation and local data persistence for Code Nexus."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

DATA_DIR = Path(__file__).resolve().parent / "data"
# Hosts with a read-only project filesystem (Vercel, AWS Lambda, some containers)
# only allow writes under /tmp. Honour an explicit CODENEXUS_DB first, then fall
# back to /tmp on those hosts, and finally to a file beside this module locally.
_READ_ONLY_HOST = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_DATABASE = Path(
	os.getenv("CODENEXUS_DB")
	or ("/tmp/code_nexus.db" if _READ_ONLY_HOST
		else str(Path(__file__).resolve().parent / "code_nexus.db"))
)


class DataStore:
	"""Load prototype datasets and persist operational records in SQLite."""

	DATASETS = {
		"zones": "zones.json",
		"sensors": "sensors.json",
		"history": "history.json",
		"infrastructure": "infrastructure.json",
	}

	def __init__(self, database_path: str | Path = DEFAULT_DATABASE, data_dir: str | Path = DATA_DIR) -> None:
		self.database_path = Path(database_path)
		self.data_dir = Path(data_dir)
		self.database_path.parent.mkdir(parents=True, exist_ok=True)
		self.initialize_database()
		self.seed_field_reports()

	def connection(self) -> sqlite3.Connection:
		connection = sqlite3.connect(self.database_path)
		connection.row_factory = sqlite3.Row
		return connection

	def load_dataset(self, name: str) -> list[dict[str, Any]]:
		"""Load one prepared JSON dataset and reject malformed top-level values."""
		if name not in self.DATASETS:
			raise ValueError(f"unknown dataset: {name}")
		path = self.data_dir / self.DATASETS[name]
		try:
			payload = json.loads(path.read_text(encoding="utf-8"))
		except (FileNotFoundError, json.JSONDecodeError) as error:
			raise ValueError(f"unable to load {path.name}: {error}") from error
		if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
			raise ValueError(f"{path.name} must contain a JSON array of objects")
		return payload

	def load_all_datasets(self) -> dict[str, list[dict[str, Any]]]:
		return {name: self.load_dataset(name) for name in self.DATASETS}

	def initialize_database(self) -> None:
		with self.connection() as connection:
			connection.executescript(
				"""
				CREATE TABLE IF NOT EXISTS field_reports (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					zone_id TEXT NOT NULL,
					location TEXT NOT NULL,
					observation TEXT NOT NULL,
					severity TEXT NOT NULL,
					timestamp TEXT NOT NULL,
					evidence_path TEXT,
					status TEXT NOT NULL DEFAULT 'Submitted',
					created_at TEXT NOT NULL
				);
				CREATE TABLE IF NOT EXISTS alerts (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					zone_id TEXT NOT NULL,
					level TEXT NOT NULL,
					title TEXT NOT NULL,
					reason TEXT NOT NULL,
					recommended_action TEXT NOT NULL,
					risk_score INTEGER NOT NULL,
					status TEXT NOT NULL DEFAULT 'Active',
					created_at TEXT NOT NULL
				);
				CREATE TABLE IF NOT EXISTS sensor_updates (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					zone_id TEXT NOT NULL,
					rainfall REAL NOT NULL,
					soil_moisture REAL NOT NULL,
					temperature REAL NOT NULL,
					accumulated_rainfall REAL NOT NULL,
					recorded_at TEXT NOT NULL
				);
				CREATE TABLE IF NOT EXISTS simulation_events (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					scenario TEXT NOT NULL,
					rainfall_boost REAL NOT NULL,
					moisture_boost REAL NOT NULL,
					created_at TEXT NOT NULL
				);
				CREATE TABLE IF NOT EXISTS risk_history (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					zone_id TEXT NOT NULL,
					risk_score INTEGER NOT NULL,
					risk_level TEXT NOT NULL,
					confidence REAL NOT NULL,
					recorded_at TEXT NOT NULL
				);
				CREATE TABLE IF NOT EXISTS current_sensors (
					zone_id TEXT PRIMARY KEY,
					sensor_id TEXT NOT NULL,
					rainfall REAL NOT NULL,
					soil_moisture REAL NOT NULL,
					temperature REAL NOT NULL,
					accumulated_rainfall REAL NOT NULL,
					status TEXT NOT NULL,
					recorded_at TEXT NOT NULL
				);
				"""
			)
			columns = {row[1] for row in connection.execute("PRAGMA table_info(field_reports)")}
			for column, definition in {
				"latitude": "REAL",
				"longitude": "REAL",
				"accuracy_m": "REAL",
				"media_type": "TEXT",
				"media_name": "TEXT",
				"media_data": "TEXT",   # base64 data URI of the evidence photo/video
				"is_seed": "INTEGER DEFAULT 0",   # demo baseline rows — never feed ground truth
			}.items():
				if column not in columns:
					connection.execute(f"ALTER TABLE field_reports ADD COLUMN {column} {definition}")

			sensor_columns = {row[1] for row in connection.execute("PRAGMA table_info(current_sensors)")}
			for column, definition in {
				"rainfall_source": "TEXT",
				"soil_source": "TEXT",
				"soil_observed_at": "TEXT",
			}.items():
				if column not in sensor_columns:
					connection.execute(f"ALTER TABLE current_sensors ADD COLUMN {column} {definition}")

	@staticmethod
	def timestamp() -> str:
		return datetime.now(timezone.utc).isoformat()

	def save_field_report(self, report: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute(
				"INSERT INTO field_reports (zone_id, location, observation, severity, timestamp, evidence_path, status, created_at, latitude, longitude, accuracy_m, media_type, media_name, media_data) "
				"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
				(
					report["zone_id"], report["location"], report["observation"], report["severity"],
					report.get("timestamp", self.timestamp()), report.get("evidence_path"),
					report.get("status", "Submitted"), self.timestamp(),
					report.get("latitude"), report.get("longitude"), report.get("accuracy_m"),
					report.get("media_type"), report.get("media_name"), report.get("media_data"),
				),
			)
			return int(cursor.lastrowid)

	def update_field_report_status(self, report_id: int, status: str) -> bool:
		if status not in {"Submitted", "Under review", "Verified", "Rejected"}:
			raise ValueError("invalid report status")
		with self.connection() as connection:
			cursor = connection.execute("UPDATE field_reports SET status = ? WHERE id = ?", (status, report_id))
			return cursor.rowcount == 1

	def save_alert(self, alert: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute("INSERT INTO alerts (zone_id, level, title, reason, recommended_action, risk_score, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (alert["zone_id"], alert["level"], alert["title"], alert["reason"], alert["recommended_action"], alert["risk_score"], alert.get("status", "Active"), self.timestamp()))
			return int(cursor.lastrowid)

	def save_sensor_update(self, update: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute("INSERT INTO sensor_updates (zone_id, rainfall, soil_moisture, temperature, accumulated_rainfall, recorded_at) VALUES (?, ?, ?, ?, ?, ?)", (update["zone_id"], update["rainfall"], update["soil_moisture"], update["temperature"], update["accumulated_rainfall"], update.get("recorded_at", self.timestamp())))
			return int(cursor.lastrowid)

	def upsert_current_sensor(self, reading: Mapping[str, Any]) -> None:
		with self.connection() as connection:
			connection.execute(
				"INSERT INTO current_sensors (zone_id, sensor_id, rainfall, soil_moisture, temperature, accumulated_rainfall, status, recorded_at, rainfall_source, soil_source, soil_observed_at) "
				"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
				"ON CONFLICT(zone_id) DO UPDATE SET sensor_id=excluded.sensor_id, rainfall=excluded.rainfall, soil_moisture=excluded.soil_moisture, temperature=excluded.temperature, "
				"accumulated_rainfall=excluded.accumulated_rainfall, status=excluded.status, recorded_at=excluded.recorded_at, "
				"rainfall_source=excluded.rainfall_source, soil_source=excluded.soil_source, soil_observed_at=excluded.soil_observed_at",
				(
					reading["zone_id"], reading["sensor_id"], reading["rainfall"], reading["soil_moisture"],
					reading["temperature"], reading["accumulated_rainfall"], reading.get("status", "healthy"),
					reading.get("recorded_at", self.timestamp()),
					reading.get("rainfall_source", "open-meteo"),
					reading.get("soil_source", "open-meteo"),
					reading.get("soil_observed_at"),
				),
			)

	def current_sensors(self) -> dict[str, dict[str, Any]]:
		with self.connection() as connection:
			rows = connection.execute("SELECT * FROM current_sensors").fetchall()
		readings = {}
		for row in rows:
			reading = dict(row)
			reading["id"] = reading["sensor_id"]
			readings[row["zone_id"]] = reading
		return readings

	def save_simulation_event(self, event: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute("INSERT INTO simulation_events (scenario, rainfall_boost, moisture_boost, created_at) VALUES (?, ?, ?, ?)", (event["scenario"], event["rainfall_boost"], event["moisture_boost"], self.timestamp()))
			return int(cursor.lastrowid)

	def clear_field_reports(self) -> int:
		"""Delete every field report (demo / dev reset). Returns rows removed."""
		with self.connection() as connection:
			cursor = connection.execute("DELETE FROM field_reports")
			return cursor.rowcount

	def save_risk_history(self, risk: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute("INSERT INTO risk_history (zone_id, risk_score, risk_level, confidence, recorded_at) VALUES (?, ?, ?, ?, ?)", (risk["zone_id"], risk["risk_score"], risk["risk_level"], risk["confidence"], risk.get("recorded_at", self.timestamp())))
			return int(cursor.lastrowid)

	def recent(self, table: str, limit: int = 50) -> list[dict[str, Any]]:
		if table not in {"field_reports", "alerts", "sensor_updates", "simulation_events", "risk_history"}:
			raise ValueError(f"unsupported table: {table}")
		if not isinstance(limit, int) or limit < 1:
			raise ValueError("limit must be a positive integer")
		with self.connection() as connection:
			rows = connection.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
		return [dict(row) for row in rows]

	def latest_field_report(self, zone_id: str) -> dict[str, Any] | None:
		"""Most recent *operator-submitted* field report for a zone, or None.
		Demo seed rows (is_seed = 1) are excluded so they never move the score."""
		with self.connection() as connection:
			row = connection.execute(
				"SELECT * FROM field_reports WHERE zone_id = ? AND COALESCE(is_seed, 0) = 0 ORDER BY id DESC LIMIT 1",
				(zone_id,),
			).fetchone()
		return dict(row) if row else None

	def seed_field_reports(self, force: bool = False) -> int:
		"""Insert the demo baseline field reports (backend/data/seed_reports.json)
		when the table is empty, so the Verification log is never blank. Returns
		the number of rows added."""
		path = self.data_dir / "seed_reports.json"
		if not path.exists():
			return 0
		try:
			seeds = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, ValueError):
			return 0
		if not isinstance(seeds, list):
			return 0
		with self.connection() as connection:
			if not force:
				existing = connection.execute("SELECT COUNT(*) FROM field_reports").fetchone()[0]
				if existing:
					return 0
			now = datetime.now(timezone.utc)
			added = 0
			for seed in seeds:
				when = (now - timedelta(hours=float(seed.get("hours_ago", 24)))).isoformat()
				connection.execute(
					"INSERT INTO field_reports (zone_id, location, observation, severity, timestamp, status, created_at, is_seed) "
					"VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
					(
						seed["zone_id"], seed["location"], seed["observation"], seed["severity"],
						when, seed.get("status", "Submitted"), self.timestamp(),
					),
				)
				added += 1
			return added


def simulate_zone(
	zone: Mapping[str, Any],
	scenario: str = "Normal",
	meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""Apply a scenario to zone inputs, then calculate its resulting risk.

	``meta`` is passed straight through to ``calculate_risk`` for the confidence
	model (feed source / freshness).
	"""
	if scenario not in SCENARIO_BOOSTS:
		raise ValueError(f"unknown scenario: {scenario}")
	rainfall_boost, moisture_boost = SCENARIO_BOOSTS[scenario]
	simulated = dict(zone)
	simulated["rainfall"] = max(0.0, float(zone["rainfall"]) + rainfall_boost)
	simulated["accumulated"] = max(0.0, float(zone["accumulated"]) + rainfall_boost * 1.7)
	simulated["moisture"] = max(0.0, min(100.0, float(zone["moisture"]) + moisture_boost))
	return {**simulated, **calculate_risk(simulated, meta)}


_NO_MOVEMENT = re.compile(
	r"(no|nil|not any|without)\s+(observed\s+|visible\s+|fresh\s+|sign\s+of\s+)?"
	r"(movement|slippage|slip|cracks?|displacement|subsidence|settlement)"
	r"|slope (is )?stable|nothing observed|no change",
	re.IGNORECASE,
)
_CRITICAL_SCORE = 75  # risk_engine Critical threshold
_GROUND_TRUTH_MAX_AGE = timedelta(hours=6)


def _report_age(report: Mapping[str, Any]) -> timedelta | None:
	raw = report.get("timestamp") or report.get("created_at")
	if not raw:
		return None
	try:
		when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
	except ValueError:
		return None
	if when.tzinfo is None:
		when = when.replace(tzinfo=timezone.utc)
	return datetime.now(timezone.utc) - when


def apply_ground_truth(
	result: dict[str, Any],
	report: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
	"""Let a recent field report override / bump the model score for its zone.

	Mirrors the client-side ``registerFieldAdjust`` (frontend/js/app.js) so the
	online and offline behaviours match. Mutates ``result`` in place and returns
	a ``ground_truth`` record, or ``None`` when no adjustment applies.
	"""
	if not report:
		return None
	status = str(report.get("status") or "Submitted")
	if status == "Rejected":
		return None
	age = _report_age(report)
	if age is not None and age > _GROUND_TRUTH_MAX_AGE:
		return None

	severity = str(report.get("severity") or "").lower()
	observation = str(report.get("observation") or "")

	if _NO_MOVEMENT.search(observation):
		delta_score, delta_conf = -4, 8
		note = "no slope movement observed on the ground"
	elif severity == "critical":
		delta_score, delta_conf = 13, 12
		note = "critical ground observation confirmed by field team"
	elif severity == "high":
		delta_score, delta_conf = 8, 10
		note = "high-severity ground observation confirmed"
	else:
		delta_score, delta_conf = 3, 6
		note = "field observation logged"

	before = int(result["risk_score"])
	score = max(0, min(100, before + delta_score))
	# A *verified* critical report forces at least the Critical band.
	if severity == "critical" and status == "Verified":
		score = max(score, _CRITICAL_SCORE)

	from .risk_engine import _level  # local import avoids a cycle at module load

	result["risk_score"] = score
	result["risk_level"] = _level(score)
	result["confidence"] = int(min(99, result.get("confidence", 75) + delta_conf))
	basis = result.setdefault("confidence_basis", [])
	basis.append({"factor": f"field report ({severity or 'observation'}, {status.lower()})", "effect": delta_conf})

	return {
		"severity": report.get("severity"),
		"status": status,
		"location": report.get("location"),
		"observed_at": report.get("timestamp") or report.get("created_at"),
		"delta_score": score - before,
		"delta_confidence": delta_conf,
		"note": note,
		"overridden": severity == "critical" and status == "Verified",
	}
