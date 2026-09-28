"""Call realmarket's MCP tools from a shell, exactly as an MCP client receives them.

    python scripts/call_tool.py tools                       # server instructions + every tool
    python scripts/call_tool.py call explain_price_move '{"symbol": "THYAO.IS"}'
    python scripts/call_tool.py --synthetic call get_price_summary '{"symbol": "ORNEK"}'

It runs the real server object in process, so what it prints is byte for byte what a model
sees: the same instructions, descriptions, argument validation and result envelopes. Its use
is testing how a model handles the tools without packaging an extension each time: a Claude
Code subagent on a small model (the `model-check` skill) reads `tools` and calls `call`.

Data comes from the caller's REALMARKET_* settings (e.g. REALMARKET_PRICE_PROVIDER=yahoo), or
with --synthetic from realmarket-qualify's fictional company ORNEK, with every REALMARKET_*
setting removed.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import anyio

from realmarket_mcp import qualify
from realmarket_mcp.server import INSTRUCTIONS, build_server


def describe_tools() -> str:
    lines = ["SERVER INSTRUCTIONS:", INSTRUCTIONS]
    for tool in anyio.run(build_server().list_tools):
        schema = json.dumps(tool.input_schema, ensure_ascii=False)
        lines += [f"## {tool.name}", tool.description or "", f"parameters: {schema}", ""]
    return "\n".join(lines)


def call(name: str, arguments: dict[str, Any]) -> str:
    async def run() -> Any:
        return await build_server().call_tool(name, arguments)

    return str(anyio.run(run).content[0].text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="call_tool", description=__doc__.split("\n")[0])
    parser.add_argument("--synthetic", action="store_true", help="use the fictional ORNEK data")
    parser.add_argument("--log", type=Path, help="append each call and its result here (JSONL)")
    parser.add_argument("--case", default="", help="question id recorded with each logged call")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tools", help="print the server instructions and every tool")
    run = sub.add_parser("call", help="call one tool and print its result")
    run.add_argument("name")
    run.add_argument("arguments", nargs="?", default="{}", help="JSON object")
    args = parser.parse_args(argv)

    context = (
        qualify.synthetic_environment(dt.date.today())
        if args.synthetic
        else contextlib.nullcontext()
    )
    with context:
        if args.command == "tools":
            print(describe_tools())
            return 0
        try:
            arguments = json.loads(args.arguments)
        except json.JSONDecodeError as error:
            parser.error(f"arguments must be a JSON object: {error}")
        if not isinstance(arguments, dict):
            parser.error("arguments must be a JSON object")
        text = call(args.name, arguments)
        print(text)
        if args.log:
            record = {"case": args.case, "tool": args.name, "arguments": arguments}
            record["response"] = json.loads(text)
            with args.log.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
