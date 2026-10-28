"""Storage: signed URLs (POST /storage/sign), uploads to a signed URL, and
private buckets (create with a visibility; going public needs
confirm_public=True). Same mocking approach as test_client.py."""

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


class _SyncHttp(_FakeSyncHttpClient):
    def put(self, url, content=None, headers=None):
        _FakeSyncHttpClient.calls.append({"method": "PUT", "url": url, "content": content, "headers": headers})
        return _FakeSyncHttpClient.responder("PUT", url, None, headers)


class _AsyncHttp(_FakeAsyncHttpClient):
    async def put(self, url, content=None, headers=None):
        _FakeAsyncHttpClient.calls.append({"method": "PUT", "url": url, "content": content, "headers": headers})
        return _FakeAsyncHttpClient.responder("PUT", url, None, headers)


SIGNED = {
    "success": True,
    "url": "https://acme.pgbhub.app/storage/_signed/tok",
    "path": "/storage/_signed/tok",
    "method": "GET",
    "expires_in": 900,
    "expires_at": 1,
    "bucket_visibility": "private",
}


class Base(unittest.TestCase):
    def setUp(self):
        _FakeSyncHttpClient.calls = []
        _FakeAsyncHttpClient.calls = []
        patch.object(c, "httpx", MagicMock(Client=_SyncHttp, AsyncClient=_AsyncHttp)).start()
        patch.object(c.time, "sleep").start()
        os.environ.pop("PGBHUB_PROJECT_ID", None)
        self.client = c.PGBHubClient(api_key="pgb_sec_x", endpoint="https://acme.pgbhub.app")

    def tearDown(self):
        patch.stopall()

    def respond(self, fn):
        _FakeSyncHttpClient.responder = staticmethod(fn)
        _FakeAsyncHttpClient.responder = staticmethod(fn)

    def last(self):
        return _FakeSyncHttpClient.calls[-1]


class TestSignedUrls(Base):
    def test_get_by_default_on_storage_sign_with_the_key(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, SIGNED))
        out = self.client.storage.create_signed_url("receipts", "/2026/inv-1.pdf")
        call = self.last()
        self.assertEqual((call["method"], call["url"]), ("POST", "https://acme.pgbhub.app/storage/sign"))
        self.assertEqual(call["json"], {"bucket": "receipts", "path": "2026/inv-1.pdf", "method": "GET"})
        self.assertEqual(call["headers"]["Authorization"], "Bearer pgb_sec_x")
        self.assertEqual(out["url"], SIGNED["url"])

    def test_put_sends_expires_in_and_content_type(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, SIGNED))
        self.client.storage.create_signed_url("uploads", "a.png", method="put", expires_in=600, content_type="image/png")
        self.assertEqual(self.last()["json"], {"bucket": "uploads", "path": "a.png", "method": "PUT", "expires_in": 600, "content_type": "image/png"})

    def test_bad_arguments_are_refused_without_a_request(self):
        with self.assertRaises(ValueError):
            self.client.storage.create_signed_url("b", "a", content_type="image/png")
        with self.assertRaises(ValueError):
            self.client.storage.create_signed_url("b", "a", method="DELETE")
        self.assertEqual(_FakeSyncHttpClient.calls, [])

    def test_server_refusal_is_a_pgbhub_error(self):
        self.respond(lambda m, u, j, h: _FakeResponse(400, {"error": "Bucket 'nope' not found."}))
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.storage.create_signed_url("nope", "a")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Bucket 'nope' not found.", str(ctx.exception))
        self.assertEqual(len(_FakeSyncHttpClient.calls), 1)

    def test_upload_to_signed_url_puts_bytes_without_the_key(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "bucket": "uploads", "file_path": "a.png", "size_bytes": 3}))
        out = self.client.storage.upload_to_signed_url("https://acme.pgbhub.app/storage/_signed/tok", b"\x01\x02\x03", "image/png")
        call = self.last()
        self.assertEqual((call["method"], call["url"], call["content"]), ("PUT", "https://acme.pgbhub.app/storage/_signed/tok", b"\x01\x02\x03"))
        self.assertEqual(call["headers"]["Content-Type"], "image/png")
        self.assertNotIn("Authorization", call["headers"])
        self.assertEqual(out["size_bytes"], 3)

    def test_upload_relative_url_and_refusal(self):
        self.respond(lambda m, u, j, h: _FakeResponse(415, {"error": "This content type can only be uploaded through a signed URL minted for it (content_type)."}))
        with self.assertRaises(c.PGBHubError) as ctx:
            self.client.storage.upload_to_signed_url("/storage/_signed/tok", "<svg/>", "image/svg+xml")
        self.assertEqual(ctx.exception.status_code, 415)
        self.assertEqual(self.last()["url"], "https://acme.pgbhub.app/storage/_signed/tok")
        self.assertEqual(self.last()["content"], b"<svg/>")


class TestBuckets(Base):
    def test_create_bucket_defaults_to_public_and_uses_the_endpoint_slug(self):
        self.respond(lambda m, u, j, h: _FakeResponse(201, {"success": True, "bucket": "assets", "visibility": "public"}))
        self.client.storage.create_bucket("assets")
        self.assertEqual(self.last()["url"], "https://acme.pgbhub.app/api/v1/projects/acme/storage/buckets")
        self.assertEqual(self.last()["json"], {"name": "assets", "visibility": "public"})

    def test_create_private_bucket_by_project_id(self):
        client = c.PGBHubClient(api_key="pgb_sec_x", endpoint="https://acme.pgbhub.app", project_id="prj_1")
        client.storage.create_bucket("receipts", visibility="private")
        self.assertEqual(self.last()["url"], "https://acme.pgbhub.app/api/v1/projects/prj_1/storage/buckets")
        self.assertEqual(self.last()["json"], {"name": "receipts", "visibility": "private"})

    def test_without_a_project_it_explains(self):
        client = c.PGBHubClient(api_key="k", endpoint="https://console.pgbhub.com")
        with self.assertRaises(ValueError) as ctx:
            client.storage.create_bucket("x")
        self.assertIn("project_id", str(ctx.exception))
        self.assertEqual(_FakeSyncHttpClient.calls, [])

    def test_set_private_needs_no_confirmation(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True, "bucket": "receipts", "visibility": "private", "previous_visibility": "public"}))
        out = self.client.storage.set_bucket_visibility("receipts", "private")
        self.assertEqual(self.last()["url"], "https://acme.pgbhub.app/api/v1/projects/acme/storage/buckets/receipts/visibility")
        self.assertEqual(self.last()["json"], {"visibility": "private"})
        self.assertEqual(out["previous_visibility"], "public")

    def test_set_public_is_refused_without_confirm_public(self):
        for confirm in (False, "true", 1):
            with self.assertRaises(ValueError) as ctx:
                self.client.storage.set_bucket_visibility("receipts", "public", confirm_public=confirm)
            self.assertIn("confirm_public=True", str(ctx.exception))
        self.assertEqual(_FakeSyncHttpClient.calls, [])

    def test_set_public_with_confirmation(self):
        self.client.storage.set_bucket_visibility("assets", "public", confirm_public=True)
        self.assertEqual(self.last()["json"], {"visibility": "public", "confirm_public": True})


class TestAsync(Base):
    def setUp(self):
        super().setUp()
        self.aclient = c.AsyncPGBHubClient(api_key="pgb_sec_x", endpoint="https://acme.pgbhub.app")

    def test_async_sign_upload_and_buckets(self):
        self.respond(lambda m, u, j, h: _FakeResponse(200, {"success": True}))
        run_async(self.aclient.storage.create_signed_url("receipts", "a.pdf", expires_in=60))
        run_async(self.aclient.storage.upload_to_signed_url("/storage/_signed/tok", b"x", "application/pdf"))
        run_async(self.aclient.storage.create_bucket("receipts", visibility="private"))
        run_async(self.aclient.storage.set_bucket_visibility("receipts", "public", confirm_public=True))
        calls = _FakeAsyncHttpClient.calls
        self.assertEqual([(x["method"], x["url"]) for x in calls], [
            ("POST", "https://acme.pgbhub.app/storage/sign"),
            ("PUT", "https://acme.pgbhub.app/storage/_signed/tok"),
            ("POST", "https://acme.pgbhub.app/api/v1/projects/acme/storage/buckets"),
            ("POST", "https://acme.pgbhub.app/api/v1/projects/acme/storage/buckets/receipts/visibility"),
        ])
        self.assertEqual(calls[0]["json"], {"bucket": "receipts", "path": "a.pdf", "method": "GET", "expires_in": 60})
        self.assertNotIn("Authorization", calls[1]["headers"])
        self.assertEqual(calls[3]["json"], {"visibility": "public", "confirm_public": True})

    def test_async_public_refused_without_confirmation(self):
        with self.assertRaises(ValueError):
            run_async(self.aclient.storage.set_bucket_visibility("receipts", "public"))
        self.assertEqual(_FakeAsyncHttpClient.calls, [])


if __name__ == "__main__":
    unittest.main()
