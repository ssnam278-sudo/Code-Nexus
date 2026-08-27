"""Tests for the rainfall-triggered hazard model."""

import unittest

from backend.rainfall_model import (
    antecedent_index,
    classify,
    hazard,
    id_critical_intensity,
    predisposition_index,
    storm_exceedance,
    trigger_index,
    wetness_index,
)


class AntecedentIndexTests(unittest.TestCase):
    def test_decays_older_rain(self):
        recent = antecedent_index([0, 0, 0, 0, 50])
        old = antecedent_index([50, 0, 0, 0, 0])
        self.assertGreater(recent, old)

    def test_zero_series_is_zero(self):
        self.assertEqual(antecedent_index([0, 0, 0]), 0.0)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            antecedent_index([1, -2, 3])

    def test_wetness_is_monotonic_and_bounded(self):
        self.assertAlmostEqual(wetness_index(0), 0.0)
        self.assertLess(wetness_index(50), wetness_index(150))
        self.assertLessEqual(wetness_index(10_000), 1.0)


class IntensityDurationTests(unittest.TestCase):
    def test_threshold_decreases_with_duration(self):
        # a long storm can trigger at a lower mean intensity than a short one
        self.assertGreater(id_critical_intensity(3), id_critical_intensity(48))

    def test_exceedance_flags_a_real_storm(self):
        # 72 h of steady 6 mm/h is well above Caine's line
        result = storm_exceedance([6.0] * 80)
        self.assertGreater(result["ratio"], 1.0)
        self.assertIn(result["duration_h"], (3, 6, 12, 24, 48, 72))

    def test_light_drizzle_stays_below_threshold(self):
        result = storm_exceedance([0.4] * 80)
        self.assertLess(result["ratio"], 1.0)


class TriggerAndCompositionTests(unittest.TestCase):
    def test_dry_cloudburst_is_damped_vs_wet_cloudburst(self):
        dry = trigger_index(api_mm=5, exceedance_ratio=1.5)
        wet = trigger_index(api_mm=200, exceedance_ratio=1.5)
        self.assertLess(dry, wet)

    def test_predisposition_bounds(self):
        self.assertAlmostEqual(predisposition_index(0, 0, 0), 0.0)
        self.assertAlmostEqual(predisposition_index(100, 100, 100), 1.0)
        with self.assertRaises(ValueError):
            predisposition_index(120, 50, 50)

    def test_hazard_rises_with_rain_on_a_fixed_slope(self):
        base = dict(slope=70, susceptibility=75, history=60)
        dry = hazard(**base, api_mm=10, exceedance_ratio=0.1)
        storm = hazard(**base, api_mm=220, exceedance_ratio=2.0)
        self.assertLess(dry["risk_score"], storm["risk_score"])
        self.assertEqual(storm["risk_level"], classify(storm["risk_score"]))

    def test_hazard_score_is_bounded(self):
        hi = hazard(slope=100, susceptibility=100, history=100, api_mm=9999, exceedance_ratio=99)
        lo = hazard(slope=1, susceptibility=1, history=1, api_mm=0, exceedance_ratio=0)
        self.assertLessEqual(hi["risk_score"], 100)
        self.assertGreaterEqual(lo["risk_score"], 0)

    def test_levels(self):
        self.assertEqual(classify(80), "Critical")
        self.assertEqual(classify(60), "High")
        self.assertEqual(classify(40), "Advisory")
        self.assertEqual(classify(10), "Monitoring")


if __name__ == "__main__":
    unittest.main()
