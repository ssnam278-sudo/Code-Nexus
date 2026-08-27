"""Scenario simulation and local data persistence for Code Nexus."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
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
			}.items():
				if column not in columns:
					connection.execute(f"ALTER TABLE field_reports ADD COLUMN {column} {definition}")

	@staticmethod
	def timestamp() -> str:
		return datetime.now(timezone.utc).isoformat()

	def save_field_report(self, report: Mapping[str, Any]) -> int:
		with self.connection() as connection:
			cursor = connection.execute("INSERT INTO field_reports (zone_id, location, observation, severity, timestamp, evidence_path, status, created_at, latitude, longitude, accuracy_m, media_type, media_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (report["zone_id"], report["location"], report["observation"], report["severity"], report.get("timestamp", self.timestamp()), report.get("evidence_path"), report.get("status", "Submitted"), self.timestamp(), report.get("latitude"), report.get("longitude"), report.get("accuracy_m"), report.get("media_type"), report.get("media_name")))
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
			connection.execute("INSERT INTO current_sensors (zone_id, sensor_id, rainfall, soil_moisture, temperature, accumulated_rainfall, status, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(zone_id) DO UPDATE SET sensor_id=excluded.sensor_id, rainfall=excluded.rainfall, soil_moisture=excluded.soil_moisture, temperature=excluded.temperature, accumulated_rainfall=excluded.accumulated_rainfall, status=excluded.status, recorded_at=excluded.recorded_at", (reading["zone_id"], reading["sensor_id"], reading["rainfall"], reading["soil_moisture"], reading["temperature"], reading["accumulated_rainfall"], reading.get("status", "healthy"), reading.get("recorded_at", self.timestamp())))

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
