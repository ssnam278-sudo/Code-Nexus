"""Common Alerting Protocol (CAP 1.2) output for Code Nexus alerts.

CAP is the OASIS standard India's NDMA uses for public warnings (the SACHET /
"Common Alerting Protocol India" platform). Emitting CAP means an alert produced
here can be handed straight to SACHET, state SDMA dashboards, cell broadcast, or
sirens without reformatting.

`build_cap_alert` returns a plain dict mirroring the CAP XML structure; `to_xml`
renders the wire format. This is a prototype: identifiers are synthetic and the
message is NOT signed. Production use needs a registered sender id, XML signature,
and an authorised issuing officer in the loop.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping
from xml.sax.saxutils import escape

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

# risk level -> (CAP severity, urgency, certainty, response)
_LEVEL_MAP = {
    "Critical": ("Extreme", "Immediate", "Likely", "Evacuate"),
    "High": ("Severe", "Expected", "Likely", "Prepare"),
    "Advisory": ("Moderate", "Future", "Possible", "Monitor"),
    "Monitoring": ("Minor", "Future", "Unlikely", "Monitor"),
}
_HEADLINE = {
    "Critical": "Landslide warning: move to safety now",
    "High": "Landslide alert: be ready to move",
    "Advisory": "Landslide advisory: stay alert",
    "Monitoring": "Landslide watch: no action needed",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_cap_alert(
    zone: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    sender: str = "codenexus@sdma.nic.in.example",
    impact_radius_km: float | None = None,
) -> dict[str, Any]:
    level = str(risk.get("risk_level", "Monitoring"))
    severity, urgency, certainty, response = _LEVEL_MAP.get(level, _LEVEL_MAP["Monitoring"])
    score = int(risk.get("risk_score", 0))
    lat, lon = (zone.get("coordinates") or [None, None])[:2]
    radius = impact_radius_km if impact_radius_km is not None else round(2.5 + score * 0.065, 1)

    seed = f"{zone.get('id')}|{_now()[:13]}|{level}"
    identifier = "codenexus-" + hashlib.sha1(seed.encode()).hexdigest()[:16]

    params = [
        {"valueName": "risk_score", "value": str(score)},
        {"valueName": "method", "value": str(risk.get("method", "Code Nexus hazard model"))},
    ]
    if "api_mm" in risk:
        params.append({"valueName": "antecedent_rainfall_mm", "value": str(risk["api_mm"])})
    if "exceedance_ratio" in risk:
        params.append({"valueName": "id_threshold_exceedance", "value": str(risk["exceedance_ratio"])})

    area: dict[str, Any] = {"areaDesc": zone.get("district") or zone.get("name") or "Monitored zone"}
    if lat is not None and lon is not None:
        area["circle"] = f"{lat},{lon} {radius}"

    return {
        "identifier": identifier,
        "sender": sender,
        "sent": _now(),
        "status": "Exercise",          # prototype: not a real public alert
        "msgType": "Alert",
        "scope": "Public",
        "info": {
            "language": "en-IN",
            "category": "Geo",
            "event": "Landslide",
            "urgency": urgency,
            "severity": severity,
            "certainty": certainty,
            "responseType": response,
            "headline": _HEADLINE.get(level, _HEADLINE["Monitoring"]),
            "description": str(risk.get("explanation") or risk.get("reason") or ""),
            "instruction": str(risk.get("recommended_action")
                               or "Follow instructions from local authorities."),
            "senderName": "Code Nexus (prototype) — District Disaster Management",
            "parameter": params,
            "area": area,
        },
    }


def to_xml(alert: Mapping[str, Any]) -> str:
    info = alert["info"]

    def tag(name: str, value: Any) -> str:
        return f"<{name}>{escape(str(value))}</{name}>"

    params = "".join(
        f"<parameter>{tag('valueName', p['valueName'])}{tag('value', p['value'])}</parameter>"
        for p in info.get("parameter", [])
    )
    area = info["area"]
    area_xml = tag("areaDesc", area["areaDesc"])
    if area.get("circle"):
        area_xml += tag("circle", area["circle"])

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<alert xmlns="{CAP_NS}">'
        f"{tag('identifier', alert['identifier'])}{tag('sender', alert['sender'])}"
        f"{tag('sent', alert['sent'])}{tag('status', alert['status'])}"
        f"{tag('msgType', alert['msgType'])}{tag('scope', alert['scope'])}"
        f"<info>"
        f"{tag('language', info['language'])}{tag('category', info['category'])}"
        f"{tag('event', info['event'])}{tag('urgency', info['urgency'])}"
        f"{tag('severity', info['severity'])}{tag('certainty', info['certainty'])}"
        f"{tag('responseType', info['responseType'])}{tag('headline', info['headline'])}"
        f"{tag('description', info['description'])}{tag('instruction', info['instruction'])}"
        f"{tag('senderName', info['senderName'])}{params}"
        f"<area>{area_xml}</area>"
        f"</info></alert>"
    )
