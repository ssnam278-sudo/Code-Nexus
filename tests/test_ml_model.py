import unittest

from backend.ml_model import compare_risk


class MLModelTests(unittest.TestCase):
    def setUp(self):
        self.zone = {
            "rainfall": 42.6,
            "accumulated": 184,
            "moisture": 76,
            "slope": 72,
            "susceptibility": 82,
            "history": 68,
            "exposure": 86,
        }

    def test_returns_baseline_and_model_comparison(self):
        result = compare_risk(self.zone)
        # heavy monsoon on very susceptible terrain -> top of the scale
        self.assertIn(result["baseline"]["risk_level"], {"High", "Critical"})
        self.assertGreaterEqual(result["baseline"]["risk_score"], 70)
        self.assertIn(result["model"]["prediction"], {"Monitoring", "Advisory", "High", "Critical"})
        self.assertTrue(0 <= result["model"]["confidence"] <= 100)
        self.assertEqual(len(result["model"]["top_drivers"]), 3)
        self.assertIn("explanation", result["model"])

    def test_model_is_deterministic(self):
        self.assertEqual(compare_risk(self.zone), compare_risk(self.zone))


if __name__ == "__main__":
    unittest.main()
