"""Tests for the historical event replay.

These run against the cached ERA5 rainfall under backend/data/replay_cache. If a
cache file is missing (and the machine is offline) the corresponding test skips
rather than making a network call.
"""

import unittest

from backend.replay import EVENTS, _cache_file, run_replay, summary_line


def _cached(event_id):
    return _cache_file(EVENTS[event_id]).exists()


class ReplayRegistryTests(unittest.TestCase):
    def test_has_two_events_and_a_control(self):
        controls = [e for e in EVENTS.values() if e.failure_utc is None]
        events = [e for e in EVENTS.values() if e.failure_utc is not None]
        self.assertGreaterEqual(len(events), 2)
        self.assertGreaterEqual(len(controls), 1)

    def test_unknown_event_raises(self):
        with self.assertRaises(KeyError):
            run_replay("no-such-event")


class ReplayOutcomeTests(unittest.TestCase):
    def _run(self, event_id):
        if not _cached(event_id):
            self.skipTest(f"no cached rainfall for {event_id}")
        return run_replay(event_id)

    def test_meghalaya_2022_warns_hours_ahead(self):
        r = self._run("meghalaya-2022")
        self.assertTrue(r["fired"])
        self.assertIsNotNone(r["lead_time_hours"])
        self.assertGreaterEqual(r["lead_time_hours"], 12)
        self.assertGreaterEqual(r["peak_score"], 75)          # reaches Critical
        self.assertGreaterEqual(r["critical_lead_time_hours"], 6)

    def test_sikkim_nh10_2023_warns_before_failure(self):
        r = self._run("sikkim-nh10-2023")
        self.assertTrue(r["fired"])
        self.assertGreaterEqual(r["lead_time_hours"], 6)

    def test_control_does_not_cry_wolf(self):
        r = self._run("control-meghalaya-2019")
        self.assertFalse(r["fired"])
        self.assertLess(r["peak_score"], 55)                  # never reaches "High"

    def test_steps_are_time_ordered_and_shaped(self):
        r = self._run("meghalaya-2022")
        times = [s["time"] for s in r["steps"]]
        self.assertEqual(times, sorted(times))
        for s in r["steps"]:
            self.assertIn(s["risk_level"], {"Monitoring", "Advisory", "High", "Critical"})
            self.assertGreaterEqual(s["risk_score"], 0)
            self.assertLessEqual(s["risk_score"], 100)

    def test_summary_line_mentions_lead_time(self):
        r = self._run("meghalaya-2022")
        self.assertIn("before failure", summary_line(r))


if __name__ == "__main__":
    unittest.main()
