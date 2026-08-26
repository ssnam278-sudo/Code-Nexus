"""North Eastern Region operator thresholds and alert vocabulary."""

from __future__ import annotations

from typing import Any


ALERT_LEVELS = (
    "Normal",
    "Watch",
    "Advisory",
    "Warning",
    "Critical",
    "Evacuation Recommended",
)

# District overrides are intentionally configuration, not hard-coded engine logic.
DISTRICT_THRESHOLDS: dict[str, dict[str, int]] = {
    "default": {"watch": 25, "advisory": 35, "warning": 55, "critical": 75, "evacuation": 90},
    "Tawang": {"watch": 22, "advisory": 32, "warning": 52, "critical": 72, "evacuation": 88},
    "East Siang": {"watch": 24, "advisory": 34, "warning": 54, "critical": 74, "evacuation": 90},
    "Churachandpur": {"watch": 25, "advisory": 35, "warning": 55, "critical": 75, "evacuation": 90},
}


def threshold_for(district: str | None = None) -> dict[str, int]:
    name = (district or "").split(",")[0].strip()
    return dict(DISTRICT_THRESHOLDS.get(name, DISTRICT_THRESHOLDS["default"]))


def operational_level(score: int, district: str | None = None) -> str:
    thresholds = threshold_for(district)
    if score >= thresholds["evacuation"]:
        return "Evacuation Recommended"
    if score >= thresholds["critical"]:
        return "Critical"
    if score >= thresholds["warning"]:
        return "Warning"
    if score >= thresholds["advisory"]:
        return "Advisory"
    if score >= thresholds["watch"]:
        return "Watch"
    return "Normal"
