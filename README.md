# SMTPfast Python SDK

The official Python SDK for the [SMTPfast](https://smtpfa.st) API. It covers every endpoint in the API, sync and async, with types for every request and response. It needs Python 3.10+ and depends only on `httpx`.

```bash
pip install smtpfast
```

## Send an email

```python
from smtpfast import SMTPfast

client = SMTPfast()  # reads SMTPFAST_API_KEY

email = client.emails.send({
    "from": "Acme <hello@yourdomain.com>",
    "to": ["customer@example.org"],
    "subject": "Your receipt",
    "html": "<p>Thanks for your order.</p>",
    "category": "transactional",
})
print(email["id"])
```

Email is marketing unless you set `category` to `transactional`. Marketing email gets a one-click unsubscribe header and is not sent to people who unsubscribed. Set `transactional` on receipts, password resets and account alerts so a marketing opt-out does not block them.

Requests and responses are plain dicts, typed with `TypedDict`s from `smtpfast.types`, so your editor and type checker know every field. A new field or value from the API never breaks your code, because the SDK does not validate responses at runtime.

Every API operation is a method, named after its path: `client.domains.verify(id)`, `client.contacts.segments.add(contact_id, segment_id)`, `client.inboxes.threads.emails.reply(inbox_id, thread_id, email_id, params)`. Path parameters come first, then the request body, and query parameters are keyword arguments: `client.emails.list(limit=20, status="bounced")`.

## Async

```python
from smtpfast import AsyncSMTPfast

async with AsyncSMTPfast() as client:
    await client.emails.send({...})
```

## Options

```python
client = SMTPfast(
    api_key="sf_...",            # default: SMTPFAST_API_KEY
    base_url="https://smtpfa.st/api",
    max_retries=2,                # after 429 (with Retry-After), 408, 5xx and dropped connections
    timeout=60.0,                 # per attempt, in seconds
)

client.emails.send(params, idempotency_key="order-1234", options={"timeout": 10})
```

## Retries and idempotency

Reads, `PUT` and `DELETE` are retried after a 5xx answer or a dropped connection. A send, reply or forward is retried with the same `Idempotency-Key`, so the API returns the first answer instead of sending twice. When you do not give a key, the SDK makes one per call. Other `POST` and `PATCH` calls are retried only after a per-second rate limit, which the API rejects before doing any work.

## Errors

Every error is an `SMTPfastError`. An answer outside 2xx raises an `APIError` with `status`, `body` and `headers`, as one of `BadRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `ConflictError`, `UnprocessableEntityError`, `RateLimitError` or `InternalServerError`. No answer at all raises `APIConnectionError` or `APITimeoutError`.

```python
import smtpfast

try:
    client.emails.get("em_missing")
except smtpfast.NotFoundError as err:
    print(err.status, err.body)
```

## Pagination

Lists that page with a cursor also have a `..._all` method that fetches the next pages as you iterate:

```python
for email in client.emails.list_all(limit=100):
    print(email["id"], email["status"])
```

## Webhooks

```python
from smtpfast import webhooks

# The raw body, before any JSON parsing.
event = webhooks.parse(request.body, request.headers, secret=os.environ["SMTPFAST_WEBHOOK_SECRET"])
if event["type"] == "email.bounced":
    ...
```

`webhooks.verify_signature(payload, signature, secret)` returns a bool if you only need the check.

## How this SDK is made

The SDK is generated from the [OpenAPI document](https://smtpfa.st/api/v1/openapi.json), so it follows the API without hand edits. `scripts/generate.py` (standard library only) writes `src/smtpfast/types.py` and `src/smtpfast/_resources.py`, naming every method from the `x-sdk-group` and `x-sdk-method` the spec gives each operation; the SDKs for other languages use the same names. `_core.py`, `_errors.py` and `webhooks.py` are written by hand.

```bash
python scripts/pull_spec.py   # download the published spec into spec/openapi.json
python scripts/generate.py    # regenerate types.py and _resources.py
pytest -q                     # unit tests, including one call per operation
SMTPFAST_API_KEY=sf_... pytest tests/test_live.py   # read-only calls, checked against the spec
```

A daily workflow pulls the spec and opens a pull request when it changed.

## License

MIT
