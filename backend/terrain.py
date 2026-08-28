"""Real DEM-derived terrain for each zone.

Elevations come from the Open-Meteo Elevation API (free, keyless, ~90 m SRTM/GLO
data). For each zone centre we sample a small grid, then derive the terrain
factors that landslide susceptibility zonation actually uses (GSI / BIS IS 14496
practice) when lithology layers are unavailable:

  * slope angle       -- primary control on shear stress
  * local relief      -- energy available for failure / runout
  * surface roughness -- proxy for past instability and structural complexity
  * profile curvature -- concave hollows concentrate subsurface flow

Results are cached under backend/data/terrain_cache/ and fall back to the static
values in zones.json if the API is unreachable.
"""

from __future__ import annotations

import json
import math
import statistics
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
CACHE_DIR = Path(__file__).resolve().parent / "data" / "terrain_cache"
GRID_RADIUS = 4          # (2R+1)^2 = 81 samples (Open-Meteo elevation caps at 100/call)
GRID_STEP_DEG = 0.011    # ~1.1 km  ->  ~9 km analysis window (the monitored corridor)
SLOPE_PERCENTILE = 88    # zone terrain factor = the steep tail, not the valley-floor centre
USER_AGENT = "CodeNexus/1.0 (landslide terrain analysis)"

# susceptibility composition (documented, tunable)
SUSC_WEIGHTS = {"slope": 0.42, "relief": 0.28, "roughness": 0.20, "curvature": 0.10}
SLOPE_FULL_DEG = 38.0        # slope angle mapped to 100 (SRTM/GLO ~90 m smooths peaks)
RELIEF_FULL_M = 1600.0       # relief across the ~8.5 km window mapped to 100
ROUGHNESS_FULL_M = 420.0     # elevation std-dev mapped to 100


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _grid_coords(lat: float, lon: float) -> list[tuple[float, float]]:
    coords = []
    for dy in range(-GRID_RADIUS, GRID_RADIUS + 1):
        for dx in range(-GRID_RADIUS, GRID_RADIUS + 1):
            coords.append((lat + dy * GRID_STEP_DEG, lon + dx * GRID_STEP_DEG))
    return coords


def fetch_elevations(coords: list[tuple[float, float]], *, timeout: float = 30.0) -> list[float]:
    query = urllib.parse.urlencode({
        "latitude": ",".join(f"{c[0]:.5f}" for c in coords),
        "longitude": ",".join(f"{c[1]:.5f}" for c in coords),
    })
    req = urllib.request.Request(f"{ELEVATION_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    elev = payload.get("elevation")
    if not isinstance(elev, list) or len(elev) != len(coords):
        raise RuntimeError("malformed elevation response")
    return [float(x) for x in elev]


def terrain_metrics(lat: float, elevations: list[float]) -> dict[str, float]:
    """Slope / relief / roughness / curvature from a flat (2R+1)^2 elevation grid."""
    side = 2 * GRID_RADIUS + 1
    if len(elevations) != side * side:
        raise ValueError("elevation grid has the wrong length")
    g = [elevations[r * side:(r + 1) * side] for r in range(side)]
    c = GRID_RADIUS

    dx_m = GRID_STEP_DEG * 111_320.0 * math.cos(math.radians(lat))
    dy_m = GRID_STEP_DEG * 110_540.0

    dz_dx = (g[c][c + 1] - g[c][c - 1]) / (2 * dx_m)
    dz_dy = (g[c + 1][c] - g[c - 1][c]) / (2 * dy_m)
    slope_deg = math.degrees(math.atan(math.hypot(dz_dx, dz_dy)))

    # slope at every interior cell, then take a high percentile: a monitored zone
    # is a corridor, and the hazard is the steepest terrain threatening it, not
    # the (often valley-floor) centre pixel.
    grads = []
    for r in range(1, side - 1):
        for col in range(1, side - 1):
            gx = (g[r][col + 1] - g[r][col - 1]) / (2 * dx_m)
            gy = (g[r + 1][col] - g[r - 1][col]) / (2 * dy_m)
            grads.append(math.degrees(math.atan(math.hypot(gx, gy))))
    grads.sort()
    mean_slope_deg = statistics.fmean(grads) if grads else slope_deg
    k = min(len(grads) - 1, int(len(grads) * SLOPE_PERCENTILE / 100)) if grads else 0
    steep_slope_deg = grads[k] if grads else slope_deg

    relief_m = max(elevations) - min(elevations)
    roughness_m = statistics.pstdev(elevations)

    d2x = (g[c][c + 1] + g[c][c - 1] - 2 * g[c][c]) / (dx_m ** 2)
    d2y = (g[c + 1][c] + g[c - 1][c] - 2 * g[c][c]) / (dy_m ** 2)
    curvature = d2x + d2y            # <0 concave (hollow), >0 convex (nose)

    return {
        "elevation_m": round(g[c][c], 1),
        "slope_deg": round(slope_deg, 2),
        "mean_slope_deg": round(mean_slope_deg, 2),
        "steep_slope_deg": round(steep_slope_deg, 2),
        "local_relief_m": round(relief_m, 1),
        "roughness_m": round(roughness_m, 2),
        "profile_curvature": curvature,
    }


def terrain_indices(m: Mapping[str, float]) -> dict[str, float]:
    """0-100 slope and susceptibility fields for the hazard model."""
    slope_deg = m.get("steep_slope_deg") or max(m["slope_deg"], m["mean_slope_deg"])
    slope_field = round(min(100.0, slope_deg / SLOPE_FULL_DEG * 100.0), 1)

    slope_term = _clamp(slope_deg / SLOPE_FULL_DEG) * 100
    relief_term = _clamp(m["local_relief_m"] / RELIEF_FULL_M) * 100
    rough_term = _clamp(m["roughness_m"] / ROUGHNESS_FULL_M) * 100
    concavity = _clamp(-m["profile_curvature"] * 5.0e4) * 100    # hollows add susceptibility
    w = SUSC_WEIGHTS
    susceptibility = round(
        w["slope"] * slope_term + w["relief"] * relief_term
        + w["roughness"] * rough_term + w["curvature"] * concavity,
        1,
    )
    return {"slope": slope_field, "susceptibility": min(100.0, susceptibility)}


def _cache_path(zone_id: str) -> Path:
    return CACHE_DIR / f"{zone_id}.json"


def resolve_terrain(zone: Mapping[str, Any], *, refresh: bool = False) -> dict[str, Any]:
    """Return {'slope','susceptibility','metrics','source'} for a zone, cached."""
    cache = _cache_path(zone["id"])
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    lat, lon = zone["coordinates"]
    prior_slope = float(zone.get("slope", 50))
    prior_susc = float(zone.get("susceptibility", 50))
    try:
        elevations = fetch_elevations(_grid_coords(lat, lon))
        metrics = terrain_metrics(lat, elevations)
        indices = terrain_indices(metrics)
        # 65 % measured DEM, 35 % curated corridor prior -- keeps a monitoring
        # point that happens to sit on the valley floor from zeroing out a zone
        # whose hazard is really on the access-road cut slopes. Drop the prior
        # once monitoring points are field-placed on the governing slopes.
        result = {
            "zone_id": zone["id"],
            "slope": round(0.65 * indices["slope"] + 0.35 * prior_slope, 1),
            "susceptibility": round(0.65 * indices["susceptibility"] + 0.35 * prior_susc, 1),
            "dem_slope": indices["slope"],
            "dem_susceptibility": indices["susceptibility"],
            "prior_slope": prior_slope,
            "prior_susceptibility": prior_susc,
            "metrics": metrics,
            "source": "Open-Meteo Elevation (SRTM/GLO ~90 m), 65/35 blend with corridor prior",
        }
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        return {
            "zone_id": zone["id"],
            "slope": float(zone.get("slope", 50)),
            "susceptibility": float(zone.get("susceptibility", 50)),
            "metrics": None,
            "source": f"static fallback ({exc})",
        }
