"""Dataclasses for the PtData HTTP API.

Shapes follow ``https://api.ptdata.io/openapi.json``. Unknown JSON fields are ignored.
``MetricValue.value`` is the number the API returned. It is not scaled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ptdata.exceptions import PtDataError


def _require(body: dict[str, Any], key: str) -> Any:
    if key not in body:
        raise PtDataError(f"PtData response is missing {key}.")
    return body[key]


def _as_date(value: Any, field_name: str) -> date:
    if not isinstance(value, str):
        raise PtDataError(f"Could not parse {field_name} as a date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PtDataError(f"Could not parse {field_name} as a date.") from exc


def _as_date_opt(value: Any, field_name: str) -> date | None:
    if value is None:
        return None
    return _as_date(value, field_name)


def _as_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise PtDataError(f"Could not parse {field_name} as a datetime.")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise PtDataError(f"Could not parse {field_name} as a datetime.") from exc


def _as_datetime_opt(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _as_datetime(value, field_name)


def _as_number(value: Any, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PtDataError(f"Field {field_name} is not a number.")
    return value


def _as_number_opt(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    return _as_number(value, field_name)


def _as_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PtDataError(f"Field {field_name} is not an object.")
    return value


@dataclass
class DerivationInput:
    """One filed amount that went into a derived quarter."""

    fiscal_period: str
    accession: str
    knowledge_from: datetime
    value: int | float


@dataclass
class Derivation:
    """How a quarter was produced. Present only when the service derived or copied it.

    ``method`` is one of ``fy_minus_q1_q3``, ``ytd_minus_prior_ytd``, ``direct_q4_fact``,
    or ``fy_instant``. This client does not compute quarters itself.
    """

    method: str
    inputs: list[DerivationInput]


@dataclass
class MetricValue:
    """One fundamental.

    ``value`` is the raw API number (USD amounts are not converted from millions).
    ``knowledge_from`` is the API timestamp, often the filing date at 00:00Z, not the
    SEC acceptance time. A missing metric is not a ``MetricValue``; see
    ``FundamentalsResponse.unavailable``.
    """

    value: int | float
    unit: str
    fiscal_year: int
    fiscal_period: str
    source_accession: str
    knowledge_from: datetime
    methodology_version: str
    provenance: str = "xbrl"
    extraction_confidence: str | None = None
    derivation: Derivation | None = None


@dataclass
class MetricGuidance:
    """Why a requested metric is absent.

    ``code`` is ``not_reported`` or ``financials_family``. ``available_alternatives``
    may be empty. Do not treat the absence as zero and do not invent a total.
    """

    reason: str
    docs_url: str
    code: str = "not_reported"
    available_alternatives: list[str] = field(default_factory=list)
    detail: str | None = None


@dataclass
class Lineage:
    """Provenance attached to a response."""

    source: str
    knowledge_from: datetime
    methodology_version: str
    ingestion_run_id: int | None = None
    amends_chain: list[str] | None = None
    derived_inputs: list[str] | None = None


@dataclass
class FundamentalsResponse:
    """``GET /v1/fundamentals``."""

    ticker: str
    as_of_date: date
    metrics: dict[str, MetricValue]
    lineage: Lineage
    unavailable: dict[str, MetricGuidance] = field(default_factory=dict)


@dataclass
class Constituent:
    """One index member as understood on the queried date."""

    ticker: str
    cik: int | None = None
    name: str | None = None


@dataclass
class IndexConstituentsResponse:
    """``GET /v1/index-constituents``."""

    index: str
    as_of_date: date
    tickers: list[str]
    constituents: list[Constituent]
    lineage: Lineage


@dataclass
class FilingMeta:
    """One filing row. ``acceptance_datetime`` is the SEC acceptance time."""

    accession_number: str
    form_type: str
    filing_date: date
    acceptance_datetime: datetime
    period_of_report: date | None = None
    amends_accession: str | None = None


@dataclass
class FilingMetadataResponse:
    """``GET /v1/filings``. ``filings`` is newest first, as the API sends it."""

    ticker: str
    as_of_date: date
    filings: list[FilingMeta]
    lineage: Lineage


@dataclass
class FilingRef:
    """Filing pointer on an earnings event."""

    accession_number: str
    acceptance_datetime: datetime


@dataclass
class AsReported:
    """Figures stated in the earnings filing. Absent fields are null, not zero."""

    revenue: int | float | None = None
    eps_gaap: int | float | None = None
    eps_non_gaap: int | float | None = None


@dataclass
class ImpliedExpectationBlock:
    """Optional earnings block from the OpenAPI schema. Null when the API sends null."""

    as_of_date: date
    expected_move_pct: int | float
    method: str
    atm_iv: int | float | None = None


@dataclass
class EarningsEventResponse:
    """``GET /v1/earnings-event``. This route has no ``as_of_date``.

    ``fiscal_period`` is ``FY`` or ``Q1``–``Q3``. A fourth-quarter release is stored as ``FY``.
    Use ``sec_acceptance_ts`` and ``as_reported`` revenue and ``eps_gaap``.
    """

    ticker: str
    fiscal_year: int
    fiscal_period: str
    dissemination_confidence: str
    filing_accession: str
    filing: FilingRef
    lineage: Lineage
    sec_acceptance_ts: datetime | None = None
    dissemination_ts: datetime | None = None
    as_reported: AsReported | None = None
    implied_expectation: ImpliedExpectationBlock | None = None


def _parse_derivation(body: Any) -> Derivation | None:
    if body is None:
        return None
    raw = _as_object(body, "derivation")
    inputs_raw = raw.get("inputs", [])
    if not isinstance(inputs_raw, list):
        raise PtDataError("Field derivation.inputs is not a list.")
    inputs: list[DerivationInput] = []
    for item in inputs_raw:
        row = _as_object(item, "derivation.inputs")
        inputs.append(
            DerivationInput(
                fiscal_period=str(_require(row, "fiscal_period")),
                accession=str(_require(row, "accession")),
                knowledge_from=_as_datetime(row.get("knowledge_from"), "derivation.knowledge_from"),
                value=_as_number(row.get("value"), "derivation.value"),
            )
        )
    return Derivation(method=str(_require(raw, "method")), inputs=inputs)


def _parse_metric(body: Any) -> MetricValue:
    raw = _as_object(body, "metric")
    provenance = raw.get("provenance", "xbrl")
    if provenance is None:
        provenance = "xbrl"
    return MetricValue(
        value=_as_number(raw.get("value"), "value"),
        unit=str(_require(raw, "unit")),
        fiscal_year=int(_require(raw, "fiscal_year")),
        fiscal_period=str(_require(raw, "fiscal_period")),
        source_accession=str(_require(raw, "source_accession")),
        knowledge_from=_as_datetime(raw.get("knowledge_from"), "knowledge_from"),
        methodology_version=str(_require(raw, "methodology_version")),
        provenance=str(provenance),
        extraction_confidence=raw.get("extraction_confidence"),
        derivation=_parse_derivation(raw.get("derivation")),
    )


def _parse_guidance(body: Any) -> MetricGuidance:
    raw = _as_object(body, "unavailable")
    alternatives = raw.get("available_alternatives", [])
    if not isinstance(alternatives, list):
        raise PtDataError("Field available_alternatives is not a list.")
    return MetricGuidance(
        reason=str(_require(raw, "reason")),
        docs_url=str(_require(raw, "docs_url")),
        code=str(raw.get("code") or "not_reported"),
        available_alternatives=[str(item) for item in alternatives],
        detail=raw.get("detail"),
    )


def _parse_lineage(body: Any) -> Lineage:
    raw = _as_object(body, "lineage")
    run_id = raw.get("ingestion_run_id")
    if run_id is not None and (isinstance(run_id, bool) or not isinstance(run_id, int)):
        raise PtDataError("Field ingestion_run_id is not an integer.")
    amends = raw.get("amends_chain")
    derived = raw.get("derived_inputs")
    if amends is not None and not isinstance(amends, list):
        raise PtDataError("Field amends_chain is not a list.")
    if derived is not None and not isinstance(derived, list):
        raise PtDataError("Field derived_inputs is not a list.")
    return Lineage(
        source=str(_require(raw, "source")),
        knowledge_from=_as_datetime(raw.get("knowledge_from"), "lineage.knowledge_from"),
        methodology_version=str(_require(raw, "methodology_version")),
        ingestion_run_id=run_id,
        amends_chain=[str(item) for item in amends] if amends is not None else None,
        derived_inputs=[str(item) for item in derived] if derived is not None else None,
    )


def _parse_map(raw: Any, field_name: str, parser: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    body = _as_object(raw, field_name)
    return {str(key): parser(value) for key, value in body.items()}


def parse_fundamentals(body: dict[str, Any]) -> FundamentalsResponse:
    """Build a ``FundamentalsResponse``. ``unavailable`` defaults to an empty map."""
    metrics_raw = body.get("metrics", {})
    return FundamentalsResponse(
        ticker=str(_require(body, "ticker")),
        as_of_date=_as_date(body.get("as_of_date"), "as_of_date"),
        metrics=_parse_map(metrics_raw, "metrics", _parse_metric),
        unavailable=_parse_map(body.get("unavailable", {}), "unavailable", _parse_guidance),
        lineage=_parse_lineage(body.get("lineage")),
    )


def parse_index_constituents(body: dict[str, Any]) -> IndexConstituentsResponse:
    """Build an ``IndexConstituentsResponse``."""
    tickers = _require(body, "tickers")
    rows = _require(body, "constituents")
    if not isinstance(tickers, list) or not isinstance(rows, list):
        raise PtDataError("Index constituents response is malformed.")
    constituents: list[Constituent] = []
    for item in rows:
        raw = _as_object(item, "constituents")
        cik = raw.get("cik")
        if cik is not None and (isinstance(cik, bool) or not isinstance(cik, int)):
            raise PtDataError("Field cik is not an integer.")
        constituents.append(Constituent(ticker=str(_require(raw, "ticker")), cik=cik, name=raw.get("name")))
    return IndexConstituentsResponse(
        index=str(_require(body, "index")),
        as_of_date=_as_date(body.get("as_of_date"), "as_of_date"),
        tickers=[str(item) for item in tickers],
        constituents=constituents,
        lineage=_parse_lineage(body.get("lineage")),
    )


def parse_filings(body: dict[str, Any]) -> FilingMetadataResponse:
    """Build a ``FilingMetadataResponse``. Order is preserved."""
    rows = _require(body, "filings")
    if not isinstance(rows, list):
        raise PtDataError("Field filings is not a list.")
    filings: list[FilingMeta] = []
    for item in rows:
        raw = _as_object(item, "filings")
        filings.append(
            FilingMeta(
                accession_number=str(_require(raw, "accession_number")),
                form_type=str(_require(raw, "form_type")),
                filing_date=_as_date(raw.get("filing_date"), "filing_date"),
                acceptance_datetime=_as_datetime(raw.get("acceptance_datetime"), "acceptance_datetime"),
                period_of_report=_as_date_opt(raw.get("period_of_report"), "period_of_report"),
                amends_accession=raw.get("amends_accession"),
            )
        )
    return FilingMetadataResponse(
        ticker=str(_require(body, "ticker")),
        as_of_date=_as_date(body.get("as_of_date"), "as_of_date"),
        filings=filings,
        lineage=_parse_lineage(body.get("lineage")),
    )


def _parse_as_reported(body: Any) -> AsReported | None:
    if body is None:
        return None
    raw = _as_object(body, "as_reported")
    return AsReported(
        revenue=_as_number_opt(raw.get("revenue"), "as_reported.revenue"),
        eps_gaap=_as_number_opt(raw.get("eps_gaap"), "as_reported.eps_gaap"),
        eps_non_gaap=_as_number_opt(raw.get("eps_non_gaap"), "as_reported.eps_non_gaap"),
    )


def _parse_implied(body: Any) -> ImpliedExpectationBlock | None:
    if body is None:
        return None
    raw = _as_object(body, "implied_expectation")
    return ImpliedExpectationBlock(
        as_of_date=_as_date(raw.get("as_of_date"), "implied_expectation.as_of_date"),
        expected_move_pct=_as_number(raw.get("expected_move_pct"), "expected_move_pct"),
        method=str(_require(raw, "method")),
        atm_iv=_as_number_opt(raw.get("atm_iv"), "atm_iv"),
    )


def parse_earnings_event(body: dict[str, Any]) -> EarningsEventResponse:
    """Build an ``EarningsEventResponse``."""
    filing_raw = _as_object(_require(body, "filing"), "filing")
    filing = FilingRef(
        accession_number=str(_require(filing_raw, "accession_number")),
        acceptance_datetime=_as_datetime(filing_raw.get("acceptance_datetime"), "filing.acceptance_datetime"),
    )
    return EarningsEventResponse(
        ticker=str(_require(body, "ticker")),
        fiscal_year=int(_require(body, "fiscal_year")),
        fiscal_period=str(_require(body, "fiscal_period")),
        dissemination_confidence=str(_require(body, "dissemination_confidence")),
        filing_accession=str(_require(body, "filing_accession")),
        filing=filing,
        lineage=_parse_lineage(body.get("lineage")),
        sec_acceptance_ts=_as_datetime_opt(body.get("sec_acceptance_ts"), "sec_acceptance_ts"),
        dissemination_ts=_as_datetime_opt(body.get("dissemination_ts"), "dissemination_ts"),
        as_reported=_parse_as_reported(body.get("as_reported")),
        implied_expectation=_parse_implied(body.get("implied_expectation")),
    )
