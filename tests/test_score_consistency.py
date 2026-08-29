"""One score per zone: /api/zones, /api/risk, /api/simulation and the Live
Forecast 'now' value must all agree for the same zone + scenario."""

import unittest

from backend.app import app, _zone_records, _risk_record, _overlay_unified_now
from backend.live_hazard import all_live_hazards


class ScoreConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_zones_and_risk_endpoints_match(self):
        zones = self.client.get("/api/zones").get_json()
        for z in zones:
            single = self.client.get(f"/api/risk?zone_id={z['id']}").get_json()
            self.assertEqual(z["risk_score"], single["risk_score"], z["id"])
            self.assertEqual(z["risk_level"], single["risk_level"], z["id"])

    def test_simulation_matches_risk_record(self):
        payload = self.client.post("/api/simulation", json={"scenario": "Heavy Rain"}).get_json()
        for result in payload["results"]:
            record = next(z for z in _zone_records() if z["id"] == result["zone_id"])
            expected = _risk_record(record, "Heavy Rain")
            self.assertEqual(result["risk_score"], expected["risk_score"], result["zone_id"])

    def test_field_report_binds_to_its_zone_and_clears(self):
        self.client.post("/api/reports/clear")
        r = self.client.post("/api/reports", json={
            "zone_id": "garo", "location": "South Garo Hills",
            "observation": "fresh scarp", "severity": "Critical", "status": "Under review",
        })
        self.assertEqual(r.status_code, 201)
        garo = self.client.get("/api/risk?zone_id=garo").get_json()
        tawang = self.client.get("/api/risk?zone_id=tawang").get_json()
        self.assertIsNotNone(garo.get("ground_truth"), "report must adjust its own zone")
        self.assertIsNone(tawang.get("ground_truth"), "report must not touch other zones")
        cleared = self.client.delete("/api/reports").get_json()
        self.assertGreaterEqual(cleared["cleared"], 1)
        self.assertIsNone(self.client.get("/api/risk?zone_id=garo").get_json().get("ground_truth"))

    def test_live_forecast_now_uses_unified_score(self):
        records = [z for z in _zone_records() if all(k in z for k in ("slope", "susceptibility", "history", "coordinates"))]
        # feed the overlay a fake hazard payload and confirm it rewrites now-scores
        fake = {"zones": [{"zone_id": records[0]["id"], "now": {"risk_score": 3, "risk_level": "Monitoring"}}]}
        out = _overlay_unified_now(fake)
        unified = _risk_record(records[0])
        self.assertEqual(out["zones"][0]["now"]["risk_score"], unified["risk_score"])
        self.assertEqual(out["zones"][0]["now"]["trigger_model_score"], 3)


if __name__ == "__main__":
    unittest.main()
