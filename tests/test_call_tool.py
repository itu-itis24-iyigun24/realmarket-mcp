"""scripts/call_tool.py: the shell bridge a model check uses to reach the tools."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "call_tool.py"
spec = importlib.util.spec_from_file_location("call_tool", SCRIPT)
assert spec is not None and spec.loader is not None
call_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(call_tool)


def test_tools_lists_the_instructions_and_every_tool(capsys: pytest.CaptureFixture[str]) -> None:
    assert call_tool.main(["--synthetic", "tools"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("SERVER INSTRUCTIONS:")
    assert "## analyze_portfolio" in out and "## explain_price_move" in out


def test_call_returns_the_client_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    assert call_tool.main(["--synthetic", "call", "search_assets", '{"query": "ORNEK"}']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["results"][0]["symbol"] == "ORNEK"


def test_bad_arguments_are_refused() -> None:
    with pytest.raises(SystemExit):
        call_tool.main(["--synthetic", "call", "search_assets", "[1]"])
