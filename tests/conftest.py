import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import smtpfast
import smtpfast._core


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtpfast._core, "_backoff", lambda attempt: 0.0)


Reply = httpx.Response | Exception | Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, replies: list[Reply]) -> None:
        self.replies = list(replies)
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.calls.append(request)
        reply = self.replies.pop(0) if self.replies else ok({"ok": True})
        if isinstance(reply, Exception):
            raise reply
        return reply(request) if callable(reply) else reply

    def body(self, i: int = 0) -> Any:
        return json.loads(self.calls[i].content) if self.calls[i].content else None


def ok(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers or {})


def make(replies: list[Reply] | None = None, **kwargs: Any) -> tuple[smtpfast.SMTPfast, Recorder]:
    rec = Recorder(replies or [])
    client = smtpfast.SMTPfast("sf_test_key", http_client=httpx.Client(transport=httpx.MockTransport(rec)), **kwargs)
    return client, rec


def make_async(replies: list[Reply] | None = None, **kwargs: Any) -> tuple[smtpfast.AsyncSMTPfast, Recorder]:
    rec = Recorder(replies or [])
    client = smtpfast.AsyncSMTPfast("sf_test_key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(rec)), **kwargs)
    return client, rec
