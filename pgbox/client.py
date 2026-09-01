"""Official PGBox Python Client SDK."""

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
    def __init__(self, client: PGBoxClient):
        self._client = client

    def __getattr__(self, name: str):
        def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


class AsyncActionsProxy:
    def __init__(self, client: AsyncPGBoxClient):
        self._client = client

    def __getattr__(self, name: str):
        async def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return await self._client.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


class DocumentCollection:
    def __init__(self, client: PGBoxClient, name: str):
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
    def __init__(self, client: AsyncPGBoxClient, name: str):
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

    def __init__(self, client: PGBoxClient, table_name: str):
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

    def __init__(self, client: AsyncPGBoxClient, table_name: str):
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


class PGBoxClient:
    """PGBox Client supporting direct dynamic table models and action invocations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("PGBOX_API_KEY")
        self.endpoint = (endpoint or os.environ.get("PGBOX_ENDPOINT", "https://cloud.pgboxhub.com")).rstrip("/")
        self.database = database or os.environ.get("PGBOX_DATABASE", "postgres")
        self.actions = ActionsProxy(self)

    def table(self, name: str) -> TableClient:
        """Access a typed table model accessor."""
        return TableClient(self, name)

    def collection(self, name: str) -> DocumentCollection:
        """Access a document store collection."""
        return DocumentCollection(self, name)

    def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated request to PGBox."""
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
        """Fetch the semantic schema JSON from PGBox."""
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


class AsyncPGBoxClient:
    """Async PGBox Client supporting dynamic table models and actions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("PGBOX_API_KEY")
        self.endpoint = (endpoint or os.environ.get("PGBOX_ENDPOINT", "https://cloud.pgboxhub.com")).rstrip("/")
        self.database = database or os.environ.get("PGBOX_DATABASE", "postgres")
        self.actions = AsyncActionsProxy(self)

    def table(self, name: str) -> AsyncTableClient:
        """Access an async typed table model accessor."""
        return AsyncTableClient(self, name)

    def collection(self, name: str) -> AsyncDocumentCollection:
        """Access an async document store collection."""
        return AsyncDocumentCollection(self, name)

    async def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated async request to PGBox."""
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
pgb = PGBoxClient()
PGBox = PGBoxClient
