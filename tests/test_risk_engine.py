import unittest

from backend.risk_engine import _level, calculate_risk
from backend.simulator import apply_ground_truth, simulate_zone


BASE_ZONE = {
    "rainfall": 7.4,
    "accumulated": 42,
    "moisture": 29,
    "slope": 38,
    "susceptibility": 34,
    "history": 25,
    "exposure": 32,
}


class RiskEngineTests(unittest.TestCase):
    def test_low_stable_conditions(self):
        result = calculate_risk(BASE_ZONE)
        self.assertEqual(result["risk_level"], "Monitoring")
        self.assertLess(result["risk_score"], 35)

    def test_moderate_conditions(self):
        zone = {**BASE_ZONE, "rainfall": 18.4, "accumulated": 96, "moisture": 51, "slope": 55, "susceptibility": 59, "history": 48, "exposure": 63}
        self.assertEqual(calculate_risk(zone)["risk_level"], "Advisory")

    def test_heavy_and_extreme_rain_increase_risk(self):
        zone = {**BASE_ZONE, "slope": 72, "susceptibility": 82, "history": 68, "exposure": 86}
        normal = simulate_zone(zone, "Normal")
        heavy = simulate_zone(zone, "Heavy Rain")
        extreme = simulate_zone(zone, "Extreme Rain")
        self.assertLess(normal["risk_score"], heavy["risk_score"])
        self.assertLess(heavy["risk_score"], extreme["risk_score"])
        self.assertIn(extreme["risk_level"], {"High", "Critical"})

    def test_recovery_decreases_risk(self):
        zone = {**BASE_ZONE, "rainfall": 42.6, "accumulated": 184, "moisture": 76, "slope": 72, "susceptibility": 82, "history": 68, "exposure": 86}
        self.assertLess(simulate_zone(zone, "Recovery")["risk_score"], simulate_zone(zone, "Heavy Rain")["risk_score"])

    def test_deterministic_and_bounded(self):
        self.assertEqual(calculate_risk(BASE_ZONE), calculate_risk(BASE_ZONE))
        result = calculate_risk({field: 100 for field in BASE_ZONE})
        self.assertTrue(0 <= result["risk_score"] <= 100)

    def test_thresholds(self):
        expected = ((0, "Monitoring"), (34, "Monitoring"), (35, "Advisory"), (54, "Advisory"), (55, "High"), (74, "High"), (75, "Critical"), (100, "Critical"))
        for score, level in expected:
            self.assertEqual(_level(score), level)

    def test_invalid_input(self):
        for field, value in (("rainfall", -1), ("moisture", 101), ("slope", "steep"), ("history", None)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                calculate_risk({**BASE_ZONE, field: value})

    def test_confidence_reflects_feed_freshness(self):
        live = calculate_risk(BASE_ZONE, {"data_source": "open-meteo", "feed_age_seconds": 300})
        sim = calculate_risk(BASE_ZONE, {"data_source": "simulated"})
        self.assertGreater(live["confidence"], sim["confidence"])
        self.assertTrue(live["confidence_basis"])
        self.assertTrue(40 <= sim["confidence"] <= 97)

    def test_formula_and_weights_published(self):
        result = calculate_risk(BASE_ZONE)
        self.assertIn("formula", result)
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0, places=6)
        contributions = sum(f["contribution"] for f in result["contributing_factors"])
        self.assertEqual(round(contributions), result["risk_score"])

    def test_critical_field_report_bumps_score(self):
        result = simulate_zone({**BASE_ZONE, "slope": 60, "susceptibility": 60, "history": 55}, "Normal")
        before = result["risk_score"]
        gt = apply_ground_truth(result, {"severity": "Critical", "status": "Under review", "observation": "fresh scarp"})
        self.assertIsNotNone(gt)
        self.assertGreater(result["risk_score"], before)
        self.assertEqual(gt["delta_score"], result["risk_score"] - before)

    def test_verified_critical_report_forces_critical_band(self):
        result = simulate_zone(BASE_ZONE, "Normal")  # a Monitoring-level zone
        apply_ground_truth(result, {"severity": "Critical", "status": "Verified", "observation": "road buried"})
        self.assertGreaterEqual(result["risk_score"], 75)
        self.assertEqual(result["risk_level"], "Critical")

    def test_rejected_report_is_ignored(self):
        result = simulate_zone(BASE_ZONE, "Normal")
        self.assertIsNone(apply_ground_truth(result, {"severity": "Critical", "status": "Rejected", "observation": "x"}))


if __name__ == "__main__":
    unittest.main()