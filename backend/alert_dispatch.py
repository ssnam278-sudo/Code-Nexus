"""Fire an alert when a zone first escalates into High or Critical.

Always: record the new level in ``live_alert_state`` and log a line.
Real dispatch channels, all free and all opt-in via environment variables:

* ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHAT_ID`` -- sends a message through the
  Telegram Bot API (https://api.telegram.org/bot<token>/sendMessage). The token
  lives only in the environment (Vercel / Render project settings), never in the
  repo. See ``TELEGRAM_SETUP.md``.
* ``ALERT_WEBHOOK_URL`` -- generic JSON webhook (Slack / Discord / any endpoint);
  a top-level ``text`` field is included for chat webhooks.

Every network failure is logged and swallowed so a dispatch problem can never
take down the request that triggered it.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .cap import build_cap_alert
from .live_store import LiveStore

_ESCALATIONS = {"High", "Critical"}
_RANK = {"Monitoring": 0, "Advisory": 1, "High": 2, "Critical": 3}

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_IST = ZoneInfo("Asia/Kolkata")


def ist_stamp() -> str:
    """Current time in India Standard Time, e.g. '2026-08-29 17:15 IST'.

    Uses the tz database (via zoneinfo / tzdata) so it stays correct regardless
    of the server's own timezone.
    """
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M IST")


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())


def webhook_configured() -> bool:
    return bool(os.getenv("ALERT_WEBHOOK_URL", "").strip())


def _post_json(url: str, body: dict[str, Any], timeout: float = 10.0) -> bool:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except OSError as exc:
        print(f"[alert_dispatch] POST {url.split('?')[0]} failed: {exc}", flush=True)
        return False


def send_telegram_message(text: str) -> bool | None:
    """Send ``text`` to the configured Telegram chat.

    Returns ``True``/``False`` on delivery success/failure, or ``None`` when
    ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID`` are not set.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None
    return _post_json(
        _TELEGRAM_API.format(token=token),
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def _lead_bits(forecast: Mapping[str, Any]) -> str:
    bits = []
    if forecast.get("lead_time_to_critical_h"):
        bits.append(f"Critical projected in ~{forecast['lead_time_to_critical_h']} h")
    elif forecast.get("lead_time_to_high_h"):
        bits.append(f"High projected in ~{forecast['lead_time_to_high_h']} h")
    return "; ".join(bits)


def alert_messages(
    zone: Mapping[str, Any],
    level: str,
    now: Mapping[str, Any],
    forecast: Mapping[str, Any] | None = None,
    *,
    test: bool = False,
) -> tuple[str, str]:
    """Return (plain_text, html_text) for one zone alert.

    ``test=True`` keeps every zone detail but swaps the banner so the recipient
    can tell it is a wiring check, not a live warning.
    """
    forecast = forecast or {}
    name = zone.get("name", zone["id"])
    district = zone.get("district", "")
    score = now["risk_score"]
    coords = zone.get("coordinates") or []
    coord_str = f"{coords[0]:.4f}, {coords[1]:.4f}" if len(coords) == 2 else "n/a"
    action = {
        "High": "Field inspection; pre-position response teams.",
        "Critical": "Immediate verification; consider closing the road and moving exposed residents.",
    }.get(level, "Monitor.")
    lead = _lead_bits(forecast)
    stamp = ist_stamp()

    if test:
        banner_plain = f"[Code Nexus] TEST alert - would notify: {level} risk"
        banner_html = "\U0001f9ea <b>Code Nexus - TEST alert</b> (wiring check, no live risk)"
    else:
        banner_plain = f"[Code Nexus] {level} landslide risk"
        banner_html = f"\U0001f6a8 <b>Code Nexus - {level} landslide risk</b>"

    plain = (
        f"{banner_plain} - {name} ({district}). "
        f"Score {score}{('; ' + lead) if lead else ''}. {action}"
    )
    html = (
        f"{banner_html}\n"
        f"<b>{name}</b>{(' - ' + district) if district else ''}\n"
        f"Risk score: <b>{score}</b>/100 ({level})\n"
        + (f"Forecast: {lead}\n" if lead else "")
        + f"Coordinates: {coord_str}\n"
        f"Action: {action}\n"
        f"<i>{stamp}</i>"
    )
    return plain, html


# backwards-compatible alias
_messages = alert_messages


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

    forecast = live_hazard.get("forecast", {})
    plain, html = _messages(zone, new_level, now, forecast)
    print(plain, flush=True)

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

    telegram_delivered = send_telegram_message(html)

    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    webhook_delivered = _post_json(webhook_url, {"text": plain, "cap": cap}) if webhook_url else None

    return {
        "dispatched": True,
        "zone": zone["id"],
        "level": new_level,
        "previous": prev_level,
        "cap_identifier": cap["identifier"],
        "telegram_delivered": telegram_delivered,
        "webhook_delivered": webhook_delivered,
        "message": plain,
    }
