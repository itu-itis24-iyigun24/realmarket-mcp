"""The Claude plugin manifest must stay in step with the package it launches."""

from __future__ import annotations

import json
import re
from pathlib import Path

from realmarket_mcp import __version__, config
from realmarket_mcp.providers import cpi, sec

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((ROOT / ".claude-plugin" / name).read_text(encoding="utf-8"))


def test_versions_match_the_package() -> None:
    marketplace = _load("marketplace.json")
    assert _load("plugin.json")["version"] == __version__
    assert [p["version"] for p in marketplace["plugins"]] == [__version__]


def test_server_env_uses_known_variables_and_declared_settings() -> None:
    plugin = _load("plugin.json")
    server = plugin["mcpServers"]["realmarket"]
    known = {config.USE_YAHOO_ENV, sec.CONTACT_ENV, cpi.EVDS_KEY_ENV, cpi.FRED_KEY_ENV}
    assert set(server["env"]) <= known
    referenced = {m for v in server["env"].values() for m in re.findall(r"user_config\.(\w+)", v)}
    assert referenced == set(plugin["userConfig"])


def test_api_keys_are_masked_and_yahoo_is_opt_in() -> None:
    settings = _load("plugin.json")["userConfig"]
    assert settings["evds_api_key"]["sensitive"] and settings["fred_api_key"]["sensitive"]
    assert settings["use_yahoo"]["type"] == "boolean"
    assert settings["use_yahoo"].get("default", False) is False  # Yahoo only when ticked


def test_server_runs_from_the_installed_plugin() -> None:
    args = _load("plugin.json")["mcpServers"]["realmarket"]["args"]
    assert args[:2] == ["--from", "${CLAUDE_PLUGIN_ROOT}"] and args[-1] == "realmarket-mcp"


def _build_script():  # type: ignore[no-untyped-def]
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_mcpb", ROOT / "scripts" / "build_mcpb.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_desktop_extension_manifest_matches_the_server() -> None:
    import anyio

    from realmarket_mcp.server import build_server

    manifest = _build_script().manifest()
    server = build_server()
    assert manifest["version"] == __version__
    assert [t["name"] for t in manifest["tools"]] == [t.name for t in anyio.run(server.list_tools)]
    for prompt in manifest["prompts"]:
        for argument in prompt["arguments"]:
            assert f"${{arguments.{argument}}}" in prompt["text"]
    assert (
        manifest["server"]["mcp_config"]["env"]
        == _load("plugin.json")["mcpServers"]["realmarket"]["env"]
    )


def test_desktop_and_plugin_settings_agree() -> None:
    desktop = _build_script().manifest()["user_config"]
    plugin = _load("plugin.json")["userConfig"]
    assert set(desktop) == set(plugin)
    for key, spec in plugin.items():
        assert desktop[key]["title"] == spec["title"]
        assert desktop[key].get("sensitive", False) == spec.get("sensitive", False)
        assert desktop[key].get("default") == spec.get("default")
    assert desktop["use_yahoo"]["default"] is False  # Yahoo stays opt-in here too
