"""Audit log: one line per tool call, on the operator's disk, with no secrets and no gaps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import anyio
import pytest

from realmarket_mcp import audit
from realmarket_mcp.config import FIXTURE_DIR_ENV, PROVIDER_ENV
from realmarket_mcp.providers import cpi
from realmarket_mcp.server import build_server

FIXTURES = Path(__file__).parent / "fixtures" / "basic"


def _call(name: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
    async def run() -> Any:
        return await build_server().call_tool(name, arguments)

    result = anyio.run(run)
    return result.content[0].text, result.structured_content, bool(result.is_error)


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PROVIDER_ENV, "fixture")
    monkeypatch.setenv(FIXTURE_DIR_ENV, str(FIXTURES))
    path = tmp_path / "logs" / "audit.jsonl"  # the directory is created on first write
    monkeypatch.setenv(audit.AUDIT_ENV, str(path))
    return path


def test_each_call_is_one_line_tied_to_the_exact_response(log_file: Path) -> None:
    text, payload, is_error = _call("get_price_summary", {"symbol": "TTT", "start": "2024-01-01"})
    assert not is_error
    _call("get_price_summary", {"symbol": "NOPE"})
    ok, failed = _lines(log_file)
    assert ok["tool"] == "get_price_summary" and ok["outcome"] == "ok"
    assert ok["arguments"]["symbol"] == "TTT" and ok["arguments"]["start"] == "2024-01-01"
    assert ok["arguments"]["period"]  # defaults are recorded too: the call is reproducible
    assert ok["response_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert [p["data_version"] for p in ok["provenance"]] == [
        p["data_version"] for p in payload["provenance"]
    ]
    assert "response" not in ok  # only with REALMARKET_AUDIT_FULL
    assert (failed["outcome"], failed["error_code"]) == ("error", "unknown_symbol")


def test_full_responses_and_no_secrets(log_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(audit.FULL_ENV, "1")
    monkeypatch.setenv(cpi.EVDS_KEY_ENV, "secret-evds-key-123")
    _, payload, _ = _call("check_setup", {})
    assert payload["data"]["audit_log"] == {"enabled": True, "full_responses": True}
    (line,) = _lines(log_file)
    assert line["response"] == payload
    assert "secret-evds-key-123" not in log_file.read_text()


def test_an_unwritable_log_refuses_the_answer(
    log_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = log_file.parent
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("a file where the log directory should be")
    _, payload, is_error = _call("search_assets", {"query": "Alpha"})
    assert is_error and payload["error"]["code"] == "internal"
    assert audit.AUDIT_ENV in payload["error"]["hint"]


def test_off_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROVIDER_ENV, "fixture")
    monkeypatch.setenv(FIXTURE_DIR_ENV, str(FIXTURES))
    _, payload, _ = _call("check_setup", {})
    assert payload["data"]["audit_log"] == {"enabled": False, "full_responses": False}
    assert not list(tmp_path.iterdir())
