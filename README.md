# realmarket-mcp

An open-source [Model Context Protocol](https://modelcontextprotocol.io) server that lets
Claude and other LLMs research markets from **verified, sourced numbers**.

> **Status: pre-alpha.** The response contract and development tooling are in place; no tool
> is usable yet. See [`docs/design.md`](docs/design.md) for the plan.

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

Planned tools for v0.1: `search_assets`, `get_price_summary`, `check_data_quality`,
`compare_assets`, `compare_real_return`, plus report prompt templates.

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
