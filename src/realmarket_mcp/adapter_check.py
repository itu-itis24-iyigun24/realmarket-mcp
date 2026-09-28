"""Check a firm's data adapter against the adapter API before connecting realmarket to it.

    realmarket-adapter-check --url https://marketdata.internal/realmarket/v1 --symbol THYAO

Every endpoint is called through the same code realmarket uses at run time, so what passes
here works in production and what fails fails for the same reason, with the same message.
Required: /meta, /search, /bars. Optional: /financials, /news. The reference series realmarket
uses for comparisons (the USD exchange rate, gold, the benchmark index) are checked too,
because a missing one quietly removes those comparisons.

Exit code 0: everything required passed; 1: a required check failed; 2: bad arguments.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from realmarket_mcp import quality, tools
from realmarket_mcp.contract import ErrorCode, Severity, ToolError
from realmarket_mcp.providers import http_adapter
from realmarket_mcp.providers.http_adapter import HttpAdapterNewsProvider, HttpAdapterProvider

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def run_checks(
    connect: Callable[[], HttpAdapterProvider],
    symbol: str | None,
    *,
    today: dt.date,
) -> list[Check]:
    results: list[Check] = []

    def record(name: str, status: str, detail: str) -> None:
        results.append(Check(name, status, detail))

    try:
        adapter = connect()
    except ToolError as error:
        record("/meta", FAIL, f"{error.message} {error.hint}")
        return results
    record("/meta", PASS, f"source {adapter.name}")

    query = symbol or "a"
    try:
        found = adapter.search(query, 10)
        if found:
            record("/search", PASS, f"{len(found)} result(s) for {query!r}")
        else:
            record("/search", WARN, f"no result for {query!r}")
    except ToolError as error:
        record("/search", FAIL, error.message)
        found = []
    symbol = symbol or next((a.symbol for a in found if a.asset_class.value == "equity"), None)
    if symbol is None:
        record("/bars", FAIL, "no symbol to test: pass --symbol")
        return results

    start = today - dt.timedelta(days=400)
    try:
        series = adapter.daily_bars(symbol, start, today)
        flags = quality.check_series(series, requested_end=today)
        serious = [f.code for f in flags if f.severity is not Severity.INFO]
        detail = f"{len(series.bars)} bars for {symbol} in {series.currency}, {series.adjustment}"
        record(
            "/bars", WARN if serious else PASS, detail + (f"; flags: {serious}" if serious else "")
        )
    except ToolError as error:
        record("/bars", FAIL, error.message)
        return results

    references = {
        "exchange rate": adapter.fx_symbol("USD", series.currency.upper())
        if series.currency.upper() != "USD"
        else None,
        "gold": adapter.gold_usd_symbol,
        "benchmark": adapter.default_benchmark(symbol),
    }
    for label, reference in references.items():
        if reference is None:
            continue
        try:
            adapter.daily_bars(reference, today - dt.timedelta(days=30), today)
            record(f"/bars {label}", PASS, reference)
        except ToolError as error:
            record(
                f"/bars {label}",
                WARN,
                f"{reference}: {error.message} Comparisons that need it will be skipped.",
            )

    try:
        summary = tools.get_price_summary(adapter, symbol, "1y", today=today)
        record("price summary", PASS, f"total_return {summary.data['total_return']}")
    except ToolError as error:
        record("price summary", FAIL, error.message)

    try:
        statements = adapter.financials(symbol)
        record(
            "/financials",
            PASS,
            f"{len(statements.quarterly)} quarters, {len(statements.annual)} years"
            + ("" if statements.trailing_twelve_months else "; no ttm (no P/E under TMS 29)"),
        )
    except ToolError as error:
        status = SKIP if error.code is ErrorCode.NO_DATA_IN_RANGE else FAIL
        record("/financials", status, error.message)

    try:
        now = dt.datetime.combine(today, dt.time(), tzinfo=dt.UTC)
        news = HttpAdapterNewsProvider(adapter).search(
            symbol, now - dt.timedelta(days=30), now, language=None, limit=5
        )
        record("/news", PASS, f"{len(news)} article(s) in the last 30 days")
    except ToolError as error:
        record("/news", SKIP if error.code is ErrorCode.UNSUPPORTED else FAIL, error.message)
    return results


def render(results: list[Check]) -> str:
    lines = [f"[{r.status}] {r.name}: {r.detail}" for r in results]
    failed = sum(r.status == FAIL for r in results)
    lines.append("")
    lines.append(
        "The adapter is ready to connect."
        if not failed
        else f"{failed} check(s) failed; see docs/adapter-api.md."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="realmarket-adapter-check",
        description="Check a data adapter against the realmarket adapter API.",
    )
    parser.add_argument("--url", default=os.environ.get(http_adapter.URL_ENV, ""))
    parser.add_argument(
        "--token-env",
        default=http_adapter.TOKEN_ENV,
        help="environment variable holding the adapter's token (never passed on the command line)",
    )
    parser.add_argument("--symbol", help="a symbol the adapter serves, e.g. THYAO")
    args = parser.parse_args(argv)
    if not args.url:
        parser.error(f"pass --url or set {http_adapter.URL_ENV}")
    token = os.environ.get(args.token_env, "").strip() or None
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = run_checks(
        lambda: HttpAdapterProvider(args.url, token=token, retrieved_at=stamp),
        args.symbol,
        today=dt.date.today(),
    )
    print(render(results))
    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
