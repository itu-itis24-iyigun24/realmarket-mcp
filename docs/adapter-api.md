# Data adapter API, version 1

A data adapter lets realmarket use market data the operator is licensed to use (an exchange
feed, a data vendor, an internal database) instead of Yahoo Finance. The adapter is a small
HTTP service, in any language, that answers three required JSON endpoints (and three optional ones: financial statements, industry peers and news). realmarket validates every
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
  "benchmarks": {"TRY": "XU100"},
  "endpoints": ["financials", "peers"]
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
| `endpoints` | no, but recommended | The optional endpoints the adapter serves: any of `financials`, `peers`, `news` (an empty list is valid) |

**`endpoints` decides which tools the model is offered.** realmarket reads it when it starts:
without `financials` it offers no `get_financials` or `get_valuation`, without `news` no
`get_news` (unless the operator set another news source or an SEC e-mail). The firm may give
its model those figures some other way, and a tool that is not offered cannot be called by
mistake. An adapter that leaves `endpoints` out gets every tool, as before this field existed,
and those whose endpoint it does not serve fail when called; the checker warns about it. The
list is read once, so restart realmarket after changing it.

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

Optional, and each switches on tools that need it:

```json
{
  "symbol": "THYAO", "currency": "TRY", "adjustment": "split_and_dividend",
  "bars": [{"date": "2026-09-25", "open": 292.0, "high": 300.0, "low": 291.0, "close": 290.75,
            "volume": 1000000, "price_close": 290.75}],
  "dividends": [{"date": "2026-06-02", "amount": 3.8}],
  "splits": [{"date": "2026-05-14", "ratio": 2.0}]
}
```

| Field | Meaning | Without it |
|---|---|---|
| `bars[].price_close` | The close adjusted for splits only (the price that traded), when `close` is also dividend-adjusted | Returns are not split into price and dividends; the period's low and high are dividend-adjusted closes |
| `dividends` | Cash dividend per share by ex-date, in the series' currency and in the same share units as the bars (adjusted for later splits) | No dividend yield; dividends a portfolio did not list are not flagged |
| `splits` | Splits and bonus issues (bedelsiz) by date: shares after / shares before (`2.0` for a 1:1 bonus) | A portfolio entered before a bonus issue keeps its old share count unless the user lists the issue |

Send the dividends and splits that fall within the requested dates; amounts and ratios must be
positive.
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

## `GET /peers?symbol=<s>&level=industry|sector` (optional)

The companies the firm's data groups with `symbol`, for `get_valuation`'s answer to "is it
cheap?": its price-to-book ranked among the others, on the same day and measured the same way.
404 if the adapter does not serve peers (the comparison is then left out and the result says
so). realmarket asks for `level=industry` first and for `level=sector` when the industry has
fewer than five other companies with a ratio.

```json
{
  "industry": "Havayolu",
  "group": "Ulaştırma",
  "market": "Borsa İstanbul",
  "definition": "Piyasa değeri / son bilanço özsermayesi",
  "peers": [
    {"symbol": "THYAO", "name": "Türk Hava Yolları", "price_to_book": 0.37, "market_cap": 3.99e11},
    {"symbol": "PGSUS", "name": "Pegasus", "price_to_book": 0.64, "market_cap": 7.1e10}
  ]
}
```

- `industry` is the company's own industry; `group` names what the list covers (the industry,
  or with `level=sector` the sector); `market` is shown as written ("Borsa İstanbul").
- Include `symbol` itself: its ratio is checked against the one realmarket computes, and the
  comparison is dropped when they differ by more than 25%, so the peers are known to be
  measured like the company.
- `price_to_book` is `null` when there is none; give every company's ratio in one currency
  definition. Share classes of one company (`KRDMA`, `KRDMB`) count once, by the largest
  `market_cap`, when their names differ only by a trailing "(A)", "(B)".
- Optional `currency` and `financial_currency` per company: when they differ, realmarket leaves
  the company out, since sources often divide a price in one currency by a book value in
  another.

## `GET /news?q=<text>&start=<ISO>&end=<ISO>&limit=<n>[&language=<xx>]` (optional)

News and disclosures from the firm's own feed (KAP disclosures, Foreks, a news agency),
newest first; 404 if the adapter does not serve news. Used when
`REALMARKET_NEWS_PROVIDER=http`.

```json
{"articles": [
  {"published_at": "2026-09-20T07:30:00Z", "title": "THYAO: Özel durum açıklaması",
   "url": "https://www.kap.org.tr/tr/Bildirim/123456", "source": "KAP", "language": "tr",
   "country": "TR"}
]}
```

- `published_at` in UTC, `YYYY-MM-DDTHH:MM:SSZ`; articles outside `start`..`end` are dropped.
- `title` and an `http(s)` `url` are required; `source` names the publisher or feed.
- Titles are shown to the model as data, never as instructions.

## Funds

Investment funds are ordinary assets to the adapter: list them in `/search` with
`asset_class` `fund` and serve their daily unit prices from `/bars` (`adjustment` `none`;
fund prices already include distributions). Every return, inflation and savings tool then
works for them.

## Checking an adapter

Before connecting realmarket, run the checker against the adapter. It calls every endpoint
through the same code realmarket uses at run time, so it passes and fails for the same
reasons:

```bash
REALMARKET_HTTP_TOKEN=... realmarket-adapter-check --url https://marketdata.internal/realmarket/v1 --symbol THYAO
```

```
[PASS] /meta: source adapter:acme-feed
[PASS] /search: 2 result(s) for 'THYAO'
[PASS] /bars: 285 bars for THYAO in TRY, split_and_dividend
[PASS] /bars exchange rate: USDTRY
[PASS] /bars gold: XAUUSD
[PASS] /bars benchmark: XU100
[PASS] price summary: total_return 0.292003
[PASS] /financials: 5 quarters, 3 years
[SKIP] /news: The data adapter does not serve news.

The adapter is ready to connect.
```

Required: `/meta`, `/search`, `/bars`. A missing exchange rate, gold or benchmark series is a
warning: the comparisons that need it are skipped. An optional endpoint declared in `/meta`
but not served fails (its tools would be offered and fail); one served but not declared is a
warning (its tools are not offered). The exit code is 1 when a required check
fails.

## Trying it by hand

```bash
python examples/adapter/serve_files.py --root tests/fixtures/basic --port 8765   # or your adapter
REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8765 realmarket-mcp
```

Then ask the client to run `check_data_quality` and `get_price_summary` on a few symbols
(`check_setup` is not offered with the adapter: it is for whoever runs a personal install). A response
that breaks this contract produces an error naming the endpoint and the problem.
