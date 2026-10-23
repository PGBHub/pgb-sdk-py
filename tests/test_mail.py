"""Mail: reply_to on the wire, message_id (with the mail_id fallback) and
the typed 503 MAIL_PROVIDER_UNAVAILABLE error. Same mocking approach as
test_client.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pgbhub
from pgbhub import client as c
from test_client import _FakeAsyncHttpClient, _FakeResponse, _FakeSyncHttpClient, run_async


class Base(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        _FakeAsyncHttpClient.calls = []
        patch.object(c, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient)).start()
        patch.object(c.time, "sleep").start()
        self.client = c.PGBHubClient(api_key="pgb_sec_x", endpoint="https://p.pgbhub.app")

    def tearDown(self):
        patch.stopall()

    def respond(self, fn):
        _FakeSyncHttpClient.responder = staticmethod(fn)
        _FakeAsyncHttpClient.responder = staticmethod(fn)


class TestMailSend(Base):
    def test_reply_to_is_sent_on_the_wire(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "message_id": "m1", "mail_id": "m1"}))
        res = self.client.mail.send("a@b.co", "Hi", "Body", reply_to="support@acme.dev")
        call = _FakeSyncHttpClient.calls[-1]
        self.assertEqual((call["method"], call["url"]), ("POST", "https://p.pgbhub.app/mail/send"))
        self.assertEqual(call["json"], {"to": "a@b.co", "subject": "Hi", "text": "Body", "reply_to": "support@acme.dev"})
        self.assertEqual(call["headers"]["Authorization"], "Bearer pgb_sec_x")
        self.assertEqual(res["message_id"], "m1")

    def test_without_reply_to_no_key_is_sent(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "message_id": "m1"}))
        self.client.mail.send("a@b.co", "Hi", "Body", html="<p>Body</p>", from_addr="App <no-reply@acme.dev>")
        body = _FakeSyncHttpClient.calls[-1]["json"]
        self.assertNotIn("reply_to", body)
        self.assertEqual(body["html"], "<p>Body</p>")
        self.assertEqual(body["from"], "App <no-reply@acme.dev>")

    def test_message_id_falls_back_to_mail_id(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "mail_id": "old1"}))
        res = self.client.mail.send("a@b.co", "Hi", "Body")
        self.assertEqual((res["message_id"], res["mail_id"]), ("old1", "old1"))

    def test_provider_unavailable_is_a_typed_error_and_not_retried(self):
        self.respond(lambda m, u, j, h: _FakeResponse(503, {"error": "Email dispatch failed: no provider", "code": "MAIL_PROVIDER_UNAVAILABLE"}))
        with self.assertRaises(pgbhub.PGBHubError) as ctx:
            self.client.mail.send("a@b.co", "Hi", "Body")
        e = ctx.exception
        self.assertEqual((e.status_code, e.code), (503, pgbhub.MAIL_PROVIDER_UNAVAILABLE))
        self.assertEqual(e.message, "Email dispatch failed: no provider")
        self.assertEqual(len(_FakeSyncHttpClient.calls), 1)

    def test_bad_reply_to_400_keeps_the_server_message(self):
        self.respond(lambda m, u, j, h: _FakeResponse(400, {"error": "Invalid reply_to email address: 'a@b.co, c@d.co'"}))
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.mail.send("a@b.co", "Hi", "Body", reply_to="a@b.co, c@d.co")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIsNone(ctx.exception.code)
        self.assertIn("Invalid reply_to", ctx.exception.message)

    def test_one_recipient_only(self):
        with self.assertRaises(TypeError):
            self.client.mail.send(["a@b.co", "c@d.co"], "Hi", "Body")  # type: ignore[arg-type]


class TestAsyncMailSend(Base):
    def test_async_send_reply_to_and_fallback(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "mail_id": "old2"}))
        ac = c.AsyncPGBHubClient(api_key="pgb_sec_x", endpoint="https://p.pgbhub.app")
        res = run_async(ac.mail.send("a@b.co", "Hi", "Body", reply_to="help@acme.dev"))
        self.assertEqual(_FakeAsyncHttpClient.calls[-1]["json"]["reply_to"], "help@acme.dev")
        self.assertEqual(res["message_id"], "old2")

    def test_async_provider_unavailable(self):
        self.respond(lambda m, u, j, h: _FakeResponse(503, {"error": "down", "code": "MAIL_PROVIDER_UNAVAILABLE"}))
        ac = c.AsyncPGBHubClient(api_key="pgb_sec_x", endpoint="https://p.pgbhub.app")
        with self.assertRaises(c.PGBHubError) as ctx:
            run_async(ac.mail.send("a@b.co", "Hi", "Body"))
        self.assertEqual((ctx.exception.status_code, ctx.exception.code), (503, "MAIL_PROVIDER_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main()
