"""Regression tests for the Python SDK's Round 1 additions: AuthClient
(+ admin), StorageClient.get_file/get_media, FunctionsClient.deploy/
delete, and PGBHubClient.create_database.

Mocks httpx.Client/AsyncClient at the module level (pgbhub.client.httpx)
rather than hitting the network, pinning the exact HTTP method/path/body
each method sends against the real client code.
"""

from __future__ import annotations

import asyncio
import json as jsonlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgbhub import client as pgb_client


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None, content=b""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text or jsonlib.dumps(self._json_data)
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSyncHttpClient:
    """Stand-in for httpx.Client used as a context manager."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, url, json=None, headers=None):
        _FakeSyncHttpClient.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        return _FakeSyncHttpClient.responder(method, url, json, headers)

    def get(self, url, headers=None):
        return self.request("GET", url, headers=headers)

    def post(self, url, json=None, headers=None):
        return self.request("POST", url, json=json, headers=headers)

    def delete(self, url, headers=None):
        return self.request("DELETE", url, headers=headers)

    @staticmethod
    def responder(method, url, json, headers):
        return _FakeResponse(200, {})


class _FakeAsyncHttpClient:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, json=None, headers=None):
        _FakeAsyncHttpClient.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        return _FakeAsyncHttpClient.responder(method, url, json, headers)

    async def get(self, url, headers=None):
        return await self.request("GET", url, headers=headers)

    async def post(self, url, json=None, headers=None):
        return await self.request("POST", url, json=json, headers=headers)

    async def delete(self, url, headers=None):
        return await self.request("DELETE", url, headers=headers)

    @staticmethod
    def responder(method, url, json, headers):
        return _FakeResponse(200, {})


def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestAuthClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_sign_up_posts_and_stores_session(self):
        session = {"access_token": "at1", "refresh_token": "rt1"}
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(201, {"user": {"id": "u1"}, "session": session}))

        result = self.client.auth.sign_up("a@test.com", password="pw")

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/auth/signup")
        self.assertEqual(result["session"], session)
        self.assertEqual(self.client.auth.get_session(), session)

    def test_sign_in_failure_raises_pgbhub_auth_error_with_server_message(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(400, {"error": "Invalid email or password."}))

        with self.assertRaises(pgb_client.PGBHubAuthError) as ctx:
            self.client.auth.sign_in("a@test.com", password="wrong")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid email or password", ctx.exception.message)

    def test_sign_out_sends_x_pgb_user_token_and_clears_session(self):
        self.client.auth.set_session({"access_token": "at1", "refresh_token": "rt1"})
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"success": True}))

        self.client.auth.sign_out()

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/auth/logout")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["headers"]["X-PGB-User-Token"], "at1")
        self.assertIsNone(self.client.auth.get_session())

    def test_get_user_without_session_returns_none_with_no_network_call(self):
        result = self.client.auth.get_user()
        self.assertIsNone(result)
        self.assertEqual(len(_FakeSyncHttpClient.calls), 0)

    def test_get_user_with_session_sends_token_and_returns_user(self):
        self.client.auth.set_session({"access_token": "at1", "refresh_token": "rt1"})
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"user": {"id": "u1", "email": "a@test.com"}}))

        result = self.client.auth.get_user()

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/auth/user")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["headers"]["X-PGB-User-Token"], "at1")
        self.assertEqual(result["email"], "a@test.com")

    def test_admin_create_list_delete_user(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(201, {"user": {"id": "u2", "email": "b@test.com"}}))
        created = self.client.auth.admin.create_user("b@test.com")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/auth/admin/users")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["method"], "POST")
        self.assertEqual(created["email"], "b@test.com")

        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"users": [created]}))
        users = self.client.auth.admin.list_users()
        self.assertEqual(_FakeSyncHttpClient.calls[1]["method"], "GET")
        self.assertEqual(len(users), 1)

        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"success": True}))
        deleted = self.client.auth.admin.delete_user("u2")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["url"], "https://test.pgbhub.dev/auth/admin/users/u2")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["method"], "DELETE")
        self.assertTrue(deleted)


class TestAsyncAuthClient(unittest.TestCase):
    def setUp(self):
        _FakeAsyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.AsyncPGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_sign_up_posts_and_stores_session(self):
        session = {"access_token": "at1", "refresh_token": "rt1"}
        _FakeAsyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(201, {"user": {"id": "u1"}, "session": session}))

        result = run_async(self.client.auth.sign_up("a@test.com", password="pw"))

        self.assertEqual(_FakeAsyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/auth/signup")
        self.assertEqual(result["session"], session)


class TestStorageClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_get_file_hits_storage_path_and_returns_bytes_and_content_type(self):
        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(200, {}, headers={"content-type": "text/plain", "etag": '"abc"'}, content=b"hello")
        )

        result = self.client.storage.get_file("/notes/hello.txt")

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/storage/notes/hello.txt")
        self.assertEqual(result["content_type"], "text/plain")
        self.assertEqual(result["data"], b"hello")
        self.assertEqual(result["etag"], '"abc"')

    def test_get_media_is_alias_over_get_file_and_does_not_forward_transform_params(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {}, headers={"content-type": "image/png"}))

        self.client.storage.get_media("/avatars/pic.png", width=200, height=200)

        self.assertEqual(len(_FakeSyncHttpClient.calls), 1)
        self.assertNotIn("width", _FakeSyncHttpClient.calls[0]["url"])


class TestFunctionsClientDeployDelete(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_deploy_posts_to_collection_with_name_in_body(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(201, {"function": {"name": "send-welcome"}}))

        fn = self.client.functions.deploy("send-welcome", "def handler(): pass", timeout_ms=8000)

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/functions")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["method"], "POST")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["json"]["name"], "send-welcome")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["json"]["timeout_ms"], 8000)
        self.assertEqual(fn["name"], "send-welcome")

    def test_delete_sends_name_in_the_url(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"success": True}))

        ok = self.client.functions.delete("send-welcome")

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/functions/send-welcome")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["method"], "DELETE")
        self.assertTrue(ok)


class TestCreateDatabase(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_live_account_test", endpoint="https://test.pgbhub.dev")

    def tearDown(self):
        self.patcher.stop()

    def test_create_database_posts_name_and_defaults_pg_version(self):
        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(201, {"success": True, "database": "newdb", "pg_version": "17"})
        )

        result = self.client.create_database("newdb")

        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/api/v1/databases")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["json"]["name"], "newdb")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["json"]["pg_version"], "17")
        self.assertEqual(result["database"], "newdb")


class TestCronClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_create_posts_target_type_and_target_config(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(201, {"id": "cron_1", "name": "nightly"}))

        self.client.cron.create("nightly", "0 0 * * *", "function", {"function_name": "cleanup"}, timeout_seconds=60)

        call = _FakeSyncHttpClient.calls[0]
        self.assertEqual(call["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/crons")
        self.assertEqual(call["json"]["target_type"], "function")
        self.assertEqual(call["json"]["target_config"], {"function_name": "cleanup"})
        self.assertEqual(call["json"]["timeout_seconds"], 60)

    def test_list_reads_crons_field(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"crons": [{"id": "cron_1"}], "total": 1}))

        jobs = self.client.cron.list()
        self.assertEqual(len(jobs), 1)

    def test_toggle_run_delete_hit_right_subpaths(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {}))

        self.client.cron.toggle("cron_1", False)
        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/crons/cron_1/toggle")
        self.assertEqual(_FakeSyncHttpClient.calls[0]["json"]["enabled"], False)

        self.client.cron.run("cron_1")
        self.assertEqual(_FakeSyncHttpClient.calls[1]["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/crons/cron_1/run")
        self.assertEqual(_FakeSyncHttpClient.calls[1]["method"], "POST")

        self.client.cron.delete("cron_1")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/crons/cron_1")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["method"], "DELETE")


class TestJobsClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", database="appdb")

    def tearDown(self):
        self.patcher.stop()

    def test_enqueue_posts_job_type_and_target_type_and_unwraps_job(self):
        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(201, {"success": True, "job": {"id": 1, "status": "pending"}})
        )

        job = self.client.jobs.enqueue("send-report", "sql", {"sql": "select 1"}, max_attempts=3)

        call = _FakeSyncHttpClient.calls[0]
        self.assertEqual(call["url"], "https://test.pgbhub.dev/api/v1/databases/appdb/jobs")
        self.assertEqual(call["json"]["job_type"], "send-report")
        self.assertEqual(call["json"]["max_attempts"], 3)
        self.assertEqual(job["id"], 1)

    def test_get_returns_none_on_404_instead_of_raising(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(404, {"error": "Job not found"}))

        self.assertIsNone(self.client.jobs.get(999))

    def test_list_sends_status_and_limit_as_query_params(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"success": True, "jobs": [], "total": 0}))

        self.client.jobs.list(status="failed", limit=5)
        url = _FakeSyncHttpClient.calls[0]["url"]
        self.assertIn("status=failed", url)
        self.assertIn("limit=5", url)

    def test_cancel_returns_false_on_409_instead_of_raising(self):
        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(409, {"error": "cannot cancel"}))

        self.assertFalse(self.client.jobs.cancel(1))


class TestQueuesClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_without_project_id_raises_a_clear_error(self):
        client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev")
        with self.assertRaisesRegex(ValueError, "requires project_id"):
            client.queues.send("my-queue", {"hello": "world"})

    def test_send_hits_project_scoped_url_and_unwraps_message(self):
        client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", project_id="prj_1")
        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(200, {"ok": True, "message": {"message_id": "msg_1", "deduplicated": False}})
        )

        msg = client.queues.send("my-queue", {"hello": "world"}, delay_seconds=5)

        call = _FakeSyncHttpClient.calls[0]
        self.assertEqual(call["url"], "https://test.pgbhub.dev/api/v1/projects/prj_1/queues/my-queue/send")
        self.assertEqual(call["json"]["payload"], {"hello": "world"})
        self.assertEqual(call["json"]["delay_seconds"], 5)
        self.assertEqual(msg["message_id"], "msg_1")

    def test_receive_ack_nack_hit_right_subpaths(self):
        client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev", project_id="prj_1")

        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(200, {"ok": True, "count": 1, "messages": [{"message_id": "msg_1"}]})
        )
        msgs = client.queues.receive("my-queue", max_messages=1)
        self.assertEqual(_FakeSyncHttpClient.calls[0]["url"], "https://test.pgbhub.dev/api/v1/projects/prj_1/queues/my-queue/receive")
        self.assertEqual(len(msgs), 1)

        _FakeSyncHttpClient.responder = staticmethod(lambda m, u, j, h: _FakeResponse(200, {"ok": True}))
        client.queues.ack("my-queue", "msg_1")
        self.assertEqual(_FakeSyncHttpClient.calls[1]["url"], "https://test.pgbhub.dev/api/v1/projects/prj_1/queues/my-queue/ack")
        self.assertEqual(_FakeSyncHttpClient.calls[1]["json"]["message_id"], "msg_1")

        client.queues.nack("my-queue", "msg_1", error="boom")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["url"], "https://test.pgbhub.dev/api/v1/projects/prj_1/queues/my-queue/nack")
        self.assertEqual(_FakeSyncHttpClient.calls[2]["json"]["error"], "boom")


class TestRealtimeClient(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        self.patcher = patch.object(pgb_client, "httpx", MagicMock(Client=_FakeSyncHttpClient, AsyncClient=_FakeAsyncHttpClient))
        self.patcher.start()
        self.client = pgb_client.PGBHubClient(api_key="pgb_sec_test", endpoint="https://test.pgbhub.dev")

    def tearDown(self):
        self.patcher.stop()

    def test_broadcast_posts_to_channel_endpoint(self):
        _FakeSyncHttpClient.responder = staticmethod(
            lambda m, u, j, h: _FakeResponse(200, {"ok": True, "broadcast": {"delivered_to": 2}})
        )

        result = self.client.realtime.broadcast("general", {"text": "hi"}, event="chat")

        call = _FakeSyncHttpClient.calls[0]
        self.assertEqual(call["url"], "https://test.pgbhub.dev/api/v1/realtime/channels/general/broadcast")
        self.assertEqual(call["json"]["event"], "chat")
        self.assertEqual(call["json"]["payload"], {"text": "hi"})
        self.assertEqual(result["broadcast"]["delivered_to"], 2)


if __name__ == "__main__":
    unittest.main()
