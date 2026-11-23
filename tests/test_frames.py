"""Frame helpers. No network."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from ptdata import PtDataClient, PtDataRateLimit, constituents_frame, fundamentals_frame, fundamentals_panel
from ptdata.models import (
    Constituent,
    Derivation,
    DerivationInput,
    FundamentalsResponse,
    IndexConstituentsResponse,
    Lineage,
    MetricGuidance,
    MetricValue,
)
from tests.bodies import fundamentals
from tests.fakes import Response, Session


def _lineage() -> Lineage:
    return Lineage(
        source="edgar:xbrl:companyfacts",
        knowledge_from=datetime(2018, 2, 23, tzinfo=timezone.utc),
        methodology_version="0.1.0",
    )


def _revenue(value: float = 10.0) -> MetricValue:
    return MetricValue(
        value=value,
        unit="USD",
        fiscal_year=2017,
        fiscal_period="FY",
        source_accession="0000000000-18-000001",
        knowledge_from=datetime(2018, 2, 23, tzinfo=timezone.utc),
        methodology_version="0.1.0",
        provenance="xbrl",
    )


def test_unavailable_is_not_zero_and_q4_method_is_kept():
    derived = _revenue(94930000000.0)
    derived.fiscal_period = "Q4"
    derived.provenance = "derived"
    derived.derivation = Derivation(
        method="fy_minus_q1_q3",
        inputs=[
            DerivationInput(
                fiscal_period="FY",
                accession="0000320193-24-000123",
                knowledge_from=datetime(2024, 11, 1, tzinfo=timezone.utc),
                value=391035000000.0,
            )
        ],
    )
    response = FundamentalsResponse(
        ticker="AAPL",
        as_of_date=date(2026, 11, 1),
        metrics={"revenue": derived},
        lineage=_lineage(),
        unavailable={
            "eps_diluted": MetricGuidance(
                reason="not derived",
                docs_url="https://example.test/financials",
                code="not_reported",
                available_alternatives=["revenue"],
            ),
            "operating_income": MetricGuidance(
                reason="no single revenue line",
                docs_url="https://example.test/financials",
                code="financials_family",
                available_alternatives=["total_revenue", "net_interest_income"],
            ),
        },
    )
    frame = fundamentals_frame(response)
    missing = frame.loc[frame["metric"] == "operating_income"].iloc[0]
    assert pd.isna(missing["value"])
    assert missing["value"] != 0
    assert pd.isna(missing["fiscal_year"])
    assert missing["unavailable_code"] == "financials_family"
    assert missing["available_alternatives"] == ["total_revenue", "net_interest_income"]
    present = frame.loc[frame["metric"] == "revenue"].iloc[0]
    assert present["value"] == 94930000000.0
    assert present["derivation_method"] == "fy_minus_q1_q3"
    assert present["source_accession"] == "0000000000-18-000001"
    assert present["provenance"] == "derived"
    assert pd.isna(present["unavailable_code"])
    assert frame["value"].sum(min_count=1) == 94930000000.0


def test_panel_batches_metrics_and_stops_on_daily_limit(tmp_path):
    first = fundamentals(ticker="GE", as_of_date="2018-06-30")
    second = fundamentals(ticker="GE", as_of_date="2026-11-01")
    second["metrics"]["revenue"]["value"] = 99279000000.0
    session = Session([Response(200, first), Response(200, second)])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    frame = fundamentals_panel(client, ["GE"], ["2018-06-30", "2026-11-01"], ["revenue", "net_income"], fiscal_year=2017)
    assert len(session.calls) == 2
    assert session.calls[0]["params"].count(("metrics", "revenue")) == 1
    assert session.calls[0]["params"].count(("metrics", "net_income")) == 1
    assert set(frame["as_of_date"].dt.strftime("%Y-%m-%d")) == {"2018-06-30", "2026-11-01"}
    assert frame.loc[frame["metric"] == "revenue", "value"].tolist() == [122092000000.0, 99279000000.0]

    class _Daily:
        def fundamentals(self, *args, **kwargs):
            raise PtDataRateLimit("stop", retry_after=10, scope="daily", tier="free")

    with pytest.raises(PtDataRateLimit) as caught:
        fundamentals_panel(_Daily(), ["GE", "AAPL"], ["2018-06-30", "2026-11-01"], ["revenue"])
    assert caught.value.scope == "daily"


def test_constituents_frame_keeps_null_cik_and_extra_tickers():
    response = IndexConstituentsResponse(
        index="SP500",
        as_of_date=date(2020, 12, 21),
        tickers=["A", "AAL", "ORPHAN"],
        constituents=[
            Constituent(ticker="A", cik=1090872, name="AGILENT TECHNOLOGIES, INC."),
            Constituent(ticker="AAL", cik=None, name=None),
        ],
        lineage=_lineage(),
    )
    frame = constituents_frame(response)
    assert frame["ticker"].tolist() == ["A", "AAL", "ORPHAN"]
    assert frame.loc[0, "cik"] == 1090872
    assert pd.isna(frame.loc[1, "cik"])
    assert frame.loc[2, "name"] is None or pd.isna(frame.loc[2, "name"])
    assert frame.loc[0, "index"] == "SP500"
    assert frame.loc[0, "as_of_date"] == pd.Timestamp("2020-12-21")
