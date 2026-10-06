import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from conftest import make, make_async, ok

import smtpfast
from smtpfast import webhooks

NO_WAIT = {"Retry-After": "0"}


def test_send_email():
    client, rec = make([ok({"id": "em_1", "object": "email"})])
    sent = client.emails.send({"from": "a@yourapp.dev", "to": ["b@inbox.dev"], "subject": "Hi", "text": "Hello"})
    assert sent == {"id": "em_1", "object": "email"}
    req = rec.calls[0]
    assert req.method == "POST"
    assert str(req.url) == "https://smtpfa.st/api/v1/emails"
    assert req.headers["authorization"] == "Bearer sf_test_key"
    assert req.headers["user-agent"].startswith("smtpfast-python/")
    assert rec.body() == {"from": "a@yourapp.dev", "to": ["b@inbox.dev"], "subject": "Hi", "text": "Hello"}


def test_path_params_are_encoded():
    client, rec = make()
    client.inboxes.threads.emails.reply("in 1", "th_2", "em/3", {"text": "Thanks"})
    assert rec.calls[0].url.raw_path.decode() == "/api/v1/inboxes/in%201/threads/th_2/emails/em%2F3/reply"


def test_query_params_skip_none_and_format_bools():
    client, rec = make([ok({"data": [], "has_more": False})])
    client.contacts.list(limit=5, disposable=False)
    assert dict(rec.calls[0].url.params) == {"limit": "5", "disposable": "false"}


def test_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("SMTPFAST_API_KEY", "sf_env")
    rec_calls = []
    transport = httpx.MockTransport(lambda r: rec_calls.append(r) or ok([]))
    client = smtpfast.SMTPfast(base_url="http://localhost:3000/api/", http_client=httpx.Client(transport=transport))
    client.domains.list()
    assert str(rec_calls[0].url) == "http://localhost:3000/api/v1/domains"
    assert rec_calls[0].headers["authorization"] == "Bearer sf_env"


def test_no_api_key(monkeypatch):
    monkeypatch.delenv("SMTPFAST_API_KEY", raising=False)
    with pytest.raises(smtpfast.SMTPfastError):
        smtpfast.SMTPfast()


def test_typed_errors():
    client, _ = make([ok({"error": "Invalid API key"}, 401)])
    with pytest.raises(smtpfast.AuthenticationError) as info:
        client.domains.list()
    assert info.value.status == 401
    assert str(info.value) == "401: Invalid API key"
    assert info.value.body == {"error": "Invalid API key"}


def test_error_keeps_extra_fields():
    body = {"error": "Missing template variables", "missing_variables": ["NAME"]}
    client, _ = make([ok(body, 422)])
    with pytest.raises(smtpfast.UnprocessableEntityError) as info:
        client.emails.send({"from": "a@yourapp.dev", "to": "b@inbox.dev", "template": {"id": "t"}})
    assert info.value.body == body


def test_retries_get_after_503():
    client, rec = make([ok({"error": "busy"}, 503, NO_WAIT), ok([])])
    assert client.domains.list() == []
    assert len(rec.calls) == 2


def test_send_retry_reuses_idempotency_key():
    client, rec = make([ok({"error": "oops"}, 500, NO_WAIT), ok({"id": "em_1"})])
    client.emails.send({"from": "a@yourapp.dev", "to": "b@inbox.dev", "subject": "s", "text": "t"})
    keys = [c.headers.get("idempotency-key") for c in rec.calls]
    assert len(keys) == 2 and keys[0] and keys[0] == keys[1]


def test_callers_idempotency_key():
    client, rec = make([ok({"id": "em_1"})])
    client.emails.send({"from": "a@yourapp.dev", "to": "b@inbox.dev", "subject": "s", "text": "t"}, idempotency_key="order-42")
    assert rec.calls[0].headers["idempotency-key"] == "order-42"


def test_post_without_key_is_not_retried_after_500():
    client, rec = make([ok({"error": "oops"}, 500, NO_WAIT)])
    with pytest.raises(smtpfast.InternalServerError):
        client.contacts.create({"email": "b@inbox.dev"})
    assert len(rec.calls) == 1


def test_per_second_429_is_retried_for_any_method():
    client, rec = make([ok({"error": "Rate limit exceeded"}, 429, NO_WAIT), ok({"id": "ct_1"})])
    assert client.contacts.create({"email": "b@inbox.dev"}) == {"id": "ct_1"}
    assert len(rec.calls) == 2


def test_429_without_retry_after_is_not_retried():
    client, rec = make([ok({"error": "Hourly sending limit reached"}, 429)])
    with pytest.raises(smtpfast.RateLimitError):
        client.domains.list()
    assert len(rec.calls) == 1


def test_stops_after_max_retries():
    client, rec = make([ok({"error": "busy"}, 503, NO_WAIT)] * 5, max_retries=2)
    with pytest.raises(smtpfast.InternalServerError):
        client.domains.list()
    assert len(rec.calls) == 3


def test_dropped_connection():
    drop = httpx.ConnectError("reset")
    client, rec = make([drop, drop], max_retries=1)
    with pytest.raises(smtpfast.APIConnectionError):
        client.domains.list()
    assert len(rec.calls) == 2


def test_timeout():
    client, _ = make([httpx.ReadTimeout("slow")], max_retries=0)
    with pytest.raises(smtpfast.APITimeoutError):
        client.domains.list()


def test_list_all_follows_cursor():
    client, rec = make([
        ok({"object": "list", "data": [{"id": "a"}, {"id": "b"}], "has_more": True}),
        ok({"object": "list", "data": [{"id": "c"}], "has_more": False}),
    ])
    assert [e["id"] for e in client.logs.list_all(limit=2)] == ["a", "b", "c"]
    assert "after" not in rec.calls[0].url.params
    assert rec.calls[1].url.params["after"] == "b"
    assert rec.calls[1].url.params["limit"] == "2"


def test_async_client():
    async def run():
        client, rec = make_async([
            ok({"data": [{"id": "t1"}], "has_more": True}),
            ok({"data": [], "has_more": False}),
            ok({"id": "em_1"}),
        ])
        threads = [t async for t in client.inboxes.threads.list_all("in_1")]
        sent = await client.emails.send({"from": "a@yourapp.dev", "to": "b@inbox.dev", "subject": "s", "text": "t"})
        await client.aclose()
        return threads, sent, rec

    threads, sent, rec = asyncio.run(run())
    assert threads == [{"id": "t1"}]
    assert sent == {"id": "em_1"}
    assert [c.url.path for c in rec.calls[:2]] == ["/api/v1/inboxes/in_1/threads"] * 2


def test_webhook_signature():
    secret = "whsec_test"
    payload = json.dumps({"type": "email.delivered", "data": {"id": "em_1"}})
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert webhooks.verify_signature(payload, sig, secret)
    assert webhooks.verify_signature(payload.encode(), sig, secret)
    assert not webhooks.verify_signature(payload + " ", sig, secret)
    assert not webhooks.verify_signature(payload, None, secret)
    assert webhooks.parse(payload, {"X-SMTPfast-Signature": sig}, secret)["type"] == "email.delivered"
    with pytest.raises(webhooks.WebhookVerificationError):
        webhooks.parse(payload, {"x-smtpfast-signature": "00"}, secret)


def test_custom_header_does_not_make_a_post_retryable():
    client, rec = make([ok({"error": "oops"}, 500, NO_WAIT)], headers={"Idempotency-Key": "x"})
    with pytest.raises(smtpfast.InternalServerError):
        client.broadcasts.send_test("bc_1", {"to": "me@inbox.dev"})
    assert len(rec.calls) == 1


def test_callers_header_key_is_kept_in_any_case():
    client, rec = make([ok({"id": "em_1"})])
    client.emails.send({"from": "a@yourapp.dev", "to": "b@inbox.dev"}, options={"headers": {"idempotency-key": "mine"}})
    assert rec.calls[0].headers.get_list("idempotency-key") == ["mine"]


def test_long_retry_after_stops_retries():
    client, rec = make([ok({"error": "down"}, 503, {"Retry-After": "120"})])
    with pytest.raises(smtpfast.InternalServerError):
        client.domains.list()
    assert len(rec.calls) == 1


def test_unreadable_retry_after_falls_back_to_backoff():
    client, rec = make([ok({"error": "down"}, 503, {"Retry-After": "NaN"})] * 2, max_retries=1)
    with pytest.raises(smtpfast.InternalServerError):
        client.domains.list()
    assert len(rec.calls) == 2


def test_redirect_is_an_error():
    client, _ = make([httpx.Response(302, headers={"Location": "https://smtpfa.st/login"})])
    with pytest.raises(smtpfast.APIError) as info:
        client.domains.list()
    assert info.value.status == 302


def test_list_all_drops_before_and_latest():
    client, rec = make([ok({"data": [{"id": "a"}], "has_more": True}), ok({"data": [], "has_more": False})])
    list(client.inboxes.threads.emails.list_all("in_1", "th_1", limit=1))
    assert [dict(c.url.params) for c in rec.calls] == [{"limit": "1"}, {"limit": "1", "after": "a"}]


def test_non_ascii_signature_is_rejected_not_raised():
    assert not webhooks.verify_signature("{}", "é", "secret")
    with pytest.raises(webhooks.WebhookVerificationError):
        webhooks.parse("{}", {"X-SMTPfast-Signature": "é"}, "secret")
