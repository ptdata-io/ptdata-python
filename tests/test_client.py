"""Client tests. No network."""

from __future__ import annotations

import logging
from email.utils import formatdate
import time

import pytest
import requests

from ptdata import PtDataAuthError, PtDataNotFound, PtDataRateLimit, PtDataValidationError
from ptdata.client import USER_AGENT, PtDataClient, PtDataError
from ptdata.models import parse_earnings_event
from ptdata.exceptions import PtDataError as PtDataErrorFromPackage
from tests.bodies import Q4_DERIVATION, constituents_body, earnings_body, filings_body, fundamentals, metric
from tests.fakes import Response, Session


def test_user_agent_auth_and_redacted_cache(tmp_path, caplog):
    secret = "super-secret-token"
    session = Session([Response(200, fundamentals())])
    client = PtDataClient(api_key=secret, cache_dir=tmp_path, session=session)
    caplog.set_level(logging.DEBUG)
    fund = client.fundamentals("GE", "2018-02-28", ["revenue"], fiscal_year=2017)
    assert fund.metrics["revenue"].value == 122092000000.0
    assert session.calls[0]["headers"]["Authorization"] == f"Bearer {secret}"
    assert session.calls[0]["headers"]["User-Agent"] == USER_AGENT
    assert session.calls[0]["headers"]["User-Agent"] == "ptdata-python/0.1.1"
    assert secret not in caplog.text
    cached = list(tmp_path.rglob("*.json"))
    assert len(cached) == 1
    assert secret.encode() not in cached[0].read_bytes()
    assert client._session is session


def test_empty_key_and_missing_env_omit_authorization(tmp_path, monkeypatch):
    monkeypatch.delenv("PTDATA_API_KEY", raising=False)
    bare = Session([Response(200, fundamentals())])
    PtDataClient(api_key="", cache_dir=tmp_path, session=bare).fundamentals("GE", "2018-02-28", ["revenue"])
    assert "Authorization" not in bare.calls[0]["headers"]

    implied = Session([Response(200, fundamentals())])
    PtDataClient(cache_dir=tmp_path / "env-missing", session=implied).fundamentals("GE", "2018-02-28", ["revenue"])
    assert "Authorization" not in implied.calls[0]["headers"]


def test_omitted_key_reads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PTDATA_API_KEY", "from-env")
    session = Session([Response(200, fundamentals())])
    PtDataClient(cache_dir=tmp_path, session=session).fundamentals("GE", "2018-02-28", ["revenue"])
    assert session.calls[0]["headers"]["Authorization"] == "Bearer from-env"


def test_metrics_are_repeated_sorted_query_parameters(tmp_path):
    session = Session([Response(200, fundamentals())])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    client.fundamentals("AAPL", "2024-11-01", ["revenue", "net_income"], fiscal_year=2024, fiscal_period="FY")
    params = session.calls[0]["params"]
    assert params.count(("metrics", "revenue")) == 1
    assert params.count(("metrics", "net_income")) == 1
    assert ("fiscal_year", "2024") in params
    assert ("fiscal_period", "FY") in params
    assert ("ticker", "AAPL") in params
    assert params == sorted(params)
    assert session.calls[0]["url"] == "https://api.ptdata.io/v1/fundamentals"


def test_empty_metrics_do_not_call(tmp_path):
    session = Session([])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    with pytest.raises(ValueError, match="metrics is required"):
        client.fundamentals("GE", "2018-02-28", [])
    with pytest.raises(ValueError, match="metrics is required"):
        client.fundamentals("GE", "2018-02-28", None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.fundamentals("GE", "2018-02-28", "revenue")  # type: ignore[arg-type]
    assert session.calls == []


def test_disk_cache_off_by_default_still_reuses_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PTDATA_CACHE_DIR", raising=False)
    session = Session([Response(200, fundamentals()), Response(200, fundamentals())])
    client = PtDataClient(api_key="", session=session)
    assert client.cache_dir is None
    first = client.fundamentals("GE", "2018-02-28", ["revenue"], fiscal_year=2017)
    second = client.fundamentals("GE", "2018-02-28", ["revenue"], fiscal_year=2017)
    assert first.metrics["revenue"].value == second.metrics["revenue"].value
    assert len(session.calls) == 1
    assert client.calls_made == 1
    assert list(tmp_path.rglob("*.json")) == []


def test_disk_cache_hit_makes_no_further_http_and_ignores_key(tmp_path):
    session = Session([Response(200, fundamentals())])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    first = client.fundamentals("GE", "2018-02-28", ["revenue", "net_income"], fiscal_year=2017)
    second = client.fundamentals("GE", "2018-02-28", ["revenue", "net_income"], fiscal_year=2017)
    assert first.metrics["revenue"].source_accession == second.metrics["revenue"].source_accession
    assert len(session.calls) == 1
    assert client.calls_made == 1

    other = Session([])
    revived = PtDataClient(api_key="different-key", cache_dir=tmp_path, session=other)
    again = revived.fundamentals("GE", "2018-02-28", ["net_income", "revenue"], fiscal_year=2017)
    assert again.metrics["revenue"].value == first.metrics["revenue"].value
    assert other.calls == []
    assert revived.calls_made == 0


def test_unknown_ticker_raises_not_found(tmp_path):
    session = Session([Response(404, {"detail": "no company linked to ticker 'ZZZZ'"})])
    client = PtDataClient(cache_dir=tmp_path, session=session, api_key="")
    with pytest.raises(PtDataNotFound, match="no company linked") as caught:
        client.filings("ZZZZ", "2024-01-01", form_type="10-K")
    assert caught.value.detail == "no company linked to ticker 'ZZZZ'"
    assert caught.value.status_code == 404
    assert len(session.calls) == 1


def test_401_does_not_retry_and_redacts_the_key(tmp_path, caplog):
    secret = "super-secret-token"
    session = Session(
        [
            Response(401, {"detail": f"rejected {secret}"}),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key=secret, cache_dir=tmp_path, session=session)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(PtDataAuthError, match="HTTP 401") as caught:
        client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert secret not in str(caught.value)
    assert "[redacted]" in str(caught.value)
    assert secret not in caplog.text
    assert len(session.calls) == 1
    assert client.calls_made == 1


def test_422_validation(tmp_path):
    detail = [{"loc": ["query", "as_of_date"], "msg": "Input should be a valid date", "type": "date_type"}]
    session = Session([Response(422, {"detail": detail}), Response(200, fundamentals())])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    with pytest.raises(PtDataValidationError, match="as_of_date") as caught:
        client.fundamentals("GE", "not-a-date", ["revenue"])
    assert caught.value.status_code == 422
    assert caught.value.detail == detail
    assert len(session.calls) == 1


def test_rate_limit_honors_retry_after_seconds(tmp_path):
    sleeps: list[float] = []
    session = Session(
        [
            Response(429, {"detail": "rate limit exceeded", "scope": "rate", "tier": "free"}, {"Retry-After": "3"}),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    fund = client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert fund.metrics["revenue"].value == 122092000000.0
    assert sleeps == [3.0]
    assert client.calls_made == 2


def test_rate_limit_honors_http_date(tmp_path):
    sleeps: list[float] = []
    header = formatdate(time.time() + 30, usegmt=True)
    session = Session(
        [
            Response(429, {"scope": "rate", "tier": "pro"}, {"Retry-After": header}),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert sleeps[0] == pytest.approx(30, abs=2)


def test_rate_limit_above_cap_does_not_sleep(tmp_path):
    sleeps: list[float] = []
    header = formatdate(time.time() + 1000, usegmt=True)
    session = Session([Response(429, {"scope": "rate", "tier": "free"}, {"Retry-After": header})])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    with pytest.raises(PtDataRateLimit, match="client cap") as caught:
        client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert sleeps == []
    assert caught.value.scope == "rate"
    assert caught.value.tier == "free"
    assert caught.value.retry_after is not None
    assert caught.value.retry_after > 180
    assert len(session.calls) == 1


def test_rate_limit_persists(tmp_path):
    sleeps: list[float] = []
    session = Session(
        [
            Response(429, {"scope": "rate", "tier": "scale"}, {"Retry-After": "1"}),
            Response(429, {"scope": "rate", "tier": "scale"}, {"Retry-After": "1"}),
        ]
    )
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append, max_retries=2)
    with pytest.raises(PtDataRateLimit, match="persisted") as caught:
        client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert sleeps == [1.0, 1.0]
    assert caught.value.scope == "rate"
    assert caught.value.tier == "scale"
    assert len(session.calls) == 2


def test_daily_scope_does_not_retry(tmp_path):
    sleeps: list[float] = []
    session = Session(
        [
            Response(
                429,
                {"detail": "daily request limit exceeded", "scope": "daily", "tier": "free"},
                {"Retry-After": "40000"},
            ),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    with pytest.raises(PtDataRateLimit, match="Stop") as caught:
        client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert caught.value.scope == "daily"
    assert caught.value.tier == "free"
    assert caught.value.retry_after == 40000
    assert sleeps == []
    assert len(session.calls) == 1
    assert client.calls_made == 1


def test_5xx_retries_then_succeeds(tmp_path):
    sleeps: list[float] = []
    session = Session(
        [
            Response(503, {"detail": "unavailable"}),
            Response(502, {"detail": "bad gateway"}),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    fund = client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert fund.ticker == "GE"
    assert sleeps == [1.0, 2.0]
    assert client.calls_made == 3


def test_5xx_exhausted(tmp_path):
    session = Session([Response(500, {"detail": "down"})])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session, sleeper=lambda _seconds: None, max_retries=1)
    with pytest.raises(PtDataError, match="last HTTP 500") as caught:
        client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert caught.value.status_code == 500
    assert type(caught.value) is PtDataError
    assert PtDataError is PtDataErrorFromPackage


def test_transport_error_retries_and_redacts(tmp_path):
    secret = "super-secret-token"
    sleeps: list[float] = []
    session = Session(
        [
            requests.ConnectionError(f"boom {secret}"),
            Response(200, fundamentals()),
        ]
    )
    client = PtDataClient(api_key=secret, cache_dir=tmp_path, session=session, sleeper=sleeps.append)
    fund = client.fundamentals("GE", "2018-02-28", ["revenue"])
    assert fund.metrics["revenue"].unit == "USD"
    assert sleeps == [1.0]

    failing = Session([requests.ConnectionError(f"boom {secret}")])
    limited = PtDataClient(api_key=secret, cache_dir=tmp_path / "fail", session=failing, max_retries=1)
    with pytest.raises(PtDataError, match="redacted") as caught:
        limited.fundamentals("GE", "2018-02-28", ["revenue"])
    assert secret not in str(caught.value)


def test_filings_form_type_warning_and_earnings_and_index(tmp_path):
    session = Session([Response(200, filings_body()), Response(200, filings_body())])
    client = PtDataClient(api_key="", cache_dir=tmp_path, session=session)
    with pytest.warns(UserWarning, match="form_type"):
        warned = client.filings("AAPL", "2024-11-02")
    assert warned.filings[0].form_type == "10-K"
    assert ("form_type", "10-K") not in session.calls[0]["params"]
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        quiet = client.filings("AAPL", "2024-11-02", form_type="10-K")
    assert quiet.filings[0].acceptance_datetime.tzinfo is not None
    assert ("form_type", "10-K") in session.calls[1]["params"]

    earn_session = Session([Response(200, earnings_body())])
    events = PtDataClient(api_key="", cache_dir=tmp_path / "earn", session=earn_session)
    event = events.earnings_event("AAPL", 2023, "FY")
    params = earn_session.calls[0]["params"]
    assert earn_session.calls[0]["url"].endswith("/v1/earnings-event")
    assert ("fiscal_year", "2023") in params
    assert ("fiscal_period", "FY") in params
    assert all(key != "as_of_date" for key, _value in params)
    assert event.as_reported is not None
    assert event.as_reported.revenue == 383285000000.0
    assert event.as_reported.eps_gaap == 6.13
    assert event.implied_expectation is None
    assert event.sec_acceptance_ts is not None
    assert event.sec_acceptance_ts.isoformat() == "2023-11-02T20:30:32+00:00"

    members_session = Session([Response(200, constituents_body())])
    members = PtDataClient(api_key="", cache_dir=tmp_path / "idx", session=members_session)
    parsed = members.index_constituents("SP500", "2020-12-21")
    assert members_session.calls[0]["url"].endswith("/v1/index-constituents")
    assert parsed.tickers[:3] == ["A", "AAL", "AAP"]
    assert parsed.constituents[0].cik == 1090872
    assert len(parsed.tickers) == 3


def test_earnings_optional_block_parses_when_present():
    body = earnings_body()
    body["implied_expectation"] = {
        "as_of_date": "2023-11-02",
        "expected_move_pct": 1.5,
        "atm_iv": None,
        "method": "atm_straddle",
    }
    parsed = parse_earnings_event(body)
    assert parsed.implied_expectation is not None
    assert parsed.implied_expectation.as_of_date.isoformat() == "2023-11-02"
    assert parsed.implied_expectation.expected_move_pct == 1.5
    assert parsed.implied_expectation.method == "atm_straddle"
    assert parsed.implied_expectation.atm_iv is None


def test_q4_derivation_and_financials_family_are_parsed(tmp_path):
    body = fundamentals(
        ticker="AAPL",
        as_of_date="2026-11-01",
        metrics={
            "revenue": metric(
                94930000000.0,
                fiscal_period="Q4",
                accession="0000320193-24-000123",
                provenance="derived",
                derivation=Q4_DERIVATION,
            )
        },
        unavailable={
            "eps_diluted": {
                "reason": "Q4 EPS/share count is not additive; not derived",
                "code": "not_reported",
                "available_alternatives": ["revenue"],
                "docs_url": "https://example.test/financials",
                "detail": "not derived",
            }
        },
    )
    body["metrics"]["revenue"]["fiscal_year"] = 2024
    session = Session([Response(200, body)])
    fund = PtDataClient(api_key="", cache_dir=tmp_path, session=session).fundamentals(
        "AAPL", "2026-11-01", ["revenue", "eps_diluted"], fiscal_year=2024, fiscal_period="Q4"
    )
    revenue = fund.metrics["revenue"]
    assert revenue.value == 94930000000.0
    assert revenue.provenance == "derived"
    assert revenue.derivation is not None
    assert revenue.derivation.method == "fy_minus_q1_q3"
    assert revenue.derivation.inputs[0].accession == "0000320193-24-000123"
    assert "eps_diluted" not in fund.metrics
    assert fund.unavailable["eps_diluted"].code == "not_reported"

    bank = fundamentals(
        ticker="BLK",
        metrics={},
        unavailable={
            "revenue": {
                "reason": "no single revenue line",
                "code": "financials_family",
                "available_alternatives": ["total_revenue", "net_interest_income"],
                "docs_url": "https://example.test/financials",
                "detail": None,
            }
        },
    )
    bank_session = Session([Response(200, bank)])
    parsed = PtDataClient(api_key="", cache_dir=tmp_path / "bank", session=bank_session).fundamentals(
        "BLK", "2018-06-30", ["revenue"], fiscal_year=2017
    )
    assert parsed.metrics == {}
    guidance = parsed.unavailable["revenue"]
    assert guidance.code == "financials_family"
    assert guidance.available_alternatives == ["total_revenue", "net_interest_income"]
    assert 0 not in (item.value for item in parsed.metrics.values())
