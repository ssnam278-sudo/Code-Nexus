"""Telegram / SMS dispatch wiring — no network: urlopen is patched."""

import io
import json
import unittest
from unittest.mock import patch

from backend import alert_dispatch


def _fake_response(status=200, body=b'{"ok": true}'):
    resp = io.BytesIO(body)
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


class SmsTests(unittest.TestCase):
    def test_skipped_when_no_recipient(self):
        with patch.dict("os.environ", {"SMS_TO": ""}, clear=False):
            self.assertIsNone(alert_dispatch.send_sms("hi"))
            self.assertFalse(alert_dispatch.sms_configured())

    def test_textbelt_is_default_and_posts_form(self):
        captured = {}

        def fake_urlopen(req, timeout=15):
            captured["url"] = req.full_url
            captured["body"] = req.data.decode()
            return _fake_response(200, b'{"success": true, "quotaRemaining": 1}')

        env = {"SMS_TO": "+919876543210"}
        with patch.dict("os.environ", env, clear=False), \
             patch.dict("os.environ", {"SMS_PROVIDER": ""}, clear=False), \
             patch("backend.alert_dispatch.urllib.request.urlopen", fake_urlopen):
            self.assertTrue(alert_dispatch.sms_configured())
            ok = alert_dispatch.send_sms("Code Nexus ALERT: test")

        self.assertTrue(ok)
        self.assertEqual(captured["url"], "https://textbelt.com/text")
        self.assertIn("phone=%2B919876543210", captured["body"])
        self.assertIn("key=textbelt", captured["body"])
        self.assertIn("message=", captured["body"])

    def test_textbelt_failure_when_success_false(self):
        with patch.dict("os.environ", {"SMS_TO": "+91999"}, clear=False), \
             patch("backend.alert_dispatch.urllib.request.urlopen",
                   lambda req, timeout=15: _fake_response(200, b'{"success": false, "error": "Out of quota"}')):
            self.assertFalse(alert_dispatch.send_sms("x"))

    def test_twilio_needs_all_three_vars(self):
        with patch.dict("os.environ", {"SMS_TO": "+91999", "SMS_PROVIDER": "twilio",
                                       "TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "t",
                                       "TWILIO_FROM": ""}, clear=False):
            self.assertFalse(alert_dispatch.sms_configured())

    def test_sms_text_is_short_and_names_the_zone(self):
        msg = alert_dispatch.sms_text(
            {"id": "tawang", "name": "Tawang Corridor"}, "Critical", {"risk_score": 82}, test=True
        )
        self.assertIn("Tawang Corridor", msg)
        self.assertIn("82/100", msg)
        self.assertTrue(msg.startswith("TEST Code Nexus ALERT"))
        self.assertLessEqual(len(msg), 320)


if __name__ == "__main__":
    unittest.main()
