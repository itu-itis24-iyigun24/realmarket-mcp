"""Audit log: one JSON line per tool call, written on the operator's own disk.

A firm that offers realmarket to its customers must be able to show afterwards what the
assistant was given: which tool ran with which arguments, which data (provider, period, exact
data version) the figures came from, which warnings were attached, and a hash of the exact
response text the model received. Set ``REALMARKET_AUDIT_LOG`` to a file path to turn it on;
lines are appended, never rewritten. ``REALMARKET_AUDIT_FULL=1`` also stores each full
response, which makes the log larger but lets a reviewer read exactly what was shown.

What is never written: API keys, tokens and any other setting (arguments are the tool's own
parameters only). Arguments can hold a customer's portfolio amounts; the file stays on the
operator's machine, and its retention and access are the operator's responsibility.

If the log is configured but cannot be written, the tool call fails instead of answering
unlogged: an audit trail with silent gaps is not one.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from realmarket_mcp import __version__

AUDIT_ENV = "REALMARKET_AUDIT_LOG"
FULL_ENV = "REALMARKET_AUDIT_FULL"

# What the figures rest on: provider, dataset, period and the exact data version.
PROVENANCE_KEYS = (
    "provider",
    "dataset",
    "symbols",
    "period_start",
    "period_end",
    "retrieved_at",
    "data_version",
)

_lock = threading.Lock()


def audit_path(env: Mapping[str, str] | None = None) -> Path | None:
    value = (os.environ if env is None else env).get(AUDIT_ENV, "").strip()
    return Path(value).expanduser() if value else None


def full_responses(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(FULL_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _plain(value: Any) -> Any:
    """Arguments as JSON: pydantic models (a purchase lot) become their fields."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    return value


def entry(
    *,
    tool: str,
    arguments: Mapping[str, Any],
    started_at: dt.datetime,
    duration_ms: float,
    response_text: str,
    payload: Mapping[str, Any],
    full: bool,
) -> dict[str, Any]:
    ok = bool(payload.get("ok"))
    error = payload.get("error") or {}
    record: dict[str, Any] = {
        "time": started_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "server_version": __version__,
        "tool": tool,
        "arguments": _plain(dict(arguments)),
        "outcome": "ok" if ok else "error",
        "error_code": None if ok else error.get("code"),
        "duration_ms": round(duration_ms, 1),
        "provenance": [
            {k: p.get(k) for k in PROVENANCE_KEYS} for p in payload.get("provenance", [])
        ],
        "quality_flags": [
            f"{f.get('severity')}:{f.get('code')}" for f in payload.get("quality_flags", [])
        ],
        # SHA-256 of the exact text the model received; a client that keeps the response can
        # prove it is the one logged here.
        "response_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
    }
    if full:
        record["response"] = dict(payload)
    return record


def write(path: Path, record: Mapping[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
