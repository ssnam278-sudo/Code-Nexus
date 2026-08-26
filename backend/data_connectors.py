"""API-ready contracts for environmental and geospatial data providers."""

from __future__ import annotations

from typing import Any


CONNECTORS: tuple[dict[str, Any], ...] = (
    {"id": "open-meteo", "name": "Open-Meteo live weather", "provider": "Open-Meteo", "status": "live", "variables": ["rainfall", "temperature", "soil_moisture", "forecast"]},
    {"id": "imd", "name": "IMD rainfall", "provider": "India Meteorological Department", "status": "placeholder", "variables": ["rainfall", "forecast"]},
    {"id": "gpm-chirps", "name": "GPM / CHIRPS precipitation", "provider": "NASA GPM / Climate Hazards Center", "status": "placeholder", "variables": ["rainfall", "accumulated_rainfall"]},
    {"id": "sentinel", "name": "Sentinel satellite", "provider": "Copernicus Sentinel", "status": "placeholder", "variables": ["landcover", "change_detection"]},
    {"id": "dem", "name": "Digital elevation model", "provider": "SRTM / Copernicus DEM", "status": "prepared", "variables": ["slope", "elevation"]},
    {"id": "soil-moisture", "name": "Soil moisture", "provider": "SMAP / local sensors", "status": "placeholder", "variables": ["moisture"]},
)


def source_register() -> list[dict[str, Any]]:
    """Return provider metadata without making network calls."""
    return [dict(connector, variables=list(connector["variables"])) for connector in CONNECTORS]
