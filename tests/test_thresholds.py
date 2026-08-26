import unittest

from backend.thresholds import operational_level, threshold_for


class ThresholdTests(unittest.TestCase):
    def test_default_operational_levels(self):
        self.assertEqual(operational_level(0), "Normal")
        self.assertEqual(operational_level(25), "Watch")
        self.assertEqual(operational_level(35), "Advisory")
        self.assertEqual(operational_level(55), "Warning")
        self.assertEqual(operational_level(75), "Critical")
        self.assertEqual(operational_level(90), "Evacuation Recommended")

    def test_district_override_is_applied(self):
        self.assertEqual(operational_level(72, "Tawang, Arunachal Pradesh"), "Critical")
        self.assertEqual(threshold_for("Unknown district")["critical"], 75)


if __name__ == "__main__":
    unittest.main()
