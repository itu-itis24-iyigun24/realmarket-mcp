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

## Choosing a local model

Tool use quality varies more between models than answer quality does. Before rolling out:

- test with the same questions used for realmarket's own checks (real return of a stock over
  three years, a monthly savings plan, a quarter's financial statements, "should I buy X?") and
  compare every figure in the answer with the tool result — the figures must match exactly;
- check that the model reports warning flags first and does not add figures of its own;
- smaller models tend to skip the tool and answer from memory. Keep the server instructions in
  the system prompt, and consider refusing to show an answer that cites no tool result.

## Configuration summary

| Variable | Purpose |
|---|---|
| `REALMARKET_PRICE_PROVIDER=http`, `REALMARKET_HTTP_URL`, `REALMARKET_HTTP_TOKEN` | the firm's data adapter |
| `REALMARKET_EVDS_API_KEY` | Turkish CPI (current) and TL deposit rates |
| `REALMARKET_SEC_CONTACT` | official US company statements (the firm's contact e-mail) |
| `REALMARKET_NEWS_PROVIDER=none` | turn off GDELT news if the firm uses its own news source |

`check_setup` reports what is configured, without showing values.

## Responsibilities that stay with the firm

- Licences for the market data it serves through the adapter, and the terms of every other
  source it enables (see the README's "Data sources, terms and privacy").
- The regulatory review of the product it offers to customers.
- Authentication, rate limiting and logging on its own gateway.

realmarket is Apache-2.0 licensed: it can be used, modified and offered commercially, with the
licence and notices kept.
