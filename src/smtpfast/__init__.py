"""The official Python SDK for the SMTPfast API."""
from . import types, webhooks
from ._client import AsyncSMTPfast, SMTPfast
from ._core import RequestOptions
from ._errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SMTPfastError,
    UnprocessableEntityError,
)
from ._version import __version__

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AsyncSMTPfast",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestOptions",
    "SMTPfast",
    "SMTPfastError",
    "UnprocessableEntityError",
    "__version__",
    "types",
    "webhooks",
]
