import io
import json
import unittest
from unittest.mock import patch

from backend.nasa_power import fetch_soil_moisture


def _resp(payload):
    r = io.BytesIO(json.dumps(payload).encode())
    r.__enter__ = lambda self: self
    r.__exit__ = lambda *a: None
    return r


class NasaPowerTests(unittest.TestCase):
    def test_takes_newest_valid_day_as_percentage(self):
        payload = {
            "properties": {
                "parameter": {
                    "GWETTOP": {"20260825": 0.41, "20260826": 0.55, "20260827": -999.0},
                    "GWETROOT": {"20260826": 0.60},
                }
            }
        }
        with patch("backend.nasa_power.urlopen", return_value=_resp(payload)):
            reading = fetch_soil_moisture({"id": "tawang", "coordinates": [27.58, 91.86]})
        self.assertEqual(reading["soil_moisture"], 55.0)          # 0.55 * 100, newest non-fill
        self.assertEqual(reading["soil_source"], "nasa-power")
        self.assertEqual(reading["root_zone_soil_moisture"], 60.0)
        self.assertIn("observed_at", reading)

    def test_all_fill_raises(self):
        payload = {"properties": {"parameter": {"GWETTOP": {"20260826": -999.0}}}}
        with patch("backend.nasa_power.urlopen", return_value=_resp(payload)):
            with self.assertRaises(ValueError):
                fetch_soil_moisture({"id": "x", "coordinates": [1, 2]})


if __name__ == "__main__":
    unittest.main()
