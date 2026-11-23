"""Errors raised by the PtData client."""

from __future__ import annotations

from typing import Any


class PtDataError(Exception):
    """Base error for the PtData client.

    Attributes:
        status_code: HTTP status when the failure came from a response.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PtDataNotFound(PtDataError):
    """HTTP 404. ``detail`` is the API's detail text."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=404)
        self.detail = detail


class PtDataAuthError(PtDataError):
    """HTTP 401. The bearer token was rejected."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=401)


class PtDataValidationError(PtDataError):
    """HTTP 422. ``detail`` is the parsed validation payload when one was sent."""

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message, status_code=422)
        self.detail = detail


class PtDataRateLimit(PtDataError):
    """HTTP 429.

    ``scope`` is ``rate`` (per-minute) or ``daily``. A daily limit is not retried.
    ``retry_after`` is seconds from the ``Retry-After`` header when the server sent one.
    ``tier`` is the server's tier string (``free``, ``pro``, or ``scale``) when present.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        scope: str = "rate",
        tier: str | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after
        self.scope = scope
        self.tier = tier
