# Integrating realmarket in a firm's own AI assistant

This guide is for a brokerage, bank, asset manager or fintech that wants to offer its customers
an AI assistant for market research, using its own licensed data and its own language model.

## What realmarket provides

realmarket is the calculation and verification layer between the model and the data:

- figures computed in code, never by the model: returns, real (inflation-adjusted) returns,
  returns in US dollars and gold, a TL deposit comparison, money-weighted savings returns,
  event reactions, financial-statement growth including Turkish inflation accounting (TMS 29);
- provenance on every figure (source, period, retrieval time, a hash of the exact data used)
  and the credit line the source requires;
- data-quality flags placed next to the figures they affect (gaps, split seams, placeholder
  bars, stale data, statements that do not reconcile);
- descriptive language only: the tools and their instructions never produce buy, sell or hold
  recommendations, which matters for investment-advice regulation (SPK in Türkiye).

The firm provides the data (through an adapter), the model, and the customer-facing product.

## Architecture

```
customer ─ firm's app ─ firm's LLM ─ MCP client ─ realmarket (MCP server) ─┬─ data adapter ─ licensed feed
                                                                          ├─ TCMB EVDS (CPI, deposit rates)
                                                                          ├─ SEC EDGAR / ESEF (official statements)
                                                                          └─ GDELT (news listings; optional)
```

1. **Data adapter.** A small HTTP service over the firm's licensed prices and, optionally,
   financial statements. Specification: [`adapter-api.md`](adapter-api.md); a working
   example: `examples/adapter/serve_files.py`. Set `REALMARKET_PRICE_PROVIDER=http` and
   `REALMARKET_HTTP_URL`. Yahoo is then not used at all.
2. **realmarket server.** Run it centrally with the Streamable HTTP transport:

   ```bash
   realmarket-mcp --transport http --host 127.0.0.1 --port 8000     # endpoint: /mcp
   ```

   The endpoint has no authentication of its own. Keep it on an internal interface and put it
   behind the firm's API gateway, which authenticates the application calling it.
3. **Model and MCP client.** Any model that supports tool calling can use realmarket through an
   MCP client; the server is not tied to Claude. The server sends usage instructions at
   connection time (cite provenance, lead with quality flags, no recommendations) and ships
   three report prompts; keep them in the model's context.

## Qualifying a local model

realmarket guarantees its own figures, not what a model does with them, and tool use varies
more between models than answer quality does. `realmarket-qualify` tests a model before it
answers customers. It works with any server that offers an OpenAI-compatible
`/chat/completions` endpoint with tool calling (Ollama, vLLM, LM Studio, a hosted API):

```bash
realmarket-qualify --base-url http://localhost:11434/v1 --model qwen2.5:14b --output report.json
```

It asks the model a fixed set of Turkish questions with realmarket's own tools and server
instructions, about a synthetic, fictional company (ORNEK) generated on the fly. No market
data, API keys or network access other than the model server is needed, and every firm runs
the same questions. Each answer is checked automatically:

| Check | Fails when |
|---|---|
| `tools_used` | the model answered from memory instead of calling the tool the question needs |
| `figure:<field>` | the key figure the tool returned (e.g. the real return) is not in the answer |
| `no_unsupported_figures` | the answer contains a figure found in no tool result: invented, miscalculated, or a ratio the tool deliberately withheld (a P/E computed from other figures) |
| `no_advice` | the answer recommends buying, selling or holding |

Numbers are read in Turkish and English style (`1.234,5` / `1,234.5`), percentages are matched
to the tool's fractions, and amounts in thousands, millions or billions to the full figures.
The checks are strict on purpose: treat a failure as an answer a person must read. The exit
code is 0 when every case passes, 1 when any fails and 2 when the model server cannot be
reached; `--output` writes every question, tool call and answer as JSON.

`--live --cases firm-cases.json` runs the firm's own questions against its configured sources
(its adapter); the file is a JSON list of `{"id", "question", "expect_tools": [...],
"expect_figures": [{"tool", "path", "label"}]}`. `--api-key-env NAME` reads the model
server's key from that environment variable. Keep the server instructions in the model's
system prompt in production too; the test uses them.

## Configuration summary

| Variable | Purpose |
|---|---|
| `REALMARKET_PRICE_PROVIDER=http`, `REALMARKET_HTTP_URL`, `REALMARKET_HTTP_TOKEN` | the firm's data adapter |
| `REALMARKET_EVDS_API_KEY` | Turkish CPI (current) and TL deposit rates |
| `REALMARKET_SEC_CONTACT` | official US company statements (the firm's contact e-mail) |
| `REALMARKET_NEWS_PROVIDER=none` | turn off GDELT news if the firm uses its own news source |
| `REALMARKET_AUDIT_LOG=/var/log/realmarket/audit.jsonl` | audit log, one line per tool call (below) |
| `REALMARKET_AUDIT_FULL=1` | also store each full response in the audit log |

`realmarket-qualify` (below) tests the firm's model before rollout.

`check_setup` reports what is configured, without showing values.

## Audit log

With `REALMARKET_AUDIT_LOG` set, every tool call appends one JSON line to that file on the
firm's own server, so the firm can show afterwards what the assistant was given:

```json
{"time": "2026-09-27T12:00:03.114Z", "server_version": "0.1.4", "tool": "get_valuation",
 "arguments": {"symbol": "BIMAS.IS", "price_symbol": null}, "outcome": "ok", "error_code": null,
 "duration_ms": 842.6,
 "provenance": [{"provider": "adapter:acme-feed", "dataset": "daily_bars", "symbols": ["BIMAS.IS"],
   "period_start": "2026-09-06", "period_end": "2026-09-25", "retrieved_at": "2026-09-27T12:00:02Z",
   "data_version": "sha256:…"}, …],
 "quality_flags": ["warning:no_tms29_trailing_earnings"],
 "response_sha256": "…"}
```

- `arguments` are the tool's own parameters with defaults filled in, so the call can be
  repeated; `data_version` identifies the exact data each figure came from.
- `response_sha256` is the SHA-256 of the exact response text the model received. If the
  firm's application also stores the response, the two can be matched.
- `REALMARKET_AUDIT_FULL=1` stores the full response as well.
- Settings, API keys and tokens are never written. Arguments can contain a customer's
  portfolio amounts: retention, access control and rotation of the file are the firm's.
- If the file cannot be written (path, permissions, disk), the tool returns an error instead
  of answering unlogged. `check_setup` reports whether the log is on.
- The log records what the tools returned, not what the model then wrote to the customer;
  the firm's application should keep the final answer next to it.

## Responsibilities that stay with the firm

- Licences for the market data it serves through the adapter, and the terms of every other
  source it enables (see the README's "Data sources, terms and privacy").
- The regulatory review of the product it offers to customers.
- Authentication, rate limiting and logging on its own gateway.

realmarket is Apache-2.0 licensed: it can be used, modified and offered commercially, with the
licence and notices kept.
