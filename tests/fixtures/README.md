All data under this directory is **synthetic**: invented symbols, names and round-number
prices built so expected results can be computed by hand. It is not market data.

`evds/` and `fred/` hold CPI API responses with the exact JSON shape the live APIs returned on
2026-09-25 (keys, string-typed values, `null` and `"."` for missing months, EVDS's unpadded
`YYYY-M` dates), but with synthetic index values.
