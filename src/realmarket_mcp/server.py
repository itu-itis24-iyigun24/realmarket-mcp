"""MCP server entry point: registers tools and converts contract envelopes to MCP results."""

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
from realmarket_mcp.config import load_price_provider
from realmarket_mcp.contract import ErrorCode, ToolError, ToolResult
from realmarket_mcp.periods import Period

log = logging.getLogger(__name__)

INSTRUCTIONS = """\
Market research tools that return computed, sourced figures. Use them instead of recalling
prices or returns from memory. Every result cites its data source under "provenance"; cite it
when you report a number. If "quality_flags" contains a warning or critical flag, state it
before any conclusion that depends on the affected data. Results are research, not investment
advice: do not turn them into buy, sell or hold recommendations.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)


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
        """Find assets by name or ticker and return their canonical symbols, currency and
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
        symbol: Annotated[str, Field(description="A symbol returned by search_assets.")],
        period: Annotated[
            Period, Field(description="Lookback ending at `end`. Ignored when `start` is given.")
        ] = "1y",
        start: Annotated[
            str | None, Field(description="Optional ISO start date, e.g. '2023-01-01'.")
        ] = None,
        end: Annotated[
            str | None, Field(description="Optional ISO end date; defaults to today.")
        ] = None,
    ) -> CallToolResult:
        """Measure one asset's performance over a period: total and annualized return,
        annualized volatility, maximum drawdown with its dates, and data coverage, all in the
        asset's own currency. Use it for "how did X do" questions. It does not adjust for
        inflation or convert currency. Ratios are fractions (0.12 means 12%)."""
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

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
