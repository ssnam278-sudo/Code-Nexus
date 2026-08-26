import io
import json
import unittest
from unittest.mock import patch

from backend.open_meteo import fetch_current


class OpenMeteoTests(unittest.TestCase):
    def test_normalizes_current_weather_response(self):
        payload = {
            "current": {
                "time": "2026-08-26T08:30",
                "temperature_2m": 32.6,
                "precipitation": 1.2,
                "soil_moisture_0_to_1cm": 0.33,
            },
            "hourly": {"precipitation": [0.1] * 24},
        }
        response = io.BytesIO(json.dumps(payload).encode())
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        with patch("backend.open_meteo.urlopen", return_value=response):
            reading = fetch_current({"id": "tawang", "coordinates": [27.4, 94.9]})
        self.assertEqual(reading["sensor_id"], "open-meteo-tawang")
        self.assertEqual(reading["rainfall"], 1.2)
        self.assertEqual(reading["soil_moisture"], 33.0)
        self.assertEqual(reading["accumulated_rainfall"], 2.4)
        self.assertEqual(reading["provider"], "Open-Meteo")


if __name__ == "__main__":
    unittest.main()
