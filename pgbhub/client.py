"""Official PGBHub Python Client SDK."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
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
    effects_queued: int = 0
    effects_preview: Optional[list] = None
    message: Optional[str] = None



def _with_query(client: Any, path: str, query: dict[str, Any]) -> str:
    """Path plus query string; `dbname` is added only when a database was configured."""
    params = {k: v for k, v in query.items() if v is not None and v != ""}
    if getattr(client, "database_explicit", False):
        params = {"dbname": client.database, **params}
    return f"{path}?{urllib.parse.urlencode(params)}" if params else path


def _action_body(options: dict[str, Any]) -> dict[str, Any]:
    """Map register(name=, sql=, effects=, ...) onto the API's field names."""
    if not options.get("name") or not options.get("sql"):
        raise ValueError("register() needs name= and sql= (use %(param)s placeholders in the SQL).")
    body = {
        "name": options["name"],
        "sql_template": options["sql"],
        "title": options.get("title"),
        "description": options.get("description") or "",
        "input_schema": options.get("input_schema"),
        "output_schema": options.get("output_schema"),
        "sample_params": options.get("sample_params"),
        "effects": options.get("effects"),
        "webhook_url": options.get("webhook_url"),
    }
    return {k: v for k, v in body.items() if v is not None}


class ActionsProxy:
    def __init__(self, client: PGBHubClient):
        self._client = client

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker

    def run(self, name: str, params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
        """Same as `client.actions.<name>(params)`, for names held in a variable."""
        return self._client.invoke_action(name, params or {}, dry_run=dry_run)

    def list(self) -> list[dict[str, Any]]:
        """Every registered action."""
        return _auth_request(self._client, "GET", self._client_path("/v1/actions")).get("actions", [])

    def get(self, name: str) -> dict[str, Any]:
        return _auth_request(self._client, "GET", self._client_path(f"/v1/actions/{urllib.parse.quote(name, safe='')}"))

    def register(self, **options: Any) -> dict[str, Any]:
        """Create or replace an action. See _action_body for the accepted options."""
        return _auth_request(self._client, "POST", self._client_path("/v1/actions/register"), _action_body(options))

    def delete(self, name: str) -> None:
        _auth_request(self._client, "DELETE", self._client_path(f"/v1/actions/{urllib.parse.quote(name, safe='')}"))

    def deliveries(self, action: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """What the actions' effects did: delivered, waiting, or failed (with the reason)."""
        return _auth_request(self._client, "GET", self._client_path("/v1/actions/deliveries", action=action, status=status, limit=limit)).get("deliveries", [])

    def retry_delivery(self, delivery_id: int) -> None:
        """Put a failed delivery back in the queue."""
        _auth_request(self._client, "POST", self._client_path(f"/v1/actions/deliveries/{int(delivery_id)}/retry"), {})

    def _client_path(self, path: str, **query: Any) -> str:
        return _with_query(self._client, path, query)


class AsyncActionsProxy:
    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return await self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker

    async def run(self, name: str, params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
        return await self._client.invoke_action(name, params or {}, dry_run=dry_run)

    async def list(self) -> list[dict[str, Any]]:
        return (await _auth_request_async(self._client, "GET", _with_query(self._client, "/v1/actions", {}))).get("actions", [])

    async def get(self, name: str) -> dict[str, Any]:
        return await _auth_request_async(self._client, "GET", _with_query(self._client, f"/v1/actions/{urllib.parse.quote(name, safe='')}", {}))

    async def register(self, **options: Any) -> dict[str, Any]:
        return await _auth_request_async(self._client, "POST", _with_query(self._client, "/v1/actions/register", {}), _action_body(options))

    async def delete(self, name: str) -> None:
        await _auth_request_async(self._client, "DELETE", _with_query(self._client, f"/v1/actions/{urllib.parse.quote(name, safe='')}", {}))

    async def deliveries(self, action: Optional[str] = None, status: Optional[str] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
        path = _with_query(self._client, "/v1/actions/deliveries", {"action": action, "status": status, "limit": limit})
        return (await _auth_request_async(self._client, "GET", path)).get("deliveries", [])

    async def retry_delivery(self, delivery_id: int) -> None:
        await _auth_request_async(self._client, "POST", _with_query(self._client, f"/v1/actions/deliveries/{int(delivery_id)}/retry", {}), {})


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


class PGBHubError(Exception):
    """Raised on a non-2xx response or a network failure, carrying the
    server's own message plus `status_code`, `code`, `body` and (for 429)
    `retry_after` seconds. `PGBHubAuthError` is kept as an alias."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: Optional[str] = None,
        body: Any = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.body = body
        self.retry_after = retry_after


PGBHubAuthError = PGBHubError

_RETRY_STATUSES = (502, 503, 504)


def _error_message(data: Any, fallback: str) -> str:
    if isinstance(data, dict):
        for key in ("error", "detail", "message"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return fallback


def _raise_for_response(status: int, data: Any, text: str, headers: Any) -> None:
    retry_after = None
    try:
        raw = (headers or {}).get("retry-after")
        if raw is not None and float(raw) > 0:
            retry_after = float(raw)
    except Exception:
        retry_after = None
    code = data.get("code") if isinstance(data, dict) and isinstance(data.get("code"), str) else None
    raise PGBHubError(status, _error_message(data, text or f"HTTP {status}"), code=code, body=data, retry_after=retry_after)


def _client_timeout(client: Any, default: float) -> float:
    return float(getattr(client, "timeout", None) or default)


def _build_headers(client: Any, extra_headers: Optional[dict[str, str]], has_body: bool = True) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if has_body:
        headers["Content-Type"] = "application/json"
    if client.api_key:
        headers["Authorization"] = f"Bearer {client.api_key}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _auth_request(
    client: PGBHubClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Shared HTTP helper: server errors become PGBHubError, GETs retry
    transient failures (502/503/504, connection errors) with backoff."""
    url = path if path.startswith("http") else f"{client.endpoint}{path}"
    headers = _build_headers(client, extra_headers)
    timeout = timeout if timeout is not None else _client_timeout(client, 30.0)
    attempts = 1 + (int(getattr(client, "max_retries", 2)) if method.upper() == "GET" else 0)
    delay = float(getattr(client, "retry_delay", 0.3))

    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            if httpx is not None:
                with httpx.Client(timeout=timeout) as http:
                    res = http.request(method, url, json=json_body, headers=headers)
                status, text, res_headers = res.status_code, res.text, getattr(res, "headers", {})
                try:
                    data = res.json()
                except Exception:
                    data = {}
            else:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(json_body).encode("utf-8") if json_body is not None else None,
                    headers=headers,
                    method=method,
                )
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        status, text, res_headers = resp.status, resp.read().decode("utf-8"), resp.headers
                except urllib.error.HTTPError as exc:
                    status, text, res_headers = exc.code, exc.read().decode("utf-8", "replace"), exc.headers
                try:
                    data = json.loads(text)
                except Exception:
                    data = {}
        except PGBHubError:
            raise
        except Exception as exc:
            if not last:
                time.sleep(delay * (2 ** attempt))
                continue
            timed_out = "timeout" in type(exc).__name__.lower()
            raise PGBHubError(
                0,
                f"PGBHub request timed out after {timeout}s: {method} {url}" if timed_out else f"PGBHub request failed (network error): {method} {url}: {exc}",
                code="timeout" if timed_out else "network_error",
            ) from exc
        if status in _RETRY_STATUSES and not last:
            time.sleep(delay * (2 ** attempt))
            continue
        if status >= 400:
            _raise_for_response(status, data, text, res_headers)
        return data
    raise PGBHubError(0, f"PGBHub request failed: {method} {url}", code="network_error")


async def _auth_request_async(
    client: AsyncPGBHubClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    url = path if path.startswith("http") else f"{client.endpoint}{path}"
    headers = _build_headers(client, extra_headers)
    timeout = timeout if timeout is not None else _client_timeout(client, 30.0)
    attempts = 1 + (int(getattr(client, "max_retries", 2)) if method.upper() == "GET" else 0)
    delay = float(getattr(client, "retry_delay", 0.3))

    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                res = await http.request(method, url, json=json_body, headers=headers)
            try:
                data = res.json()
            except Exception:
                data = {}
        except PGBHubError:
            raise
        except Exception as exc:
            if not last:
                await asyncio.sleep(delay * (2 ** attempt))
                continue
            timed_out = "timeout" in type(exc).__name__.lower()
            raise PGBHubError(
                0,
                f"PGBHub request timed out after {timeout}s: {method} {url}" if timed_out else f"PGBHub request failed (network error): {method} {url}: {exc}",
                code="timeout" if timed_out else "network_error",
            ) from exc
        if res.status_code in _RETRY_STATUSES and not last:
            await asyncio.sleep(delay * (2 ** attempt))
            continue
        if res.status_code >= 400:
            _raise_for_response(res.status_code, data, res.text, getattr(res, "headers", {}))
        return data
    raise PGBHubError(0, f"PGBHub request failed: {method} {url}", code="network_error")


def _resolve_endpoint(endpoint: Optional[str], project_id: Optional[str]) -> str:
    """Explicit endpoint, then PGBHUB_ENDPOINT / PGBHUB_PROJECT_URL, then the
    project's own address https://<project_id>.pgbhub.app, then the shared cloud."""
    domain = os.environ.get("PGBHUB_PROJECT_DOMAIN") or "pgbhub.app"
    chosen = (
        endpoint
        or os.environ.get("PGBHUB_ENDPOINT")
        or os.environ.get("PGBHUB_PROJECT_URL")
        or (f"https://{project_id}.{domain}" if project_id else "https://console.pgbhub.com")
    )
    return chosen.rstrip("/")


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


def _with_redirect(body: dict[str, Any], redirect_to: Optional[str]) -> dict[str, Any]:
    if redirect_to:
        body["redirect_to"] = redirect_to
    return body


class _AuthBase:
    """Every end-user auth call, shared by the sync and async clients.

    Methods build the request and hand it to `_exec`, which the sync client
    runs directly and the async client returns as an awaitable. The client's
    own key identifies the *project*; the signed-in user's access token is
    sent separately as `X-PGB-User-Token` on calls that act as that user.
    """

    def __init__(self, client: Any):
        self._client = client
        self._session: Optional[dict[str, Any]] = None

    def _exec(self, method, path, body=None, headers=None, after=None):  # pragma: no cover - overridden
        raise NotImplementedError

    def _as_user(self) -> dict[str, str]:
        token = (self._session or {}).get("access_token")
        if not token:
            raise PGBHubError(401, "PGBHub Auth: no signed-in user (sign in first, or call set_session()).", code="not_signed_in")
        return {"X-PGB-User-Token": token}

    def _keep_session(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("session"):
            self._session = data["session"]
        return data

    def get_session(self) -> Optional[dict[str, Any]]:
        """The active session, or None."""
        return self._session

    def set_session(self, session: Optional[dict[str, Any]]) -> None:
        """Adopt a session (for example one restored from storage)."""
        self._session = session

    def get_settings(self):
        """The project's sign-in rules (methods on, password policy, social providers). No sign-in needed."""
        return self._exec("GET", "/auth/settings")

    def sign_up(self, email: str, password: Optional[str] = None, metadata: Optional[dict[str, Any]] = None, redirect_to: Optional[str] = None):
        """Sign up with email & password. When the project requires email
        verification the result has `verification_required` and no session."""
        body = _with_redirect({"email": email, "password": password, "metadata": metadata or {}}, redirect_to)
        return self._exec("POST", "/auth/signup", body, after=self._keep_session)

    def sign_in(self, email: str, password: Optional[str] = None):
        """Sign in with email & password. With two-factor on, the result has
        `mfa_required` and no session: finish with verify_mfa()."""
        return self._exec("POST", "/auth/login", {"email": email, "password": password}, after=self._keep_session)

    def refresh_session(self, refresh_token: Optional[str] = None):
        """Exchange a refresh token for a new session, rotating the refresh token."""
        token = refresh_token or (self._session or {}).get("refresh_token")
        if not token:
            raise ValueError("refresh_session() requires a refresh token (none provided and no active session).")
        return self._exec("POST", "/auth/refresh", {"refresh_token": token}, after=self._keep_session)

    def request_otp(self, email: str):
        """Email a one-time passcode for passwordless sign-in."""
        return self._exec("POST", "/auth/otp", {"email": email})

    def verify_otp(self, email: str, token: str):
        """Verify a one-time passcode and establish a session."""
        return self._exec("POST", "/auth/otp/verify", {"email": email, "token": token}, after=self._keep_session)

    def send_magic_link(self, email: str, redirect_to: Optional[str] = None):
        """Email a passwordless magic link. `redirect_to` must be allowed in the project's settings."""
        return self._exec("POST", "/auth/magic", _with_redirect({"email": email}, redirect_to))

    def verify_magic_link(self, token: str):
        """Verify a magic link token and establish a session."""
        return self._exec("POST", "/auth/magic/verify", {"token": token}, after=self._keep_session)

    def resend_verification(self, email: str, redirect_to: Optional[str] = None):
        """Send the email-verification message again."""
        return self._exec("POST", "/auth/resend-verification", _with_redirect({"email": email}, redirect_to))

    def forgot_password(self, email: str, redirect_to: Optional[str] = None):
        """Email a password-reset link. Always succeeds, so it never reveals which emails have accounts."""
        return self._exec("POST", "/auth/forgot-password", _with_redirect({"email": email}, redirect_to))

    def reset_password(self, token: str, password: str):
        """Set a new password using the token from the reset email."""
        return self._exec("POST", "/auth/reset-password", {"token": token, "password": password})

    def change_password(self, new_password: str, current_password: Optional[str] = None):
        """Change the signed-in user's password. Other sessions are signed out; this one stays."""
        return self._exec(
            "POST", "/auth/user/password",
            {"current_password": current_password or "", "new_password": new_password},
            headers=self._as_user(),
        )

    def update_user(self, metadata: dict[str, Any]):
        """Merge values into the user's profile (`user_metadata`). A key set to None is removed."""
        return self._exec("POST", "/auth/user/update", {"user_metadata": metadata}, headers=self._as_user())

    def delete_account(self, password: Optional[str] = None):
        """Permanently delete the signed-in user's own account."""
        return self._exec("POST", "/auth/user/delete", {"password": password or ""}, headers=self._as_user(), after=self._forget_session)

    def _forget_session(self, data: dict[str, Any]) -> dict[str, Any]:
        self._session = None
        return data

    def get_events(self):
        """The user's recent sign-ins and security events."""
        return self._exec("GET", "/auth/user/events", headers=self._as_user(), after=lambda d: d.get("events") or [])

    def list_sessions(self):
        """The user's active sessions (devices). `is_current` marks this one."""
        return self._exec("GET", "/auth/sessions", headers=self._as_user(), after=lambda d: d.get("sessions") or [])

    def revoke_session(self, session_id: str):
        """Sign out one session (for example an old phone)."""
        return self._exec("DELETE", f"/auth/sessions/{urllib.parse.quote(session_id, safe='')}", headers=self._as_user())

    def revoke_other_sessions(self):
        """Sign out every session except this one. Returns how many were ended."""
        return self._exec("POST", "/auth/sessions/revoke-all", {}, headers=self._as_user(), after=lambda d: d.get("revoked", 0))

    def enroll_mfa(self):
        """Start two-factor enrolment: show `provisioning_uri` as a QR code, then confirm_mfa()."""
        return self._exec("POST", "/auth/mfa/enroll", {}, headers=self._as_user())

    def confirm_mfa(self, code: str):
        """Confirm enrolment with a current code. Returns one-time backup codes: show them once."""
        return self._exec("POST", "/auth/mfa/confirm", {"code": code}, headers=self._as_user())

    def disable_mfa(self, code: str):
        """Turn two-factor off (needs a current code)."""
        return self._exec("POST", "/auth/mfa/disable", {"code": code}, headers=self._as_user())

    def verify_mfa(self, challenge_token: str, code: str):
        """Finish a sign-in that returned `mfa_required`."""
        return self._exec("POST", "/auth/mfa/verify", {"challenge_token": challenge_token, "code": code}, after=self._keep_session)

    def oauth_start(self, provider: str, redirect_uri: str):
        """Get the provider's authorize URL (`authorize_url`) and the `state` to check on return."""
        q = urllib.parse.urlencode({"redirect_uri": redirect_uri})
        return self._exec("GET", f"/auth/oauth/{urllib.parse.quote(provider, safe='')}/start?{q}")

    def oauth_callback(self, provider: str, code: str, state: str, redirect_uri: str):
        """Finish a social sign-in with the `code` and `state` the provider sent back."""
        return self._exec(
            "POST", f"/auth/oauth/{urllib.parse.quote(provider, safe='')}/callback",
            {"code": code, "state": state, "redirect_uri": redirect_uri},
            after=self._keep_session,
        )


class AuthClient(_AuthBase):
    """Built-in PGB Auth client (`client.auth`)."""

    def __init__(self, client: PGBHubClient):
        super().__init__(client)
        self.admin = AuthAdminClient(client)

    def _exec(self, method, path, body=None, headers=None, after=None):
        data = _auth_request(self._client, method, path, body, extra_headers=headers)
        return after(data) if after else data

    def sign_out(self) -> None:
        """Sign out and invalidate the current session (best effort on the server)."""
        token = (self._session or {}).get("access_token")
        if token:
            try:
                _auth_request(self._client, "POST", "/auth/logout", {}, extra_headers={"X-PGB-User-Token": token})
            except Exception:
                pass  # a failed server-side revoke must not block clearing local state
        self._session = None

    def get_user(self) -> Optional[dict[str, Any]]:
        """The current user, or None when signed out or the session has expired."""
        token = (self._session or {}).get("access_token")
        if not token:
            return None
        try:
            return _auth_request(self._client, "GET", "/auth/user", extra_headers={"X-PGB-User-Token": token}).get("user")
        except PGBHubError as exc:
            if exc.status_code in (401, 403):
                return None
            raise


class AsyncAuthClient(_AuthBase):
    """Async counterpart of AuthClient: every call is awaitable."""

    def __init__(self, client: AsyncPGBHubClient):
        super().__init__(client)
        self.admin = AsyncAuthAdminClient(client)

    async def _exec(self, method, path, body=None, headers=None, after=None):
        data = await _auth_request_async(self._client, method, path, body, extra_headers=headers)
        return after(data) if after else data

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
            return (await _auth_request_async(self._client, "GET", "/auth/user", extra_headers={"X-PGB-User-Token": token})).get("user")
        except PGBHubError as exc:
            if exc.status_code in (401, 403):
                return None
            raise


_VISIBILITIES = ("public", "private")


def _project_ref(client: Any) -> str:
    """The project bucket calls address: `project_id` when configured,
    otherwise the slug in a https://<slug>.pgbhub.app endpoint."""
    if getattr(client, "project_id", None):
        return str(client.project_id)
    domain = os.environ.get("PGBHUB_PROJECT_DOMAIN") or "pgbhub.app"
    host = (urllib.parse.urlparse(client.endpoint).hostname or "").lower()
    suffix = f".{domain}"
    if host.endswith(suffix):
        slug = host[: -len(suffix)]
        if slug and "." not in slug:
            return slug
    raise ValueError(
        "Bucket management needs the project: pass project_id=..., set PGBHUB_PROJECT_ID, "
        "or use the project's address (https://<slug>.pgbhub.app) as the endpoint."
    )


def _buckets_path(client: Any, bucket: Optional[str] = None, action: str = "") -> str:
    path = f"/api/v1/projects/{urllib.parse.quote(_project_ref(client), safe='')}/storage/buckets"
    if bucket is not None:
        path += f"/{urllib.parse.quote(bucket, safe='')}"
    return path + action


def _sign_body(bucket: str, path: str, method: str, expires_in: Optional[int], content_type: Optional[str]) -> dict[str, Any]:
    verb = (method or "GET").upper()
    if verb not in ("GET", "PUT"):
        raise ValueError(f"method must be 'GET' or 'PUT', not {method!r}")
    if content_type and verb != "PUT":
        raise ValueError("content_type applies only to PUT (upload) URLs")
    body: dict[str, Any] = {"bucket": bucket, "path": path.lstrip("/"), "method": verb}
    if expires_in is not None:
        body["expires_in"] = int(expires_in)
    if content_type:
        body["content_type"] = content_type
    return body


def _create_bucket_body(name: str, visibility: str) -> dict[str, Any]:
    if visibility not in _VISIBILITIES:
        raise ValueError(f"visibility must be 'public' or 'private', not {visibility!r}")
    return {"name": name, "visibility": visibility}


def _visibility_body(name: str, visibility: str, confirm_public: bool) -> dict[str, Any]:
    if visibility not in _VISIBILITIES:
        raise ValueError(f"visibility must be 'public' or 'private', not {visibility!r}")
    if visibility == "public":
        if confirm_public is not True:
            raise ValueError(
                f"Making bucket '{name}' public exposes every object in it to anyone with its URL. "
                "Pass confirm_public=True to proceed."
            )
        return {"visibility": "public", "confirm_public": True}
    return {"visibility": "private"}


def _signed_upload_target(client: Any, url: str) -> str:
    return f"{client.endpoint}{url}" if url.startswith("/") else url


def _upload_payload(body: Any) -> bytes:
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)


def _upload_result(status: int, text: str, headers: Any, data: Any) -> dict[str, Any]:
    if status >= 400:
        _raise_for_response(status, data, text, headers)
    return data if isinstance(data, dict) else {}


class StorageClient:
    """Storage client (`client.storage`): file/media download, signed URLs and
    bucket visibility.

    Buckets are public unless made private. A private bucket's objects are
    readable only with the project's secret key (`pgb_sec_...`), by project
    members in the console, or through a signed URL; publishable keys never
    read them."""

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

    def create_signed_url(
        self,
        bucket: str,
        path: str,
        method: str = "GET",
        expires_in: Optional[int] = None,
        content_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """A signed URL for one object: GET to download (also from a private
        bucket), PUT to upload. Calls POST /storage/sign on the project's
        address and needs the project's secret key, so call it on a server
        and hand only the URL out. Returns {"url", "path", "method", "bucket",
        "file_path", "expires_in", "expires_at", "content_type",
        "bucket_visibility"}. Default lifetime 900 s; at most 86400 s for GET
        and 3600 s for PUT."""
        return _auth_request(self._client, "POST", "/storage/sign", _sign_body(bucket, path, method, expires_in, content_type))

    def upload_to_signed_url(self, url: str, body: Any, content_type: str = "application/octet-stream") -> dict[str, Any]:
        """PUT bytes (or a str) to a signed upload URL. No API key is sent: the
        URL is the credential. If the URL was minted with a content_type, pass
        the same one. Never retried. Returns {"success", "bucket", "file_path", "size_bytes"}."""
        target = _signed_upload_target(self._client, url)
        payload = _upload_payload(body)
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        timeout = _client_timeout(self._client, 30.0)
        try:
            if httpx is not None:
                with httpx.Client(timeout=timeout) as http:
                    res = http.put(target, content=payload, headers=headers)
                status, text, res_headers = res.status_code, res.text, getattr(res, "headers", {})
            else:
                req = urllib.request.Request(target, data=payload, headers=headers, method="PUT")
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        status, text, res_headers = resp.status, resp.read().decode("utf-8"), resp.headers
                except urllib.error.HTTPError as exc:
                    status, text, res_headers = exc.code, exc.read().decode("utf-8", "replace"), exc.headers
        except Exception as exc:
            raise PGBHubError(0, f"Signed upload failed (network error): {exc}", code="network_error") from exc
        try:
            data = json.loads(text) if text else {}
        except Exception:
            data = {}
        return _upload_result(status, text, res_headers, data)

    def create_bucket(self, name: str, visibility: str = "public") -> dict[str, Any]:
        """Create a bucket, public by default or "private". Needs the project's
        secret key (or an account key with storage rights)."""
        return _auth_request(self._client, "POST", _buckets_path(self._client), _create_bucket_body(name, visibility))

    def set_bucket_visibility(self, name: str, visibility: str, confirm_public: bool = False) -> dict[str, Any]:
        """Make a bucket "private" or "public". Going private is enforced within
        seconds, but copies a browser or the CDN already fetched are not
        recalled. Going public exposes every object, so it needs
        confirm_public=True; without it this raises ValueError and sends nothing."""
        body = _visibility_body(name, visibility, confirm_public)
        return _auth_request(self._client, "POST", _buckets_path(self._client, name, "/visibility"), body)


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

    async def create_signed_url(
        self,
        bucket: str,
        path: str,
        method: str = "GET",
        expires_in: Optional[int] = None,
        content_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """See StorageClient.create_signed_url."""
        return await _auth_request_async(self._client, "POST", "/storage/sign", _sign_body(bucket, path, method, expires_in, content_type))

    async def upload_to_signed_url(self, url: str, body: Any, content_type: str = "application/octet-stream") -> dict[str, Any]:
        """See StorageClient.upload_to_signed_url."""
        target = _signed_upload_target(self._client, url)
        payload = _upload_payload(body)
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=_client_timeout(self._client, 30.0)) as http:
                res = await http.put(target, content=payload, headers=headers)
        except Exception as exc:
            raise PGBHubError(0, f"Signed upload failed (network error): {exc}", code="network_error") from exc
        try:
            data = res.json()
        except Exception:
            data = {}
        return _upload_result(res.status_code, res.text, getattr(res, "headers", {}), data)

    async def create_bucket(self, name: str, visibility: str = "public") -> dict[str, Any]:
        """See StorageClient.create_bucket."""
        return await _auth_request_async(self._client, "POST", _buckets_path(self._client), _create_bucket_body(name, visibility))

    async def set_bucket_visibility(self, name: str, visibility: str, confirm_public: bool = False) -> dict[str, Any]:
        """See StorageClient.set_bucket_visibility."""
        body = _visibility_body(name, visibility, confirm_public)
        return await _auth_request_async(self._client, "POST", _buckets_path(self._client, name, "/visibility"), body)


MAIL_PROVIDER_UNAVAILABLE = "MAIL_PROVIDER_UNAVAILABLE"
"""`PGBHubError.code` when the platform has no mail provider configured (HTTP 503)."""


def _mail_body(
    to: str,
    subject: str,
    text: str,
    html: Optional[str],
    from_addr: Optional[str],
    reply_to: Optional[str],
) -> dict[str, Any]:
    if not isinstance(to, str):
        raise TypeError("mail.send() takes one recipient address as a string")
    body: dict[str, Any] = {"to": to, "subject": subject, "text": text}
    if html is not None:
        body["html"] = html
    if from_addr is not None:
        body["from"] = from_addr
    if reply_to:
        body["reply_to"] = reply_to
    return body


def _mail_result(data: Any) -> dict[str, Any]:
    result = dict(data) if isinstance(data, dict) else {}
    if result.get("message_id") is None and result.get("mail_id") is not None:
        result["message_id"] = result["mail_id"]
    return result


class MailClient:
    """Transactional mail (`client.mail`). Sending needs the project's
    secret key. A failed send raises `PGBHubError`; with no mail provider
    configured that is status 503 and code `MAIL_PROVIDER_UNAVAILABLE`."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: Optional[str] = None,
        from_addr: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send one email. `reply_to` is a single address for the Reply-To
        header (line breaks, commas and semicolons are refused with 400).
        Returns the server's result with `message_id` set (filled from
        `mail_id` on an older server)."""
        body = _mail_body(to, subject, text, html, from_addr, reply_to)
        return _mail_result(_auth_request(self._client, "POST", "/mail/send", body))


class AsyncMailClient:
    """Async counterpart of MailClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: Optional[str] = None,
        from_addr: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """See MailClient.send."""
        body = _mail_body(to, subject, text, html, from_addr, reply_to)
        return _mail_result(await _auth_request_async(self._client, "POST", "/mail/send", body))


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


class CronClient:
    """Scheduled (cron) job management (`client.cron`), addressed by
    database name. target_config's shape depends on target_type:
    function -> {function_name, payload}, sql -> {sql},
    action -> {action_name, params}, http -> {url, method, body?},
    mail -> {to, subject, body}.
    """

    def __init__(self, client: PGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    @property
    def _base(self) -> str:
        return f"{self._client.endpoint}/api/v1/databases/{self._client.database}/crons"

    def list(self) -> list[dict[str, Any]]:
        """List scheduled cron jobs."""
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.get(self._base, headers=self._headers())
                res.raise_for_status()
                return res.json().get("crons", [])
        req = urllib.request.Request(self._base, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("crons", [])

    def create(self, name: str, expression: str, target_type: str, target_config: dict[str, Any], **options: Any) -> dict[str, Any]:
        """Create a scheduled cron job. `options` may include description,
        timezone, is_enabled, concurrency_policy, timeout_seconds,
        max_retries, retry_delay_seconds."""
        body = {"name": name, "expression": expression, "target_type": target_type, "target_config": target_config, **options}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(self._base, json=body, headers=self._headers())
                res.raise_for_status()
                return res.json()
        req = urllib.request.Request(self._base, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def toggle(self, cron_id: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a cron job."""
        url = f"{self._base}/{cron_id}/toggle"
        body = {"enabled": enabled}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=body, headers=self._headers())
                res.raise_for_status()
                return res.json()
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run(self, cron_id: str) -> dict[str, Any]:
        """Manually trigger a cron job to run immediately."""
        url = f"{self._base}/{cron_id}/run"
        if httpx is not None:
            with httpx.Client(timeout=40.0) as http:
                res = http.post(url, headers=self._headers())
                res.raise_for_status()
                return res.json()
        req = urllib.request.Request(url, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=40.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def delete(self, cron_id: str) -> bool:
        """Delete a cron job."""
        url = f"{self._base}/{cron_id}"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.delete(url, headers=self._headers())
                res.raise_for_status()
                return bool(res.json().get("deleted"))
        req = urllib.request.Request(url, headers=self._headers(), method="DELETE")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return bool(json.loads(resp.read().decode("utf-8")).get("deleted"))

    def list_runs(self, cron_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List recent run history for a cron job."""
        url = f"{self._base}/{cron_id}/runs?limit={limit}"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.get(url, headers=self._headers())
                res.raise_for_status()
                return res.json().get("runs", [])
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("runs", [])

    def update(self, cron_id: str, **updates: Any) -> dict[str, Any]:
        """Update a cron job's configuration (name, description,
        expression, timezone, concurrency_policy, timeout_seconds,
        max_retries, target_type, target_config)."""
        url = f"{self._base}/{cron_id}"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.request("PATCH", url, json=updates, headers=self._headers())
                res.raise_for_status()
                return res.json()
        req = urllib.request.Request(url, data=json.dumps(updates).encode("utf-8"), headers=self._headers(), method="PATCH")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))


class AsyncCronClient:
    """Async counterpart of CronClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    @property
    def _base(self) -> str:
        return f"{self._client.endpoint}/api/v1/databases/{self._client.database}/crons"

    async def list(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.get(self._base, headers=self._headers())
            res.raise_for_status()
            return res.json().get("crons", [])

    async def create(self, name: str, expression: str, target_type: str, target_config: dict[str, Any], **options: Any) -> dict[str, Any]:
        body = {"name": name, "expression": expression, "target_type": target_type, "target_config": target_config, **options}
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._base, json=body, headers=self._headers())
            res.raise_for_status()
            return res.json()

    async def toggle(self, cron_id: str, enabled: bool) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(f"{self._base}/{cron_id}/toggle", json={"enabled": enabled}, headers=self._headers())
            res.raise_for_status()
            return res.json()

    async def run(self, cron_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=40.0) as http:
            res = await http.post(f"{self._base}/{cron_id}/run", headers=self._headers())
            res.raise_for_status()
            return res.json()

    async def delete(self, cron_id: str) -> bool:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.delete(f"{self._base}/{cron_id}", headers=self._headers())
            res.raise_for_status()
            return bool(res.json().get("deleted"))

    async def list_runs(self, cron_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.get(f"{self._base}/{cron_id}/runs?limit={limit}", headers=self._headers())
            res.raise_for_status()
            return res.json().get("runs", [])

    async def update(self, cron_id: str, **updates: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.request("PATCH", f"{self._base}/{cron_id}", json=updates, headers=self._headers())
            res.raise_for_status()
            return res.json()


class JobsClient:
    """On-demand asynchronous background job queue (`client.jobs`),
    addressed by database name. Execution happens out-of-band in the
    server's own jobs scheduler -- these methods only enqueue/inspect/
    cancel."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    @property
    def _base(self) -> str:
        return f"{self._client.endpoint}/api/v1/databases/{self._client.database}/jobs"

    def enqueue(self, job_type: str, target_type: str, target_config: dict[str, Any], **options: Any) -> dict[str, Any]:
        """Enqueue a new background job. `options` may include payload,
        idempotency_key, max_attempts."""
        body = {"job_type": job_type, "target_type": target_type, "target_config": target_config, **options}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(self._base, json=body, headers=self._headers())
                res.raise_for_status()
                return res.json().get("job", {})
        req = urllib.request.Request(self._base, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("job", {})

    def get(self, job_id: int) -> Optional[dict[str, Any]]:
        """Fetch a single job by ID, or None if not found."""
        url = f"{self._base}/{job_id}"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.get(url, headers=self._headers())
                if res.status_code == 404:
                    return None
                res.raise_for_status()
                return res.json().get("job")
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8")).get("job")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def list(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """List jobs, optionally filtered by status."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        qs = urllib.parse.urlencode(params)
        url = f"{self._base}?{qs}"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.get(url, headers=self._headers())
                res.raise_for_status()
                return res.json().get("jobs", [])
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("jobs", [])

    def cancel(self, job_id: int) -> bool:
        """Cancel a pending/running job. Returns False if it could not
        be cancelled (already running or finished) instead of raising."""
        url = f"{self._base}/{job_id}/cancel"
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, headers=self._headers())
                if res.status_code == 409:
                    return False
                res.raise_for_status()
                return bool(res.json().get("cancelled"))
        req = urllib.request.Request(url, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return bool(json.loads(resp.read().decode("utf-8")).get("cancelled"))
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return False
            raise


class AsyncJobsClient:
    """Async counterpart of JobsClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    @property
    def _base(self) -> str:
        return f"{self._client.endpoint}/api/v1/databases/{self._client.database}/jobs"

    async def enqueue(self, job_type: str, target_type: str, target_config: dict[str, Any], **options: Any) -> dict[str, Any]:
        body = {"job_type": job_type, "target_type": target_type, "target_config": target_config, **options}
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._base, json=body, headers=self._headers())
            res.raise_for_status()
            return res.json().get("job", {})

    async def get(self, job_id: int) -> Optional[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.get(f"{self._base}/{job_id}", headers=self._headers())
            if res.status_code == 404:
                return None
            res.raise_for_status()
            return res.json().get("job")

    async def list(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        params = {"limit": limit}
        if status:
            params["status"] = status
        qs = urllib.parse.urlencode(params)
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.get(f"{self._base}?{qs}", headers=self._headers())
            res.raise_for_status()
            return res.json().get("jobs", [])

    async def cancel(self, job_id: int) -> bool:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(f"{self._base}/{job_id}/cancel", headers=self._headers())
            if res.status_code == 409:
                return False
            res.raise_for_status()
            return bool(res.json().get("cancelled"))


class QueuesClient:
    """Durable message queues (`client.queues`). Unlike Cron/Jobs/
    Functions, queue routes are addressed by project ID, not database
    name (/api/v1/projects/{id}/queues/...) -- pass project_id to
    PGBHubClient or set PGBHUB_PROJECT_ID. Queue creation/deletion is
    dashboard-only today (no API route); this client covers
    send/receive/ack/nack against an already-created queue."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    def _url(self, queue_name: str, action: str) -> str:
        if not self._client.project_id:
            raise ValueError("QueuesClient requires project_id — pass project_id= to PGBHubClient, or set PGBHUB_PROJECT_ID.")
        return f"{self._client.endpoint}/api/v1/projects/{self._client.project_id}/queues/{queue_name}/{action}"

    def send(self, queue_name: str, payload: Any, **options: Any) -> dict[str, Any]:
        """Send a message to a queue. `options` may include
        delay_seconds, deduplication_id."""
        body = {"payload": payload, **options}
        url = self._url(queue_name, "send")
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=body, headers=self._headers())
                res.raise_for_status()
                return res.json().get("message", {})
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("message", {})

    def receive(self, queue_name: str, **options: Any) -> list[dict[str, Any]]:
        """Receive (and lease) messages from a queue. `options` may
        include max_messages, visibility_timeout, consumer_id."""
        url = self._url(queue_name, "receive")
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=options, headers=self._headers())
                res.raise_for_status()
                return res.json().get("messages", [])
        req = urllib.request.Request(url, data=json.dumps(options).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8")).get("messages", [])

    def ack(self, queue_name: str, message_id: str) -> bool:
        """Acknowledge (delete) a successfully processed message."""
        url = self._url(queue_name, "ack")
        body = {"message_id": message_id}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=body, headers=self._headers())
                res.raise_for_status()
                return bool(res.json().get("ok"))
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return bool(json.loads(resp.read().decode("utf-8")).get("ok"))

    def nack(self, queue_name: str, message_id: str, error: Optional[str] = None) -> bool:
        """Negatively acknowledge a message — returns it to the queue
        (or to the DLQ past max retries)."""
        url = self._url(queue_name, "nack")
        body = {"message_id": message_id, "error": error}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=body, headers=self._headers())
                res.raise_for_status()
                return bool(res.json().get("ok"))
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return bool(json.loads(resp.read().decode("utf-8")).get("ok"))


class AsyncQueuesClient:
    """Async counterpart of QueuesClient."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    def _url(self, queue_name: str, action: str) -> str:
        if not self._client.project_id:
            raise ValueError("QueuesClient requires project_id — pass project_id= to AsyncPGBHubClient, or set PGBHUB_PROJECT_ID.")
        return f"{self._client.endpoint}/api/v1/projects/{self._client.project_id}/queues/{queue_name}/{action}"

    async def send(self, queue_name: str, payload: Any, **options: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._url(queue_name, "send"), json={"payload": payload, **options}, headers=self._headers())
            res.raise_for_status()
            return res.json().get("message", {})

    async def receive(self, queue_name: str, **options: Any) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._url(queue_name, "receive"), json=options, headers=self._headers())
            res.raise_for_status()
            return res.json().get("messages", [])

    async def ack(self, queue_name: str, message_id: str) -> bool:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._url(queue_name, "ack"), json={"message_id": message_id}, headers=self._headers())
            res.raise_for_status()
            return bool(res.json().get("ok"))

    async def nack(self, queue_name: str, message_id: str, error: Optional[str] = None) -> bool:
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(self._url(queue_name, "nack"), json={"message_id": message_id, "error": error}, headers=self._headers())
            res.raise_for_status()
            return bool(res.json().get("ok"))


class RealtimeClient:
    """Realtime broadcast channels (`client.realtime`). Channel names
    are namespaced server-side by project, so two different projects'
    channels of the same name never collide. Streaming/subscribe is not
    exposed synchronously here (use AsyncRealtimeClient.stream for SSE
    subscription)."""

    def __init__(self, client: PGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    def broadcast(self, channel: str, payload: Any, event: str = "message", sender_id: Optional[str] = None) -> dict[str, Any]:
        """Broadcast a message to a realtime channel."""
        url = f"{self._client.endpoint}/api/v1/realtime/channels/{channel}/broadcast"
        body = {"channel": channel, "event": event, "payload": payload, "sender_id": sender_id}
        if httpx is not None:
            with httpx.Client(timeout=15.0) as http:
                res = http.post(url, json=body, headers=self._headers())
                res.raise_for_status()
                return res.json()
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8"))


class AsyncRealtimeClient:
    """Async counterpart of RealtimeClient, plus SSE stream subscription."""

    def __init__(self, client: AsyncPGBHubClient):
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        return headers

    async def broadcast(self, channel: str, payload: Any, event: str = "message", sender_id: Optional[str] = None) -> dict[str, Any]:
        url = f"{self._client.endpoint}/api/v1/realtime/channels/{channel}/broadcast"
        body = {"channel": channel, "event": event, "payload": payload, "sender_id": sender_id}
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(url, json=body, headers=self._headers())
            res.raise_for_status()
            return res.json()

    async def stream(self, channel: str):
        """Subscribe to a realtime channel via Server-Sent Events.
        Yields {"event": str, "data": Any} dicts as they arrive; stop
        iterating (e.g. `break`) to disconnect."""
        url = f"{self._client.endpoint}/api/v1/realtime/stream"
        headers = {"Accept": "text/event-stream"}
        if self._client.api_key:
            headers["Authorization"] = f"Bearer {self._client.api_key}"
        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream("GET", url, params={"channel": channel}, headers=headers) as res:
                res.raise_for_status()
                current_event = "message"
                current_data: list[str] = []
                async for line in res.aiter_lines():
                    if line == "":
                        if current_data:
                            raw = "\n".join(current_data)
                            try:
                                data: Any = json.loads(raw)
                            except Exception:
                                data = raw
                            yield {"event": current_event, "data": data}
                            current_event = "message"
                            current_data = []
                    elif line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[len("data:"):].strip())


class PGBHubClient:
    """PGBHub Client supporting direct dynamic table models and action invocations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        database: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_delay: float = 0.3,
    ):
        self.api_key = api_key or os.environ.get("PGBHUB_API_KEY") or os.environ.get("PGBHUB_PUBLISHABLE_KEY")
        self.project_id = project_id or os.environ.get("PGBHUB_PROJECT_ID")
        self.endpoint = _resolve_endpoint(endpoint, self.project_id)
        explicit_db = database or os.environ.get("PGBHUB_DATABASE")
        self.database = explicit_db or "postgres"
        self.database_explicit = bool(explicit_db)
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.actions = ActionsProxy(self)
        self.functions = FunctionsClient(self)
        self.auth = AuthClient(self)
        self.storage = StorageClient(self)
        self.mail = MailClient(self)
        self.cron = CronClient(self)
        self.jobs = JobsClient(self)
        self.queues = QueuesClient(self)
        self.realtime = RealtimeClient(self)

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
        """Make an authenticated POST to PGBHub. A database is only named when
        one was configured; otherwise the server uses the one the key belongs to."""
        data = {**payload, "dbname": self.database} if self.database_explicit else dict(payload)
        return _auth_request(self, "POST", path if path.startswith("/") else "/" + path, data)

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
        project_id: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_delay: float = 0.3,
    ):
        self.api_key = api_key or os.environ.get("PGBHUB_API_KEY") or os.environ.get("PGBHUB_PUBLISHABLE_KEY")
        self.project_id = project_id or os.environ.get("PGBHUB_PROJECT_ID")
        self.endpoint = _resolve_endpoint(endpoint, self.project_id)
        explicit_db = database or os.environ.get("PGBHUB_DATABASE")
        self.database = explicit_db or "postgres"
        self.database_explicit = bool(explicit_db)
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.actions = AsyncActionsProxy(self)
        self.functions = AsyncFunctionsClient(self)
        self.auth = AsyncAuthClient(self)
        self.storage = AsyncStorageClient(self)
        self.mail = AsyncMailClient(self)
        self.cron = AsyncCronClient(self)
        self.jobs = AsyncJobsClient(self)
        self.queues = AsyncQueuesClient(self)
        self.realtime = AsyncRealtimeClient(self)

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
        """Make an authenticated async POST to PGBHub (see PGBHubClient.request)."""
        data = {**payload, "dbname": self.database} if self.database_explicit else dict(payload)
        return await _auth_request_async(self, "POST", path if path.startswith("/") else "/" + path, data)

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
