"""Check that a webhook request came from SMTPfast.

The X-SMTPfast-Signature header is the hex HMAC-SHA256 of the raw request
body, keyed with the webhook's signing secret. Pass the body exactly as
received, before any JSON parsing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

from ._errors import SMTPfastError

_HEX_SHA256 = re.compile(r"[0-9a-f]{64}")


class WebhookVerificationError(SMTPfastError):
    """The signature is missing or does not match the body."""


def verify_signature(payload: str | bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    signature = signature.strip().lower()
    if not _HEX_SHA256.fullmatch(signature):
        return False
    body = payload.encode() if isinstance(payload, str) else payload
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse(payload: str | bytes, headers: Mapping[str, str], secret: str) -> dict[str, Any]:
    """Verify the signature, then return the parsed event. Raises WebhookVerificationError."""
    signature = next((v for k, v in headers.items() if k.lower() == "x-smtpfast-signature"), None)
    if not verify_signature(payload, signature, secret):
        raise WebhookVerificationError("Webhook signature does not match")
    event: dict[str, Any] = json.loads(payload)
    return event
