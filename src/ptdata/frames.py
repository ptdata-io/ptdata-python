"""Pandas helpers. Missing metrics stay missing; they are not filled with zero."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import pandas as pd

from ptdata.models import FundamentalsResponse, IndexConstituentsResponse

_FUNDAMENTAL_COLUMNS = [
    "ticker",
    "as_of_date",
    "metric",
    "value",
    "unit",
    "fiscal_year",
    "fiscal_period",
    "source_accession",
    "knowledge_from",
    "provenance",
    "extraction_confidence",
    "derivation_method",
    "unavailable_code",
    "unavailable_reason",
    "available_alternatives",
]


def fundamentals_frame(responses: FundamentalsResponse | Sequence[FundamentalsResponse]) -> pd.DataFrame:
    """One row per ticker, as-of date, and metric.

    Rows cover both returned metrics and ``unavailable`` entries. Unavailable rows
    have a null ``value`` (not zero) plus ``unavailable_code``, ``unavailable_reason``,
    and ``available_alternatives``.
    """
    if isinstance(responses, FundamentalsResponse):
        items: Sequence[FundamentalsResponse] = [responses]
    else:
        items = responses
    rows: list[dict[str, Any]] = []
    for response in items:
        for name, metric in response.metrics.items():
            rows.append(
                {
                    "ticker": response.ticker,
                    "as_of_date": response.as_of_date,
                    "metric": name,
                    "value": metric.value,
                    "unit": metric.unit,
                    "fiscal_year": metric.fiscal_year,
                    "fiscal_period": metric.fiscal_period,
                    "source_accession": metric.source_accession,
                    "knowledge_from": metric.knowledge_from,
                    "provenance": metric.provenance,
                    "extraction_confidence": metric.extraction_confidence,
                    "derivation_method": metric.derivation.method if metric.derivation else None,
                    "unavailable_code": None,
                    "unavailable_reason": None,
                    "available_alternatives": None,
                }
            )
        for name, guidance in response.unavailable.items():
            rows.append(
                {
                    "ticker": response.ticker,
                    "as_of_date": response.as_of_date,
                    "metric": name,
                    "value": None,
                    "unit": None,
                    "fiscal_year": None,
                    "fiscal_period": None,
                    "source_accession": None,
                    "knowledge_from": None,
                    "provenance": None,
                    "extraction_confidence": None,
                    "derivation_method": None,
                    "unavailable_code": guidance.code,
                    "unavailable_reason": guidance.reason,
                    "available_alternatives": list(guidance.available_alternatives),
                }
            )
    frame = pd.DataFrame(rows, columns=_FUNDAMENTAL_COLUMNS)
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    frame["knowledge_from"] = pd.to_datetime(frame["knowledge_from"], utc=True)
    frame["value"] = pd.to_numeric(frame["value"])
    frame["fiscal_year"] = pd.to_numeric(frame["fiscal_year"], errors="coerce").astype("Int64")
    return frame


def fundamentals_panel(
    client: Any,
    tickers: Sequence[str],
    as_of_dates: Sequence[str | date],
    metrics: Sequence[str],
    fiscal_year: int | None = None,
    fiscal_period: str = "FY",
) -> pd.DataFrame:
    """Call ``fundamentals`` once per ticker and as-of date, then stack the frames.

    Metrics for one call are sent together. The client sleeps on a per-minute
    429 and raises ``PtDataRateLimit`` with ``scope="daily"`` without retrying.
    This helper does not catch that error, so a daily limit stops the loop.
    """
    if isinstance(metrics, str) or not isinstance(metrics, Sequence) or len(metrics) == 0:
        raise ValueError("metrics is required.")
    responses: list[FundamentalsResponse] = []
    for ticker in tickers:
        for as_of_date in as_of_dates:
            responses.append(
                client.fundamentals(
                    ticker,
                    as_of_date,
                    list(metrics),
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                )
            )
    return fundamentals_frame(responses)


def constituents_frame(response: IndexConstituentsResponse) -> pd.DataFrame:
    """One row per constituent, with ``index`` and ``as_of_date`` repeated.

    Tickers present only in ``response.tickers`` are included with a null CIK and name.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in response.constituents:
        seen.add(item.ticker)
        rows.append(
            {
                "index": response.index,
                "as_of_date": response.as_of_date,
                "ticker": item.ticker,
                "cik": item.cik,
                "name": item.name,
            }
        )
    for ticker in response.tickers:
        if ticker in seen:
            continue
        rows.append(
            {
                "index": response.index,
                "as_of_date": response.as_of_date,
                "ticker": ticker,
                "cik": None,
                "name": None,
            }
        )
    frame = pd.DataFrame(rows, columns=["index", "as_of_date", "ticker", "cik", "name"])
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    frame["cik"] = pd.to_numeric(frame["cik"], errors="coerce").astype("Int64")
    return frame
