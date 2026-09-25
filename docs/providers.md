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
| TCMB EVDS (Central Bank of the Republic of Türkiye) | `providers/cpi.py` | Turkish CPI `TP.FG.J0` (source: TÜİK) | `REALMARKET_EVDS_API_KEY` | yes, free | EVDS terms of use | cite TCMB EVDS / TÜİK |
| User CSV | `inflation.py` | any monthly CPI series | `REALMARKET_CPI_CSV_<REGION>` | — | the user's own source | — |
| Fixture | `providers/fixture.py` | synthetic test data | `REALMARKET_PRICE_PROVIDER=fixture` | — | — | — |

FRED notice: *This product uses the FRED® API but is not endorsed or certified by the Federal
Reserve Bank of St. Louis.*

## To verify before the first public release

These points were reviewed without network access and must be checked against the live pages:

- [ ] Yahoo: the exact clause on automated or non-personal use; keep the provider opt-in.
- [ ] FRED: current API terms and the exact required notice wording.
- [ ] EVDS: whether automated access is permitted, the required attribution, and the JSON
      response format parsed in `providers/cpi.py`. The API base URL was verified on 2026-09-25:
      `https://evds3.tcmb.gov.tr/igmevdsms-dis/` (evds2 now redirects to evds3).
- [ ] Run `pip-licenses` on a clean `.[yahoo]` install (`frozendict`, pulled in by `yfinance`,
      is LGPL-3.0; acceptable as an optional, separately installed dependency).
