# ptdata

Python client for the [PtData](https://ptdata.io) HTTP API at `https://api.ptdata.io`. It returns point-in-time fundamentals, SEC filings, index membership, and earnings 8-K metadata.

This package was written with AI assistance.

PtData has no prices. It does not serve consensus estimates or intraday data. This client does not fetch prices. Use a separate price source if you need them.

## Install

```bash
pip install ptdata
```

Python 3.11 or newer. Runtime dependencies are `pandas` and `requests`.

## Access and limits

No API key is required on the free tier. Limits are 120 requests per minute and 200 requests per day per IP, reset at UTC midnight. The same data is served on every tier. Free access is for evaluation. Commercial use needs a paid plan: Pro is $49/month, Scale is $199/month. Create a bearer token at https://api.ptdata.io/account. On 2026-11-23 the pricing page also listed Pro at 1,200/minute and 15,000/day, and Scale at 5,000/minute and 100,000/day.

```python
from ptdata import PtDataClient

client = PtDataClient()  # reads PTDATA_API_KEY if set, otherwise the free tier
```

Pass `api_key=""` to force the free tier even when `PTDATA_API_KEY` is set. An empty string sends no `Authorization` header. The key is not written into logs, exception text, or the disk cache. The cache key is the path plus the sorted query.

`User-Agent` is `ptdata-python/<version>`.

HTTP 429 carries `Retry-After` (a number of seconds or an HTTP-date) and JSON fields `scope` (`rate` or `daily`) and `tier`. This client sleeps on `scope=rate`, capped at 180 seconds, and retries. `scope=daily` raises `PtDataRateLimit` and does not retry. Do not loop on a daily limit. Transient HTTP 5xx responses are retried. Only idempotent GETs are sent.

The disk cache is off unless `cache_dir` is set. One `PtDataClient` still reuses identical responses in memory. The example below turns the disk cache on.

## Usage

```python
from ptdata import PtDataClient

client = PtDataClient()
fund = client.fundamentals(
    "GE",
    as_of_date="2018-02-28",
    metrics=["revenue", "net_income"],
    fiscal_year=2017,
)
fund.metrics["revenue"].value  # 122092000000.0
fund.metrics["revenue"].source_accession  # 0000040545-18-000014
```

Checked on the live API on 2026-11-23: GE FY2017 revenue as of 2018-02-28 is `122092000000.0` USD, accession `0000040545-18-000014`. Net income on that same response is `-5786000000.0`, same accession. Numbers are the raw API values, not millions.

`metrics` is required. If it is omitted, the API returns an empty `metrics` object; this method raises `ValueError` instead of sending that request. Without `fiscal_year`, the API returns the latest `fiscal_period` known on `as_of_date` (default `FY`), not the latest quarter.

Always read `fund.unavailable`. A missing metric is not zero. `code="financials_family"` means the filer has no single revenue line. Use `available_alternatives` when the API sends them, and do not invent a total.

`knowledge_from` on a metric is often the filing date at 00:00Z, not the SEC acceptance time. For acceptance time, use filings:

```python
members = client.index_constituents("SP500", as_of_date="2020-12-21")
filings = client.filings("AAPL", as_of_date="2024-11-02", form_type="10-K")
event = client.earnings_event("AAPL", fiscal_year=2023, fiscal_period="FY")
```

Documented index codes are `SP500`, `DJIA`, `DJT`, `DJU`, and `NDX`. Membership is whatever the API returns for that date.

`filings` without `form_type` matches the API and warns: the list can include every form type and be very large. Pass a form type such as `10-K` or `10-Q`.

`earnings_event` has no `as_of_date`. `fiscal_period` is `FY` or `Q1`–`Q3`. A fourth-quarter earnings release is stored as `FY`. Use `sec_acceptance_ts` and `as_reported.revenue` / `as_reported.eps_gaap`. Checked on 2026-11-23: AAPL FY2023 `as_reported.revenue` is `383285000000.0` and `eps_gaap` is `6.13`. Acceptance time on that response is `2023-11-02T20:30:32Z`.

This client does not derive quarters. A Q4 value is the API's value. When the service built it, `derivation.method` is set (live AAPL FY2024 Q4 revenue as of 2026-11-01 used `fy_minus_q1_q3`, provenance `derived`, accession `0000320193-24-000123`).

## Pandas

`fundamentals_frame` is one row per ticker, as-of date, and metric, including unavailable metrics. Columns include `value`, `unit`, `fiscal_year`, `fiscal_period`, `source_accession`, `knowledge_from`, `provenance`, and `unavailable_code` / `unavailable_reason` / `available_alternatives`. Unavailable `value` is null, not zero.

`fundamentals_panel(client, tickers, as_of_dates, metrics, ...)` loops those calls. A daily 429 stops the loop. `constituents_frame` is one row per member.

## Look-ahead example

`examples/look_ahead_fy2017.py` loads FY2017 `revenue`, `operating_income`, `net_income`, `operating_cash_flow`, and `total_assets` for GE, AMD, CRM, JPM, MSFT, and AAPL as of `2018-06-30` and as of `2026-11-01`. Metrics for one ticker and date go in one request, so a cold cache is 12 calls. The script sets `cache_dir` to `examples/.cache` (gitignored) and `api_key=""`.

Recorded on 2026-11-23. First run `http_calls=12`. Second run `http_calls=0`.

`pct_change = (latest - first) / abs(first) * 100`. A blank value is unavailable, not zero. `2018-06-30` is the comparison date used by the study below, not the filing morning of every company. CRM's FY2017 10-K was already public then (`knowledge_from` `2017-03-06`).

```
FY2017 as of 2018-06-30 vs 2026-11-01
http_calls=12
pct_change = (latest - first) / abs(first) * 100. Blank value means unavailable, not zero.
ticker              metric   first_value      first_accession  latest_value     latest_accession pct_change first_unavailable latest_unavailable
    GE             revenue  122092000000 0000040545-18-000014   99279000000 0000040545-20-000009     -18.69
    GE    operating_income                                                                                       not_reported       not_reported
    GE          net_income   -5786000000 0000040545-18-000014   -8484000000 0000040545-19-000014     -46.63
    GE operating_cash_flow   10426000000 0000040545-18-000014    6554000000 0000040545-20-000009     -37.14
    GE        total_assets  369245000000 0000040545-18-000032  369245000000 0000040545-18-000032       0.00
   AMD             revenue    5329000000 0000002488-18-000042    5329000000 0000002488-18-000042       0.00
   AMD    operating_income     204000000 0000002488-18-000042     127000000 0000002488-19-000011     -37.75
   AMD          net_income      43000000 0000002488-18-000042     -33000000 0000002488-19-000011    -176.74
   AMD operating_cash_flow      68000000 0000002488-18-000042      12000000 0000002488-19-000011     -82.35
   AMD        total_assets    3552000000 0000002488-18-000068    3552000000 0000002488-18-000068       0.00
   CRM             revenue    8391984000 0001108524-17-000006    8391984000 0001108524-17-000006       0.00
   CRM    operating_income      64228000 0001108524-17-000006     218000000 0001108524-19-000009     239.42
   CRM          net_income     179632000 0001108524-17-000006     323000000 0001108524-19-000009      79.81
   CRM operating_cash_flow    2162198000 0001108524-17-000006    2162000000 0001108524-19-000009      -0.01
   CRM        total_assets   17584923000 0001108524-17-000006   17584923000 0001108524-17-000006       0.00
   JPM             revenue   99624000000 0000019617-18-000057  100705000000 0000019617-19-000054       1.09
   JPM    operating_income                                                                                       not_reported       not_reported
   JPM          net_income   24441000000 0000019617-18-000057   24441000000 0000019617-18-000057       0.00
   JPM operating_cash_flow   -2501000000 0000019617-18-000057  -10827000000 0000019617-19-000054    -332.91
   JPM        total_assets 2533600000000 0000019617-18-000057 2533600000000 0000019617-18-000057       0.00
  MSFT             revenue   89950000000 0001564590-17-014900   89950000000 0001564590-17-014900       0.00
  MSFT    operating_income   22326000000 0001564590-17-014900   29025000000 0001564590-18-019062      30.01
  MSFT          net_income   21204000000 0001564590-17-014900   25489000000 0001564590-18-019062      20.21
  MSFT operating_cash_flow   39507000000 0001564590-17-014900   39507000000 0001564590-18-019062       0.00
  MSFT        total_assets  250312000000 0001564590-17-020171  250312000000 0001564590-17-020171       0.00
  AAPL             revenue  229234000000 0000320193-17-000070  229234000000 0000320193-17-000070       0.00
  AAPL    operating_income   61344000000 0000320193-17-000070   61344000000 0000320193-17-000070       0.00
  AAPL          net_income   48351000000 0000320193-17-000070   48351000000 0000320193-17-000070       0.00
  AAPL operating_cash_flow   63598000000 0000320193-17-000070   64225000000 0000320193-18-000145       0.99
  AAPL        total_assets  375319000000 0000320193-17-000070  375319000000 0000320193-17-000070       0.00
operating_income / total_assets, rank 1 = highest. Names without operating_income are skipped.
skipped: GE, JPM
ticker first_oi_over_assets latest_oi_over_assets  first_rank  latest_rank
   AMD             0.057432              0.035755           3            3
   CRM             0.003652              0.012397           4            4
  MSFT             0.089193              0.115955           2            2
  AAPL             0.163445              0.163445           1            1
http_calls=12
```

GE and JPM have no `operating_income` at this coordinate (`not_reported`). They are left out of the ratio. In this six-name set the rank order of the other four names does not change. That is not a claim about a larger universe. An accession can change when the printed percent change is `0.00` (MSFT `operating_cash_flow`). Not investment advice.

The 86-name study was not re-run. Its README, read on 2026-11-23, says: 46 of 86 companies differ by at least 1% on at least one core line, and 21 by 5% or more; operating income changed for 29 of 68 companies, operating cash flow for 19 of 86, and total assets for 0 of 86; ranked on operating income / total assets, 4 of 68 changed quintile, so a broad rank mostly survived. https://github.com/ptdata-io/fy2017-restatements

## Coverage

Figures below are the public site and the methodology docs as read on 2026-11-23, not a new census of the database. The site says 8,300+ companies and about 6,300 with fundamentals. The methodology says XBRL statement facts start at FY2009, and FY2001–2008 values are a parsed tier (`provenance=parsed`, with `extraction_confidence`) for a growing subset of companies, not every filer. S&P 500 membership is reconstructed from 1996; older dates can under-include names that were not verified. Index codes also include DJIA, NDX, DJT, and DJU, with shallower history on some of them.

## Errors

| Situation | Exception |
| --- | --- |
| HTTP 404 | `PtDataNotFound` (`detail` is the API text) |
| HTTP 401 | `PtDataAuthError` |
| HTTP 422 | `PtDataValidationError` |
| HTTP 429 after the wait cap, or still limited after retries | `PtDataRateLimit` (`scope="rate"`, `retry_after`, `tier`) |
| HTTP 429 `scope=daily` | `PtDataRateLimit` with `scope="daily"`. Not retried. |
| Other HTTP failures, after 5xx retries | `PtDataError` |

## Tests

`pytest` does not call the network. The GE FY2017 check is marked `live` and skipped unless `PTDATA_LIVE=1`.

## Links

- https://ptdata.io
- https://api.ptdata.io/docs
- info@ptdata.io
