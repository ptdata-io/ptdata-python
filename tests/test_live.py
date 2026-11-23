"""One live check. Skipped unless PTDATA_LIVE=1, so a plain pytest run stays offline."""

from __future__ import annotations

import os

import pytest

from ptdata import PtDataClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("PTDATA_LIVE") != "1", reason="set PTDATA_LIVE=1 to call the live API")
def test_ge_fy2017_revenue_as_of_2018_02_28():
    client = PtDataClient(api_key="", cache_dir=None)
    fund = client.fundamentals(
        "GE",
        "2018-02-28",
        ["revenue"],
        fiscal_year=2017,
        fiscal_period="FY",
    )
    revenue = fund.metrics["revenue"]
    assert revenue.value == 122092000000.0
    assert revenue.source_accession == "0000040545-18-000014"
