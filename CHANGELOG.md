# Changelog

## 0.1.0 — 2026-09-25

First public release (alpha). Market research tools for Claude and other MCP clients that
compute figures in code and return them with their sources. Not investment advice.

**Tools:** `search_assets`, `get_price_summary`, `compare_real_return` (nominal vs inflation,
in US dollars and in gold), `compare_assets`, `check_data_quality`, `portfolio_real_return`,
`get_event_reaction`, `get_financials`, `get_news`; three report prompts and a methodology
resource.

**Data sources:** SEC EDGAR (official US financial statements; needs only a contact e-mail),
OECD and FRED (CPI, no key needed), TCMB EVDS (Turkish CPI, optional key), GDELT (news), and
Yahoo Finance (opt-in; its terms prohibit automated access without permission — see the
README). Every result carries provenance, the credit its source asks for, and data-quality
flags.

**Install:**

- Claude Code / Cowork plugin:
  `claude plugin marketplace add itu-itis24-iyigun24/realmarket-mcp`, then
  `claude plugin install realmarket@realmarket` (needs [uv](https://docs.astral.sh/uv/)).
- Claude Desktop: download `realmarket-0.1.0.mcpb` below and open it with Claude Desktop.
  Verify the download against the `.sha256` file.
- Any MCP client:
  `pip install "realmarket-mcp[yahoo] @ git+https://github.com/itu-itis24-iyigun24/realmarket-mcp@v0.1.0"`.

**Known limits:** statements for non-US companies come from Yahoo (unofficial); Türkiye's
keyless CPI ends at 2025-12 until the OECD carries TÜİK's 2026 rebasing (set an EVDS key for
current data); KAP disclosures are not included.
