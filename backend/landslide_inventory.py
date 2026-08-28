"""Historical vulnerability from a small curated inventory of real, dated
Northeast-India landslides.

This is a stand-in for the full GSI landslide inventory / NASA Global Landslide
Catalog: enough real points to make the ``history`` factor data-driven rather than
a hand-set constant. ``history_index`` is a distance- and recency-decayed density
of past failures around a location, weighted up for fatal events.

Replace ``INVENTORY`` with the full GSI inventory (or the NASA GLC CSV filtered to
the NER) before operational use.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

# (place, ISO date, lat, lon, fatal, source)
INVENTORY: list[dict[str, Any]] = [
    {"place": "Tupul / Noney, Manipur", "date": "2022-06-30", "lat": 24.68, "lon": 93.66, "fatal": True,
     "source": "Territorial Army camp slide, 55+ killed"},
    {"place": "Sohra (Cherrapunji), Meghalaya", "date": "2022-06-17", "lat": 25.30, "lon": 91.70, "fatal": True,
     "source": "Record June rainfall, multiple slides"},
    {"place": "NH-10 Rangpo-Singtam, Sikkim", "date": "2023-06-19", "lat": 27.17, "lon": 88.53, "fatal": False,
     "source": "NH-10 closed several days"},
    {"place": "Dima Hasao (New Haflong), Assam", "date": "2022-05-14", "lat": 25.16, "lon": 93.02, "fatal": True,
     "source": "Lumding-Badarpur hill section severed"},
    {"place": "Itanagar-Naharlagun, Arunachal Pradesh", "date": "2022-06-17", "lat": 27.10, "lon": 93.62, "fatal": True,
     "source": "Prolonged monsoon rainfall"},
    {"place": "Aizawl, Mizoram", "date": "2017-07-10", "lat": 23.73, "lon": 92.72, "fatal": True,
     "source": "Urban slope failures"},
    {"place": "Kalimpong / NH-10, West Bengal", "date": "2015-07-01", "lat": 27.06, "lon": 88.47, "fatal": True,
     "source": "Monsoon slides, road blockage"},
    {"place": "Lish river / Gorubathan, West Bengal", "date": "2016-07-12", "lat": 26.97, "lon": 88.68, "fatal": False,
     "source": "Debris flows on the Lish"},
    {"place": "Serchhip, Mizoram", "date": "2021-06-25", "lat": 23.30, "lon": 92.85, "fatal": False,
     "source": "Road and settlement slides"},
    {"place": "Papum Pare (NH-415), Arunachal Pradesh", "date": "2024-06-14", "lat": 27.09, "lon": 93.70, "fatal": False,
     "source": "Highway slips after heavy rain"},
    {"place": "Ukhrul, Manipur", "date": "2023-07-16", "lat": 25.05, "lon": 94.36, "fatal": False,
     "source": "Drainage failure, road slips"},
    {"place": "Mokokchung, Nagaland", "date": "2022-07-05", "lat": 26.32, "lon": 94.52, "fatal": False,
     "source": "Monsoon slope failures"},
    {"place": "Tawang district roads, Arunachal Pradesh", "date": "2022-07-01", "lat": 27.58, "lon": 91.86, "fatal": False,
     "source": "Recurrent monsoon road slides"},
    {"place": "Reiek / Mamit, Mizoram", "date": "2018-06-20", "lat": 23.70, "lon": 92.60, "fatal": False,
     "source": "Hillslope failures"},
    {"place": "Longleng, Nagaland", "date": "2019-07-20", "lat": 26.60, "lon": 94.83, "fatal": False,
     "source": "Road and terrace slides"},
]

MAX_RANGE_KM = 80.0
SPATIAL_DECAY_KM = 30.0
RECENCY_HALF_LIFE_YR = 9.0
FATAL_WEIGHT = 1.8
SQUASH = 1.3


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def history_index(lat: float, lon: float, *, as_of: date | None = None) -> dict[str, Any]:
    """Distance/recency-decayed density of past failures -> 0..100 plus context."""
    today = as_of or date.today()
    contributions = []
    total = 0.0
    for ev in INVENTORY:
        d_km = _haversine_km(lat, lon, ev["lat"], ev["lon"])
        if d_km > MAX_RANGE_KM:
            continue
        years = (today - date.fromisoformat(ev["date"])).days / 365.25
        spatial = math.exp(-d_km / SPATIAL_DECAY_KM)
        recency = math.exp(-max(0.0, years) / (RECENCY_HALF_LIFE_YR / math.log(2)))
        w = spatial * recency * (FATAL_WEIGHT if ev["fatal"] else 1.0)
        total += w
        contributions.append({"place": ev["place"], "date": ev["date"],
                              "distance_km": round(d_km, 1), "weight": round(w, 3)})
    score = round(100.0 * (1.0 - math.exp(-total / SQUASH)), 1)
    contributions.sort(key=lambda c: c["weight"], reverse=True)
    return {
        "history": score,
        "nearby_events": contributions[:5],
        "events_within_range": len(contributions),
        "source": "Curated NER landslide inventory (15 real dated events)",
    }
