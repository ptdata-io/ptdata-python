"""Small API bodies shaped like the live OpenAPI schemas."""

from __future__ import annotations

from typing import Any

LINEAGE = {
    "source": "edgar:xbrl:companyfacts",
    "knowledge_from": "2018-02-23T00:00:00Z",
    "methodology_version": "0.1.0",
}


def metric(
    value: float = 122092000000.0,
    *,
    fiscal_period: str = "FY",
    accession: str = "0000040545-18-000014",
    provenance: str = "xbrl",
    derivation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "value": value,
        "unit": "USD",
        "fiscal_year": 2017,
        "fiscal_period": fiscal_period,
        "source_accession": accession,
        "knowledge_from": "2018-02-23T00:00:00Z",
        "methodology_version": "0.1.0",
        "provenance": provenance,
        "extraction_confidence": None,
        "derivation": derivation,
    }
    return body


def fundamentals(
    *,
    metrics: dict[str, Any] | None = None,
    unavailable: dict[str, Any] | None = None,
    ticker: str = "GE",
    as_of_date: str = "2018-02-28",
) -> dict[str, Any]:
    if metrics is None:
        metrics = {"revenue": metric()}
    return {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "metrics": metrics,
        "unavailable": {} if unavailable is None else unavailable,
        "lineage": dict(LINEAGE),
    }


Q4_DERIVATION = {
    "method": "fy_minus_q1_q3",
    "inputs": [
        {
            "fiscal_period": "FY",
            "accession": "0000320193-24-000123",
            "knowledge_from": "2024-11-01T00:00:00Z",
            "value": 391035000000.0,
        },
        {
            "fiscal_period": "Q1",
            "accession": "0000320193-24-000006",
            "knowledge_from": "2024-02-02T00:00:00Z",
            "value": 119575000000.0,
        },
    ],
}


def filings_body() -> dict[str, Any]:
    return {
        "ticker": "AAPL",
        "as_of_date": "2024-11-02",
        "filings": [
            {
                "accession_number": "0000320193-24-000123",
                "form_type": "10-K",
                "filing_date": "2024-11-01",
                "acceptance_datetime": "2024-11-01T10:01:36Z",
                "period_of_report": "2024-09-28",
                "amends_accession": None,
            }
        ],
        "lineage": dict(LINEAGE),
    }


def constituents_body() -> dict[str, Any]:
    return {
        "index": "SP500",
        "as_of_date": "2020-12-21",
        "tickers": ["A", "AAL", "AAP"],
        "constituents": [
            {"ticker": "A", "cik": 1090872, "name": "AGILENT TECHNOLOGIES, INC."},
            {"ticker": "AAL", "cik": 6201, "name": "American Airlines Group Inc."},
            {"ticker": "AAP", "cik": None, "name": None},
        ],
        "lineage": dict(LINEAGE),
    }


def earnings_body() -> dict[str, Any]:
    return {
        "ticker": "AAPL",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "sec_acceptance_ts": "2023-11-02T20:30:32Z",
        "dissemination_ts": None,
        "dissemination_confidence": "unknown",
        "filing_accession": "0000320193-23-000104",
        "filing": {
            "accession_number": "0000320193-23-000104",
            "acceptance_datetime": "2023-11-02T20:30:32Z",
        },
        "as_reported": {"revenue": 383285000000.0, "eps_gaap": 6.13, "eps_non_gaap": None},
        "implied_expectation": None,
        "lineage": {
            "source": "edgar:8-k:0000320193-23-000104",
            "knowledge_from": "2023-11-02T20:30:32Z",
            "methodology_version": "0.1.0",
        },
    }
