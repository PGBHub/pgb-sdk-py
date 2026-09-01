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


class PGBoxClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = "https://cloud.pgboxhub.com",
        database: str = "postgres",
    ):
        self.api_key = api_key or os.environ.get("PGBOX_API_KEY")
        self.endpoint = endpoint.rstrip("/")
        self.database = database
        self.actions = ActionsProxy(self)

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


class AsyncPGBoxClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = "https://cloud.pgboxhub.com",
        database: str = "postgres",
    ):
        self.api_key = api_key or os.environ.get("PGBOX_API_KEY")
        self.endpoint = endpoint.rstrip("/")
        self.database = database
        self.actions = AsyncActionsProxy(self)

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
