from __future__ import annotations

from typing import Any

import httpx


class SMTPfastError(Exception):
    """Every error the SDK raises is an SMTPfastError."""


class APIError(SMTPfastError):
    """The API answered with a status outside 2xx."""

    def __init__(self, status: int, body: Any, headers: httpx.Headers) -> None:
        self.status = status
        self.body = body
        self.headers = headers
        super().__init__(_message(status, body))

    @staticmethod
    def from_response(response: httpx.Response) -> APIError:
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        status = response.status_code
        kind = _BY_STATUS.get(status) or (InternalServerError if status >= 500 else APIError)
        return kind(status, body, response.headers)


class BadRequestError(APIError):
    pass


class AuthenticationError(APIError):
    pass


class PermissionDeniedError(APIError):
    pass


class NotFoundError(APIError):
    pass


class ConflictError(APIError):
    pass


class UnprocessableEntityError(APIError):
    pass


class RateLimitError(APIError):
    pass


class InternalServerError(APIError):
    pass


class APIConnectionError(SMTPfastError):
    """The request did not get an answer: DNS, TLS, a reset connection."""

    def __init__(self, message: str = "Could not connect to the SMTPfast API") -> None:
        super().__init__(message)


class APITimeoutError(APIConnectionError):
    """No answer arrived within the timeout."""

    def __init__(self, timeout: float) -> None:
        super().__init__(f"The SMTPfast API did not answer within {timeout:g} s")


_BY_STATUS: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def _message(status: int, body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return f"{status}: {body['error']}"
    if isinstance(body, str) and body.strip():
        return f"{status}: {body.strip()[:300]}"
    return f"{status}: the SMTPfast API answered with an error"
