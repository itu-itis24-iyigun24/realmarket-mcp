"""In a firm's deployment the model offers only what the firm provides, and the firm's customer
is never asked to change a setting."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import anyio
import pytest

from realmarket_mcp import config, server
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers import http_adapter, sec
from realmarket_mcp.providers.http_adapter import HttpAdapterProvider

BASE = "https://data.firm.internal/v1"
META: dict[str, Any] = {
    "api_version": 1,
    "name": "firm-feed",
    "gold_usd_symbol": "XAUUSD",
    "fx_symbol": "{base}{quote}",
}
ALWAYS = {
    "search_assets",
    "get_price_summary",
    "compare_real_return",
    "compare_assets",
    "check_data_quality",
    "get_event_reaction",
    "portfolio_real_return",
    "analyze_portfolio",
    "explain_price_move",
}


def serve_meta(meta: Mapping[str, Any] | ToolError) -> Any:
    def fetch(url: str, headers: Mapping[str, str]) -> bytes:
        assert url == f"{BASE}/meta", url
        if isinstance(meta, ToolError):
            raise meta
        return json.dumps(meta).encode()

    return fetch


@pytest.fixture
def firm(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr(http_adapter, "_meta_cache", {})
    monkeypatch.setenv(config.PROVIDER_ENV, "http")
    monkeypatch.setenv(http_adapter.URL_ENV, BASE)
    for name in (config.NEWS_PROVIDER_ENV, config.FOREIGN_SOURCES_ENV, sec.CONTACT_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def listed(monkeypatch: pytest.MonkeyPatch, meta: Mapping[str, Any] | ToolError) -> set[str]:
    monkeypatch.setattr(HttpAdapterProvider, "_default_fetch", staticmethod(serve_meta(meta)))
    return {tool.name for tool in anyio.run(server.build_server().list_tools)}


@pytest.mark.parametrize(
    ("endpoints", "extra"),
    [
        ([], set()),
        (["peers"], set()),
        (["news"], {"get_news"}),
        (["financials"], {"get_financials", "get_valuation"}),
        (["financials", "peers", "news"], {"get_financials", "get_valuation", "get_news"}),
    ],
)
def test_only_the_tools_the_adapter_serves_are_offered(
    firm: pytest.MonkeyPatch, endpoints: list[str], extra: set[str]
) -> None:
    assert listed(firm, {**META, "endpoints": endpoints}) == ALWAYS | extra


def test_an_adapter_that_declares_nothing_keeps_every_data_tool(
    firm: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        tools = listed(firm, META)
    assert tools == ALWAYS | {"get_financials", "get_valuation", "get_news"}
    assert "declares no endpoints" in caplog.text


def test_an_unreachable_adapter_at_startup_does_not_stop_the_server(
    firm: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    down = ToolError(ErrorCode.PROVIDER_UNAVAILABLE, "Adapter down.", "Retry.")
    with caplog.at_level(logging.WARNING):
        tools = listed(firm, down)
    assert tools == ALWAYS | {"get_financials", "get_valuation", "get_news"}
    assert "Adapter down." in caplog.text


def test_settings_the_operator_chose_keep_their_tools(firm: pytest.MonkeyPatch) -> None:
    firm.setenv(sec.CONTACT_ENV, "data@firm.example")
    firm.setenv(config.NEWS_PROVIDER_ENV, "gdelt")
    firm.setenv(config.FOREIGN_SOURCES_ENV, "on")
    tools = listed(firm, {**META, "endpoints": []})
    assert tools == ALWAYS | {"get_financials", "get_valuation", "get_news", "find_official_filer"}


def test_nothing_is_hidden_outside_a_firm_deployment() -> None:
    assert config.hidden_tools({config.USE_YAHOO_ENV: "true"}, frozenset()) == set()


def test_meta_endpoints_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_adapter, "_meta_cache", {})
    ok = HttpAdapterProvider(BASE, retrieved_at="t", fetch=serve_meta({**META, "endpoints": []}))
    assert ok.endpoints == frozenset()
    for bad in (["quotes"], "news", [1]):
        monkeypatch.setattr(http_adapter, "_meta_cache", {})
        with pytest.raises(ToolError) as raised:
            HttpAdapterProvider(
                BASE, retrieved_at="t", fetch=serve_meta({**META, "endpoints": bad})
            )
        assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE


def test_the_firm_model_is_told_to_say_not_available_not_which_setting(
    firm: pytest.MonkeyPatch,
) -> None:
    assert "{setting_rule}" not in server.INSTRUCTIONS
    assert "check_setup" in server.INSTRUCTIONS
    assert server.instructions() == server.FIRM_INSTRUCTIONS
    assert "check_setup" not in server.FIRM_INSTRUCTIONS
    assert "not available here" in server.FIRM_INSTRUCTIONS


def fail(error: ToolError) -> dict[str, Any]:
    def produce() -> Any:
        raise error

    payload: dict[str, Any] = json.loads(server.respond(produce).content[0].text)  # type: ignore[union-attr]
    return payload["error"]


MISSING = ToolError(
    ErrorCode.MISSING_API_KEY,
    "No inflation source for region US is configured in this deployment.",
    "The operator can add a FRED key (REALMARKET_FRED_API_KEY).",
    {"region": "US"},
)
OFF = ToolError(
    ErrorCode.UNSUPPORTED, "The data adapter does not serve news.", "Set X.", setting=True
)
REQUEST = ToolError(ErrorCode.UNSUPPORTED, "Deposits cover TRY only.", "Use a TRY report currency.")


def test_setting_errors_reach_the_firm_customer_as_not_available(
    firm: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        for error in (MISSING, OFF):
            shown = fail(error)
            assert shown["hint"] == server.FIRM_SETTING_HINT
            assert shown["message"] == error.message and shown["code"] == error.code.value
            assert "REALMARKET_" not in json.dumps(shown)
    assert "REALMARKET_FRED_API_KEY" in caplog.text  # the operator's fix is in the log
    assert fail(REQUEST)["hint"] == "Use a TRY report currency."  # about the request: kept


def test_personal_installs_keep_the_setting_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.PROVIDER_ENV, "fixture")
    assert fail(MISSING)["hint"] == MISSING.hint
    assert fail(OFF)["hint"] == "Set X."
