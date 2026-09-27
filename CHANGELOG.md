# Changelog

## 0.1.4 — 2026-09-27

- **TL deposit comparison.** "Did it beat a deposit account?" is the question a Turkish saver
  faces. With an EVDS key, `compare_real_return` for TL assets adds `deposit_return`,
  `deposit_real_return` and `beat_deposit`, and `portfolio_real_return` accepts `DEPOSIT` as an
  alternative: a 32-day deposit renewed at TCMB's weekly weighted average rate for new TL
  deposits up to 3 months, gross of withholding tax.
- **Bring your own data.** `REALMARKET_PRICE_PROVIDER=http` reads prices, search and
  (optionally) financial statements from an operator-run HTTP adapter, validated strictly
  against the adapter API v1 (`docs/adapter-api.md`); a runnable example adapter is in
  `examples/adapter/`. The adapter's name and attribution appear on every figure it supplies.
- **Central deployment.** `realmarket-mcp --transport http` serves MCP over Streamable HTTP
  (default 127.0.0.1:8000, path `/mcp`), for a firm's own assistant and model;
  `docs/integration.md` describes the setup.
- **Valuation multiples.** New `get_valuation`: market value, P/E, P/B and P/S from the latest
  four quarters (or fiscal year). Converts statement figures to the trading currency (Yahoo's
  own P/B for Turkish Airlines is 18.3 because it skips this; the correct figure is 0.37),
  restates quarters under TMS 29, counts every share class, and states why a ratio is null.
  Every figure carries its sources, including where the share count came from and as of when.
- Checks added after an independent review of the three features above:
  - Prices quoted in pence, cents or agorot (Yahoo's `GBp`, `ZAc`, `ILA`) are converted to the
    major unit; before, a London share's market value was 100 times too high. An adapter must
    send the major unit.
  - SEC cover-page share counts are not used when they are more than 400 days older than the
    latest statements (Berkshire's last tagged count is from 2011) or when the company files
    20-F/40-F (the US listing is often an ADR worth several shares). Two sources' share counts
    more than 5% apart are flagged `shares_mismatch`.
  - `get_valuation` flags `stale_price`, sums earnings and sales over the same four quarters,
    and flags `fiscal_year_basis` and `inflation_unavailable` when it falls back to the fiscal
    year.
  - The deposit model does not carry a rate across a gap of more than 21 days inside the series.
  - An adapter's name is shown as `adapter:<name>`, so it can never pose as a built-in source.
  - API keys and tokens are not sent on to another server when a request is redirected.
- Tests no longer see the developer's own `REALMARKET_*` settings.

## 0.1.3 — 2026-09-27

From the Claude Desktop test round of v0.1.2:

- **News search copes with GDELT's rate limit.** GDELT allows one request every 5 seconds;
  requests are now spaced 5.5 seconds apart and a refused request is retried once after 6
  seconds, instead of failing (two quick searches both failed in the test).
- **An operating loss hidden by non-operating gains is flagged.** `non_operating_items_dominate`
  now also fires when net income is positive while the operating result is a loss (Turkish
  Airlines, 2026 Q2: operating loss $88m, net income $198m).
- `check_setup` no longer presents optional settings left empty as a problem (the model read
  "ignored at startup" as a fault): the field is now `optional_settings_left_empty`, with a note
  that it needs no action. It also lists official EU/UK figures by LEI, which work without Yahoo.
- `portfolio_real_return`: `invested_in_todays_money` is renamed
  `invested_in_money_of_real_return_date` — it is restated to the last CPI month, not to today.
- README: check the extension's settings after installing a new version.
- XBRL International's privacy policy is listed for the desktop extension; CI runs the tests on
  every push.

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
