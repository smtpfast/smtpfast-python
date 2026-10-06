from __future__ import annotations

from collections.abc import Mapping

import httpx
from typing_extensions import Self

from ._core import AsyncCore, SyncCore
from ._resources import AsyncResource, Resource


class SMTPfast(Resource):
    """The SMTPfast API client.

    >>> client = SMTPfast()  # reads SMTPFAST_API_KEY
    >>> client.emails.send({"from": "you@yourdomain.com", "to": "them@example.org", "subject": "Hi", "text": "Hello"})
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        max_retries: int = 2,
        timeout: float = 60.0,
        headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(SyncCore(api_key, base_url, max_retries, timeout, headers, http_client=http_client))

    def close(self) -> None:
        self._core.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncSMTPfast(AsyncResource):
    """The SMTPfast API client for asyncio. Every method is a coroutine."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        max_retries: int = 2,
        timeout: float = 60.0,
        headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(AsyncCore(api_key, base_url, max_retries, timeout, headers, http_client=http_client))

    async def aclose(self) -> None:
        await self._core.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
