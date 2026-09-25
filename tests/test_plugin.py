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
    known = {config.PROVIDER_ENV, sec.CONTACT_ENV, cpi.EVDS_KEY_ENV, cpi.FRED_KEY_ENV}
    assert set(server["env"]) <= known
    referenced = {m for v in server["env"].values() for m in re.findall(r"user_config\.(\w+)", v)}
    assert referenced == set(plugin["userConfig"])


def test_api_keys_are_masked_and_yahoo_is_opt_in() -> None:
    settings = _load("plugin.json")["userConfig"]
    assert settings["evds_api_key"]["sensitive"] and settings["fred_api_key"]["sensitive"]
    assert "default" not in settings["price_provider"]  # Yahoo only when the user types it


def test_server_runs_from_the_installed_plugin() -> None:
    args = _load("plugin.json")["mcpServers"]["realmarket"]["args"]
    assert args[:2] == ["--from", "${CLAUDE_PLUGIN_ROOT}"] and args[-1] == "realmarket-mcp"
