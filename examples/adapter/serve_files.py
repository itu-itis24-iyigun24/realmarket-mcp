"""Example realmarket data adapter (API v1), serving local files. Standard library only.

A firm replaces the `load_*` functions with calls to its licensed data feed and keeps the
HTTP layer. Run it, then point realmarket at it:

    python examples/adapter/serve_files.py --root tests/fixtures/basic --port 8765
    REALMARKET_PRICE_PROVIDER=http REALMARKET_HTTP_URL=http://127.0.0.1:8765 realmarket-mcp

File layout under --root (the same as realmarket's test fixtures):
    meta.json                 optional; the /meta body (defaults to META below)
    assets.json               [{"symbol", "name", "asset_class", "currency", "exchange",
                                "adjustment"?}]
    bars/<SYMBOL>.csv         date,open,high,low,close,volume[,price_close]   (empty = missing)
    actions/<SYMBOL>.json     optional; {"dividends": [...], "splits": [...]} for /bars
    financials/<SYMBOL>.json  optional; the /financials response body
    peers/<SYMBOL>.json       optional; {"industry": <body>, "sector": <body>} for /peers
    news.json                 optional; {"articles": [...]}, the firm's news or KAP feed

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
    columns = ("open", "high", "low", "close", "volume", "price_close")
    actions_path = ROOT / "actions" / f"{symbol}.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8")) if actions_path.exists() else {}
    return {
        "symbol": symbol,
        "currency": asset["currency"],
        # say what your feed does, e.g. "split_and_dividend"
        "adjustment": asset.get("adjustment", "as_recorded"),
        "bars": [{"date": r["date"], **{k: number(r[k]) for k in columns if k in r}} for r in rows],
        "dividends": [d for d in actions.get("dividends", []) if start <= d["date"] <= end],
        "splits": [d for d in actions.get("splits", []) if start <= d["date"] <= end],
    }


def load_news(query: str, start: str, end: str, limit: int) -> dict[str, Any] | None:
    path = ROOT / "news.json"
    if not path.exists():
        return None  # this adapter serves no news: /news answers 404
    articles = json.loads(path.read_text(encoding="utf-8"))["articles"]
    needle = query.casefold()
    hits = [
        a for a in articles if needle in a["title"].casefold() and start <= a["published_at"] <= end
    ]
    return {"articles": hits[:limit]}


def load_peers(symbol: str, level: str) -> dict[str, Any] | None:
    path = ROOT / "peers" / f"{symbol}.json"
    return json.loads(path.read_text(encoding="utf-8")).get(level) if path.exists() else None


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
            meta = ROOT / "meta.json"
            return self._send(
                200, json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else META
            )
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
        if url.path == "/peers":
            peers = load_peers(q.get("symbol", ""), q.get("level", "industry"))
            return self._send(200, peers) if peers else self._send(404, {"error": "no peers"})
        if url.path == "/news":
            news = load_news(
                q.get("q", ""), q.get("start", ""), q.get("end", "9999"), int(q.get("limit", 20))
            )
            return self._send(200, news) if news else self._send(404, {"error": "no news"})
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
