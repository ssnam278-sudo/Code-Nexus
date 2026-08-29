# Real alert dispatch via Telegram (free, no card)

Code Nexus sends a real message when a zone first crosses into **High** or
**Critical**. The bot token lives only in an environment variable on the host
(Vercel / Render) — never in this repo.

## 1. Create the bot (2 minutes)

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, pick a name and a username ending in `bot`.
3. BotFather replies with a **token** like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   This is `TELEGRAM_BOT_TOKEN`.

## 2. Get the chat id

**Personal chat:** open a chat with **@userinfobot** and send any message — it
replies with your numeric id. That is `TELEGRAM_CHAT_ID`.

**Group / channel:** add your bot to the group, send one message in the group,
then open

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

in a browser and read `result[].message.chat.id` (group ids are negative, e.g.
`-1001234567890`).

## 3. Set the environment variables

| Host | Where |
| --- | --- |
| **Vercel** | Project → Settings → Environment Variables → add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` → redeploy |
| **Render** | Service → Environment → add the same two keys (see `render.yaml` for the commented stubs) |
| **Local** | copy `.env.example` to `.env` and fill them in |

Nothing is sent until both are present. `GET /api/health` reports
`alert_dispatch.telegram_configured`.

## 4. Verify

```bash
curl -X POST https://<your-deployment>/api/alerts/dispatch-test
# -> {"telegram":"sent"}   and a test message arrives in the chat
# (add  -H "X-Ingest-Key: <INGEST_API_KEY>"  if that variable is set)
```

Or open the **Live forecast** tab in the dashboard and click **Send test alert**.

## 5. When alerts fire

* **Live path** — `GET /api/tick` runs one rainfall pull → hazard recompute →
  dispatch. It de-dupes via the `live_alert_state` table, so each upward crossing
  sends exactly one message.
  * **Render:** the background scheduler already calls this every 15 min
    (`CODENEXUS_LIVE_INGEST=1` in `render.yaml`). Nothing else to do.
  * **Vercel:** `vercel.json` registers a daily cron on `/api/tick`. Vercel's
    free (Hobby) plan only allows **daily** cron frequency, so for true
    real-time dispatch either deploy the backend on Render, or point a free
    external pinger (e.g. cron-job.org) at `https://<deployment>/api/tick`
    every 15 minutes.
* **Demo path** — the "Run escalation demo" button drives zones into Critical
  through `POST /api/simulation`; that also dispatches (once per crossing).
  Set `CODENEXUS_ALERT_ON_SIM=0` to disable.

## Message format

**Real escalation:**

```
🚨 Code Nexus - Critical landslide risk
Tawang Corridor - Tawang, Arunachal Pradesh
Risk score: 82/100 (Critical)
Forecast: Critical projected in ~5 h
Coordinates: 27.5861, 91.8594
Action: Immediate verification; consider closing the road and moving exposed residents.
2026-08-29 12:45 IST
```

**Test alert** (`POST /api/alerts/dispatch-test`, or the "Send test alert"
button) — same layout, real zone, clearly marked. It uses the current
highest-risk zone, or `?zone_id=<id>` to pick one:

```
🧪 Code Nexus - TEST alert (wiring check, no live risk)
Tawang Corridor - Tawang, Arunachal Pradesh
Risk score: 50/100 (Advisory)
Coordinates: 27.5861, 91.8594
Action: Monitor.
2026-08-29 22:15 IST
```

Timestamps are India Standard Time via `zoneinfo` (`ZoneInfo("Asia/Kolkata")`),
so they stay correct no matter the server's own timezone.
