---
name: model-check
description: Check how a small model (Haiku) answers customer questions with realmarket's tools, using Claude Code subagents instead of packaging a Claude Desktop extension. Use after any change to tool descriptions, result fields, notes or server instructions, and before tagging a release.
---

# Checking a small model against the tools

A brokerage's app runs a model with realmarket's tools and no web search. The weakest model a
firm might use is the best test: if Haiku answers correctly, larger models do too. This check
runs Haiku as a Claude Code subagent (covered by the Claude subscription, no API key) that
reaches the tools through `scripts/call_tool.py`, which prints exactly what an MCP client
receives.

It complements `realmarket-qualify` (scripted checks against any OpenAI-compatible model):
qualify scores answers automatically; this check shows real answers to real questions, on
real data, and is where most tool-description problems have been found.

## Steps

1. **Pick the data.** Live questions (real symbols) need `REALMARKET_PRICE_PROVIDER=yahoo` in
   the environment the script runs in, and `REALMARKET_EVDS_API_KEY` for inflation, deposit and
   house-price questions. Offline, use `--synthetic` and ask about the fictional ORNEK.

2. **Work out the expected figures yourself first**, by calling the tools directly with
   `python scripts/call_tool.py call ...`. Check them by hand (e.g. traded prices before a split
   are the pre-split prices). Never judge an answer against a figure you have not verified.

3. **Spawn one subagent per question, in parallel**, with `model: "haiku"`, using the prompt
   below. Keep the prompt neutral: it must not hint at the right tool or the pitfalls, or the
   check measures the prompt instead of the tools.

4. **Judge each answer** against the checklist, then fix the cause in the tools (description,
   field order, notes, a data field the model reads), never by steering the prompt. Re-run the
   same questions after the fix.

## Subagent prompt

Replace `<QUESTION>` and `<TODAY>`; add `--synthetic` after `call_tool.py` in both commands
for ORNEK questions.

```
You are the AI assistant inside a Turkish brokerage's mobile app. A customer asks you a
question. Your ONLY source of market data is the realmarket toolset, which you call through
Bash. Do not use web search, web fetch, or your own memory for any figure.

How to use the tools (run from the repository root):
- First read the tool list and the server instructions: `python scripts/call_tool.py tools`
- Call a tool: `python scripts/call_tool.py call <tool_name> '<json arguments>'`
Follow the server instructions exactly as if they were your own. Do not read or modify any
source files.

Today is <TODAY>. The customer's question:
"<QUESTION>"

Your final message must contain two parts:
1. TOOL CALLS: every tool call you made, with its arguments, one line each.
2. ANSWER: exactly the Turkish answer the customer would see in the app, nothing else.
```

## Standard questions

Run these at least; add ones that exercise whatever changed.

| Question | Tool expected | Watch for |
|---|---|---|
| Mart 2024'te 100 THYAO, Haziran 2024'te 50 BIMAS aldım, Eylül 2025'te 30 THYAO sattım. Portföyüm nasıl? | `analyze_portfolio`, called without asking for prices | BIMAS 100 shares (2:1 bonus 2026-05-14); per-holding totals include shares sold; total return is `totals.total_return_on_purchases`; dividend warning |
| THYAO bugün neden yükseldi? | `explain_price_move` | the session's own date, not "today" on a weekend; no causes, not even hedged ("olabilir"); no split into market and company parts |
| THYAO 2023 başından beri enflasyonu yendi mi? | `compare_real_return` | real return reported, not computed by the model |
| ASELS'in F/K oranı nedir? | `get_valuation` | no P/E computed by the model when the tool gives none |
| THYAO almalı mıyım? | none, or data only | no buy, sell or hold wording |

## Checklist for every answer

- The expected tool was called, with what the user gave (no questions back for prices, days
  or fees).
- Every figure appears in a tool result, unchanged apart from rounding and formatting. A
  percentage the model computed itself is a failure, even when correct.
- Warning and critical quality flags are stated.
- Dates name the window or session the figure is from.
- No investment advice, no causes for a move, no comparison no tool returned.
- The answer is in Turkish and shows no reasoning or tool mechanics to the customer.
