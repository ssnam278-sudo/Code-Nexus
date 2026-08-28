"""Persistence for the real-time rainfall feed and live alert state.

Kept separate from ``simulator.DataStore`` so the live path can be added without
touching the demo/persistence code. It opens the same SQLite file and owns two
tables of its own.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rainfall_hourly (
    zone_id     TEXT NOT NULL,
    ts_utc      TEXT NOT NULL,          -- 'YYYY-MM-DDTHH:00'
    precip_mm   REAL NOT NULL,
    kind        TEXT NOT NULL,          -- 'observed' | 'forecast'
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (zone_id, ts_utc)
);
CREATE TABLE IF NOT EXISTS live_alert_state (
    zone_id     TEXT PRIMARY KEY,
    level       TEXT NOT NULL,
    risk_score  INTEGER NOT NULL,
    changed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_ingest_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT NOT NULL,
    zones       INTEGER NOT NULL,
    hours       INTEGER NOT NULL,
    detail      TEXT
);
"""


class LiveStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c, c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- rainfall ---------------------------------------------------------
    def upsert_hours(self, zone_id: str, rows: Iterable[Mapping[str, object]]) -> int:
        fetched = self.now()
        payload = [
            (zone_id, r["ts_utc"], float(r["precip_mm"]), str(r["kind"]), fetched)
            for r in rows
        ]
        if not payload:
            return 0
        with closing(self._conn()) as c, c:
            c.executemany(
                "INSERT INTO rainfall_hourly (zone_id, ts_utc, precip_mm, kind, fetched_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(zone_id, ts_utc) DO UPDATE SET "
                "precip_mm=excluded.precip_mm, kind=excluded.kind, fetched_at=excluded.fetched_at",
                payload,
            )
        return len(payload)

    def series(self, zone_id: str) -> list[dict]:
        with closing(self._conn()) as c, c:
            rows = c.execute(
                "SELECT ts_utc, precip_mm, kind FROM rainfall_hourly "
                "WHERE zone_id = ? ORDER BY ts_utc",
                (zone_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def has_data(self) -> bool:
        with closing(self._conn()) as c, c:
            return c.execute("SELECT 1 FROM rainfall_hourly LIMIT 1").fetchone() is not None

    def prune_older_than(self, ts_utc: str) -> int:
        with closing(self._conn()) as c, c:
            cur = c.execute("DELETE FROM rainfall_hourly WHERE ts_utc < ?", (ts_utc,))
            return cur.rowcount

    # --- alert state ----------------------------------------------------
    def alert_level(self, zone_id: str) -> str:
        with closing(self._conn()) as c, c:
            row = c.execute(
                "SELECT level FROM live_alert_state WHERE zone_id = ?", (zone_id,)
            ).fetchone()
        return row["level"] if row else "Monitoring"

    def set_alert_level(self, zone_id: str, level: str, risk_score: int) -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "INSERT INTO live_alert_state (zone_id, level, risk_score, changed_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(zone_id) DO UPDATE SET level=excluded.level, "
                "risk_score=excluded.risk_score, changed_at=excluded.changed_at",
                (zone_id, level, int(risk_score), self.now()),
            )

    def log_ingest(self, zones: int, hours: int, detail: str = "") -> None:
        with closing(self._conn()) as c, c:
            c.execute(
                "INSERT INTO live_ingest_log (ran_at, zones, hours, detail) VALUES (?, ?, ?, ?)",
                (self.now(), zones, hours, detail),
            )

    def last_ingest(self) -> dict | None:
        with closing(self._conn()) as c, c:
            row = c.execute(
                "SELECT ran_at, zones, hours, detail FROM live_ingest_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
