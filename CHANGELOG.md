# Changelog

## Unreleased

- **`analyze_portfolio` `compare_with`**: only when the user asks, each holding gets another
  symbol's move (BIST 100, BIST 30, gold, any asset) over the holding's own period, from its
  first purchase to the last session or the day it was sold out, beside its own price move.
  There is deliberately no account-level comparison (money went in on different days), and the
  result says so in a data field.
- A tool called with an argument it does not have now refuses with `invalid_argument` and the
  list of valid arguments. The SDK used to drop it silently: Haiku passed a made-up
  `benchmark` to `analyze_portfolio` and believed it had been applied.
- `scripts/call_tool.py` lists and calls the tools from a shell exactly as an MCP client sees
  them (`--synthetic` for the fictional ORNEK), and the `model-check` skill uses it to have
  Haiku subagents answer standard customer questions, without packaging an extension.
- Found by its first run: the instructions say returns are fractions (Haiku had written a
  0.313 after-tax deposit return as "%313"), and the `inflation_window_truncated` warning says
  which figures cover the same months as the real return.

## 0.1.7 — 2026-09-28

- **`explain_price_move`: "why did it move today?"** The facts around one session: the
  stock's move in traded prices next to the benchmark index's move and the difference between
  them, how large the move and the volume were against recent days, whether it was an
  ex-dividend day, and news or disclosures from the day before to the day after, from GDELT
  or the firm's own feed. It deliberately does not split the move into market and company
  parts or name a cause; the notes and server instructions tell the model not to either, and
  `realmarket-qualify` has a case that fails an answer that does.
- **`analyze_portfolio`: the account itself.** From the transactions a brokerage already
  holds (buy, sell, cash dividend, bonus issue), each holding's quantity, average cost,
  market value and weight, unrealized and realized profit, dividends and total result; account
  totals and the money-weighted return; the largest holding, top-three weight and currency
  split; best and worst holding; and the current holdings' volatility and drawdown over the
  last year. It values holdings at traded prices (not dividend-adjusted closes), so dividends
  count once, and warns when the source reports dividends the transactions leave out.
  Splits and bonus issues the source reports are applied automatically (a purchase before
  BIMAS's 2-for-1 bonus issue on 2026-05-14 would otherwise show as a false loss), unless the
  transactions already record the bonus; the result says so with a `split_applied` flag.
- **News from the firm's own feed.** The adapter API gains an optional `/news` endpoint, so a
  firm can plug in KAP disclosures, Foreks or any licensed news feed
  (`REALMARKET_NEWS_PROVIDER=http`). The example adapter serves a `news.json` file.
- **`realmarket-adapter-check`** calls every adapter endpoint through realmarket's own code and
  reports PASS, WARN, FAIL or SKIP for each, including the exchange-rate, gold and benchmark
  series comparisons depend on. A firm runs it before connecting.
- Found in a Claude Desktop test with a small model:
  - `search_assets` retries without Turkish letters when a name finds nothing ("Türk Hava
    Yolları" returned nothing from Yahoo, so the model concluded Turkish shares were not
    covered).
  - `analyze_portfolio` accepts a month alone ("2024-03") and uses its first session, flagged
    `date_assumed`; its description tells the model to call it rather than ask for prices first.
  - `explain_price_move` warns, not just notes, when the latest session is not today, and says
    to name its date; the instructions also forbid adding causes, technical levels or forecasts
    found elsewhere, such as in a web search.
  - When a tool fails (a rate limit, a source that is down), the instructions tell the model
    to say so rather than list what usually moves a stock, and to call a tool with what the
    user gave instead of asking for more first.
  - `period: null`, which small models send for an unused optional argument, now means the
    default instead of failing the call.
  - `analyze_portfolio` reports the account's `total_return_on_purchases` (the model had
    computed its own, wrongly) and its notes say which per-holding figures include shares
    already sold. `explain_price_move` returns `cause: "Not determined…"` as a data field, and
    the instructions forbid comparisons no tool returned and hedged lists of possible reasons.
  - A holding's total result now comes before its open-shares-only `unrealized_return`, which
    a model had reported as the holding's return; `get_news` and `get_price_summary` point
    "why did it move" questions to `explain_price_move`.
- `check_setup` reports the `build` (commit) of a packaged extension, so test builds with the
  same version number can be told apart.
- `realmarket-qualify` gains a `portfolio` case, and a sentence that refuses advice ("hedef
  fiyat veremiyorum") no longer counts as advice, nor a month ("2024-03") or a quoted data
  version as an unsupported figure. `gemini-3.5-flash-lite` passes 7/7.
- Funds can be served by an adapter like any asset (`asset_class` `fund`).
- `docs/integration.md` describes support and pilots, and that the firm's backend shows
  customers the final answer only, never the model's reasoning.

## 0.1.6 — 2026-09-27

- Fixes from an independent review of this release:
  - **Dividends on pence-quoted shares.** Yahoo's own adjusted closes treat a dividend in pence
    as pounds, so a London share's total return left its dividends out (BP.L, one year: 0.06
    points instead of 6.6). The total-return adjustment is now computed from the dividends and
    the split-adjusted closes (`1 - dividend / previous close` at each ex-date); results for
    other markets are unchanged.
  - Because Yahoo series now carry their split-only closes and dividends, their `data_version`
    hashes differ from v0.1.5 for the same prices. Compare audit-log versions within a release.
  - After-tax deposit figures are cited and explained whenever either is given; periods the
    withholding table does not cover (before 2006) are flagged. The withholding note lists
    every rate change, including the 2018 cut.
  - The savings tool explains that HOUSE is valued as of the index's last month and notes the
    withholding tax next to DEPOSIT. Turkish-only notes are left off non-TRY results.
  - From the Claude Desktop test: the house comparison is grouped in one `house_prices`
    object with its own window and a `house_price_real_return` (the model had called Istanbul
    housing an inflation beater at +100.6% against +153.6% CPI, and put the house window's
    asset return into other rows). The server instructions now require a fresh tool call per
    asset (the model had reused Tüpraş's P/B for THYAO) and keeping each figure with its
    window.
  - The price summary adds `first_price`/`last_price`, the prices actually traded: with
    dividends included, `first_close` is dividend-adjusted (Tüpraş: 113.58 TL against 163.70
    TL traded), and the model had presented it as the starting price.
  - An empty EVDS series (a house index before 2010) now says so instead of reporting a
    format change; a failed 12-month fetch for the dividend yield is flagged.

- **Gram gold.** `compare_real_return` gives gold's own return in the asset's currency
  (`gold_return_in_currency`, `beat_gold`) and, for TL assets, the gram gold price in TL at
  both ends, from the spot price: 1,662 TL to 6,801 TL over THYAO's last three years.
- **Housing.** With an EVDS key, TL assets are compared with TCMB's house price index for
  Türkiye, Istanbul, Ankara or Izmir (`house_price_return`, `beat_house_prices`), and the
  savings tool can replay payments into housing (`HOUSE`). Sale prices only, no rent.
- **Dividend yield.** `dividend_yield_trailing_12m` in the price summary and valuation.
- **Deposit after withholding tax.** `compare_real_return` adds `deposit_return_after_tax`,
  `deposit_real_return_after_tax` and `beat_deposit_after_tax`, and the savings tool's DEPOSIT
  alternative its after-tax value: each 32-day term's interest is taxed at the stopaj rate in
  force when it opens or renews (5% to 17.5% since 2018, from a table of Resmî Gazete
  decisions). THYAO's last three years: a deposit returned 371% gross, 293% after tax.
- **Minimum wage.** `compare_real_return` measures TL holdings in net minimum wages
  (`minimum_wage_growth`, `return_in_minimum_wages`, from 2012): the wage rose 146% over the
  last three years, so THYAO's shares buy 48% fewer months of it than at the start.
- **Dividends.** `get_price_summary` splits the return into the share price and dividends
  (`price_return`, `dividend_return`) and lists the cash dividends per share paid in the
  period, from the same Yahoo request as the prices. Tüpraş over three years: 257% in total,
  of which 109 points from six dividends worth 62.95 TL a share.
- **Deposit comparison uses savings-deposit rates.** The TL deposit alternative now follows
  TCMB's rate on new *savings* deposits of 1-3 months (`TP.TRYTAS.MT02`), the account a saver
  actually holds, instead of all TL deposits including commercial ones (`TP.TRY.MT02`, which
  paid up to 5 points more in 2024). The 1-3 month bucket stays: a 32-day deposit falls in it,
  and the up-to-1-month rate is lower throughout. Periods starting before July 2012, when the
  savings series begins, use the all-deposits series throughout instead of splicing the two.
  Over THYAO's last three years the deposit return moves from 371.18% to 371.27%.

## 0.1.5 — 2026-09-27

- **Model qualification.** `realmarket-qualify --base-url <OpenAI-compatible API> --model <name>`
  checks the language model a firm puts in front of realmarket (a local model served by Ollama,
  vLLM or LM Studio, or a hosted one): Turkish questions about a synthetic company, with the
  real tools and server instructions, and automatic checks that the model called the tools,
  reported their figures unchanged, invented none, gave no buy/sell advice and did not show
  its reasoning block to the customer. Rate limits and timeouts are retried, a run is bounded
  by `--max-minutes`, and results print as they arrive. First run against an open-weights
  model (Gemma 4 26B via Google's API): every figure correct and the missing P/E explained,
  but its reasoning text was in every answer. See `docs/integration.md`.
- **Audit log.** `REALMARKET_AUDIT_LOG=<file>` appends one JSON line per tool call: tool,
  arguments, outcome, the provenance and exact data version of every figure, the quality
  flags, and a SHA-256 of the exact response the model received (`REALMARKET_AUDIT_FULL=1`
  stores the response too). No settings or keys are written; if the file cannot be written
  the tool refuses to answer rather than leave a gap. See `docs/integration.md`.
- **No P/E or P/S for TMS 29 companies without a proper trailing figure.** The market
  convention for Turkish companies under inflation accounting is the trailing twelve months
  from the latest report, in that report's money (BIMAS P/E 17.26 in a brokerage app). Yahoo's
  quarterly figures mix restated and first-reported values and lack the restated comparatives:
  summing them gave 16.7, the CPI-restated fiscal year 22.1. `get_valuation` now gives market
  value and P/B for these companies from Yahoo, and P/E and P/S only when the source states the
  trailing twelve months (adapter API: optional `ttm`). Figures are restated with CPI to the
  latest CPI month (`restated_to_money_of`); `cpi_behind_price` flags a lagging CPI series and
  `newer_quarters_not_used` a fiscal-year basis that leaves out published quarters.

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
