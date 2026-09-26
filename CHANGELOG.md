# Changelog

## 0.1.2 — 2026-09-26

- **Official figures for European and UK companies.** New `find_official_filer` finds a company
  in the ESEF annual-report index (filings.xbrl.org, XBRL International; keyless) and returns
  candidates with their LEI; `get_financials` with that LEI returns the company's official IFRS
  figures — annual, plus quarterly where the company files interim reports there. Germany and
  Ireland are not covered by the index. Growth for euro reporters is deflated with the home
  country's CPI.
- `get_financials` adds a `latest_year` block with margins and leverage, so annual-only sources
  also get ratios.
- **Savings real return no longer disappears with a recent purchase.** When the inflation series
  stops before today (usual: CPI is published weeks after month end), `portfolio_real_return`
  used to return no real figure if any purchase fell after the last CPI month — that is, for
  almost every monthly saver. The real return is now measured on the last day the series covers,
  with that day's prices, over the purchases made by then; later purchases stay in the nominal
  figures and are named in the flag. New fields: `real_return_as_of`,
  `value_at_real_return_date`. This also fixes a mismatch where today's value was compared with
  payments restated only to the last CPI month.
- `check_setup` now says what replaces a missing source (e.g. US statements from Yahoo when no
  SEC e-mail is set) and that only Turkish CPI from the OECD lags.
- Issue forms for bug reports and for figures that disagree with an official source.

## 0.1.1 — 2026-09-25

Fixes from the first hands-on test in Claude Desktop.

- **Yahoo is now a checkbox.** The "Price data provider" text field is replaced by **Use Yahoo
  Finance (unofficial)**, off by default. After upgrading, tick it again in the settings.
  Plain MCP configurations can keep `REALMARKET_PRICE_PROVIDER=yahoo`; the new
  `REALMARKET_USE_YAHOO=true` is what the checkbox sets.
- **New `check_setup` tool.** Reports which sources the server will use (prices, SEC
  statements, inflation per region, news) and which settings are missing, as present or absent
  — never their values. Claude is told to use it when a source is not configured.
- **Padded holiday bars are informational.** `placeholder_bars` (zero-volume flat bars) no
  longer counts as a warning; they do not change any figure.
- **Clearer setup instructions:** installing the Desktop extension from Settings → Extensions →
  Advanced settings, and a troubleshooting section — above all, quit the app completely and
  reopen it after changing a setting.

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
