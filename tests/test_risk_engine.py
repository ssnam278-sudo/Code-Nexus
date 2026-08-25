import unittest

from backend.risk_engine import _level, calculate_risk
from backend.simulator import simulate_zone


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


if __name__ == "__main__":
    unittest.main()