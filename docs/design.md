# realmarket-mcp design

Status: **M0 — foundations.** No tool is implemented yet. This document is the plan the
first milestones are built against; change it in the same commit as the code that departs from it.

## Purpose

An open-source [Model Context Protocol](https://modelcontextprotocol.io) server that lets
Claude, or any MCP-capable LLM client, research markets and write reports from **verified,
sourced numbers** instead of numbers the model recalls or estimates.

It answers questions such as:

- How did this asset do over a period, and what was its worst drawdown?
- Did it beat inflation in its own currency? In US dollars? Against gold?
- How do these three assets compare over the same window?
- Can the data behind these numbers be trusted? (gaps, split seams, placeholder bars)

## Non-goals

- **No advice.** No buy/sell/hold signals, price targets, or return promises. Tools measure and
  compare; the user decides.
- **No hosted service and no bundled data.** The server runs on the user's machine and fetches
  data from providers under the user's own access. The project ships code only.
- **No return prediction.** Forecasting was explored at length in the author's earlier research
  project and did not survive honest evaluation; it is out of scope here.
- **No order execution** or brokerage integration.

## Principles

1. **Compute in code, interpret in the model.** Tools return finished figures (returns,
   drawdowns, real returns), never raw data the model must crunch.
2. **Every number is sourced.** Each result cites provider, dataset, period, retrieval time and
   a content hash of the exact data used (`Provenance`).
3. **Surface data problems; never silently repair them.** Gaps, seams and suspicious moves are
   returned as `QualityFlag`s next to the numbers they affect.
4. **Deterministic.** Same data version + same arguments = byte-identical result, whichever LLM
   is calling.
5. **Provider-agnostic.** Sources are plug-ins behind one interface; no tool names a provider.
6. **Offline tests.** The suite never touches the network (`tests/conftest.py`).

The binding response shape is in [`tool-contract.md`](tool-contract.md), implemented in
`src/realmarket_mcp/contract.py`.

## Architecture

```
 LLM client (Claude Desktop, Claude Code, other MCP clients)
        │  MCP (stdio first; streamable HTTP later)
 ┌──────▼───────────────────────────────────────────────┐
 │ server      tool + prompt + resource registration    │
 ├──────────────────────────────────────────────────────┤
 │ tools       argument validation → calculation →      │
 │             ToolResult / ToolError (contract.py)     │
 ├──────────────────────────────────────────────────────┤
 │ analytics   pure functions: returns, drawdown,       │
 │             volatility, real return, FX conversion   │
 ├──────────────────────────────────────────────────────┤
 │ quality     gap / seam / placeholder-bar detection   │
 ├──────────────────────────────────────────────────────┤
 │ store       normalized series + local cache,         │
 │             keyed by data_version (SHA-256)          │
 ├──────────────────────────────────────────────────────┤
 │ providers   the only network code: prices, FX, CPI   │
 └──────────────────────────────────────────────────────┘
```

### Provider interface (sketch)

```python
class PriceProvider(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[AssetRef]: ...
    def daily_bars(self, symbol: str, start: date, end: date) -> RawBars: ...


class CpiProvider(Protocol):
    name: str
    regions: frozenset[str]  # e.g. {"TR"}, {"US"}, {"EA"}

    def monthly_index(self, region: str, start: date, end: date) -> RawSeries: ...
```

Providers return raw payloads; the store normalizes them (session date, OHLC, volume,
currency, adjustment policy) and computes `data_version`. API keys come only from environment
variables named `REALMARKET_<PROVIDER>_API_KEY`.

## v0.1 scope

**Assets:** equities and indices, FX pairs, gold. **Inflation:** Turkey (TÜFE), United States
(CPI), euro area (HICP).

| Tool | Purpose | Milestone |
|---|---|---|
| `search_assets` | Resolve a name or ticker to canonical symbols, with exchange and currency | M1 |
| `get_price_summary` | Period return, annualized return, volatility, max drawdown, data coverage | M1 |
| `check_data_quality` | Gaps, split/redenomination seams, zero-volume placeholder bars, stale latest bar | M2 |
| `compare_assets` | The summary metrics side by side for 2–10 assets on one aligned calendar | M2 |
| `compare_real_return` | Nominal vs inflation-adjusted return, and the same return measured in USD and in gold | M3 |

**Prompts** (MCP prompt templates the user picks in their client): `single_asset_report`,
`real_return_report`, `comparison_report`. Each tells the model which tools to call, to cite
provenance, to state quality flags before conclusions, and to avoid advice language.

**Resources:** `realmarket://methodology` (how every metric is computed, with formulas) and
`realmarket://providers` (active providers and their terms links).

### Candidate providers

To be confirmed by the `compliance-reviewer` agent against each provider's current terms
before implementation; nothing below is a claim about those terms yet.

| Data | Candidates |
|---|---|
| Prices | a keyed provider with explicit API terms (default), Yahoo Finance via `yfinance` (opt-in only, unofficial) |
| FX, gold | central-bank reference rates, the price provider |
| CPI | TCMB EVDS (TR), FRED (US), ECB Data Portal (euro area) |

## Porting from the research repository

The author's private `trading` repository holds tested code worth reusing. Port by copying and
adapting (English names, no pandas where plain Python suffices), with its tests, never by
importing that repository.

| Source (`trading/src/trading_ai/…`) | Lines | Becomes | Why |
|---|---|---|---|
| `data/normalize.py` | 222 | `store/normalize.py` | OHLC validation with bounded float tolerance, explicit adjustment policy |
| `continuity.py` | 198 | `quality/continuity.py` | gap and seam detection proven on real provider corruption |
| `data/inflation.py` | 69 | `analytics/inflation.py` | monthly CPI real return and real CAGR |
| `data/providers.py` | 139 | `providers/base.py` | provider protocol and fixture providers |
| `evaluation/trading_metrics.py` | 88 | `analytics/metrics.py` | return, drawdown and risk metrics |
| `data/raw_store.py` | 98 | `store/raw.py` | immutable, hash-versioned raw snapshots |

Not ported: the walk-forward research stack, models, ledger, experiment evaluators and the
legacy backtest engine. They answer a different question (prediction) than this project asks.

## Milestones

- **M0 — foundations (done):** license, packaging, response contract with tests, offline test
  guard, Claude Code development agents, skills and hooks.
- **M1 — first tool end to end:** pin the MCP Python SDK, stdio server, `search_assets` and
  `get_price_summary` against a fixture provider, one real price provider.
- **M2 — trust:** port normalization and continuity checks, `check_data_quality`,
  `compare_assets`, local cache.
- **M3 — real returns:** CPI providers, `compare_real_return`, report prompts, methodology resource.
- **M4 — release:** PyPI package, install docs for common MCP clients, CI, public repository.

## Open questions

- Default price provider: which keyed provider offers acceptable terms and BIST coverage?
- Cache location and eviction policy on the user's machine.
- Whether to add streamable-HTTP transport in v0.1 or defer it.
