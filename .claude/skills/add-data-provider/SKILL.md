---
name: add-data-provider
description: Workflow for adding a market-data, FX, or inflation (CPI) provider to realmarket-mcp - terms check, provider interface, normalization, recorded fixtures, integrity review. Use whenever a new data source is integrated or an existing provider's parsing changes.
---

# Adding a data provider

A provider is the only code allowed to touch the network. Everything downstream works on
normalized, versioned data, so a provider bug becomes a wrong number in every tool.

1. **Check terms before code.** Delegate to `compliance-reviewer`: fetch the provider's terms
   of use, confirm automated personal use is allowed, note API-key, rate-limit and attribution
   requirements. Add the entry to `docs/providers.md`. Stop if the terms forbid it.

2. **Implement the provider interface** (see "Provider interface" in `docs/design.md`):
   - Fetch raw data; API keys come only from environment variables named
     `REALMARKET_<PROVIDER>_API_KEY`, and a missing key raises `ToolError(MISSING_API_KEY)`
     whose hint names the variable and the signup page.
   - Map provider failures to `PROVIDER_UNAVAILABLE` / `RATE_LIMITED` (retryable) or
     `UNKNOWN_SYMBOL` / `NO_DATA_IN_RANGE` (not retryable).
   - Normalize to the shared schema: session date, OHLC, volume, currency, adjustment policy.
     Validate OHLC consistency; flag, do not repair, inconsistent rows.
   - Compute `data_version` as a SHA-256 over the normalized bytes.

3. **Record fixtures.** Save a small real response under `tests/fixtures/<provider>/` only if
   the terms allow redistribution of that sample; otherwise build a synthetic fixture with the
   same structure. Keep each fixture under ~50 KB.

4. **Test offline.** Delegate to `test-engineer`: parsing, normalization, every error mapping,
   and the edge cases (partial latest bar, zero-volume placeholder, split seam, gaps).

5. **Integrity review.** Delegate to `data-integrity-reviewer` on the full diff.

6. **Verify.** Tests, ruff, mypy all pass; report the results.
