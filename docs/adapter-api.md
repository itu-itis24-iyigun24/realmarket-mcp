# Data adapter API, version 1

A data adapter lets realmarket use market data the operator is licensed to use (an exchange
feed, a data vendor, an internal database) instead of Yahoo Finance. The adapter is a small
HTTP service, in any language, that answers four JSON endpoints. realmarket validates every
response strictly; nothing is repaired or guessed. A runnable example that serves local files
is in [`examples/adapter/serve_files.py`](../examples/adapter/serve_files.py).

Configure realmarket with:

| Variable | Value |
|---|---|
| `REALMARKET_PRICE_PROVIDER` | `http` |
| `REALMARKET_HTTP_URL` | the adapter's base URL, e.g. `https://marketdata.internal/realmarket/v1` |
| `REALMARKET_HTTP_TOKEN` | optional; sent as `Authorization: Bearer <token>`, never logged or returned, and not sent on when the adapter redirects |

All endpoints are `GET` and return `application/json`. Dates are `YYYY-MM-DD`. Numbers are
JSON numbers (not strings); a value the source does not have is `null`, never `0` or `NaN`.
Return HTTP 404 for an unknown symbol or missing data; any other error status is reported to
the user as the adapter being unavailable.

## `GET /meta`

Describes the source. realmarket reads it once and caches it for an hour.

```json
{
  "api_version": 1,
  "name": "acme-feed",
  "attribution": "Source: ACME Market Data, licensed to Example Securities.",
  "gold_usd_symbol": "XAUUSD",
  "fx_symbol": "{base}{quote}",
  "benchmarks": {"TRY": "XU100"}
}
```

| Field | Required | Meaning |
|---|---|---|
| `api_version` | yes | `1` |
| `name` | yes | Short source name; every figure shows `adapter:<name>` as its `provider` |
| `attribution` | no | The credit line shown with every figure from this source |
| `gold_usd_symbol` | yes | Symbol of gold priced in US dollars per troy ounce |
| `fx_symbol` | yes | Pattern for exchange rates: units of `{quote}` per one `{base}` (e.g. `USDTRY` = TRY per USD) |
| `benchmarks` | no | Default index per currency, used by `get_event_reaction` |

## `GET /search?q=<text>&limit=<n>`

Assets whose symbol or name matches `q`, best match first, at most `limit`.

```json
{"assets": [
  {"symbol": "THYAO", "name": "Türk Hava Yolları A.O.", "asset_class": "equity",
   "currency": "TRY", "exchange": "BIST"}
]}
```

`asset_class` is one of `equity`, `index`, `fx`, `commodity`, `fund`, `crypto`, `other`.

## `GET /bars?symbol=<s>&start=<date>&end=<date>`

Daily bars for one symbol between two dates, inclusive, ascending by date, one bar per date.

```json
{
  "symbol": "THYAO",
  "currency": "TRY",
  "adjustment": "split_and_dividend",
  "bars": [
    {"date": "2026-09-24", "open": 290.0, "high": 295.0, "low": 288.0, "close": 292.0, "volume": 1000000},
    {"date": "2026-09-25", "open": 292.0, "high": 300.0, "low": 291.0, "close": null, "volume": 0}
  ]
}
```

- `symbol` must equal the requested symbol; `currency` is a 3-letter ISO code in the major
  unit: send pounds (`GBP`), not pence (`GBp`, `GBX`), and likewise `ZAR` and `ILS`.
- `adjustment` states the price policy of the series, e.g. `split_and_dividend` (total-return
  adjusted), `split` or `none`. It is shown with every figure; say what the feed really does.
- Do not include a bar for the current, unfinished session.
- Do not fill holidays with repeated prices. If the feed does, realmarket flags those bars as
  `placeholder_bars`.

## `GET /financials?symbol=<s>` (optional)

Financial statements, or 404 if the adapter does not serve them (realmarket then says so).

```json
{
  "currency": "TRY",
  "sector": "Industrials",
  "industry": "Airlines",
  "quarterly": [{"end": "2026-06-30", "values": {"revenue": 7205000000, "gross_profit": 458000000,
                 "operating_income": -88000000, "net_income": 198000000, "total_assets": null,
                 "total_equity": null, "total_debt": 19594000000}}],
  "annual": [{"end": "2025-12-31", "values": {"revenue": 26000000000}}]
}
```

An optional top-level `"shares_outstanding"` (all share classes, a positive number) lets
`get_valuation` compute market value from the adapter's own data.

An optional top-level `"ttm"` gives the trailing twelve months from the latest report:

```json
"ttm": {"end": "2026-06-30", "values": {"net_income": 29180000000, "revenue": 880000000000}}
```

For Turkish companies under TMS 29 (not banks) this is the only basis for P/E and P/S: this
year to date + the last fiscal year − the same period last year, the last two as restated in
the latest report, all in that report's money (the "son 12 ay" figure data vendors publish).
Without it, `get_valuation` gives market value and P/B for those companies but no P/E or P/S,
because summing quarters or using the last fiscal year gives materially wrong multiples.

Fields: `revenue`, `gross_profit`, `operating_income`, `net_income` (for the period) and
`total_assets`, `total_equity`, `total_debt` (at the period end), in `currency`, in full units.
Unknown fields are ignored. For Turkish companies other than banks, provide the figures as the
company reports them under TMS 29 (inflation accounting); realmarket applies the TMS 29 rules
to TRY reporters.

## Checking an adapter

```bash
python examples/adapter/serve_files.py --root tests/fixtures/basic --port 8765   # or your adapter
REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8765 realmarket-mcp
```

Then ask the client to run `check_setup` and `check_data_quality` on a few symbols. A response
that breaks this contract produces an error naming the endpoint and the problem.
