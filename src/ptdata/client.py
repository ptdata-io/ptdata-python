"""HTTP client for the PtData API.

GET requests only. The disk cache is off unless ``cache_dir`` is set. The cache
key is the path plus the sorted query string, never the Authorization header.
The API key is removed from exception text when a response echoes it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import warnings
from collections.abc import Sequence
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

from ptdata._version import __version__
from ptdata.exceptions import (
    PtDataAuthError,
    PtDataError,
    PtDataNotFound,
    PtDataRateLimit,
    PtDataValidationError,
)
from ptdata.models import (
    EarningsEventResponse,
    FilingMetadataResponse,
    FundamentalsResponse,
    IndexConstituentsResponse,
    parse_earnings_event,
    parse_filings,
    parse_fundamentals,
    parse_index_constituents,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.ptdata.io"
USER_AGENT = f"ptdata-python/{__version__}"
# A per-minute pause is short. A larger Retry-After is not slept: a daily limit
# mis-labelled as rate must not block the process for hours.
MAX_RATE_SLEEP_SECONDS = 180


def _redact(text: str, secret: str | None) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def _redact_obj(value: Any, secret: str | None) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[redacted]")
    if isinstance(value, list):
        return [_redact_obj(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: _redact_obj(item, secret) for key, item in value.items()}
    return value


def _stringify(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _normalize_params(params: dict[str, Any] | list[tuple[str, Any]] | None) -> list[tuple[str, str]]:
    """Sort query parameters. A list value becomes repeated keys (``metrics``)."""
    if not params:
        return []
    items: list[tuple[str, str]] = []
    pairs = params.items() if isinstance(params, dict) else params
    for key, value in pairs:
        if value is None:
            continue
        if isinstance(value, list):
            items.extend((str(key), _stringify(item)) for item in value)
        else:
            items.append((str(key), _stringify(value)))
    return sorted(items)


def _parse_retry_after(value: str | None) -> float | None:
    """Return seconds. Accepts a delta or an HTTP-date."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        return max(0.0, moment.timestamp() - time.time())


def _format_detail(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = item.get("loc", [])
                loc_text = ".".join(str(part) for part in loc) if isinstance(loc, list) else str(loc)
                msg = str(item.get("msg", ""))
                parts.append(f"{loc_text}: {msg}" if loc_text else msg)
            else:
                parts.append(str(item))
        return "; ".join(parts)
    return str(detail)


class PtDataClient:
    """Client for ``https://api.ptdata.io``.

    Args:
        base_url: API origin. Trailing slash is stripped.
        api_key: Bearer token. ``None`` reads ``PTDATA_API_KEY``. An empty string,
            or an unset variable, selects the free tier and sends no Authorization header.
        cache_dir: Disk cache directory. ``None`` (the default) disables the disk cache.
            Identical calls on one instance are still reused in memory.
        session: ``requests.Session``, or any object with a ``request`` method. One session
            is created and reused when this is omitted.
        timeout: Per-request timeout in seconds.
        max_retries: Attempts for transport errors, HTTP 5xx, and ``scope=rate`` 429s.
        sleeper: Called with a number of seconds. Tests pass a recorder.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        *,
        session: Any | None = None,
        timeout: float = 30,
        max_retries: int = 4,
        sleeper: Any | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("PTDATA_API_KEY") or None
        elif api_key == "":
            api_key = None
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleeper = sleeper or time.sleep
        self._session = session or requests.Session()
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.calls_made = 0
        self._memory: dict[str, dict[str, Any]] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def fundamentals(
        self,
        ticker: str,
        as_of_date: str | date,
        metrics: Sequence[str],
        fiscal_year: int | None = None,
        fiscal_period: str | None = "FY",
    ) -> FundamentalsResponse:
        """Return point-in-time fundamentals for one ticker.

        ``metrics`` is required. Omitting it makes the API return an empty ``metrics``
        object, so this method raises ``ValueError`` and does not send the request.

        Without ``fiscal_year``, the API returns the latest ``fiscal_period`` known on
        ``as_of_date`` (default ``FY``), not the latest quarter.

        Read ``unavailable``. An absent metric is not zero. ``code="financials_family"``
        means the filer has no single revenue line; use ``available_alternatives`` and
        do not invent a total. Values are the raw API numbers.
        """
        if metrics is None or (isinstance(metrics, Sequence) and not isinstance(metrics, str) and len(metrics) == 0):
            raise ValueError(
                "metrics is required. Omitting metrics makes /v1/fundamentals return an empty metrics object."
            )
        if isinstance(metrics, str) or not isinstance(metrics, Sequence):
            raise TypeError("metrics must be a sequence of metric names, not a string")
        params: dict[str, Any] = {
            "ticker": ticker,
            "as_of_date": as_of_date,
            "metrics": list(metrics),
        }
        if fiscal_year is not None:
            params["fiscal_year"] = fiscal_year
        if fiscal_period is not None:
            params["fiscal_period"] = fiscal_period
        return parse_fundamentals(self._get("/v1/fundamentals", params))

    def index_constituents(self, index: str, as_of_date: str | date) -> IndexConstituentsResponse:
        """Return index members as understood on ``as_of_date``.

        Documented ``index`` codes are ``SP500``, ``DJIA``, ``DJT``, ``DJU``, and ``NDX``.
        Membership is survivorship-free at the API. This method does not filter it.
        """
        return parse_index_constituents(
            self._get("/v1/index-constituents", {"index": index, "as_of_date": as_of_date})
        )

    def filings(
        self,
        ticker: str,
        as_of_date: str | date,
        form_type: str | None = None,
    ) -> FilingMetadataResponse:
        """Return filings known on ``as_of_date``, newest first.

        ``form_type`` is optional and matches the API (exact strings such as ``10-K``,
        ``10-Q``, ``10-Q/A``, ``8-K``). Without it the list includes every form type
        and can be very large. Pass a form type for research use. This method warns
        when ``form_type`` is omitted.
        """
        if form_type is None:
            warnings.warn(
                "filings() without form_type can return a very large list; pass form_type for research use.",
                UserWarning,
                stacklevel=2,
            )
        return parse_filings(
            self._get(
                "/v1/filings",
                {"ticker": ticker, "as_of_date": as_of_date, "form_type": form_type},
            )
        )

    def earnings_event(self, ticker: str, fiscal_year: int, fiscal_period: str) -> EarningsEventResponse:
        """Return one earnings 8-K event. There is no ``as_of_date``.

        ``fiscal_period`` is ``FY`` or ``Q1``–``Q3``. A fourth-quarter release is stored
        as ``FY``. Use ``sec_acceptance_ts`` (SEC acceptance time) and ``as_reported``
        revenue and ``eps_gaap``.
        """
        return parse_earnings_event(
            self._get(
                "/v1/earnings-event",
                {"ticker": ticker, "fiscal_year": fiscal_year, "fiscal_period": fiscal_period},
            )
        )

    def _get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> dict[str, Any]:
        normalized = _normalize_params(params)
        key = self._cache_key(path, normalized)
        cached = self._memory.get(key)
        if cached is None and self.cache_dir is not None:
            cached = self._read_disk(key)
        if cached is not None:
            self._memory[key] = cached
            return cached
        body = self._fetch(path, normalized)
        self._memory[key] = body
        if self.cache_dir is not None:
            self._write_disk(key, body)
        return body

    def _cache_key(self, path: str, params: list[tuple[str, str]]) -> str:
        payload = json.dumps({"path": path, "params": params}, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        if self.cache_dir is None:
            raise PtDataError("Disk cache is disabled.")
        return self.cache_dir / key[:2] / f"{key}.json"

    def _read_disk(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        if not path.is_file():
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                body = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable PtData cache file (%s).", type(exc).__name__)
            return None
        if not isinstance(body, dict):
            return None
        return body

    def _write_disk(self, key: str, body: dict[str, Any]) -> None:
        path = self._cache_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(body, handle, separators=(",", ":"))
            temporary.replace(path)
        except OSError as exc:
            logger.warning("Could not write the PtData cache (%s).", type(exc).__name__)

    def _fetch(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_status: int | None = None
        for attempt in range(self.max_retries):
            self.calls_made += 1
            try:
                response = self._session.request(
                    "GET",
                    url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "PtData request failed (%s), attempt %d of %d.",
                    type(exc).__name__,
                    attempt + 1,
                    self.max_retries,
                )
                if attempt + 1 == self.max_retries:
                    raise PtDataError(_redact(str(exc), self._api_key)) from None
                self._sleeper(self._backoff(attempt))
                continue

            status = response.status_code
            last_status = status
            if status == 200:
                return self._json_object(response)
            if status == 401:
                detail = self._detail(response)
                message = "PtData rejected the credentials (HTTP 401)."
                if detail:
                    message = f"{message} {detail}"
                raise PtDataAuthError(message)
            if status == 404:
                raise PtDataNotFound(self._detail(response) or "not found")
            if status == 422:
                detail_raw = self._json_object(response, required=False).get("detail")
                message = _redact(_format_detail(detail_raw), self._api_key) or "PtData rejected the query (HTTP 422)."
                raise PtDataValidationError(message, detail=_redact_obj(detail_raw, self._api_key))
            if status == 429:
                self._handle_rate_limit(response, attempt)
                continue
            if 500 <= status < 600:
                logger.warning("PtData returned HTTP %s, attempt %d of %d.", status, attempt + 1, self.max_retries)
                if attempt + 1 == self.max_retries:
                    break
                self._sleeper(self._backoff(attempt))
                continue
            raise PtDataError(self._detail(response) or f"HTTP {status}", status_code=status)

        raise PtDataError(
            f"PtData request failed after {self.max_retries} attempts (last HTTP {last_status}).",
            status_code=last_status,
        )

    def _handle_rate_limit(self, response: Any, attempt: int) -> None:
        body = self._json_object(response, required=False) or {}
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        scope_raw = body.get("scope")
        scope = str(scope_raw).strip().lower() if scope_raw else ""
        tier_raw = body.get("tier")
        tier = str(tier_raw) if tier_raw is not None else None
        if scope == "daily":
            # Do not sleep and do not retry. The free-tier counter resets at UTC midnight.
            wait = f"{retry_after:g} seconds" if retry_after is not None else "the Retry-After time"
            raise PtDataRateLimit(
                "PtData daily request limit is exhausted "
                f"(scope=daily, tier={tier or 'unknown'}). "
                f"Retry-After asks for {wait}. "
                "The free tier allows 200 requests per IP per UTC day. Stop.",
                retry_after=retry_after,
                scope="daily",
                tier=tier,
            )
        effective = scope or "rate"
        if retry_after is None:
            retry_after = self._backoff(attempt)
        if retry_after > MAX_RATE_SLEEP_SECONDS:
            raise PtDataRateLimit(
                f"PtData rate limit asked to wait {retry_after:g} seconds, "
                f"which is above the {MAX_RATE_SLEEP_SECONDS}s client cap.",
                retry_after=retry_after,
                scope=effective,
                tier=tier,
            )
        logger.warning("PtData rate limit (scope=%s). Waiting %s seconds.", effective, retry_after)
        self._sleeper(retry_after)
        if attempt + 1 == self.max_retries:
            raise PtDataRateLimit(
                "PtData rate limit persisted after retries.",
                retry_after=retry_after,
                scope=effective,
                tier=tier,
            )

    def _json_object(self, response: Any, required: bool = True) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            if not required:
                return {}
            raise PtDataError(
                "PtData returned a response that is not JSON.",
                status_code=response.status_code,
            ) from None
        if not isinstance(body, dict):
            if not required:
                return {}
            raise PtDataError(
                "PtData returned a JSON value that is not an object.",
                status_code=response.status_code,
            )
        return body

    def _detail(self, response: Any) -> str:
        body = self._json_object(response, required=False) or {}
        return _redact(_format_detail(body.get("detail", "")), self._api_key)

    @staticmethod
    def _backoff(attempt: int) -> float:
        return float(2**attempt)
