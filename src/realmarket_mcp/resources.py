"""Static documents served as MCP resources."""

METHODOLOGY = """\
# realmarket-mcp methodology

All ratios are fractions: 0.12 means 12%.

## Prices
- Daily bars in the asset's own currency. The provider and its adjustment policy
  (for example `split_and_dividend`) are listed in every result's provenance.
- A bar without a positive close is skipped and reported as a `missing_close` flag.

## Returns
- Total return: `last_close / first_close - 1` over the usable bars in the window.
- Annualized return: `(1 + total) ** (365.25 / calendar_days) - 1`; withheld (null) for spans
  shorter than 180 days, where it would mostly extrapolate noise.
- Volatility: sample standard deviation of daily log returns x sqrt(252).
- Maximum drawdown: largest peak-to-trough fall of the close, with its peak and trough dates.

## Inflation and real return
- Cumulative inflation: `CPI(month of last date) / CPI(month of first date) - 1`, using index
  levels. Missing months are never estimated.
- CPI is a monthly average while prices are daily, so each window edge can be off by up to
  about half a month of inflation; this matters most for short periods in high-inflation
  currencies. Windows that stay within one calendar month get no real return at all.
- Real return: `(1 + nominal) / (1 + inflation) - 1` (not `nominal - inflation`).
- If the CPI for the final month is not yet published, the real return is measured up to the
  last bar inside the published months, and an `inflation_window_truncated` flag says so.
- CPI sources, in order: a user CSV (`REALMARKET_CPI_CSV_<REGION>`, columns `month,cpi_index`);
  the official keyed API if its key is set (Türkiye `TP.GENENDEKS.T1` from TCMB EVDS, US
  `CPIAUCNS` from FRED); otherwise the OECD's national CPI (2015=100) for the US, Türkiye and
  other OECD members, with FRED's public CSV as the US fallback. Keyless OECD data can end months
  before the national release; the result then says how far it reaches.

## Live prices
- With the Yahoo provider, bars dated on or after the current UTC day are excluded because
  the session may still be in progress, so the latest figure is the previous session's close.

## US-dollar and gold terms
- US-dollar return values the holding in USD at both ends using the provider's USD exchange
  rate as of each date (the latest rate on or before it).
- Gold return values the holding in ounces of gold (gold priced in USD).
- Neither is adjusted for US inflation.

## TL deposit comparison
- A 32-day deposit opened at the rate TCMB most recently published (weighted average on new TL
  savings deposits of 1-3 months, EVDS `TP.TRYTAS.MT02`; periods starting before July 2012
  use all TL deposits, `TP.TRY.MT02`), earning `rate x days / 365` for its term and
  renewed at maturity — principal plus interest — at the rate then in force; a final partial
  term earns pro rata. Gross of withholding tax (stopaj). Rates are carried forward at most 21
  days after the last publication, never extrapolated.
- `deposit_real_return` deflates the deposit over the same window as `real_return`.

## Valuation (get_valuation)
- market_cap = latest close x shares outstanding (all share classes; the source is named).
- price_to_earnings = market_cap / earnings, price_to_book = market_cap / equity,
  price_to_sales = market_cap / sales, with statement figures converted to the share's trading
  currency at the price date when the company reports in another currency.
- Earnings and sales: the latest four consecutive quarters (80-100 days apart), otherwise the
  latest fiscal year. Equity: the latest period that has it.
- Turkish companies under TMS 29 (not banks): earnings and sales are the trailing twelve months
  as the source states them from the latest report (year to date + last fiscal year - the same
  period last year, in that report's money). A source that does not state them (Yahoo) gets no
  P/E or P/S for these companies, only market value and P/B: summing its quarters or using the
  fiscal year gave multiples 25-30% off the market figures. Do not compute a P/E from other
  tools' figures instead. Figures are restated with CPI to the latest CPI month.
- A ratio is null, with the reason, when its denominator is missing, zero or negative.

## Savings (portfolio_real_return)
- Each purchase buys `amount / price` units on its date (converted at that date's USD rates
  for foreign assets); the value is those units at the valuation date's price.
- Money-weighted return: the internal rate of return of the dated payments (XIRR).
- Real return: value of the holdings on `real_return_as_of` divided by every payment made by
  then, each restated with `CPI(last month) / CPI(purchase month)`, minus 1. `real_return_as_of`
  is today when this month's CPI is published, otherwise the last day of the last CPI month;
  purchases after it count only in the nominal figures and the alternatives, and are named in
  an `inflation_window_truncated` flag. No inflation rate is assumed for unpublished months.

## Data-quality flags
- `missing_close`, `gap` (no usable bar for over 10 calendar days), `suspicious_move`
  (one-session move beyond about -39% or +65%, often an unadjusted split or redenomination;
  severity critical), `stale` (latest bar over 7 days before the requested end).
- `placeholder_bars` is informational: zero-volume flat bars, usually holidays padded by the
  provider; they do not change returns.
"""
