# realmarket-mcp

An open-source [Model Context Protocol](https://modelcontextprotocol.io) server that lets
Claude and other LLMs research markets from **verified, sourced numbers**.

> **Status: alpha (MVP).** Price, real-return and data-quality tools are verified against the
> live Yahoo, FRED and TCMB EVDS APIs. News search (GDELT) is new and not yet live-verified;
> KAP company disclosures are not included (KAP's terms require
> MKK's written permission); use it alongside [kapmcp](#using-it-with-kapmcp-kap-disclosures-and-financial-statements) for those.

## Why

Ask an LLM how an asset performed and it will often answer from memory or estimate. For
anyone saving in a high-inflation currency, the next question — *did it actually beat
inflation?* — is even harder to answer reliably. realmarket-mcp gives the model tools that
compute these figures in code and return them with their sources:

- **Real returns**: nominal return vs. inflation in the asset's own currency, and the same
  return measured in US dollars and in gold.
- **Data-quality checks**: gaps, split and redenomination seams, placeholder bars — flagged
  next to the numbers they affect, never silently "fixed".
- **Provenance on every number**: provider, period, retrieval time and a content hash of the
  exact data used.
- **Deterministic results**: the same data and arguments give the same answer, whichever
  model asks.

## Tools

| Tool | What it answers |
|---|---|
| `search_assets` | "What is the symbol for Turkish Airlines?" |
| `get_price_summary` | "How did it do over the last year?" — return, annualized return, volatility, max drawdown |
| `compare_real_return` | "Did it beat inflation?" — nominal vs real return, plus the same holding in US dollars and in gold |
| `compare_assets` | "How do these compare?" — 2 to 10 assets over one common window |
| `check_data_quality` | "Can I trust this data?" — gaps, placeholder bars, suspicious jumps, stale data |
| `portfolio_real_return` | "Did my savings keep up with inflation?" — dated purchases valued today, money-weighted return, real return, and the same payments replayed into USD, gold or an index |
| `get_event_reaction` | "How did the stock react to that announcement?" — 1/5/20-session return vs the index, plus pre-event drift |
| `get_news` | "What was in the news about it?" — recent article listings with publisher, date and link |

It also ships three report prompts (`single_asset_report`, `real_return_report`,
`comparison_report`) and a `realmarket://methodology` resource with every formula.

## Install

Requires Python 3.11+.

```bash
pip install "realmarket-mcp[yahoo] @ git+https://github.com/itu-itis24-iyigun24/realmarket-mcp"
```

## Configure a client

All configuration is environment variables in the client's MCP server entry. Example for
Claude Desktop (`claude_desktop_config.json`) or any client using the same format:

```json
{
  "mcpServers": {
    "realmarket": {
      "command": "realmarket-mcp",
      "env": {
        "REALMARKET_PRICE_PROVIDER": "yahoo",
        "REALMARKET_EVDS_API_KEY": "your-tcmb-evds-key",
        "REALMARKET_FRED_API_KEY": "your-fred-key"
      }
    }
  }
}
```

For Claude Code: `claude mcp add realmarket -e REALMARKET_PRICE_PROVIDER=yahoo -- realmarket-mcp`.

| Variable | Purpose |
|---|---|
| `REALMARKET_PRICE_PROVIDER` | `yahoo`, or `fixture` for offline test data |
| `REALMARKET_EVDS_API_KEY` | *Optional.* Turkish CPI from TCMB EVDS, the most current source (free key at evds3.tcmb.gov.tr) |
| `REALMARKET_FRED_API_KEY` | *Optional.* US CPI through the FRED API (free key at fred.stlouisfed.org) |
| `REALMARKET_CPI_CSV_<REGION>` | Your own monthly CPI file for any region (`month,cpi_index`), e.g. `REALMARKET_CPI_CSV_TR` |
| `REALMARKET_NEWS_PROVIDER` | `gdelt` (default, free, no key) or `none` |
| `REALMARKET_FIXTURE_DIR` | Directory for the `fixture` provider |

**No key is required.** Without keys, inflation comes from FRED's public CSV (US) and the OECD
(Türkiye and other OECD members). The OECD's Türkiye series currently ends at 2025-12, so
without an EVDS key Turkish real returns stop there and say so; set the EVDS key for current data.

### About the Yahoo Finance provider

`yahoo` uses the community [`yfinance`](https://github.com/ranaroussi/yfinance) library, which
reads Yahoo Finance's public web endpoints. It is **not an official API**: Yahoo's terms
restrict automated and commercial use, the endpoints change without notice, and some
histories contain errors (which is why `check_data_quality` exists). realmarket-mcp is not
affiliated with or endorsed by Yahoo; Yahoo is a trademark of its owner. The provider is off
unless you select it, is meant for personal research use, and you are responsible for
complying with Yahoo's terms and for not redistributing the data. Data may be delayed or
wrong, and the interface may break without notice. Symbols follow Yahoo's conventions:
`THYAO.IS` (Borsa Istanbul), `XU100.IS`, `USDTRY=X`, `GC=F` (gold).

### CPI sources

| Region | Without a key | With a key |
|---|---|---|
| Türkiye | OECD (matches TÜİK; currently ends 2025-12) | TCMB EVDS (current) |
| United States | FRED public CSV (current) | FRED API (same data) |
| Other OECD members (e.g. DE, GB) | OECD (current where published) | — |
| Anything else | `REALMARKET_CPI_CSV_<REGION>` | — |

Use of FRED, the OECD and EVDS is subject to their terms. This product uses the FRED® API but is
not endorsed or certified by the Federal Reserve Bank of St. Louis. Turkish CPI is published by
TÜİK. See [`docs/providers.md`](docs/providers.md).

## Using it with kapmcp (KAP disclosures and financial statements)

realmarket-mcp does not read KAP, Turkey's Public Disclosure Platform: KAP's terms require MKK's
written permission for automated use (see [`docs/providers.md`](docs/providers.md)). The
independent open-source project [kapmcp](https://github.com/hasancagrigungor/kapmcp)
(`pip install kap-mcp-server`) covers KAP through MKK's official API. MCP clients can run
several servers at once, so the two can be used side by side and the model picks tools from
both.

| Question | Served by |
|---|---|
| Company disclosures, attachments, official financial statements, corporate actions | kapmcp |
| Nominal vs inflation-adjusted return; the same holding in US dollars and in gold | realmarket-mcp |
| "Can I trust this price history?" (seams, gaps, placeholder bars) | realmarket-mcp |
| Recent news coverage with publisher, date and link | either (kapmcp via Yahoo, realmarket-mcp via GDELT) |

Example configuration with both servers:

```json
{
  "mcpServers": {
    "realmarket": {
      "command": "realmarket-mcp",
      "env": {
        "REALMARKET_PRICE_PROVIDER": "yahoo",
        "REALMARKET_EVDS_API_KEY": "your-tcmb-evds-key",
        "REALMARKET_FRED_API_KEY": "your-fred-key"
      }
    },
    "kap": {
      "command": "kapmcp",
      "env": { "KAP_API_KEY": "your-mkk-api-key" }
    }
  }
}
```

Example request that uses both: *"Summarize THYAO's latest financial report from KAP, then tell
me whether the stock beat Turkish inflation over the last three years, also in dollars and gold.
Flag any data-quality issues first."*

Notes:

- kapmcp is a separate project with its own maintainer and license (MIT); realmarket-mcp is not
  affiliated with it and has not audited it. Check its documentation for current setup.
- Its KAP tools need an API key from the [MKK API Portal](https://apiportal.mkk.com.tr) and an
  IP authorization on MKK's side; read MKK's conditions when you apply. Without a key, its
  Yahoo-based tools still work.
- When two servers offer similar tools (both can report prices), say which one you want if the
  answer matters, e.g. "use realmarket for the real return".

## Example questions

- "Did THYAO beat Turkish inflation over the last 5 years? Also in dollars and gold."
- "Compare BIST 100, gold and the S&P 500 over the last 3 years."
- "Is the price history of ASELS reliable since 2015?"

## What it is not

- **Not investment advice.** It measures and compares; it never tells you what to buy or sell.
- **Not a data service.** It ships no market data. It runs on your machine and fetches data
  from providers under your own access; you are responsible for each provider's terms.
- **Not a trading bot** and not a price-prediction tool.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python -m mypy
```

The repository includes Claude Code development agents, skills and hooks under `.claude/`;
see [`CLAUDE.md`](CLAUDE.md).

## License

[Apache-2.0](LICENSE).
