# Model check, 28 September 2026: the 119 questions through the data adapter

**Question.** Does a firm that connects its own data through the adapter get the same answers as
the Yahoo path? The adapter API gained dividends, splits and traded closes in `/bars` and an
optional `/peers` endpoint for this run; everything else is unchanged.

**Setup.** A firm-style dataset (symbols as a Turkish broker's feed names them: `THYAO`,
`XU100`, `USDTRY`, `XAUUSD`; 26 series, dividends, splits, statements and peer lists) was
built from one Yahoo snapshot and served by `examples/adapter/serve_files.py`. The dataset
stays out of the repository: realmarket ships no market data. `realmarket-adapter-check`
passed every required check and every optional one the data covers. Claude Haiku 4.5 then
answered the same 119 questions, in the same batches, with `REALMARKET_PRICE_PROVIDER=http`.

## Result

| | Yahoo path (full run 2) | Adapter path |
|---|---|---|
| Passed the automatic checks | 114 / 119 | 113 / 119 |
| Correct on reading | 115 / 119 | 116 / 119 |
| Advice, a reason for a move, a cheap/dear verdict | 0 | 0 |

Direct comparisons of the same calls on both paths gave identical figures (THYAO's P/B and
industry comparison, BIMAS's bonus issue applied to a portfolio, GARAN's dividend yield).

Haiku's three errors: a KCHOL-versus-gold answer comparing gold in dollars with the share in
lira through `compare_assets` (it says the currencies differ, but still names a winner), and
two answers computing a gap the facts gave in another form. The other three automatic
failures are the test's: calls made without the log flag, a refusal ending in "yok", and a
question answered with the previous question's portfolio.

## What the run found, and what was changed

1. **`check_setup` said statements were unavailable with the adapter.** It only knew Yahoo as
   a statement source, so with the adapter its facts said "Türkiye için yok", and Haiku
   refused four financial and valuation questions the adapter could answer. Statements are
   now reported as coming from the price source when it is on (Yahoo, the adapter, local
   files). Re-run of the four: correct.
2. **A trade dated on a closed day used the previous close.** "June 2024" written as
   2024-06-01 (a Saturday) priced a purchase at 31 May's close, so the same portfolio gave
   +20,340 TL or +21,177.50 TL depending on how the date was written. A buy or sell without a
   price on a closed day now fills at the next session, and the facts say so. Re-run: the
   adapter and Yahoo paths agree.
3. **Dividends not entered, summed by the model.** The account-level fact now states their
   total along with the result including them.

## Afterwards: assets in different currencies

`compare_assets` now measures assets priced in different currencies in one (TRY when one of
them is in TRY) and ranks them there; without a rate it ranks nothing across currencies. The
real-return fact giving an asset's return in dollars now names the asset: Haiku had read
"XU100 in dollars, -0.87%" as the dollar's own return. Re-run of the two affected questions
(KCHOL or gold; gold, the dollar and BIST 100): Sonnet 2 / 2, Haiku 6 / 6 after the second
fix (gold +32.0% in TL, the dollar +17.8%, BIST 100 +16.8%; gold +311.9% in TL against
KCHOL's +71.9% over three years, the same figure `compare_real_return` gives).
