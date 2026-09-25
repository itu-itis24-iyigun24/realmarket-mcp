"""MCP server entry point: registers tools, prompts and resources, and converts contract
envelopes into MCP results. All logic lives in ``tools``; this module is wiring only."""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from realmarket_mcp import __version__, tools
from realmarket_mcp.config import load_cpi, load_price_provider
from realmarket_mcp.contract import ErrorCode, ToolError, ToolResult
from realmarket_mcp.periods import Period
from realmarket_mcp.resources import METHODOLOGY

log = logging.getLogger(__name__)

INSTRUCTIONS = """\
Market research tools that return computed, sourced figures. Use them instead of recalling
prices or returns from memory. Every result cites its data source under "provenance"; cite it
when you report a number. If "quality_flags" contains a warning or critical flag, state it
before any conclusion that depends on the affected data. Results are research, not investment
advice: do not turn them into buy, sell or hold recommendations.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)

Symbol = Annotated[str, Field(description="A symbol returned by search_assets.")]
PeriodArg = Annotated[
    Period, Field(description="Lookback ending at `end`. Ignored when `start` is given.")
]
StartArg = Annotated[str | None, Field(description="Optional ISO start date, e.g. '2023-01-01'.")]
EndArg = Annotated[str | None, Field(description="Optional ISO end date; defaults to today.")]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _stamp(moment: dt.datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _to_call_result(payload: dict[str, object], *, is_error: bool) -> CallToolResult:
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=payload,
        is_error=is_error,
    )


def respond(produce: Callable[[], ToolResult]) -> CallToolResult:
    """Run a tool body and map every outcome onto the contract's envelopes."""
    try:
        return _to_call_result(produce().to_dict(), is_error=False)
    except ToolError as error:
        return _to_call_result(error.to_dict(), is_error=True)
    except Exception as exc:  # ContractViolation or any other bug; never the caller's fault
        log.exception("tool failed")
        internal = ToolError(
            ErrorCode.INTERNAL,
            f"Internal error: {type(exc).__name__}.",
            "This is a bug in realmarket-mcp; report it. Do not retry with the same arguments.",
        )
        return _to_call_result(internal.to_dict(), is_error=True)


def build_server() -> MCPServer:
    server: MCPServer = MCPServer(
        name="realmarket",
        title="realmarket-mcp",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    @server.tool(annotations=READ_ONLY)
    def search_assets(
        query: Annotated[str, Field(description="Company, index or asset name, or a ticker.")],
        limit: Annotated[int, Field(ge=1, le=25, description="Maximum results.")] = 10,
    ) -> CallToolResult:
        """Find assets by name or ticker and return their canonical symbols, asset class and
        exchange. Use this first whenever you are not certain of an exact symbol; every other
        tool takes the symbols it returns. Does not return prices."""
        now = _utc_now()
        return respond(
            lambda: tools.search_assets(
                load_price_provider(retrieved_at=_stamp(now)),
                query,
                limit,
                today=now.date(),
                retrieved_at=_stamp(now),
            )
        )

    @server.tool(annotations=READ_ONLY)
    def get_price_summary(
        symbol: Symbol,
        period: PeriodArg = "1y",
        start: StartArg = None,
        end: EndArg = None,
    ) -> CallToolResult:
        """Measure one asset's performance over a period: total and annualized return,
        annualized volatility, maximum drawdown with its dates, and data coverage, all nominal
        and in the asset's own currency. Use it for "how did X do" questions. For inflation,
        US-dollar or gold terms use compare_real_return; for several assets use compare_assets.
        Ratios are fractions (0.12 means 12%)."""
        now = _utc_now()
        return respond(
            lambda: tools.get_price_summary(
                load_price_provider(retrieved_at=_stamp(now)),
                symbol,
                period,
                start,
                end,
                today=now.date(),
            )
        )

    @server.tool(annotations=READ_ONLY)
    def compare_real_return(
        symbol: Symbol,
        period: PeriodArg = "5y",
        start: StartArg = None,
        end: EndArg = None,
        inflation_region: Annotated[
            str | None,
            Field(
                description="CPI region: 'TR' or 'US', or any region the user configured a CSV "
                "for. Defaults from the asset's currency (TRY -> TR, USD -> US)."
            ),
        ] = None,
    ) -> CallToolResult:
        """Answer "did this asset beat inflation?": nominal return, cumulative consumer-price
        inflation, real (inflation-adjusted) return and its annualized rate, plus the same
        holding measured in US dollars and in gold. Use it for any question about real,
        inflation-adjusted or purchasing-power returns, especially for high-inflation
        currencies. Needs a configured CPI source; the error explains how if one is missing.
        Ratios are fractions (0.12 means 12%)."""
        now = _utc_now()
        stamp = _stamp(now)
        return respond(
            lambda: tools.compare_real_return(
                load_price_provider(retrieved_at=stamp),
                lambda region, first, last: load_cpi(region, first, last, retrieved_at=stamp),
                symbol,
                period,
                start,
                end,
                inflation_region,
                today=now.date(),
            )
        )

    @server.tool(annotations=READ_ONLY)
    def compare_assets(
        symbols: Annotated[
            list[str],
            Field(min_length=2, max_length=10, description="2 to 10 symbols from search_assets."),
        ],
        period: PeriodArg = "1y",
        start: StartArg = None,
        end: EndArg = None,
    ) -> CallToolResult:
        """Put 2 to 10 assets side by side over one common date window: total and annualized
        return, volatility and maximum drawdown for each. Use it to compare assets or an asset
        against an index. Returns are nominal, each in its own currency; mixed currencies are
        flagged. Ratios are fractions (0.12 means 12%)."""
        now = _utc_now()
        return respond(
            lambda: tools.compare_assets(
                load_price_provider(retrieved_at=_stamp(now)),
                symbols,
                period,
                start,
                end,
                today=now.date(),
            )
        )

    @server.tool(annotations=READ_ONLY)
    def check_data_quality(
        symbol: Symbol,
        period: PeriodArg = "5y",
        start: StartArg = None,
        end: EndArg = None,
    ) -> CallToolResult:
        """Audit an asset's price history before trusting figures built on it: missing closes,
        zero-volume placeholder bars, gaps, suspicious one-session moves (unadjusted splits,
        redenominations, provider errors) and a stale latest bar, with an overall verdict.
        Use it when a result looks surprising or before a long-period analysis."""
        now = _utc_now()
        return respond(
            lambda: tools.check_data_quality(
                load_price_provider(retrieved_at=_stamp(now)),
                symbol,
                period,
                start,
                end,
                today=now.date(),
            )
        )

    @server.resource(
        "realmarket://methodology",
        name="methodology",
        title="How realmarket-mcp computes its figures",
        mime_type="text/markdown",
    )
    def methodology() -> str:
        return METHODOLOGY

    @server.prompt(title="Single asset report")
    def single_asset_report(asset: str, period: str = "5y") -> str:
        """A sourced performance report on one asset, including real returns."""
        return _report_prompt(
            f"Write a performance report on {asset} over the last {period}.",
            [
                "Resolve the asset with search_assets.",
                "Run check_data_quality, get_price_summary and compare_real_return for the period.",
            ],
        )

    @server.prompt(title="Did it beat inflation?")
    def real_return_report(asset: str, period: str = "5y") -> str:
        """Whether an asset preserved purchasing power, in local, US-dollar and gold terms."""
        return _report_prompt(
            f"Determine whether {asset} beat inflation over the last {period}.",
            [
                "Resolve the asset with search_assets.",
                "Run compare_real_return. Explain nominal vs real return in plain words, then the "
                "US-dollar and gold results.",
            ],
        )

    @server.prompt(title="Compare assets")
    def comparison_report(assets: str, period: str = "1y") -> str:
        """A side-by-side comparison of several assets (comma-separated)."""
        return _report_prompt(
            f"Compare these assets over the last {period}: {assets}.",
            [
                "Resolve every asset with search_assets.",
                "Run compare_assets on all of them; if currencies differ, also run "
                "compare_real_return on each.",
            ],
        )

    return server


def _report_prompt(task: str, steps: list[str]) -> str:
    numbered = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, start=1))
    return f"""{task}

Use the realmarket tools; do not use figures from memory.
{numbered}

Report rules:
- Start with any warning or critical quality flag and what it affects.
- Give each figure as a percentage with its period and currency, and cite the provider and
  period from "provenance".
- Say plainly when a figure is null and why.
- Describe what happened; do not recommend buying, selling or holding, and do not forecast.
- End with one line: "Source data: <providers>; not investment advice."
"""


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    build_server().run()


if __name__ == "__main__":
    main()
