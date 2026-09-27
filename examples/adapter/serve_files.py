"""Example realmarket data adapter (API v1), serving local files. Standard library only.

A firm replaces the three `load_*` functions with calls to its licensed data feed and keeps the
HTTP layer. Run it, then point realmarket at it:

    python examples/adapter/serve_files.py --root tests/fixtures/basic --port 8765
    REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8765 realmarket-mcp

File layout under --root (the same as realmarket's test fixtures):
    assets.json               [{"symbol", "name", "asset_class", "currency", "exchange"}]
    bars/<SYMBOL>.csv         date,open,high,low,close,volume   (empty cell = missing)
    financials/<SYMBOL>.json  optional; the /financials response body

The full contract is docs/adapter-api.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(".")
TOKEN = os.environ.get("ADAPTER_TOKEN")  # optional: require "Authorization: Bearer <token>"

META = {
    "api_version": 1,
    "name": "example-files",
    "attribution": "Source: example files served by the realmarket example adapter.",
    "gold_usd_symbol": "GOLD",
    "fx_symbol": "{base}{quote}",
    "benchmarks": {"TRY": "IDX"},
}


def load_assets() -> list[dict[str, Any]]:
    return json.loads((ROOT / "assets.json").read_text(encoding="utf-8"))


def load_bars(symbol: str, start: str, end: str) -> dict[str, Any] | None:
    asset = next((a for a in load_assets() if a["symbol"] == symbol), None)
    path = ROOT / "bars" / f"{symbol}.csv"
    if asset is None or not path.exists():
        return None

    def number(cell: str) -> float | None:
        return float(cell) if cell.strip() else None

    with path.open(encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if start <= r["date"] <= end]
    return {
        "symbol": symbol,
        "currency": asset["currency"],
        "adjustment": "as_recorded",  # say what your feed does, e.g. "split_and_dividend"
        "bars": [
            {
                "date": r["date"],
                **{k: number(r[k]) for k in ("open", "high", "low", "close", "volume")},
            }
            for r in rows
        ],
    }


def load_financials(symbol: str) -> dict[str, Any] | None:
    path = ROOT / "financials" / f"{symbol}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: Any) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if TOKEN and self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"error": "unauthorized"})
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/meta":
            return self._send(200, META)
        if url.path == "/search":
            needle = q.get("q", "").casefold()
            hits = [
                a
                for a in load_assets()
                if needle in a["symbol"].casefold() or needle in a["name"].casefold()
            ]
            return self._send(200, {"assets": hits[: int(q.get("limit", 10))]})
        if url.path == "/bars":
            bars = load_bars(q.get("symbol", ""), q.get("start", ""), q.get("end", "9999"))
            return self._send(200, bars) if bars else self._send(404, {"error": "unknown symbol"})
        if url.path == "/financials":
            statements = load_financials(q.get("symbol", ""))
            if statements:
                return self._send(200, statements)
            return self._send(404, {"error": "no statements"})
        return self._send(404, {"error": "unknown endpoint"})

    def log_message(self, *_args: Any) -> None:  # keep stdout quiet
        pass


def main() -> None:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ROOT = args.root
    print(f"realmarket example adapter on http://127.0.0.1:{args.port} serving {ROOT}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
