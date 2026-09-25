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
  `CPIAUCNS` from FRED); otherwise keyless sources: FRED's public CSV for the US and the OECD's
  national CPI (2015=100) for Türkiye and other OECD members. Keyless OECD data can end months
  before the national release; the result then says how far it reaches.

## Live prices
- With the Yahoo provider, bars dated on or after the current UTC day are excluded because
  the session may still be in progress, so the latest figure is the previous session's close.

## US-dollar and gold terms
- US-dollar return values the holding in USD at both ends using the provider's USD exchange
  rate as of each date (the latest rate on or before it).
- Gold return values the holding in ounces of gold (gold priced in USD).
- Neither is adjusted for US inflation.

## Data-quality flags
- `missing_close`, `placeholder_bars` (zero-volume flat bars, usually padded holidays),
  `gap` (no usable bar for over 10 calendar days), `suspicious_move` (one-session move beyond
  about -39% or +65%, often an unadjusted split or redenomination; severity critical),
  `stale` (latest bar over 7 days before the requested end).
"""
