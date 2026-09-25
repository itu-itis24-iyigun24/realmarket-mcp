# Data providers

realmarket-mcp ships no data. Each user fetches data from these providers under their own
access, and is responsible for complying with each provider's terms and for not
redistributing the data they retrieve.

Every provider module must have an entry here before it is merged (see the
`add-data-provider` skill).

| Provider | Module | Data | Enabled by | API key | Terms | Attribution |
|---|---|---|---|---|---|---|
| Yahoo Finance (via the community `yfinance` library) | `providers/yahoo.py` | daily prices, FX, gold futures, financial statements | `REALMARKET_PRICE_PROVIDER=yahoo` + `[yahoo]` extra | no | Yahoo terms of service; prohibit automated access without permission | not affiliated with or endorsed by Yahoo |
| SEC EDGAR XBRL API | `providers/sec.py` | US company financial statements (companyfacts), ticker→CIK list, SIC industry | `REALMARKET_SEC_CONTACT` (an e-mail, not a key) | no | SEC "Accessing EDGAR Data": declared User-Agent with contact, max 10 requests/s; data is public | cite "SEC EDGAR" |
| FRED (Federal Reserve Bank of St. Louis) | `providers/cpi.py` | US CPI `CPIAUCNS` (source: BLS) | `REALMARKET_FRED_API_KEY` | yes, free | FRED API terms of use | see notice below |
| TCMB EVDS (Central Bank of the Republic of Türkiye) | `providers/cpi.py` | Turkish CPI `TP.GENENDEKS.T1` (2003=100) (source: TÜİK) | `REALMARKET_EVDS_API_KEY` | yes, free | EVDS terms of use | cite TCMB EVDS / TÜİK |
| FRED public CSV | `providers/cpi.py` | US CPI `CPIAUCNS` without a key | fallback when the OECD is unavailable | no | FRED website terms (personal, non-commercial downloads) | "U.S. Bureau of Labor Statistics via FRED" |
| OECD Data Explorer API | `providers/cpi.py` | national monthly CPI (2015=100) for OECD members, incl. US | default when no official key | no | OECD terms and conditions; CC BY 4.0; 60 downloads/hour | cite "OECD" and the dataset |
| GDELT Project | `providers/gdelt.py` | news article listings (title, link, publisher, date) | default; `REALMARKET_NEWS_PROVIDER=none` disables | no | GDELT terms (open data; citation requested) | cite "The GDELT Project" |
| KAP (Public Disclosure Platform) | **not implemented — terms forbid it** | company disclosures and financial statements | — | — | see finding below | — |
| User CSV | `inflation.py` | any monthly CPI series | `REALMARKET_CPI_CSV_<REGION>` | — | the user's own source | — |
| Fixture | `providers/fixture.py` | synthetic test data | `REALMARKET_PRICE_PROVIDER=fixture` | — | — | — |

FRED notice: *This product uses the FRED® API but is not endorsed or certified by the Federal
Reserve Bank of St. Louis.*

## Checked before the first public release

`[x]` checked; `[~]` checked, with a decision still open. Each item says how it was checked:
read directly, or — where the build environment's network blocks the site — through web
search of the provider's own pages, which is weaker evidence and should be re-read from a
normal connection.

- [~] Yahoo — **decision needed.** legal.yahoo.com is not reachable from the build environment;
      the clause was read through web-search results of Yahoo's own Terms of Service pages
      (2026-09-25): users may not "access or collect data, or attempt to access or collect data,
      from our Services using any automated means, devices, programs, algorithms or
      methodologies, including but not limited to robots, spiders, scrapers, data mining tools,
      or data gathering or extraction tools, for any purpose without our express, prior
      permission". There is no personal-use exception. The provider stays opt-in, the README now
      states this plainly, and whether to keep shipping it is recorded as an open decision.
- [x] FRED API terms read on 2026-09-25 (`fred.stlouisfed.org/docs/api/terms_of_use.html`).
      Required: the notice "This product uses the FRED® API but is not endorsed or certified by
      the Federal Reserve Bank of St. Louis." placed prominently (README, extension description,
      and the `attribution` of every FRED provenance block); for an application used by others,
      show a link to the API terms and state that users agree to be bound by them (README "Data
      sources, terms and privacy"; extension description). `CPIAUCNS` is "Public Domain:
      Citation Requested" (series page); citation: "U.S. Bureau of Labor Statistics via FRED".
      The FRED website terms (`fred.stlouisfed.org/legal/`) govern the keyless CSV: downloads
      are licensed for personal, non-commercial use and disruptive data-gathering is prohibited;
      programmatic use is sanctioned only through the API. The CSV is therefore now only the US
      fallback when the OECD is unavailable, and the OECD (CC BY 4.0) is the keyless default —
      its US series equals FRED's month for month (both skip October 2025).
- [x] FRED: JSON response format parsed in `providers/cpi.py` (verified live on 2026-09-25).
      `observations[].date` is `YYYY-MM-01`, `value` is a string; a month BLS did not publish is
      `"."` (October 2025 is missing in `CPIAUCNS`) and is skipped, never filled. The August 2026
      level, 334.980, matches the BLS CPI release (+3.4% over 12 months, not seasonally adjusted).
- [x] EVDS terms read on 2026-09-25 (English PDF, docId 21; Turkish, docId 18, served by
      `evds3.tcmb.gov.tr/igmevdsms-dis/documents/showDocument`). "Data provided in the EVDS
      application can be accessed via web services" and "may be used and published by third
      parties provided that such data are used with reference"; translations must be marked as
      unofficial; even commercial reuse must not charge its users for the data; not investment
      advice. Attribution used: "Source: TÜİK consumer price index via CBRT (TCMB) EVDS".
      Privacy policy: docId 22.
- [x] EVDS: API base URL, series and JSON response format (verified live on 2026-09-25).
      Base URL `https://evds3.tcmb.gov.tr/igmevdsms-dis/` (evds2 now redirects to evds3); key
      sent as the `key` header. Response is `{"totalCount", "items": [...]}`, each item holding
      `Tarih` as unpadded `YYYY-M`, the series column with dots as underscores, string values,
      `null` for a missing month, and a `UNIXTIME` object. **Fixed:** the former series
      `TP.FG.J0` was archived with its last value at 2026-01 after TÜİK rebased CPI to
      2025=100, which cut every Turkish real return short at January 2026. The provider now
      reads `TP.GENENDEKS.T1` (general index, 2003=100, continued), identical to `TP.FG.J0`
      through 2026-01 and published through 2026-08. Its August 2026 change, +31.50% year on
      year and +1.84% month on month, matches TÜİK's release (31.51% and 1.84%; the 0.01-point
      gap is rounding of the chained 2003=100 levels). Regression test:
      `tests/test_inflation.py::test_evds_uses_the_live_series_not_the_archived_one`.
- [x] GDELT verified live on 2026-09-25: a non-empty `articles` response has exactly the field
      set the tests use (`url`, `url_mobile`, `title`, `seendate`, `socialimage`, `domain`,
      `language`, `sourcecountry`), and the saved live response parses correctly through
      `get_news` (dates, languages, countries, newest first). The rate-limit response (HTTP 429,
      plain text) is mapped to `rate_limited`. Terms (gdeltproject.org is not reachable from the
      build environment; read through web search of its About page): datasets are free for
      "unlimited and unrestricted use for any academic, commercial, or governmental use", and
      use or redistribution must cite the GDELT Project with a link to gdeltproject.org — every
      news result's provenance does. GDELT publishes no privacy policy found; it receives only
      the search text.
- [x] KAP: reviewed on 2026-09-25 — **stop; no KAP provider.** kap.org.tr has no robots.txt, but
      its "Telif Hakkı ve Çekince İhbarı" page (`/tr/icerik/Diger/telif-hakki-ve-cekince-ihbari`,
      section "Kullanım izni ve şartları") states that users may use the information only to
      inform themselves, and that without MKK's prior written permission it may not be copied in
      whole or in part, put into application, distributed, reproduced, modified, or stored for
      later use. A tool that fetches and processes KAP data falls under that. The site's JSON
      endpoints (`/tr/api/...`) are internal to its web app, not a published API; KAP data is
      licensed separately through its data-publishing service. Options: request written
      permission from MKK, or use a licensed source.
- [x] FRED public CSV and OECD API verified live on 2026-09-25. FRED CSV (`fredgraph.csv?id=
      CPIAUCNS`) equals the keyed API on every overlapping month; it resets connections for
      bare User-Agent strings, so requests send `realmarket-mcp/<version> (+<repo URL>)`. OECD
      (`OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0`, key `<ISO3>.M.N.CPI.IX._T.N._Z`): Türkiye's
      month-on-month changes equal EVDS exactly (2021-09..2025-12 cumulative +515.76% in both),
      but the series ends at 2025-12 (TÜİK's 2026 rebasing is not yet carried); DE and GB run to
      2026-08; JP, CH and the euro area return 404 "NoRecordsFound" in this dataflow.
- [x] SEC EDGAR: verified live on 2026-09-25. `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
      and `data.sec.gov/submissions/...` answer 200 to `realmarket-mcp/<version> <e-mail>`; a
      User-Agent **with a URL in it returns 403** ("Undeclared Automated Tool"), so the SEC agent
      string omits the repository URL. The ticker list `www.sec.gov/files/company_tickers.json`
      is `{"0": {"cik_str", "ticker", "title"}, ...}` (10,413 entries) with class shares as
      `BRK-B`. The SEC's developer page ("Fair Access") limits each user to 10 requests per
      second, asks for efficient scripts that download only what they need, and blocks
      unclassified bots; a declared agent making 2-3 targeted API calls per request fits that.
- [x] OECD (read through web search of oecd.org, not reachable directly, 2026-09-25): the API is
      free subject to the OECD Terms and Conditions; data are under CC BY 4.0 (Open Access
      Policy, July 2024); cite as "OECD (year), (dataset name), (data source) DOI or URL (accessed
      on (date))" — provenance names the dataflow and retrieval time. Anonymous limit: 60 data
      downloads per hour per IP; each region's series is now fetched once and reused for six
      hours (`config.OECD_CACHE_SECONDS`), keeping its original retrieval time.
- [x] Desktop extension `privacy_policies` (2026-09-25): SEC
      `https://www.sec.gov/about/privacy-information` (opened); TCMB EVDS docId 22 (opened);
      FRED `https://www.stlouisfed.org/about-us/privacy-policy` (linked from FRED's own terms
      pages); OECD `https://www.oecd.org/en/about/privacy.html` and Yahoo
      `https://legal.yahoo.com/us/en/yahoo/privacy/index.html` (official-domain search results;
      not reachable here). GDELT: none found.
- [x] Licences (2026-09-25): a clean `.[yahoo]` install has 48 third-party packages, all
      permissive (MIT, BSD, Apache-2.0, PSF, ISC-style); `certifi` is MPL-2.0 (file-level,
      used unmodified); `peewee` reports "UNKNOWN" but its licence file is MIT. `frozendict`
      (LGPL) is no longer pulled in by `yfinance` 1.7.
## Financial statements (Yahoo): reliability test, 2026-09-25

`get_financials` output for the 2026 Q2 reports of eight Borsa Istanbul companies, compared
with the results the companies published (via press coverage of their KAP filings).

| Company | Check | Tool | Official | Result |
|---|---|---|---|---|
| BIMAS | Q2 revenue; YoY revenue / net income | 221.90bn; +9.6% / +125% | 221.90bn; +9.6% / +128% | match |
| THYAO (reports in USD) | Q2 revenue, net income; YoY | 7.21bn, 0.20bn USD; +20.5% / -71.5% | 7.2bn, 0.197bn USD; +20-21% / -71% | match |
| GARAN (bank) | Q2 and H1 net income | 30.29bn; 63.44bn | 30.29bn; 63.44bn | match |
| AKBNK (bank) | YoY net income | +36.6% | +36.6% | match |
| FROTO | YoY revenue / net income | -14.1% / -44.9% | -14% / -45% | match |
| EREGL | YoY net income | +554% | +554% | match |
| TUPRS | YoY net income / **revenue** | +291% / **+59.7%** | +291% / **+43%** | **revenue mismatch, not flagged** |
| ASELS | Q2 revenue | 70.96bn | ~51.8bn (from official H1) | **wrong; flagged** (`missing_quarter`, `unusual_change`) |

Findings that shaped the tool:

- For companies under TMS 29, Yahoo stores the prior-year quarter and year **as restated in
  the latest filing** (BIMAS Q2 2025 = 202.43bn in June 2026 money), but the previous quarter
  **as first reported** (BIMAS Q1 2026 = 212.86bn; restated by CPI Jun/Mar = 1.0701 it gives
  the official 227.8bn exactly). Year-on-year comparisons are therefore used as reported, and
  quarter-on-quarter comparisons restate the earlier quarter with CPI. A first version that
  deflated everything double-counted inflation (BIMAS "real" -17% against the official +9.6%).
- Because of that mix, quarters are not reconciled with annual totals for TMS 29 years.
- Latest-quarter headline figures matched in 7 of 8 companies; one error was caught by the
  flags and one (TUPRS revenue growth) was not. The tool therefore always tells the model to
  verify material figures in the official filing.

## Financial statements (SEC EDGAR): check, 2026-09-25

`get_financials` via SEC EDGAR against figures the companies published (periods before this
project's reference cutoff, so they can be checked against the press releases):

| Company | Check | Tool | Published | Result |
|---|---|---|---|---|
| Apple | FY2025 Q4 revenue (derived: FY − 9 months) | 102.466bn | 102.466bn | match |
| Microsoft | FY2025 revenue; FY2025 Q4 revenue (derived) | 281.724bn; 76.441bn | 281.7bn; 76.4bn | match |
| NVIDIA | FY2025 revenue / net income; Q4 FY2025 revenue (derived) | 130.497bn / 72.880bn; 39.331bn | 130.5bn / 72.9bn; 39.3bn | match |
| JPMorgan (bank) | 2024 net revenue; Q4 2024 net revenue | 177.556bn; 42.768bn | 177.6bn; 42.8bn | match |
| Eli Lilly | 2024 revenue; Q4 2024 revenue (derived) | 45.043bn; 13.533bn | 45.04bn; 13.53bn | match |
| Coca-Cola | 2024 revenue; Q4 2024 revenue (derived); 2024 total debt | 47.061bn; 11.544bn; 44.2bn | 47.1bn; 11.5bn; ~44bn | match (after the fixes below) |

Findings that shaped the provider:

- Banks tag their quarterly top line as `RevenuesNetOfInterestExpense` and the annual one as
  `Revenues` (JPMorgan); both are read, per period, in a fixed order of preference.
- An integrity review of the first version found, and these are now fixed with regression
  tests: debt collapsing to short-term borrowings when the long-term element changed
  (Coca-Cola moved to `LongTermDebtAndCapitalLeaseObligations` in 2024: 42.2bn fell to 1.1bn;
  JPMorgan tags no `LongTermDebt` since 2014) — debt is now null without a long-term figure;
  commercial paper added on top of `ShortTermBorrowings`, which already includes it; a fourth
  quarter computed from a recast annual figure and a nine-month figure filed before the recast
  — it now uses the first-reported pair and the notes name restated years; one element per
  field, so quarters and years never mix `Revenues` with another total; bare numbers such as
  `7203` are no longer treated as CIKs (only `CIK…`).
- Live end to end with tickers: AAPL, GOOGL, BRK-B, JPM and KO from the SEC; ASML files US
  GAAP in EUR (annual only, Form 20-F; 2025 revenue 32.667bn, as published); TSM files IFRS, so
  `auto` falls back to the price provider (Yahoo, TWD). A fallback happens only when the SEC has
  no data for the company or does not list the ticker, never on an outage.
- Alphabet 2026 Q2: net income 112.2bn against operating income 40.8bn, because the 10-Q
  reports a 99.0bn gain on equity securities. The figure is correct as filed; the tool adds the
  informational flag `non_operating_items_dominate` when net income exceeds 1.5x operating
  income, so the model does not read it as operating performance.
- Some companies tag no `GrossProfit` or `OperatingIncomeLoss` (Eli Lilly); those fields stay
  null rather than being computed from other lines.
- Old years can mix a restated annual figure with first-reported quarters (Microsoft FY2016,
  after its ASC 606 restatement), so the quarter-to-year reconciliation covers only the four
  years shown.
