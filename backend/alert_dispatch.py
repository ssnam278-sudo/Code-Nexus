"""Fire an alert when a zone first escalates into High or Critical.

Always: record the new level in ``live_alert_state`` and log a line.
Real dispatch channels, all opt-in via environment variables:

* ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHAT_ID`` -- Telegram Bot API message.
* ``SMS_TO`` (+ optional ``SMS_PROVIDER``) -- a real phone SMS:
    - ``textbelt``  (default) POST to https://textbelt.com/text. Works with the
      shared free key ``textbelt`` (1 SMS/day) or your own ``TEXTBELT_KEY``.
    - ``twilio``    needs ``TWILIO_ACCOUNT_SID`` / ``TWILIO_AUTH_TOKEN`` / ``TWILIO_FROM``.
    - ``fast2sms``  (India) needs ``FAST2SMS_KEY``.
* ``ALERT_WEBHOOK_URL`` -- generic JSON webhook (Slack / Discord / any endpoint).

The token/keys live only in the environment (Vercel / Render project settings),
never in the repo. See ``ALERTS_SETUP.md``. Every network failure is logged and
swallowed so a dispatch problem can never take down the request that triggered it.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
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


def _sms_provider() -> str:
    return (os.getenv("SMS_PROVIDER") or "textbelt").strip().lower()


def sms_configured() -> bool:
    if not os.getenv("SMS_TO", "").strip():
        return False
    provider = _sms_provider()
    if provider == "twilio":
        return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and os.getenv("TWILIO_FROM"))
    if provider == "fast2sms":
        return bool(os.getenv("FAST2SMS_KEY", "").strip())
    return True   # textbelt works with the shared free key


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


def _post_form(url: str, fields: dict[str, str], headers: dict[str, str] | None = None, timeout: float = 15.0) -> bool:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            ok = 200 <= resp.status < 300
            if "textbelt.com" in url:
                try:
                    ok = ok and bool(json.loads(body).get("success"))
                except ValueError:
                    ok = False
            return ok
    except OSError as exc:
        print(f"[alert_dispatch] SMS POST {url} failed: {exc}", flush=True)
        return False


def _sms_textbelt(number: str, text: str) -> bool:
    return _post_form("https://textbelt.com/text", {
        "phone": number,
        "message": text[:320],
        "key": os.getenv("TEXTBELT_KEY", "textbelt").strip() or "textbelt",
    })


def _sms_twilio(number: str, text: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    frm = os.getenv("TWILIO_FROM", "").strip()
    if not (sid and token and frm):
        return False
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    return _post_form(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        {"To": number, "From": frm, "Body": text[:1500]},
        headers={"Authorization": "Basic " + auth},
    )


def _sms_fast2sms(number: str, text: str) -> bool:
    key = os.getenv("FAST2SMS_KEY", "").strip()
    if not key:
        return False
    digits = number.replace("+91", "").replace("+", "").strip()
    return _post_form(
        "https://www.fast2sms.com/dev/bulkV2",
        {"route": "q", "language": "english", "message": text[:300], "numbers": digits},
        headers={"authorization": key},
    )


def send_sms(text: str) -> bool | None:
    """Send ``text`` as an SMS to every number in ``SMS_TO``.

    Returns ``True``/``False`` on success/failure, or ``None`` when ``SMS_TO`` is
    not set. Provider is ``SMS_PROVIDER`` (``textbelt`` default / ``twilio`` /
    ``fast2sms``).
    """
    to = os.getenv("SMS_TO", "").strip()
    if not to:
        return None
    numbers = [n.strip() for n in to.replace(";", ",").split(",") if n.strip()]
    provider = _sms_provider()
    sender = {"twilio": _sms_twilio, "fast2sms": _sms_fast2sms}.get(provider, _sms_textbelt)
    results = [sender(n, text) for n in numbers]
    return bool(results) and all(results)


def sms_text(
    zone: Mapping[str, Any],
    level: str,
    now: Mapping[str, Any],
    forecast: Mapping[str, Any] | None = None,
    *,
    test: bool = False,
) -> str:
    """Short single-message SMS form of an alert (kept under ~2 segments)."""
    name = zone.get("name", zone["id"])
    score = now["risk_score"]
    lead = _lead_bits(forecast or {})
    action = {
        "High": "Inspect & pre-position teams.",
        "Critical": "Verify now; move exposed residents.",
    }.get(level, "Monitor.")
    prefix = "TEST " if test else ""
    msg = f"{prefix}Code Nexus ALERT: {level} landslide risk - {name}. Score {score}/100."
    if lead:
        msg += f" {lead}."
    msg += f" {action} {ist_stamp()}"
    return msg[:320]


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
    sms_delivered = send_sms(sms_text(zone, new_level, now, forecast))

    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    webhook_delivered = _post_json(webhook_url, {"text": plain, "cap": cap}) if webhook_url else None

    return {
        "dispatched": True,
        "zone": zone["id"],
        "level": new_level,
        "previous": prev_level,
        "cap_identifier": cap["identifier"],
        "telegram_delivered": telegram_delivered,
        "sms_delivered": sms_delivered,
        "webhook_delivered": webhook_delivered,
        "message": plain,
    }
