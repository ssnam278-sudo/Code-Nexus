"""Resolve a zone's real terrain + historical-vulnerability profile.

Merges:
  * DEM-derived slope & susceptibility           (terrain.py, Open-Meteo Elevation)
  * inventory-derived historical vulnerability     (landslide_inventory.py)
  * exposure                                       (from zones.json for now)

Each data-driven factor is blended with the curated ``zones.json`` prior so a
sparse demo inventory / a valley-floor monitoring point does not collapse a real
corridor's hazard. Blends are explicit and documented; drop the priors once the
full GSI terrain + inventory layers are wired in.

Results are cached per zone under ``backend/data/zone_profile_cache/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .landslide_inventory import history_index
from .terrain import resolve_terrain

CACHE_DIR = Path(__file__).resolve().parent / "data" / "zone_profile_cache"
HISTORY_BLEND_DEM = 0.5     # 50 % inventory density, 50 % curated prior


def _cache(zone_id: str) -> Path:
    return CACHE_DIR / f"{zone_id}.json"


def resolve_profile(zone: Mapping[str, Any], *, refresh: bool = False) -> dict[str, Any]:
    cache = _cache(zone["id"])
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    terrain = resolve_terrain(zone, refresh=refresh)

    lat, lon = zone["coordinates"]
    hist = history_index(lat, lon)
    prior_hist = float(zone.get("history", 40))
    blended_history = round(
        HISTORY_BLEND_DEM * hist["history"] + (1 - HISTORY_BLEND_DEM) * prior_hist, 1
    )

    profile = {
        "zone_id": zone["id"],
        "name": zone.get("name"),
        "coordinates": [lat, lon],
        "slope": terrain["slope"],
        "susceptibility": terrain["susceptibility"],
        "history": blended_history,
        "exposure": float(zone.get("exposure", 50)),
        "terrain_metrics": terrain.get("metrics"),
        "history_detail": {
            "inventory_score": hist["history"],
            "prior": prior_hist,
            "nearby_events": hist["nearby_events"],
            "events_within_range": hist["events_within_range"],
        },
        "sources": {
            "terrain": terrain.get("source"),
            "history": hist["source"] + f" (blended {int(HISTORY_BLEND_DEM*100)}/"
                       f"{int((1-HISTORY_BLEND_DEM)*100)} with prior)",
            "exposure": "zones.json (prototype)",
        },
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(profile, indent=1), encoding="utf-8")
    return profile


def apply_profiles(zones: list[dict[str, Any]], *, refresh: bool = False) -> list[dict[str, Any]]:
    """Overlay resolved slope/susceptibility/history onto a list of zone records."""
    out = []
    for zone in zones:
        if "coordinates" not in zone:
            out.append(zone)
            continue
        try:
            p = resolve_profile(zone, refresh=refresh)
            out.append({**zone, "slope": p["slope"], "susceptibility": p["susceptibility"],
                        "history": p["history"], "terrain_profile": {
                            "metrics": p["terrain_metrics"],
                            "history_detail": p["history_detail"],
                            "sources": p["sources"]}})
        except (OSError, RuntimeError, ValueError, KeyError):
            out.append(zone)   # keep the static values
    return out
