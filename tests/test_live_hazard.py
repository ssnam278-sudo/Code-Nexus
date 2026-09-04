"""Tests for the real-time hazard path (live_store + live_hazard + alert_dispatch).

No network: a synthetic rainfall series is written straight into a temp LiveStore.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.alert_dispatch import dispatch
from backend.live_hazard import zone_live_hazard
from backend.live_store import LiveStore

ZONE = {
    "id": "test-zone",
    "name": "Test Ridge",
    "district": "Testville",
    "coordinates": [25.3, 91.7],
    "slope": 74,
    "susceptibility": 82,
    "history": 66,
    "exposure": 70,
}


def _hours(n_past, n_future):
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for k in range(-n_past, n_future):
        yield (base + timedelta(hours=k)).strftime("%Y-%m-%dT%H:00"), k


def _write_series(store, *, past_mm_per_h, future_mm_per_h):
    rows = []
    for ts, k in _hours(360, 72):
        rows.append({
            "ts_utc": ts,
            "precip_mm": past_mm_per_h if k < 0 else future_mm_per_h,
            "kind": "observed" if k < 0 else "forecast",
        })
    store.upsert_hours(ZONE["id"], rows)


class LiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LiveStore(Path(self.tmp.name) / "live.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_upsert_is_idempotent(self):
        rows = [{"ts_utc": "2026-06-01T00:00", "precip_mm": 3.0, "kind": "observed"}]
        self.store.upsert_hours(ZONE["id"], rows)
        self.store.upsert_hours(ZONE["id"], [{**rows[0], "precip_mm": 9.0}])
        series = self.store.series(ZONE["id"])
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["precip_mm"], 9.0)

    def test_alert_level_roundtrip(self):
        self.assertEqual(self.store.alert_level(ZONE["id"]), "Monitoring")
        self.store.set_alert_level(ZONE["id"], "High", 61)
        self.assertEqual(self.store.alert_level(ZONE["id"]), "High")


class LiveHazardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LiveStore(Path(self.tmp.name) / "live.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_quiet_series_stays_low_no_lead_time(self):
        _write_series(self.store, past_mm_per_h=0.05, future_mm_per_h=0.05)
        hz = zone_live_hazard(self.store, ZONE)
        self.assertLess(hz["now"]["risk_score"], 55)
        self.assertIn(hz["forecast"]["lead_time_to_high_h"], (None, 0))

    def test_forecast_storm_produces_a_lead_time(self):
        # dry-ish now, heavy rain in the forecast -> should warn ahead of time
        _write_series(self.store, past_mm_per_h=0.3, future_mm_per_h=6.0)
        hz = zone_live_hazard(self.store, ZONE)
        fc = hz["forecast"]
        self.assertGreater(fc["projected_peak_score"], hz["now"]["risk_score"])
        self.assertIsNotNone(fc["lead_time_to_high_h"])
        self.assertGreater(fc["lead_time_to_high_h"], 0)
        self.assertEqual(len(fc["horizon"]), 4)

    def test_trajectory_is_ordered_and_tagged(self):
        _write_series(self.store, past_mm_per_h=1.0, future_mm_per_h=2.0)
        traj = zone_live_hazard(self.store, ZONE)["trajectory"]
        self.assertTrue(traj)
        self.assertEqual([s["time"] for s in traj], sorted(s["time"] for s in traj))
        self.assertEqual(traj[0]["kind"], "observed")
        self.assertEqual(traj[-1]["kind"], "forecast")
        # per-hour rainfall is exposed for the Situation Room rainfall timeline
        self.assertTrue(all(isinstance(s["rain"], (int, float)) for s in traj))
        self.assertAlmostEqual(traj[-1]["rain"], 2.0, places=3)

    def test_no_data_returns_status(self):
        self.assertEqual(zone_live_hazard(self.store, ZONE).get("status"), "no_data")


class AlertDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LiveStore(Path(self.tmp.name) / "live.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_escalation_dispatches_once_then_holds(self):
        _write_series(self.store, past_mm_per_h=5.0, future_mm_per_h=6.0)  # already wet + storming
        hz = zone_live_hazard(self.store, ZONE)
        self.assertIn(hz["now"]["risk_level"], {"High", "Critical"})

        first = dispatch(self.store, ZONE, hz)
        self.assertTrue(first["dispatched"])
        self.assertIn("cap_identifier", first)

        second = dispatch(self.store, ZONE, hz)   # same level -> no re-fire
        self.assertFalse(second["dispatched"])

    def test_no_dispatch_when_calm(self):
        _write_series(self.store, past_mm_per_h=0.02, future_mm_per_h=0.02)
        hz = zone_live_hazard(self.store, ZONE)
        self.assertFalse(dispatch(self.store, ZONE, hz)["dispatched"])


if __name__ == "__main__":
    unittest.main()
