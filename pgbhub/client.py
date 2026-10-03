"""Official PGBHub Python Client SDK."""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:  # type: ignore
        def __init__(self, **data: Any):
            for k, v in data.items():
                setattr(self, k, v)

        @classmethod
        def model_validate(cls, data: Any):
            if isinstance(data, cls):
                return data
            if isinstance(data, dict):
                return cls(**data)
            return data

        def dict(self) -> dict[str, Any]:
            return self.__dict__


class ActionResponse(BaseModel):
    action: str = ""
    status: str = "completed"
    dry_run: bool = False
    duration_ms: float = 0.0
    results: Any = None
    outbox_id: Optional[int] = None
    message: Optional[str] = None



class ActionsProxy:
    def __init__(self, client: PGBHubClient):
        self._client = client

    def __getattr__(self, name: str):
        def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


class AsyncActionsProxy:
    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def __getattr__(self, name: str):
        async def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return await self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


class DocumentCollection:
    def __init__(self, client: PGBHubClient, name: str):
        self._client = client
        self.name = name

    def insert_one(self, doc: dict[str, Any]) -> ActionResponse:
        return self._client.invoke_action(f"insert_{self.name}", doc)

    def find(self, filter: Optional[dict[str, Any]] = None) -> ActionResponse:
        return self._client.invoke_action(f"find_{self.name}", filter or {})

    def update_one(self, filter: dict[str, Any], update: dict[str, Any]) -> ActionResponse:
        return self._client.invoke_action(f"update_{self.name}", {"filter": filter, "update": update})

    def delete_one(self, filter: dict[str, Any]) -> ActionResponse:
        return self._client.invoke_action(f"delete_{self.name}", filter)


class AsyncDocumentCollection:
    def __init__(self, client: AsyncPGBHubClient, name: str):
        self._client = client
        self.name = name

    async def insert_one(self, doc: dict[str, Any]) -> ActionResponse:
        return await self._client.invoke_action(f"insert_{self.name}", doc)

    async def find(self, filter: Optional[dict[str, Any]] = None) -> ActionResponse:
        return await self._client.invoke_action(f"find_{self.name}", filter or {})

    async def update_one(self, filter: dict[str, Any], update: dict[str, Any]) -> ActionResponse:
        return await self._client.invoke_action(f"update_{self.name}", {"filter": filter, "update": update})

    async def delete_one(self, filter: dict[str, Any]) -> ActionResponse:
        return await self._client.invoke_action(f"delete_{self.name}", filter)


class TableClient:
    """Synchronous typed table accessor supporting find, find_one, create, update, delete, and count."""

    def __init__(self, client: PGBHubClient, table_name: str):
        self._client = client
        self.table_name = table_name

    def find(
        self,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        order: str = "ASC",
    ) -> list[dict[str, Any]]:
        """Find records matching filter."""
        res = self._client.request(
            "/v1/data/find",
            {
                "table": self.table_name,
                "filter": filter or {},
                "limit": limit,
                "offset": offset,
                "orderBy": order_by,
                "order": order,
            },
        )
        return res.get("rows", [])

    def find_one(self, filter: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """Find first single record matching filter."""
        rows = self.find(filter=filter, limit=1)
        return rows[0] if rows else None

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a record and return the inserted row."""
        res = self._client.request("/v1/data/insert", {"table": self.table_name, "data": data})
        return res.get("row", data)

    def insert_one(self, data: dict[str, Any]) -> dict[str, Any]:
        """Alias for create."""
        return self.create(data)

    def update(self, filter: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
        """Update records matching filter."""
        res = self._client.request(
            "/v1/data/update",
            {"table": self.table_name, "filter": filter, "data": data},
        )
        return res.get("rows", [])

    def delete(self, filter: dict[str, Any]) -> dict[str, Any]:
        """Delete records matching filter."""
        return self._client.request(
            "/v1/data/delete",
            {"table": self.table_name, "filter": filter},
        )

    def count(self, filter: Optional[dict[str, Any]] = None) -> int:
        """Count records matching filter."""
        res = self._client.request(
            "/v1/data/count",
            {"table": self.table_name, "filter": filter or {}},
        )
        return res.get("count", 0)


class AsyncTableClient:
    """Asynchronous typed table accessor."""

    def __init__(self, client: AsyncPGBHubClient, table_name: str):
        self._client = client
        self.table_name = table_name

    async def find(
        self,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        order: str = "ASC",
    ) -> list[dict[str, Any]]:
        """Find records matching filter asynchronously."""
        res = await self._client.request(
            "/v1/data/find",
            {
                "table": self.table_name,
                "filter": filter or {},
                "limit": limit,
                "offset": offset,
                "orderBy": order_by,
                "order": order,
            },
        )
        return res.get("rows", [])

    async def find_one(self, filter: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """Find first single record matching filter."""
        rows = await self.find(filter=filter, limit=1)
        return rows[0] if rows else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a record and return the inserted row."""
        res = await self._client.request("/v1/data/insert", {"table": self.table_name, "data": data})
        return res.get("row", data)

    async def insert_one(self, data: dict[str, Any]) -> dict[str, Any]:
        """Alias for create."""
        return await self.create(data)

    async def update(self, filter: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
        """Update records matching filter."""
        res = await self._client.request(
            "/v1/data/update",
            {"table": self.table_name, "filter": filter, "data": data},
        )
        return res.get("rows", [])

    async def delete(self, filter: dict[str, Any]) -> dict[str, Any]:
        """Delete records matching filter."""
        return await self._client.request(
            "/v1/data/delete",
            {"table": self.table_name, "filter": filter},
        )

    async def count(self, filter: Optional[dict[str, Any]] = None) -> int:
        """Count records matching filter."""
        res = await self._client.request(
            "/v1/data/count",
            {"table": self.table_name, "filter": filter or {}},
        )
        return res.get("count", 0)


class PGBHubAuthError(Exception):
    """Raised by AuthClient/AsyncAuthClient/StorageClient.get_file on a
    non-2xx response, carrying the server's own parsed error message
    instead of a generic httpx.HTTPStatusError with no useful detail."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _auth_request(
    client: PGBHubClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Shared HTTP helper for AuthClient/AuthAdminClient — see PGBHubAuthError."""
    url = f"{client.endpoint}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if client.api_key:
        headers["Authorization"] = f"Bearer {client.api_key}"
    if extra_headers:
        headers.update(extra_headers)

    if httpx is not None:
        with httpx.Client(timeout=timeout) as http:
            res = http.request(method, url, json=json_body, headers=headers)
            try:
                data = res.json()
            except Exception:
                data = {}
            if res.status_code >= 400:
                raise PGBHubAuthError(res.status_code, data.get("error") or res.text)
            return data
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(json_body).encode("utf-8") if json_body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            raise PGBHubAuthError(exc.code, data.get("error") or body) from exc


async def _auth_request_async(
    client: AsyncPGBHubClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    url = f"{client.endpoint}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if client.api_key:
        headers["Authorization"] = f"Bearer {client.api_key}"
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=timeout) as http:
        res = await http.request(method, url, json=json_body, headers=headers)
        try:
            data = res.json()
        except Exception:
            data = {}
        if res.status_code >= 400:
            raise PGBHubAuthError(res.status_code, data.get("error") or res.text)
        return data


class AuthAdminClient:
    """Secret-key-only user management (`client.auth.admin.*`), mirrors
    pgb-cloud's /auth/admin/users CRUD exactly."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: bool = True,
    ) -> dict[str, Any]:
        """Create a user directly (bypasses signup email verification)."""
        data = _auth_request(
            self._client,
            "POST",
            "/auth/admin/users",
            {"email": email, "password": password, "metadata": metadata or {}, "is_verified": is_verified},
        )
        return data.get("user", data)

    def list_users(self) -> list[dict[str, Any]]:
        """List users registered in this project."""
        data = _auth_request(self._client, "GET", "/auth/admin/users")
        return data.get("users", [])

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single user by ID, or None if not found."""
        try:
            data = _auth_request(self._client, "GET", f"/auth/admin/users/{user_id}")
            return data.get("user")
        except PGBHubAuthError:
            return None

    def update_user(
        self,
        user_id: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Update a user's password, metadata, or verification status."""
        body: dict[str, Any] = {}
        if password is not None:
            body["password"] = password
        if metadata is not None:
            body["metadata"] = metadata
        if is_verified is not None:
            body["is_verified"] = is_verified
        data = _auth_request(self._client, "PATCH", f"/auth/admin/users/{user_id}", body)
        return data.get("user", data)

    def delete_user(self, user_id: str) -> bool:
        """Delete a user and invalidate their sessions."""
        data = _auth_request(self._client, "DELETE", f"/auth/admin/users/{user_id}")
        return bool(data.get("success"))


class AsyncAuthAdminClient:
    """Async counterpart of AuthAdminClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    async def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: bool = True,
    ) -> dict[str, Any]:
        data = await _auth_request_async(
            self._client,
            "POST",
            "/auth/admin/users",
            {"email": email, "password": password, "metadata": metadata or {}, "is_verified": is_verified},
        )
        return data.get("user", data)

    async def list_users(self) -> list[dict[str, Any]]:
        data = await _auth_request_async(self._client, "GET", "/auth/admin/users")
        return data.get("users", [])

    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        try:
            data = await _auth_request_async(self._client, "GET", f"/auth/admin/users/{user_id}")
            return data.get("user")
        except PGBHubAuthError:
            return None

    async def update_user(
        self,
        user_id: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: Optional[bool] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if password is not None:
            body["password"] = password
        if metadata is not None:
            body["metadata"] = metadata
        if is_verified is not None:
            body["is_verified"] = is_verified
        data = await _auth_request_async(self._client, "PATCH", f"/auth/admin/users/{user_id}", body)
        return data.get("user", data)

    async def delete_user(self, user_id: str) -> bool:
        data = await _auth_request_async(self._client, "DELETE", f"/auth/admin/users/{user_id}")
        return bool(data.get("success"))


class AuthClient:
    """Built-In PGB Auth-as-a-Service client (`client.auth`).

    Two different bearer tokens are in play: the client's own `api_key`
    (a project Secret/Publishable key) identifies the *project*, sent as
    `Authorization: Bearer <key>` on every call; the *end user's* own
    access token (held in the session set via sign_up/sign_in/set_session)
    is sent separately as `X-PGB-User-Token` on the routes that need to
    know who's calling (get_user, sign_out).
    """

    def __init__(self, client: PGBHubClient):
        self._client = client
        self._session: Optional[dict[str, Any]] = None
        self.admin = AuthAdminClient(client)

    def sign_up(
        self,
        email: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Sign up a new user with email & password."""
        data = _auth_request(
            self._client, "POST", "/auth/signup",
            {"email": email, "password": password, "metadata": metadata or {}},
        )
        self._session = data.get("session")
        return data

    def sign_in(self, email: str, password: Optional[str] = None) -> dict[str, Any]:
        """Sign in with email & password."""
        data = _auth_request(self._client, "POST", "/auth/login", {"email": email, "password": password})
        if data.get("session"):
            self._session = data["session"]
        return data

    def sign_out(self) -> None:
        """Sign out and invalidate the current session."""
        token = (self._session or {}).get("access_token")
        if token:
            try:
                _auth_request(self._client, "POST", "/auth/logout", {}, extra_headers={"X-PGB-User-Token": token})
            except Exception:
                pass  # best effort — a failed server-side revoke must not block clearing local state
        self._session = None

    def get_user(self) -> Optional[dict[str, Any]]:
        """Get the current authenticated user's details."""
        token = (self._session or {}).get("access_token")
        if not token:
            return None
        try:
            data = _auth_request(self._client, "GET", "/auth/user", extra_headers={"X-PGB-User-Token": token})
            return data.get("user")
        except PGBHubAuthError:
            return None

    def get_session(self) -> Optional[dict[str, Any]]:
        """Get the current active session."""
        return self._session

    def set_session(self, session: Optional[dict[str, Any]]) -> None:
        """Set the active session."""
        self._session = session

    def refresh_session(self, refresh_token: Optional[str] = None) -> dict[str, Any]:
        """Exchange a refresh token for a new session, rotating the refresh token."""
        token = refresh_token or (self._session or {}).get("refresh_token")
        if not token:
            raise ValueError("refresh_session() requires a refresh token (none provided and no active session).")
        data = _auth_request(self._client, "POST", "/auth/refresh", {"refresh_token": token})
        self._session = data.get("session")
        return data

    def request_otp(self, email: str) -> dict[str, Any]:
        """Request a one-time passcode for passwordless sign-in."""
        return _auth_request(self._client, "POST", "/auth/otp", {"email": email})

    def verify_otp(self, email: str, token: str) -> dict[str, Any]:
        """Verify a one-time passcode and establish a session."""
        data = _auth_request(self._client, "POST", "/auth/otp/verify", {"email": email, "token": token})
        self._session = data.get("session")
        return data

    def send_magic_link(self, email: str) -> dict[str, Any]:
        """Send a passwordless magic link."""
        return _auth_request(self._client, "POST", "/auth/magic", {"email": email})

    def verify_magic_link(self, token: str) -> dict[str, Any]:
        """Verify a magic link token and establish a session."""
        data = _auth_request(self._client, "POST", "/auth/magic/verify", {"token": token})
        self._session = data.get("session")
        return data


class AsyncAuthClient:
    """Async counterpart of AuthClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client
        self._session: Optional[dict[str, Any]] = None
        self.admin = AsyncAuthAdminClient(client)

    async def sign_up(
        self,
        email: str,
        password: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        data = await _auth_request_async(
            self._client, "POST", "/auth/signup",
            {"email": email, "password": password, "metadata": metadata or {}},
        )
        self._session = data.get("session")
        return data

    async def sign_in(self, email: str, password: Optional[str] = None) -> dict[str, Any]:
        data = await _auth_request_async(self._client, "POST", "/auth/login", {"email": email, "password": password})
        if data.get("session"):
            self._session = data["session"]
        return data

    async def sign_out(self) -> None:
        token = (self._session or {}).get("access_token")
        if token:
            try:
                await _auth_request_async(self._client, "POST", "/auth/logout", {}, extra_headers={"X-PGB-User-Token": token})
            except Exception:
                pass
        self._session = None

    async def get_user(self) -> Optional[dict[str, Any]]:
        token = (self._session or {}).get("access_token")
        if not token:
            return None
        try:
            data = await _auth_request_async(self._client, "GET", "/auth/user", extra_headers={"X-PGB-User-Token": token})
            return data.get("user")
        except PGBHubAuthError:
            return None

    def get_session(self) -> Optional[dict[str, Any]]:
        return self._session

    def set_session(self, session: Optional[dict[str, Any]]) -> None:
        self._session = session

    async def refresh_session(self, refresh_token: Optional[str] = None) -> dict[str, Any]:
        token = refresh_token or (self._session or {}).get("refresh_token")
        if not token:
            raise ValueError("refresh_session() requires a refresh token (none provided and no active session).")
        data = await _auth_request_async(self._client, "POST", "/auth/refresh", {"refresh_token": token})
        self._session = data.get("session")
        return data

    async def request_otp(self, email: str) -> dict[str, Any]:
        return await _auth_request_async(self._client, "POST", "/auth/otp", {"email": email})

    async def verify_otp(self, email: str, token: str) -> dict[str, Any]:
        data = await _auth_request_async(self._client, "POST", "/auth/otp/verify", {"email": email, "token": token})
        self._session = data.get("session")
        return data

    async def send_magic_link(self, email: str) -> dict[str, Any]:
        return await _auth_request_async(self._client, "POST", "/auth/magic", {"email": email})

    async def verify_magic_link(self, token: str) -> dict[str, Any]:
        data = await _auth_request_async(self._client, "POST", "/auth/magic/verify", {"token": token})
        self._session = data.get("session")
        return data


class StorageClient:
    """Storage client (`client.storage`) — currently covers file/media
    download only; upload/list/delete are not yet exposed in the Python
    SDK (tracked as follow-up breadth work, matching the TS SDK's
    existing coverage)."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def get_file(self, file_path: str) -> dict[str, Any]:
        """Download a stored file's raw bytes.

        Returns {"data": bytes, "content_type": str, "path": str, "etag": Optional[str]}.
        """
        clean_path = file_path.lstrip("/")
        url = f"{self._client.endpoint}/storage/{clean_path}"
        headers = {"Accept": "*/*"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"

        if httpx is not None:
            with httpx.Client(timeout=30.0) as http:
                res = http.get(url, headers=headers)
                if res.status_code >= 400:
                    raise PGBHubAuthError(res.status_code, res.text)
                return {
                    "data": res.content,
                    "content_type": res.headers.get("content-type", "application/octet-stream"),
                    "path": clean_path,
                    "etag": res.headers.get("etag"),
                }
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    return {
                        "data": resp.read(),
                        "content_type": resp.headers.get("content-type", "application/octet-stream"),
                        "path": clean_path,
                        "etag": resp.headers.get("etag"),
                    }
            except urllib.error.HTTPError as exc:
                raise PGBHubAuthError(exc.code, exc.read().decode("utf-8", "replace")) from exc

    def get_media(self, file_path: str, **_transform_options: Any) -> dict[str, Any]:
        """Download a stored image.

        The server has no on-the-fly image-transform support yet (no
        width/height/format handling exists in its storage delivery
        route) — transform kwargs are accepted here for forward
        compatibility only and currently have no effect. This is a thin
        alias over get_file(); do not rely on resizing/format conversion
        actually happening until PGBHub ships real transform support.
        """
        return self.get_file(file_path)


class AsyncStorageClient:
    """Async counterpart of StorageClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    async def get_file(self, file_path: str) -> dict[str, Any]:
        clean_path = file_path.lstrip("/")
        url = f"{self._client.endpoint}/storage/{clean_path}"
        headers = {"Accept": "*/*"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        async with httpx.AsyncClient(timeout=30.0) as http:
            res = await http.get(url, headers=headers)
            if res.status_code >= 400:
                raise PGBHubAuthError(res.status_code, res.text)
            return {
                "data": res.content,
                "content_type": res.headers.get("content-type", "application/octet-stream"),
                "path": clean_path,
                "etag": res.headers.get("etag"),
            }

    async def get_media(self, file_path: str, **_transform_options: Any) -> dict[str, Any]:
        """See StorageClient.get_media — thin alias, no server-side transform support yet."""
        return await self.get_file(file_path)


class FunctionsClient:
    """Synchronous client for invoking and managing PGBHub Serverless Cloud Functions."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def invoke(
        self,
        name: str,
        payload: Any = None,
        headers: Optional[dict[str, str]] = None,
        query: Optional[dict[str, str]] = None,
    ) -> Any:
        """Invoke a serverless cloud function."""
        query_str = ""
        if query:
            import urllib.parse
            query_str = f"?{urllib.parse.urlencode(query)}"

        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions/{name}/invoke{query_str}"
        req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            req_headers["Authorization"] = f"Bearer {self._client.api_key}"
        if headers:
            req_headers.update(headers)

        data = payload if payload is not None else {}

        if httpx is not None:
            with httpx.Client(timeout=30.0) as http:
                res = http.post(url, json=data, headers=req_headers)
                res.raise_for_status()
                return res.json()
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=req_headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

    def list(self) -> list[dict[str, Any]]:
        """List all cloud functions in the target database."""
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions"
        headers = {"Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"

        if httpx is not None:
            with httpx.Client(timeout=10.0) as http:
                res = http.get(url, headers=headers)
                res.raise_for_status()
                return res.json().get("functions", [])
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8")).get("functions", [])

    def deploy(self, name: str, code: str, **options: Any) -> dict[str, Any]:
        """Create or update a function's code and configuration.

        The server's save-function logic is an upsert regardless of
        which route calls it, so this always POSTs to the functions
        collection endpoint (name in the body, not the URL). Accepts the
        same optional fields the backend does (title, description,
        runtime, entrypoint, trigger_type, trigger_config, env_vars,
        is_enabled, timeout_ms, memory_mb) as keyword arguments.
        """
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        body = {"name": name, "code": code, **options}

        if httpx is not None:
            with httpx.Client(timeout=30.0) as http:
                res = http.post(url, json=body, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data.get("function", data)
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("function", data)

    def delete(self, name: str) -> bool:
        """Delete a cloud function."""
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions/{name}"
        headers = {"Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"

        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.delete(url, headers=headers)
                res.raise_for_status()
                return bool(res.json().get("success"))
        else:
            req = urllib.request.Request(url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return bool(json.loads(resp.read().decode("utf-8")).get("success"))


class AsyncFunctionsClient:
    """Asynchronous client for invoking and managing PGBHub Serverless Cloud Functions."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    async def invoke(
        self,
        name: str,
        payload: Any = None,
        headers: Optional[dict[str, str]] = None,
        query: Optional[dict[str, str]] = None,
    ) -> Any:
        """Invoke a serverless cloud function asynchronously."""
        query_str = ""
        if query:
            import urllib.parse
            query_str = f"?{urllib.parse.urlencode(query)}"

        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions/{name}/invoke{query_str}"
        req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            req_headers["Authorization"] = f"Bearer {self._client.api_key}"
        if headers:
            req_headers.update(headers)

        data = payload if payload is not None else {}
        async with httpx.AsyncClient(timeout=30.0) as http:
            res = await http.post(url, json=data, headers=req_headers)
            res.raise_for_status()
            return res.json()

    async def list(self) -> list[dict[str, Any]]:
        """List all cloud functions asynchronously."""
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions"
        headers = {"Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"

        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.get(url, headers=headers)
            res.raise_for_status()
            return res.json().get("functions", [])

    async def deploy(self, name: str, code: str, **options: Any) -> dict[str, Any]:
        """See FunctionsClient.deploy — same upsert semantics, async."""
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        body = {"name": name, "code": code, **options}
        async with httpx.AsyncClient(timeout=30.0) as http:
            res = await http.post(url, json=body, headers=headers)
            res.raise_for_status()
            data = res.json()
            return data.get("function", data)

    async def delete(self, name: str) -> bool:
        """Delete a cloud function asynchronously."""
        url = f"{self._client.endpoint}/api/v1/databases/{self._client.database}/functions/{name}"
        headers = {"Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.delete(url, headers=headers)
            res.raise_for_status()
            return bool(res.json().get("success"))


class PGBHubClient:
    """PGBHub Client supporting direct dynamic table models and action invocations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("PGBHUB_API_KEY")
        self.endpoint = (endpoint or os.environ.get("PGBHUB_ENDPOINT", "https://cloud.pgbhub.com")).rstrip("/")
        self.database = database or os.environ.get("PGBHUB_DATABASE", "postgres")
        self.actions = ActionsProxy(self)
        self.functions = FunctionsClient(self)
        self.auth = AuthClient(self)
        self.storage = StorageClient(self)

    def table(self, name: str) -> TableClient:
        """Access a typed table model accessor."""
        return TableClient(self, name)

    def collection(self, name: str) -> DocumentCollection:
        """Access a document store collection."""
        return DocumentCollection(self, name)

    def create_database(
        self,
        name: str,
        pg_version: str = "17",
        extensions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Provision a new PGBHub-managed PostgreSQL database.

        Requires an account-level API key (scope_type "account", not a
        project-scoped pgb_sec_/pgb_pub_ key) — a project key is
        permanently bound to the one database it was issued for and the
        server rejects (403) any attempt to use it to provision an
        unrelated new one.
        """
        url = f"{self.endpoint}/api/v1/databases"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"name": name, "pg_version": pg_version, "extensions": extensions}

        if httpx is not None:
            with httpx.Client(timeout=30.0) as http:
                res = http.post(url, json=body, headers=headers)
                res.raise_for_status()
                return res.json()
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

    def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated request to PGBHub."""
        url = f"{self.endpoint}{path if path.startswith('/') else '/' + path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = {**payload, "dbname": self.database}

        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=data, headers=headers)
                res.raise_for_status()
                return res.json()
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

    def get_schema(self) -> dict[str, Any]:
        """Fetch the semantic schema JSON from PGBHub."""
        url = f"{self.endpoint}/api/v1/databases/{self.database}/schema.json"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if httpx is not None:
            with httpx.Client(timeout=10.0) as http:
                res = http.get(url, headers=headers)
                res.raise_for_status()
                return res.json()
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

    def invoke_action(
        self,
        action_name: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> ActionResponse:
        """Invoke an action synchronously."""
        res_data = self.request(
            "/v1/actions/invoke",
            {"action": action_name, "params": params, "dry_run": dry_run},
        )
        return ActionResponse.model_validate(res_data)

    def __getattr__(self, name: str):
        """Allow calling tables e.g. `client.user.find(...)` or actions e.g. `client.saveUser(params)`."""
        # Return a TableClient that also functions as an action invoker if called directly
        table_c = self.table(name)
        return table_c


class AsyncPGBHubClient:
    """Async PGBHub Client supporting dynamic table models and actions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("PGBHUB_API_KEY")
        self.endpoint = (endpoint or os.environ.get("PGBHUB_ENDPOINT", "https://cloud.pgbhub.com")).rstrip("/")
        self.database = database or os.environ.get("PGBHUB_DATABASE", "postgres")
        self.actions = AsyncActionsProxy(self)
        self.functions = AsyncFunctionsClient(self)
        self.auth = AsyncAuthClient(self)
        self.storage = AsyncStorageClient(self)

    def table(self, name: str) -> AsyncTableClient:
        """Access an async typed table model accessor."""
        return AsyncTableClient(self, name)

    def collection(self, name: str) -> AsyncDocumentCollection:
        """Access an async document store collection."""
        return AsyncDocumentCollection(self, name)

    async def create_database(
        self,
        name: str,
        pg_version: str = "17",
        extensions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """See PGBHubClient.create_database — same account-key requirement, async."""
        url = f"{self.endpoint}/api/v1/databases"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"name": name, "pg_version": pg_version, "extensions": extensions}
        async with httpx.AsyncClient(timeout=30.0) as http:
            res = await http.post(url, json=body, headers=headers)
            res.raise_for_status()
            return res.json()

    async def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated async request to PGBHub."""
        url = f"{self.endpoint}{path if path.startswith('/') else '/' + path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = {**payload, "dbname": self.database}
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(url, json=data, headers=headers)
            res.raise_for_status()
            return res.json()

    async def get_schema(self) -> dict[str, Any]:
        """Fetch the semantic schema JSON asynchronously."""
        url = f"{self.endpoint}/api/v1/databases/{self.database}/schema.json"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.get(url, headers=headers)
            res.raise_for_status()
            return res.json()

    async def invoke_action(
        self,
        action_name: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> ActionResponse:
        """Invoke an action asynchronously."""
        res_data = await self.request(
            "/v1/actions/invoke",
            {"action": action_name, "params": params, "dry_run": dry_run},
        )
        return ActionResponse.model_validate(res_data)

    def __getattr__(self, name: str):
        """Allow calling async tables e.g. `await client.user.find(...)`."""
        return self.table(name)


# Singleton shorthand instance
pgb = PGBHubClient()
PGBHub = PGBHubClient
