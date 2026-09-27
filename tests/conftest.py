"""Test-suite guard: tests run offline.

Any attempt to open a network connection fails loudly, so a test can never depend on a live
provider (flaky, slow, and it would silently spend a user's API quota). Providers are tested
against recorded fixtures instead. This is an accident guard, not a security boundary.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest


class NetworkAccessInTests(RuntimeError):
    pass


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkAccessInTests("tests must not use the network; use a recorded fixture")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


@pytest.fixture(autouse=True)
def _no_provider_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Providers space their requests to respect rate limits; tests must not wait for real."""
    from realmarket_mcp.providers import gdelt

    monkeypatch.setattr(gdelt, "MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(gdelt, "RETRY_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(gdelt, "_last_request", 0.0)


@pytest.fixture(autouse=True)
def _no_user_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's own settings or keys (they would reach the network)."""
    import os

    for name in [n for n in os.environ if n.startswith("REALMARKET_")]:
        monkeypatch.delenv(name)
