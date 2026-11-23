"""FY2017 fundamentals as of 2018-06-30 and as of 2026-11-01.

Six tickers and five metrics are two dates, so a cold cache makes 12 HTTP calls.
The disk cache is ``examples/.cache``. A second run should print ``http_calls=0``.

Not investment advice. PtData does not provide prices.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ptdata import PtDataClient, fundamentals_panel

TICKERS = ["GE", "AMD", "CRM", "JPM", "MSFT", "AAPL"]
METRICS = [
    "revenue",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "total_assets",
]
FIRST = "2018-06-30"
LATEST = "2026-11-01"
CACHE = Path(__file__).resolve().parent / ".cache"


def _blank(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value)


def _cell_num(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    number = float(value)
    if number.is_integer():
        return f"{number:.0f}"
    return str(value)


def _cell_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2f}"


def _pct(first: object, latest: object) -> float | None:
    if first is None or latest is None or pd.isna(first) or pd.isna(latest):
        return None
    base = float(first)
    if base == 0:
        return None
    return (float(latest) - base) / abs(base) * 100


def _ratio(part: pd.DataFrame) -> float | None:
    income = part.loc[part["metric"] == "operating_income", "value"]
    assets = part.loc[part["metric"] == "total_assets", "value"]
    if income.empty or assets.empty or pd.isna(income.iloc[0]) or pd.isna(assets.iloc[0]):
        return None
    assets_value = float(assets.iloc[0])
    if assets_value == 0:
        return None
    return float(income.iloc[0]) / assets_value


def main() -> None:
    # api_key="" forces the free tier (no Authorization header) even if
    # PTDATA_API_KEY is set. Omit the argument to use that variable.
    client = PtDataClient(api_key="", cache_dir=CACHE)
    frame = fundamentals_panel(
        client,
        TICKERS,
        [FIRST, LATEST],
        METRICS,
        fiscal_year=2017,
        fiscal_period="FY",
    )
    print(f"FY2017 as of {FIRST} vs {LATEST}")
    print(f"http_calls={client.calls_made}")

    dated = frame.copy()
    dated["as_of_date"] = dated["as_of_date"].dt.strftime("%Y-%m-%d")
    keep = ["ticker", "metric", "value", "source_accession", "unavailable_code"]
    first = dated.loc[dated["as_of_date"] == FIRST, keep].rename(
        columns={
            "value": "first_value",
            "source_accession": "first_accession",
            "unavailable_code": "first_unavailable",
        }
    )
    latest = dated.loc[dated["as_of_date"] == LATEST, keep].rename(
        columns={
            "value": "latest_value",
            "source_accession": "latest_accession",
            "unavailable_code": "latest_unavailable",
        }
    )
    merged = first.merge(latest, on=["ticker", "metric"], how="outer")
    merged["ticker"] = pd.Categorical(merged["ticker"], TICKERS, ordered=True)
    merged["metric"] = pd.Categorical(merged["metric"], METRICS, ordered=True)
    merged = merged.sort_values(["ticker", "metric"]).reset_index(drop=True)
    merged["pct_change"] = [_pct(a, b) for a, b in zip(merged["first_value"], merged["latest_value"], strict=True)]

    display = pd.DataFrame(
        {
            "ticker": merged["ticker"].astype(str),
            "metric": merged["metric"].astype(str),
            "first_value": merged["first_value"].map(_cell_num),
            "first_accession": merged["first_accession"].map(_blank),
            "latest_value": merged["latest_value"].map(_cell_num),
            "latest_accession": merged["latest_accession"].map(_blank),
            "pct_change": merged["pct_change"].map(_cell_pct),
            "first_unavailable": merged["first_unavailable"].map(_blank),
            "latest_unavailable": merged["latest_unavailable"].map(_blank),
        }
    )
    print("pct_change = (latest - first) / abs(first) * 100. Blank value means unavailable, not zero.")
    print(display.to_string(index=False))

    ratios = []
    for ticker in TICKERS:
        part = dated.loc[dated["ticker"] == ticker]
        ratios.append(
            {
                "ticker": ticker,
                "first_oi_over_assets": _ratio(part.loc[part["as_of_date"] == FIRST]),
                "latest_oi_over_assets": _ratio(part.loc[part["as_of_date"] == LATEST]),
            }
        )
    ranks = pd.DataFrame(ratios)
    both = ranks.dropna(subset=["first_oi_over_assets", "latest_oi_over_assets"]).copy()
    both["first_rank"] = both["first_oi_over_assets"].rank(ascending=False, method="min").astype(int)
    both["latest_rank"] = both["latest_oi_over_assets"].rank(ascending=False, method="min").astype(int)
    skipped = [ticker for ticker in TICKERS if ticker not in set(both["ticker"])]
    print("operating_income / total_assets, rank 1 = highest. Names without operating_income are skipped.")
    print("skipped: " + (", ".join(skipped) if skipped else "(none)"))
    shown = both.copy()
    shown["first_oi_over_assets"] = shown["first_oi_over_assets"].map(lambda v: f"{v:.6f}")
    shown["latest_oi_over_assets"] = shown["latest_oi_over_assets"].map(lambda v: f"{v:.6f}")
    print(shown.to_string(index=False))
    print(f"http_calls={client.calls_made}")


if __name__ == "__main__":
    main()
