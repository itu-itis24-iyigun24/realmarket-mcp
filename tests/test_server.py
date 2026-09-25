"""End-to-end through the MCP server object, in process (no transport, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest

from realmarket_mcp import config
from realmarket_mcp.config import FIXTURE_DIR_ENV, PROVIDER_ENV
from realmarket_mcp.server import build_server

FIXTURES = Path(__file__).parent / "fixtures" / "basic"


def _call(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    async def run() -> Any:
        return await build_server().call_tool(name, arguments)

    result = anyio.run(run)
    payload = json.loads(result.content[0].text)
    assert payload == result.structured_content
    return payload, bool(result.is_error)


@pytest.fixture
def fixture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PROVIDER_ENV, "fixture")
    monkeypatch.setenv(FIXTURE_DIR_ENV, str(FIXTURES))


def test_tools_are_listed_with_descriptions_and_read_only_hints() -> None:
    listed = anyio.run(build_server().list_tools)
    by_name = {tool.name: tool for tool in listed}
    assert set(by_name) == {
        "search_assets",
        "get_price_summary",
        "compare_real_return",
        "compare_assets",
        "check_data_quality",
        "get_news",
        "get_event_reaction",
        "portfolio_real_return",
        "get_financials",
    }
    for tool in listed:
        assert tool.description and len(tool.description) > 80
        assert tool.annotations is not None and tool.annotations.read_only_hint is True


def test_search_then_summary_round_trip(fixture_env: None) -> None:
    found, is_error = _call("search_assets", {"query": "Alpha"})
    assert not is_error
    symbol = found["data"]["results"][0]["symbol"]

    summary, is_error = _call("get_price_summary", {"symbol": symbol, "start": "2024-01-01"})
    assert not is_error
    assert summary["ok"] is True
    assert summary["data"]["total_return"] == pytest.approx(0.2)
    assert summary["provenance"][0]["provider"] == "fixture"


def test_errors_come_back_as_error_envelopes(fixture_env: None) -> None:
    payload, is_error = _call("get_price_summary", {"symbol": "NOPE"})
    assert is_error
    assert payload["error"]["code"] == "unknown_symbol"
    assert payload["error"]["retryable"] is False


def test_missing_configuration_is_explained_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.delenv(FIXTURE_DIR_ENV, raising=False)
    payload, is_error = _call("search_assets", {"query": "x"})
    assert is_error
    assert PROVIDER_ENV in payload["error"]["hint"]


def test_prompts_and_methodology_are_published() -> None:
    server = build_server()
    prompts = {p.name for p in anyio.run(server.list_prompts)}
    assert prompts == {"single_asset_report", "real_return_report", "comparison_report"}
    resources = {str(r.uri) for r in anyio.run(server.list_resources)}
    assert resources == {"realmarket://methodology"}


def test_compare_assets_validates_list_length_before_running(fixture_env: None) -> None:
    async def run() -> object:
        return await build_server().call_tool("compare_assets", {"symbols": ["AAA"]})

    with pytest.raises(Exception, match="symbols"):
        anyio.run(run)


def test_real_return_through_the_server_with_a_csv_cpi(
    fixture_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cpi = tmp_path / "tr.csv"
    cpi.write_text("month,cpi_index\n2023-01,100\n2024-01,160\n")
    monkeypatch.setenv("REALMARKET_CPI_CSV_TR", str(cpi))
    payload, is_error = _call(
        "compare_real_return", {"symbol": "TTT", "start": "2023-01-01", "end": "2024-01-02"}
    )
    assert not is_error
    assert payload["data"]["real_return"] == pytest.approx(0.25)


def test_portfolio_through_the_server(
    fixture_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cpi = tmp_path / "tr.csv"
    cpi.write_text("month,cpi_index\n2023-01,100\n2024-01,160\n")
    monkeypatch.setenv("REALMARKET_CPI_CSV_TR", str(cpi))
    payload, is_error = _call(
        "portfolio_real_return",
        {"purchases": [{"symbol": "TTT", "date": "2023-01-02", "amount": 1000}]},
    )
    assert not is_error, payload
    assert payload["data"]["invested"] == 1000.0


def test_settings_a_host_left_empty_or_unsubstituted_are_dropped() -> None:
    env = {
        "REALMARKET_SEC_CONTACT": "${user_config.sec_contact}",
        "REALMARKET_PRICE_PROVIDER": "  ",
        "REALMARKET_FRED_API_KEY": "abc",
        "PATH": "",
    }
    assert sorted(config.drop_unset_values(env)) == [
        "REALMARKET_PRICE_PROVIDER",
        "REALMARKET_SEC_CONTACT",
    ]
    assert env == {"REALMARKET_FRED_API_KEY": "abc", "PATH": ""}
