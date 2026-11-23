# REPORT

Local package only. Nothing was published and nothing was pushed.

## What was built

`/Users/peppe/src/ptdata-python` is a Python 3.11+ package named `ptdata` (import `ptdata`). Hatchling, MIT, copyright PtData S.A. Dependencies: `pandas` and `requests`. No `financetoolkit` dependency. No vectorbt extra.

`PtDataClient` wraps the four GETs in the OpenAPI document fetched on 2026-11-23: `/v1/fundamentals`, `/v1/index-constituents`, `/v1/filings`, `/v1/earnings-event`. Base URL `https://api.ptdata.io`. One `requests.Session`. `User-Agent` is `ptdata-python/0.1.0`.

HTTP behavior reused from `~/src/financetoolkit-ptdata/src/financetoolkit_ptdata/client.py`: cache key is the path plus the sorted query (repeated `metrics` keys, not the Authorization header); `Retry-After` accepts seconds or an HTTP-date; `scope=rate` sleeps up to 180 seconds and retries; `scope=daily` raises and does not sleep or retry; the API key is redacted from exception text. Disk cache is off unless `cache_dir` is passed. The example passes `examples/.cache`. Identical calls on one client are still reused in memory.

The client does not derive quarters and does not treat Q4 or `cost_of_revenue` as missing. It returns the API body, including `derivation` when present. `metrics` is required (`ValueError` when omitted or empty). `filings` allows `form_type=None` and warns that the list can be very large. Values are not scaled. `unavailable` is always on the model and in `fundamentals_frame` (null value, not zero).

Pandas helpers: `fundamentals_frame`, `fundamentals_panel`, `constituents_frame`.

## Live checks (2026-11-23, free tier, no API key)

OpenAPI at `https://api.ptdata.io/openapi.json` listed only those four GET routes. Schemas used for the dataclasses include `MetricValue`, `MetricGuidance`, `Derivation` (`fy_minus_q1_q3`, `ytd_minus_prior_ytd`, `direct_q4_fact`, `fy_instant`), `Lineage`, filings, constituents, and earnings. Unknown JSON fields are ignored.

About 34 free GETs were made while checking figures, then the example made 12, then a second example process made 0 (12 cache files under `examples/.cache`). No daily 429 was hit.

Matched the notes that were re-checked:

- GE FY2017 as of 2018-02-28: `revenue` `122092000000.0` USD, `net_income` `-5786000000.0`, accession `0000040545-18-000014` for both.
- AAPL FY2024 as of 2026-11-01: `revenue` `391035000000.0`, `cost_of_revenue` `210352000000.0`, `gross_profit` `180683000000.0`, `operating_income` `123216000000.0`, `net_income` `93736000000.0`, `eps_diluted` `6.08`, `operating_cash_flow` `118254000000.0`, `capex` `9447000000.0`, `total_assets` `364980000000.0`, `stockholders_equity` `56950000000.0`, accession `0000320193-24-000123`. `eps_basic` was `unavailable` / `not_reported`.
- AAPL FY2024 Q4 as of 2026-11-01: `revenue` `94930000000.0`, `cost_of_revenue` `51051000000.0`, accession `0000320193-24-000123`, `provenance=derived`, `derivation.method=fy_minus_q1_q3`. `total_assets` was `364980000000.0`, `provenance=xbrl`, `method=fy_instant`. `eps_diluted` was `unavailable` / `not_reported` (not derived).
- AAPL FY2023 earnings: `as_reported.revenue` `383285000000.0`, `eps_gaap` `6.13`, `sec_acceptance_ts` `2023-11-02T20:30:32Z`, filing accession `0000320193-23-000104`.
- SP500 on 2020-12-21: 503 tickers, first three `A`, `AAL`, `AAP`.

Example (FY2017, as of 2018-06-30 vs 2026-11-01), first process `http_calls=12`, second process `http_calls=0`. The README table is that output. GE and JPM `operating_income` were `not_reported` on both dates, so the operating-income / total-assets rank skips them. AMD, CRM, MSFT, and AAPL did not change rank. Total assets did not change for these six names.

`https://github.com/ptdata-io/fy2017-restatements` README, read the same day, still contains: 46 of 86 at least 1%, 21 at least 5%, operating income 29 of 68, operating cash flow 19 of 86, total assets 0 of 86, and 4 of 68 quintile changes. Those sentences are quoted in the package README. The 86-name sample was not re-run.

Coverage text in the README is from https://ptdata.io and https://github.com/ptdata-io/ptdata-methodology (`docs/08-known-limitations.md`, `docs/05-index-membership.md`, `docs/09-pre-xbrl-fundamentals.md`) as fetched that day. The methodology page's measured counts are dated 2026-07-23 in that file (~8,318 companies, ~6,306 with fundamentals, parsed tier ~1,539 companies). They were not re-counted here. The site's rounded figures are 8,300+ companies and ~6,300 with fundamentals. Pro $49/month and Scale $199/month matched the pricing page, which also listed the paid rate limits cited in the README.

Metric names actually returned or marked unavailable in these calls: `revenue`, `cost_of_revenue`, `gross_profit`, `operating_income`, `net_income`, `eps_diluted`, `eps_basic`, `operating_cash_flow`, `capex`, `total_assets`, `stockholders_equity`. The methodology page describes a larger logical set (including share counts, cash, debt, liabilities, `ebit`, and the revenue family). This client does not hard-code that list. `ytd_minus_prior_ytd` and `direct_q4_fact` are in the OpenAPI description and were not in the responses fetched here. `fy_minus_q1_q3` and `fy_instant` were.

BLK FY2017 as of 2018-06-30: `revenue` and `total_revenue` came back `unavailable` with `code=financials_family` and an empty `available_alternatives` list. `net_income` was `not_reported`. JPM FY2017 did report `revenue` (not `financials_family`); `operating_income` was `not_reported`, with alternatives that included `total_revenue`, `total_net_revenue`, `net_interest_income`, and `noninterest_income`.

AAPL `10-K` filings as of 2024-11-02: 29 rows, newest accession `0000320193-24-000123`, `acceptance_datetime` `2024-11-01T10:01:36Z`.

## Deviations

The task text said a later as-of date shows GE FY2017 revenue restated to $110.97B from accession `0000040545-19-000014`. The live API did not return that number.

- As of 2019-03-01 and 2020-02-23: `revenue` `118243000000.0`, accession `0000040545-19-000014`.
- As of 2020-02-24 and 2026-11-01: `revenue` `99279000000.0`, accession `0000040545-20-000009`.

The README example uses the 2026-11-01 figure. `$110.97B` is not stated as a current fact.

No other checked figure in the task's "re-checked on 2026-11-23" list disagreed with the live API.

## Gaps

- Not published. No PyPI, TestPyPI, GitHub repo, remote, tag, or push. See the commands below; they were not run.
- No vectorbt extra and no price example. PtData has no prices.
- Earnings README text covers acceptance time and as-reported revenue and `eps_gaap` only. The model still parses `as_reported.eps_non_gaap` and `implied_expectation` because they are in the OpenAPI schema. The AAPL FY2023 response had `implied_expectation: null`. That field is not documented in the README.
- Unknown JSON fields are ignored, so a response field this client does not model is not copied onto the dataclass.
- Default `pytest` does not hit the network (24 passed, 1 skipped on the run recorded with this file). The skipped test is `tests/test_live.py`, which runs only when `PTDATA_LIVE=1`.
- Pre-XBRL `provenance=parsed` was not fetched live in this session. The frame keeps `extraction_confidence` when the API sends it.
- Paid bearer auth was not called live (no key in the environment). HTTP 401 is covered by a mock. 404, 422, and both 429 scopes are mocked.

## Tests and packaging

From `/Users/peppe/src/ptdata-python`, with the local `.venv` (Python 3.11.15):

- `pip install -e ".[dev]"` completed.
- `python -c "import ptdata; from ptdata import PtDataClient"` printed `0.1.0`.
- `pytest`: 24 passed, 1 skipped, no network.
- Example: `http_calls=12`, then `http_calls=0`.

A local `python -m build` was run to check packaging. It wrote `dist/ptdata-0.1.0-py3-none-any.whl` and `dist/ptdata-0.1.0.tar.gz`. The wheel contains `ptdata/*.py`. `dist/` is gitignored. That build is not a release.

## Publish commands that were not executed

```bash
cd /Users/peppe/src/ptdata-python
python -m build
twine upload dist/*
git remote add origin git@github.com:ptdata-io/ptdata-python.git
git tag v0.1.0
git push -u origin main
git push origin v0.1.0
```

None of those publish or push commands were run. There was no `twine upload`, no TestPyPI upload, no `uv`/`flit` publish, no `gh repo create`, and no PR. A local `python -m build` (packaging check only) is separate from the release sequence above and was not followed by an upload. No git remote was added, no tag was created, and nothing was pushed.
