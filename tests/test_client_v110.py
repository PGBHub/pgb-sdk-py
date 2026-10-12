"""1.1.0: endpoint resolution, PGBHubError, GET retries, full auth surface,
Actions management. Same mocking approach as test_client.py."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pgbhub import client as c
from test_client import _FakeAsyncHttpClient, _FakeResponse, _FakeSyncHttpClient, run_async


class Base(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        _FakeAsyncHttpClient.calls = []
        self.p = patch.object(c, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.p.start()
        self.sleep = patch.object(c.time, "sleep").start()
        self.client = c.PGBHubClient(api_key="pgb_sec_x", endpoint="https://p.pgbhub.app")

    def tearDown(self):
        patch.stopall()

    def respond(self, fn):
        _FakeSyncHttpClient.responder = staticmethod(fn)

    def last(self):
        return _FakeSyncHttpClient.calls[-1]


class TestEndpoint(unittest.TestCase):
    def test_project_id_selects_the_project_address(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(c.PGBHubClient(project_id="shop").endpoint, "https://shop.pgbhub.app")
            self.assertEqual(c.PGBHubClient().endpoint, "https://cloud.pgbhub.com")

    def test_explicit_endpoint_and_domain_override(self):
        with patch.dict(os.environ, {"PGBHUB_PROJECT_DOMAIN": "example.test"}, clear=True):
            self.assertEqual(c.PGBHubClient(project_id="shop").endpoint, "https://shop.example.test")
            self.assertEqual(c.PGBHubClient(project_id="shop", endpoint="https://x.io/").endpoint, "https://x.io")

    def test_database_is_only_sent_when_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(c.PGBHubClient().database_explicit)
            self.assertTrue(c.PGBHubClient(database="app").database_explicit)


class TestErrors(Base):
    def test_server_message_code_and_retry_after_are_carried(self):
        self.respond(lambda m, u, j, h: _FakeResponse(429, {"error": "Too many", "code": "rate_limited"}, headers={"retry-after": "7"}))
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.auth.sign_in("a@b.c", "pw")
        e = ctx.exception
        self.assertEqual((e.status_code, e.code, e.retry_after, e.message), (429, "rate_limited", 7.0, "Too many"))

    def test_legacy_name_is_the_same_class(self):
        self.assertIs(c.PGBHubAuthError, c.PGBHubError)

    def test_get_retries_transient_failures_but_post_does_not(self):
        answers = [_FakeResponse(503, {"error": "busy"}), _FakeResponse(200, {"actions": []})]
        self.respond(lambda m, u, j, h: answers.pop(0))
        self.assertEqual(self.client.actions.list(), [])
        self.assertEqual(len(_FakeSyncHttpClient.calls), 2)

        _FakeSyncHttpClient.calls = []
        self.respond(lambda m, u, j, h: _FakeResponse(503, {"error": "busy"}))
        with self.assertRaises(c.PGBHubError):
            self.client.auth.sign_in("a@b.c", "pw")
        self.assertEqual(len(_FakeSyncHttpClient.calls), 1)

    def test_network_errors_become_pgbhub_errors(self):
        def boom(*a):
            raise ConnectionError("down")
        self.respond(boom)
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.auth.sign_in("a@b.c", "pw")
        self.assertEqual(ctx.exception.code, "network_error")


class TestAuthSurface(Base):
    def signed_in(self):
        self.client.auth.set_session({"access_token": "at", "refresh_token": "rt"})

    def test_signup_with_verification_keeps_no_session_and_sends_redirect(self):
        self.respond(lambda m, u, j, h: _FakeResponse(201, {"user": {"id": "u"}, "session": None, "verification_required": True}))
        r = self.client.auth.sign_up("a@b.c", "pw", redirect_to="https://app/verified")
        self.assertTrue(r["verification_required"])
        self.assertIsNone(self.client.auth.get_session())
        self.assertEqual(self.last()["json"]["redirect_to"], "https://app/verified")

    def test_password_flows_never_need_a_session_except_change(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"message": "ok"}))
        self.client.auth.forgot_password("a@b.c", redirect_to="https://app/reset")
        self.assertEqual(self.last()["url"], "https://p.pgbhub.app/auth/forgot-password")
        self.client.auth.reset_password("tok", "newpw")
        self.assertEqual(self.last()["json"], {"token": "tok", "password": "newpw"})
        self.client.auth.resend_verification("a@b.c")
        self.assertEqual(self.last()["url"], "https://p.pgbhub.app/auth/resend-verification")
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.auth.change_password("n", "o")
        self.assertEqual(ctx.exception.code, "not_signed_in")

    def test_user_actions_send_the_user_token(self):
        self.signed_in()
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"message": "ok", "user": {}}))
        self.client.auth.change_password("new", "old")
        self.assertEqual(self.last()["headers"]["X-PGB-User-Token"], "at")
        self.assertEqual(self.last()["json"], {"current_password": "old", "new_password": "new"})
        self.client.auth.update_user({"plan": "pro"})
        self.assertEqual(self.last()["json"], {"user_metadata": {"plan": "pro"}})

    def test_delete_account_clears_the_session(self):
        self.signed_in()
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"message": "deleted"}))
        self.client.auth.delete_account("pw")
        self.assertEqual(self.last()["url"], "https://p.pgbhub.app/auth/user/delete")
        self.assertIsNone(self.client.auth.get_session())

    def test_sessions_events_and_mfa(self):
        self.signed_in()
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"sessions": [{"id": "s1"}], "events": [{"type": "login"}], "revoked": 2}))
        self.assertEqual(self.client.auth.list_sessions(), [{"id": "s1"}])
        self.assertEqual(self.client.auth.get_events(), [{"type": "login"}])
        self.assertEqual(self.client.auth.revoke_other_sessions(), 2)
        self.client.auth.revoke_session("s 1")
        self.assertEqual((self.last()["method"], self.last()["url"]), ("DELETE", "https://p.pgbhub.app/auth/sessions/s%201"))
        self.client.auth.enroll_mfa()
        self.client.auth.confirm_mfa("123456")
        self.assertEqual(self.last()["url"], "https://p.pgbhub.app/auth/mfa/confirm")

    def test_mfa_login_then_verify_stores_the_session(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"mfa_required": True, "challenge_token": "ch"}))
        self.assertTrue(self.client.auth.sign_in("a@b.c", "pw")["mfa_required"])
        self.assertIsNone(self.client.auth.get_session())
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"session": {"access_token": "at2"}}))
        self.client.auth.verify_mfa("ch", "123456")
        self.assertEqual(self.client.auth.get_session()["access_token"], "at2")

    def test_oauth_start_and_callback(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"authorize_url": "https://g", "state": "s", "session": {"access_token": "at3"}}))
        self.client.auth.oauth_start("google", "https://app/cb")
        self.assertIn("/auth/oauth/google/start?redirect_uri=https%3A%2F%2Fapp%2Fcb", self.last()["url"])
        self.client.auth.oauth_callback("google", "code", "s", "https://app/cb")
        self.assertEqual(self.client.auth.get_session()["access_token"], "at3")

    def test_get_user_returns_none_only_for_an_expired_session(self):
        self.signed_in()
        self.respond(lambda m, u, j, h: _FakeResponse(401, {"error": "expired"}))
        self.assertIsNone(self.client.auth.get_user())
        self.respond(lambda m, u, j, h: _FakeResponse(500, {"error": "boom"}))
        with self.assertRaises(c.PGBHubError):
            self.client.auth.get_user()

    def test_async_client_has_the_same_surface(self):
        a = c.AsyncPGBHubClient(api_key="k", endpoint="https://p.pgbhub.app")
        _FakeAsyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"message": "ok", "sessions": [{"id": "s"}]}))
        run_async(a.auth.forgot_password("a@b.c"))
        self.assertEqual(_FakeAsyncHttpClient.calls[-1]["url"], "https://p.pgbhub.app/auth/forgot-password")
        a.auth.set_session({"access_token": "t"})
        self.assertEqual(run_async(a.auth.list_sessions()), [{"id": "s"}])
        with self.assertRaises(c.PGBHubError):
            run_async(c.AsyncPGBHubClient(api_key="k", endpoint="https://p.pgbhub.app").auth.revoke_other_sessions())


class TestActions(Base):
    def test_invoke_leaves_the_database_out_unless_configured(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"action": "a", "status": "simulated", "dry_run": True, "effects_preview": [{"type": "mail"}]}))
        r = self.client.actions.saveUser({"x": 1}, dry_run=True)
        self.assertEqual(self.last()["json"], {"action": "saveUser", "params": {"x": 1}, "dry_run": True})
        self.assertEqual(r.effects_preview, [{"type": "mail"}])

    def test_register_maps_fields_and_effects(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"status": "registered"}))
        self.client.actions.register(name="signup", sql="INSERT INTO t VALUES (%(a)s)", effects=[{"type": "mail", "to": "{{params.email}}"}])
        body = self.last()["json"]
        self.assertEqual(self.last()["url"], "https://p.pgbhub.app/v1/actions/register")
        self.assertEqual((body["name"], body["sql_template"]), ("signup", "INSERT INTO t VALUES (%(a)s)"))
        self.assertEqual(body["effects"][0]["type"], "mail")
        with self.assertRaises(ValueError):
            self.client.actions.register(name="x")

    def test_list_get_delete_deliveries_retry(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"actions": [{"name": "a"}], "deliveries": [{"id": 4}]}))
        self.assertEqual(self.client.actions.list(), [{"name": "a"}])
        self.client.actions.get("a b")
        self.assertTrue(self.last()["url"].endswith("/v1/actions/a%20b"))
        self.client.actions.delete("a")
        self.assertEqual(self.last()["method"], "DELETE")
        self.assertEqual(self.client.actions.deliveries(status="failed", limit=5), [{"id": 4}])
        self.assertTrue(self.last()["url"].endswith("/v1/actions/deliveries?status=failed&limit=5"))
        self.client.actions.retry_delivery(4)
        self.assertTrue(self.last()["url"].endswith("/v1/actions/deliveries/4/retry"))

    def test_configured_database_is_passed_as_dbname(self):
        cl = c.PGBHubClient(api_key="k", endpoint="https://p.pgbhub.app", database="app")
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"actions": []}))
        cl.actions.list()
        self.assertTrue(self.last()["url"].endswith("/v1/actions?dbname=app"))

    def test_async_management(self):
        a = c.AsyncPGBHubClient(api_key="k", endpoint="https://p.pgbhub.app")
        _FakeAsyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"actions": [{"name": "z"}], "deliveries": []}))
        self.assertEqual(run_async(a.actions.list()), [{"name": "z"}])
        run_async(a.actions.retry_delivery(9))
        self.assertTrue(_FakeAsyncHttpClient.calls[-1]["url"].endswith("/deliveries/9/retry"))


if __name__ == "__main__":
    unittest.main()
