"""Open-Meteo current weather adapter for Code Nexus."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any, Mapping


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_current(zone: Mapping[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    """Fetch and normalize current Open-Meteo conditions for one zone."""
    latitude, longitude = zone["coordinates"]
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,precipitation,rain,relative_humidity_2m,soil_moisture_0_to_1cm",
        "hourly": "precipitation",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    })
    request = Request(f"{OPEN_METEO_URL}?{query}", headers={"User-Agent": "CodeNexus/1.0"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    current = payload.get("current", {})
    hourly = payload.get("hourly", {})
    precipitation = hourly.get("precipitation", [])[-24:]
    required = ("time", "temperature_2m", "precipitation", "soil_moisture_0_to_1cm")
    if any(field not in current for field in required):
        raise ValueError("Open-Meteo response is missing current weather fields")
    return {
        "zone_id": zone["id"],
        "sensor_id": f"open-meteo-{zone['id']}",
        "rainfall": max(0.0, float(current["precipitation"])),
        "soil_moisture": max(0.0, min(100.0, float(current["soil_moisture_0_to_1cm"]) * 100)),
        "temperature": float(current["temperature_2m"]),
        "accumulated_rainfall": round(max(0.0, sum(float(value or 0) for value in precipitation)), 2),
        "status": "healthy",
        "recorded_at": f"{current['time']}:00+00:00" if len(str(current["time"])) == 16 else str(current["time"]),
        "provider": "Open-Meteo",
        "provider_url": OPEN_METEO_URL,
    }
