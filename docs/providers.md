# Data providers

realmarket-mcp ships no data. Each user fetches data from these providers under their own
access, and is responsible for complying with each provider's terms and for not
redistributing the data they retrieve.

Every provider module must have an entry here before it is merged (see the
`add-data-provider` skill).

| Provider | Module | Data | Enabled by | API key | Terms | Attribution |
|---|---|---|---|---|---|---|
| Yahoo Finance (via the community `yfinance` library) | `providers/yahoo.py` | daily prices, FX, gold futures | `REALMARKET_PRICE_PROVIDER=yahoo` + `[yahoo]` extra | no | Yahoo terms of service; restrict automated use | not affiliated with or endorsed by Yahoo |
| FRED (Federal Reserve Bank of St. Louis) | `providers/cpi.py` | US CPI `CPIAUCNS` (source: BLS) | `REALMARKET_FRED_API_KEY` | yes, free | FRED API terms of use | see notice below |
| TCMB EVDS (Central Bank of the Republic of Türkiye) | `providers/cpi.py` | Turkish CPI `TP.GENENDEKS.T1` (2003=100) (source: TÜİK) | `REALMARKET_EVDS_API_KEY` | yes, free | EVDS terms of use | cite TCMB EVDS / TÜİK |
| GDELT Project | `providers/gdelt.py` | news article listings (title, link, publisher, date) | default; `REALMARKET_NEWS_PROVIDER=none` disables | no | GDELT terms (open data; citation requested) | cite "The GDELT Project" |
| KAP (Public Disclosure Platform) | *planned* | company disclosures and financial statements | will be opt-in | — | kap.org.tr terms: **not yet reviewed** | — |
| User CSV | `inflation.py` | any monthly CPI series | `REALMARKET_CPI_CSV_<REGION>` | — | the user's own source | — |
| Fixture | `providers/fixture.py` | synthetic test data | `REALMARKET_PRICE_PROVIDER=fixture` | — | — | — |

FRED notice: *This product uses the FRED® API but is not endorsed or certified by the Federal
Reserve Bank of St. Louis.*

## To verify before the first public release

Items marked done were checked against the live services; the rest still need a reading of
the providers' current terms pages.

- [ ] Yahoo: the exact clause on automated or non-personal use; keep the provider opt-in.
- [ ] FRED: current API terms and the exact required notice wording.
- [x] FRED: JSON response format parsed in `providers/cpi.py` (verified live on 2026-09-25).
      `observations[].date` is `YYYY-MM-01`, `value` is a string; a month BLS did not publish is
      `"."` (October 2025 is missing in `CPIAUCNS`) and is skipped, never filled. The August 2026
      level, 334.980, matches the BLS CPI release (+3.4% over 12 months, not seasonally adjusted).
- [ ] EVDS: whether automated access is permitted and the required attribution.
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
- [ ] GDELT: verify the DOC 2.0 API JSON shape and plain-text error messages against the live
      API (`providers/gdelt.py` was written from the documentation), and the citation wording.
- [ ] KAP: read kap.org.tr's terms of use and robots.txt **before any KAP code is written**; KAP
      data is otherwise distributed through a licensed data-publishing service. Stop if the terms
      forbid automated access.
- [ ] Run `pip-licenses` on a clean `.[yahoo]` install (`frozendict`, pulled in by `yfinance`,
      is LGPL-3.0; acceptable as an optional, separately installed dependency).
