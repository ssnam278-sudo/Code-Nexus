"""Fire an alert when a zone first escalates into High or Critical.

Always: record the new level in ``live_alert_state`` and log a line.
Optionally: POST the CAP payload to ``ALERT_WEBHOOK_URL`` (works with Slack /
Discord / Telegram-bot / any JSON endpoint -- a top-level ``text`` field is
included for chat webhooks).
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Mapping

from .cap import build_cap_alert
from .live_store import LiveStore

_ESCALATIONS = {"High", "Critical"}
_RANK = {"Monitoring": 0, "Advisory": 1, "High": 2, "Critical": 3}


def _post_webhook(url: str, body: dict[str, Any]) -> bool:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except OSError as exc:
        print(f"[alert_dispatch] webhook failed: {exc}", flush=True)
        return False


def dispatch(store: LiveStore, zone: Mapping[str, Any], live_hazard: Mapping[str, Any]) -> dict[str, Any]:
    """Compare current level to the stored one; act only on an *upward* crossing."""
    now = live_hazard.get("now")
    if not now:
        return {"dispatched": False, "reason": "no hazard"}

    new_level = now["risk_level"]
    prev_level = store.alert_level(zone["id"])
    store.set_alert_level(zone["id"], new_level, now["risk_score"])

    escalated = _RANK[new_level] > _RANK[prev_level] and new_level in _ESCALATIONS
    if not escalated:
        return {"dispatched": False, "zone": zone["id"], "level": new_level, "previous": prev_level}

    fc = live_hazard.get("forecast", {})
    payload = {
        "risk_level": new_level,
        "risk_score": now["risk_score"],
        "explanation": now.get("method", "Rainfall-triggered hazard model"),
        "recommended_action": {
            "High": "Field inspection; pre-position response teams.",
            "Critical": "Immediate verification; consider closing the road and moving exposed residents.",
        }.get(new_level, "Monitor."),
        "api_mm": now.get("api_mm"),
        "exceedance_ratio": now.get("exceedance_ratio"),
    }
    cap = build_cap_alert(zone, payload)

    lead_bits = []
    if fc.get("lead_time_to_critical_h"):
        lead_bits.append(f"Critical projected in ~{fc['lead_time_to_critical_h']} h")
    elif fc.get("lead_time_to_high_h"):
        lead_bits.append(f"High projected in ~{fc['lead_time_to_high_h']} h")
    lead = ("; " + ", ".join(lead_bits)) if lead_bits else ""

    text = (f"[Code Nexus] {new_level} landslide risk - {zone.get('name', zone['id'])} "
            f"({zone.get('district', '')}). Score {now['risk_score']}{lead}.")
    print(text, flush=True)

    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    delivered = None
    if webhook_url:
        delivered = _post_webhook(webhook_url, {"text": text, "cap": cap})

    return {
        "dispatched": True,
        "zone": zone["id"],
        "level": new_level,
        "previous": prev_level,
        "cap_identifier": cap["identifier"],
        "webhook_delivered": delivered,
        "message": text,
    }
