"""NASA POWER surface soil-moisture adapter for Code Nexus.

NASA POWER (https://power.larc.nasa.gov/) serves daily agro-climatology from the
MERRA-2 / GEOS assimilation. No API key. ``GWETTOP`` is the top-layer soil
wetness fraction (0-1); we take the most recent valid day and report it as a
percentage.

POWER's daily product lags a few days ("near real-time / preliminary"), so this
is *latest available*, not this-hour. The dashboard labels it accordingly and
keeps Open-Meteo's 0-7 cm soil moisture as a same-cycle cross-check.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any, Mapping


POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
_FILL = -999.0
_PARAMETERS = "GWETTOP,GWETROOT"


def fetch_soil_moisture(zone: Mapping[str, Any], timeout: float = 8.0) -> dict[str, Any]:
	"""Latest valid daily surface soil wetness for one zone, as a percentage."""
	latitude, longitude = zone["coordinates"]
	end = datetime.now(timezone.utc).date()
	start = end - timedelta(days=10)          # POWER lags a few days; widen the window
	query = urlencode({
		"parameters": _PARAMETERS,
		"community": "AG",
		"latitude": latitude,
		"longitude": longitude,
		"start": start.strftime("%Y%m%d"),
		"end": end.strftime("%Y%m%d"),
		"format": "JSON",
	})
	request = Request(f"{POWER_URL}?{query}", headers={"User-Agent": "CodeNexus/1.0"})
	with urlopen(request, timeout=timeout) as response:
		payload = json.load(response)

	parameters = (payload.get("properties", {}) or {}).get("parameter", {}) or {}
	top = parameters.get("GWETTOP", {}) or {}
	root = parameters.get("GWETROOT", {}) or {}
	if not top:
		raise ValueError("NASA POWER response has no GWETTOP series")

	# newest date with a real value
	for day in sorted(top, reverse=True):
		raw = top.get(day)
		if raw is None or float(raw) <= _FILL:
			continue
		fraction = max(0.0, min(1.0, float(raw)))
		root_raw = root.get(day)
		root_fraction = (
			max(0.0, min(1.0, float(root_raw)))
			if root_raw is not None and float(root_raw) > _FILL
			else None
		)
		observed = datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)
		return {
			"zone_id": zone["id"],
			"soil_moisture": round(fraction * 100.0, 1),
			"root_zone_soil_moisture": round(root_fraction * 100.0, 1) if root_fraction is not None else None,
			"soil_source": "nasa-power",
			"parameter": "GWETTOP",
			"observed_at": observed.isoformat(),
			"provider": "NASA POWER",
			"provider_url": POWER_URL,
			"fetched_at": datetime.now(timezone.utc).isoformat(),
		}
	raise ValueError("NASA POWER returned only fill values for GWETTOP")
