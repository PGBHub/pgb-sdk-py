"""Official PGBox Python Client SDK."""

from __future__ import annotations

import os
from typing import Any, Optional
import httpx
from pydantic import BaseModel


class ActionResponse(BaseModel):
    action: str
    status: str
    dry_run: bool
    duration_ms: float
    results: Any
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


class PGBoxClient:
    """PGBox Client supporting direct dynamic method calls like `pgb.saveUser(params)`."""

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

    def collection(self, name: str) -> DocumentCollection:
        """Access a document store collection."""
        return DocumentCollection(self, name)

    def get_schema(self) -> dict[str, Any]:
        """Fetch the semantic schema JSON from PGBox."""
        url = f"{self.endpoint}/api/v1/databases/{self.database}/schema.json"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=10.0) as http:
            res = http.get(url, headers=headers)
            res.raise_for_status()
            return res.json()

    def invoke_action(
        self,
        action_name: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> ActionResponse:
        """Invoke an action synchronously."""
        url = f"{self.endpoint}/v1/actions/invoke"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "action": action_name,
            "params": params,
            "dry_run": dry_run,
            "dbname": self.database,
        }

        with httpx.Client(timeout=15.0) as http:
            res = http.post(url, json=payload, headers=headers)
            res.raise_for_status()
            return ActionResponse.model_validate(res.json())

    def __getattr__(self, name: str):
        """Allow calling actions directly on the client instance, e.g. `pgb.saveUser(params)`."""
        def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return self.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


class AsyncPGBoxClient:
    """Async PGBox Client supporting direct dynamic method calls like `await pgb.saveUser(params)`."""

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

    def collection(self, name: str) -> AsyncDocumentCollection:
        """Access an async document store collection."""
        return AsyncDocumentCollection(self, name)

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
        url = f"{self.endpoint}/v1/actions/invoke"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "action": action_name,
            "params": params,
            "dry_run": dry_run,
            "dbname": self.database,
        }

        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(url, json=payload, headers=headers)
            res.raise_for_status()
            return ActionResponse.model_validate(res.json())

    def __getattr__(self, name: str):
        """Allow calling actions directly on the async client instance, e.g. `await pgb.saveUser(params)`."""
        async def invoker(params: Optional[dict[str, Any]] = None, dry_run: bool = False) -> ActionResponse:
            return await self.invoke_action(name, params or {}, dry_run=dry_run)
        return invoker


# Singleton shorthand instance
pgb = PGBoxClient()
PGBox = PGBoxClient
