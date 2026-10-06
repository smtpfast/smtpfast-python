from __future__ import annotations

import asyncio
import email.utils
import os
import random
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any
from urllib.parse import quote

import httpx
from typing_extensions import TypedDict

from ._errors import APIConnectionError, APIError, APITimeoutError, SMTPfastError
from ._version import __version__

DEFAULT_BASE_URL = "https://smtpfa.st/api"
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
SAFE_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}
MAX_RETRY_AFTER = 60.0


class RequestOptions(TypedDict, total=False):
    """Per-call settings: `timeout` in seconds, `max_retries`, and extra `headers`."""

    timeout: float
    max_retries: int
    headers: Mapping[str, str]


class _Core:
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        max_retries: int,
        timeout: float,
        headers: Mapping[str, str] | None,
    ) -> None:
        key = (api_key or os.environ.get("SMTPFAST_API_KEY") or "").strip()
        if not key:
            raise SMTPfastError("No API key: pass api_key= or set the SMTPFAST_API_KEY environment variable.")
        self.base_url = (base_url or os.environ.get("SMTPFAST_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {key}",
            "User-Agent": f"smtpfast-python/{__version__}",
            "Accept": "application/json",
            **(headers or {}),
        }

    def _build(self, http_method, route, path_params, query, body, idempotent, idempotency_key, options):
        options = options or {}
        max_retries = options.get("max_retries", self.max_retries)
        timeout = options.get("timeout", self.timeout)
        headers = {**self.headers, **(options.get("headers") or {})}
        if idempotent:
            key = idempotency_key or (str(uuid.uuid4()) if max_retries > 0 else None)
            if key:
                headers["Idempotency-Key"] = key
        params = {k: _query_value(v) for k, v in (query or {}).items() if v is not None}
        request = httpx.Request(
            http_method,
            self.base_url + _fill(route, path_params),
            params=params,
            json=body,
            headers=headers,
            extensions={"timeout": httpx.Timeout(timeout).as_dict()},
        )
        return request, max_retries, timeout


class SyncCore(_Core):
    def __init__(self, *args: Any, http_client: httpx.Client | None = None) -> None:
        super().__init__(*args)
        self.http = http_client or httpx.Client()
        self._owns_http = http_client is None

    def request(self, http_method, route, *, path_params=None, query=None, body=None, idempotent=False, idempotency_key=None, options=None):
        request, max_retries, timeout = self._build(http_method, route, path_params, query, body, idempotent, idempotency_key, options)
        retryable = _retryable(request)
        attempt = 0
        while True:
            try:
                response = self.http.send(request)
            except httpx.TimeoutException as err:
                if not retryable or attempt >= max_retries:
                    raise APITimeoutError(timeout) from err
                time.sleep(_backoff(attempt))
                attempt += 1
                continue
            except httpx.TransportError as err:
                if not retryable or attempt >= max_retries:
                    raise APIConnectionError() from err
                time.sleep(_backoff(attempt))
                attempt += 1
                continue
            wait = _retry_delay(response, attempt, retryable)
            if wait is None or attempt >= max_retries:
                response.read()
                return _result(response)
            response.close()
            time.sleep(wait)
            attempt += 1

    def paginate(self, http_method, route, *, path_params=None, query=None, body=None, options=None) -> Iterator[Any]:
        query = dict(query or {})
        while True:
            page = self.request(http_method, route, path_params=path_params, query=query, options=options) or {}
            items = page.get("data") or []
            yield from items
            last = items[-1] if items else None
            if not page.get("has_more") or not isinstance(last, dict) or not last.get("id"):
                return
            query["after"] = last["id"]

    def close(self) -> None:
        if self._owns_http:
            self.http.close()


class AsyncCore(_Core):
    def __init__(self, *args: Any, http_client: httpx.AsyncClient | None = None) -> None:
        super().__init__(*args)
        self.http = http_client or httpx.AsyncClient()
        self._owns_http = http_client is None

    async def request(self, http_method, route, *, path_params=None, query=None, body=None, idempotent=False, idempotency_key=None, options=None):
        request, max_retries, timeout = self._build(http_method, route, path_params, query, body, idempotent, idempotency_key, options)
        retryable = _retryable(request)
        attempt = 0
        while True:
            try:
                response = await self.http.send(request)
            except httpx.TimeoutException as err:
                if not retryable or attempt >= max_retries:
                    raise APITimeoutError(timeout) from err
                await asyncio.sleep(_backoff(attempt))
                attempt += 1
                continue
            except httpx.TransportError as err:
                if not retryable or attempt >= max_retries:
                    raise APIConnectionError() from err
                await asyncio.sleep(_backoff(attempt))
                attempt += 1
                continue
            wait = _retry_delay(response, attempt, retryable)
            if wait is None or attempt >= max_retries:
                await response.aread()
                return _result(response)
            await response.aclose()
            await asyncio.sleep(wait)
            attempt += 1

    async def paginate(self, http_method, route, *, path_params=None, query=None, body=None, options=None) -> AsyncIterator[Any]:
        query = dict(query or {})
        while True:
            page = await self.request(http_method, route, path_params=path_params, query=query, options=options) or {}
            items = page.get("data") or []
            for item in items:
                yield item
            last = items[-1] if items else None
            if not page.get("has_more") or not isinstance(last, dict) or not last.get("id"):
                return
            query["after"] = last["id"]

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()


class _SyncResource:
    def __init__(self, core: SyncCore) -> None:
        self._core = core


class _AsyncResource:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core


def _fill(route: str, values: Mapping[str, str] | None) -> str:
    for name, value in (values or {}).items():
        route = route.replace("{" + name + "}", quote(str(value), safe=""))
    return route


def _query_value(v: Any) -> Any:
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def _retryable(request: httpx.Request) -> bool:
    return request.method in SAFE_METHODS or "Idempotency-Key" in request.headers


def _retry_delay(response: httpx.Response, attempt: int, retryable: bool) -> float | None:
    """Seconds to wait before retrying this response, or None for no retry."""
    if response.status_code not in RETRY_STATUS:
        return None
    after = _retry_after(response.headers.get("Retry-After"))
    if response.status_code == 429:
        # A per-second limit sends Retry-After and rejects before any work is
        # done, so any method may retry. Without the header (an hourly or
        # daily limit), retrying soon cannot succeed.
        if after is None or after > MAX_RETRY_AFTER:
            return None
        return after
    if not retryable:
        return None
    return after if after is not None and after <= MAX_RETRY_AFTER else _backoff(attempt)


def _retry_after(header: str | None) -> float | None:
    if not header:
        return None
    try:
        return max(float(header), 0.0)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return None
        return max(float(parsed.timestamp() - time.time()), 0.0)


def _backoff(attempt: int) -> float:
    return float(min(0.5 * 2**attempt, 8.0)) * (0.75 + random.random() * 0.5)


def _result(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        raise APIError.from_response(response)
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text
