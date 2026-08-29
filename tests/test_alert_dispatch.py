"""Telegram / dispatch wiring — no network: urlopen is patched."""

import io
import json
import unittest
from unittest.mock import patch

from backend import alert_dispatch


def _fake_response(status=200):
    resp = io.BytesIO(b'{"ok": true}')
    resp.status = status
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    return resp


class TelegramTests(unittest.TestCase):
    def test_skipped_when_not_configured(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}, clear=False):
            self.assertIsNone(alert_dispatch.send_telegram_message("hi"))
            self.assertFalse(alert_dispatch.telegram_configured())

    def test_posts_expected_payload(self):
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return _fake_response(200)

        env = {"TELEGRAM_BOT_TOKEN": "123:ABC", "TELEGRAM_CHAT_ID": "-100999"}
        with patch.dict("os.environ", env, clear=False), \
             patch("backend.alert_dispatch.urllib.request.urlopen", fake_urlopen):
            self.assertTrue(alert_dispatch.telegram_configured())
            delivered = alert_dispatch.send_telegram_message("<b>test</b>")

        self.assertTrue(delivered)
        self.assertIn("/bot123:ABC/sendMessage", captured["url"])
        self.assertEqual(captured["body"]["chat_id"], "-100999")
        self.assertEqual(captured["body"]["parse_mode"], "HTML")
        self.assertEqual(captured["body"]["text"], "<b>test</b>")


if __name__ == "__main__":
    unittest.main()
