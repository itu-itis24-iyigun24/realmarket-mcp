# Tool contract

Every realmarket-mcp tool follows this contract so that any LLM, calling any tool, gets the
same predictable shape. The executable version is `src/realmarket_mcp/contract.py`; where this
document and the code disagree, the code wins and this document is fixed.

Contract version: **1**.

## 1. Naming and descriptions

- Tool names are `verb_noun`, snake_case: `get_price_summary`, `compare_assets`.
- A description states, in order: what the tool returns; when to use it; when **not** to use it
  and which tool to use instead; limits (maximum period, series length). Three to six sentences.
- No provider names, no marketing words, no advice verbs ("buy", "sell", "should").

## 2. Arguments

| Kind | Convention | Example |
|---|---|---|
| Dates | ISO-8601 calendar date | `"2024-01-31"` |
| Periods | explicit `start`/`end`, or an enum shortcut | `"1y"`, `"5y"`, `"ytd"`, `"max"` |
| Symbols | canonical symbols returned by `search_assets` | `"THYAO.IS"` |
| Currencies | ISO-4217 code | `"TRY"`, `"USD"` |
| Inflation regions | short code | `"TR"`, `"US"`, `"EA"` |
| Choices | enums, never free text | `"frequency": "monthly"` |

Keep arguments few; give every optional argument a documented default.

## 3. Success envelope

```json
{
  "ok": true,
  "contract_version": "1",
  "tool": "get_price_summary",
  "data": {
    "symbol": "THYAO.IS",
    "currency": "TRY",
    "total_return": 0.4312,
    "annualized_return": 0.1964,
    "max_drawdown": -0.2875,
    "sessions": 498,
    "first_close": null
  },
  "provenance": [
    {
      "provider": "example",
      "dataset": "daily_ohlc",
      "symbols": ["THYAO.IS"],
      "period_start": "2023-01-02",
      "period_end": "2024-12-31",
      "retrieved_at": "2025-01-02T08:15:00Z",
      "data_version": "sha256:9f2c…",
      "adjustment": "split_and_dividend"
    }
  ],
  "quality_flags": [
    {
      "code": "gap",
      "severity": "warning",
      "message": "No bars for 12 consecutive calendar days.",
      "affected": ["2024-04-08", "2024-04-19"]
    }
  ],
  "notes": ["Returns are simple returns on adjusted closes."],
  "disclaimer": "Informational research output …"
}
```

Rules, enforced by `contract.py`:

- **Ratios are fractions:** `0.1964` means 19.64%. Units are stated in the description.
- **Missing is `null`.** `NaN` and `Infinity` are refused; a tool may not fill gaps with `0`.
- **At least one `provenance` entry.** `data_version` identifies the exact data used.
- **Bounded size:** no list longer than `MAX_SERIES_POINTS` (500). Tools downsample or
  paginate and say so in `notes`.
- **Quality flags come with the numbers they affect.** Severity `critical` means the figure
  should not be relied on; clients are told (in prompts) to state such flags first.
- **Disclaimer on every success.**

## 4. Error envelope

```json
{
  "ok": false,
  "contract_version": "1",
  "error": {
    "code": "unknown_symbol",
    "message": "No asset matches 'THYAO'.",
    "hint": "Call search_assets with the company name and use a returned symbol.",
    "retryable": false,
    "details": {"query": "THYAO"}
  }
}
```

| Code | Meaning | Retryable |
|---|---|---|
| `invalid_argument` | an argument is malformed or out of range | no |
| `unknown_symbol` | the symbol does not resolve | no |
| `no_data_in_range` | the symbol exists but has no data in the period | no |
| `missing_api_key` | the provider needs a key the user has not set | no |
| `provider_unavailable` | the provider failed or timed out | yes |
| `rate_limited` | the provider's rate limit was hit | yes |
| `unsupported` | valid request this server cannot serve (e.g. region without CPI source) | no |
| `internal` | a bug in realmarket-mcp | no |

Every error carries a `hint` that tells the caller the next concrete step — the call to make,
the variable to set, the range to try. A hint of "try again later" is only acceptable for
retryable codes.

## 5. Determinism and caching

- Results depend only on arguments and the data version. No wall-clock values in `data`;
  `retrieved_at` lives in provenance.
- Dictionary keys and list orders are stable (symbols in request order, dates ascending).

## 6. Versioning

Adding an optional argument or a new key in `data` is compatible. Renaming or removing a tool,
an argument or a key, or changing a unit, is breaking: it bumps `CONTRACT_VERSION` and is noted
in the changelog.
