"""The HTTP endpoint behind a bearer token, and closed exposure by default."""

from __future__ import annotations

from typing import Any

import anyio
import pytest
from starlette.testclient import TestClient

from realmarket_mcp import http_auth, server
from realmarket_mcp.http_auth import AuthConfigError, BearerTokenMiddleware

TOKEN = "t" * 40
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"accept": "application/json, text/event-stream"}


def test_the_token_comes_from_the_environment_and_must_be_long() -> None:
    assert http_auth.server_token({}) is None
    assert http_auth.server_token({http_auth.TOKEN_ENV: f"  {TOKEN} "}) == TOKEN
    with pytest.raises(AuthConfigError) as raised:
        http_auth.server_token({http_auth.TOKEN_ENV: "hunter2xyz"})
    assert "token_urlsafe" in str(raised.value)
    assert "hunter2xyz" not in str(raised.value)  # the value is never echoed


@pytest.mark.parametrize(
    ("host", "loopback"),
    [("127.0.0.1", True), ("::1", True), ("localhost", True), ("0.0.0.0", False),
     ("10.0.0.5", False), ("realmarket.internal", False)],
)  # fmt: skip
def test_loopback_hosts(host: str, loopback: bool) -> None:
    assert http_auth.is_loopback(host) is loopback


def test_exposure_beyond_this_machine_needs_a_token_or_an_explicit_choice() -> None:
    http_auth.check_exposure("127.0.0.1", None, allow_unauthenticated=False)
    http_auth.check_exposure("0.0.0.0", TOKEN, allow_unauthenticated=False)
    http_auth.check_exposure("0.0.0.0", None, allow_unauthenticated=True)
    with pytest.raises(AuthConfigError) as raised:
        http_auth.check_exposure("0.0.0.0", None, allow_unauthenticated=False)
    assert http_auth.TOKEN_ENV in str(raised.value)


def call(headers: list[tuple[bytes, bytes]], scope_type: str = "http") -> tuple[bool, list[Any]]:
    reached: list[bool] = []
    sent: list[Any] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        reached.append(True)

    async def send(message: Any) -> None:
        sent.append(message)

    async def receive() -> Any:
        return {"type": "http.request"}

    middleware = BearerTokenMiddleware(app, TOKEN)
    scope = {"type": scope_type, "headers": headers}
    anyio.run(middleware, scope, receive, send)
    return bool(reached), sent


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ([(b"authorization", f"Bearer {TOKEN}".encode())], True),
        ([(b"authorization", f"bearer {TOKEN}".encode())], True),  # the scheme is case-blind
        ([], False),
        ([(b"authorization", b"Bearer wrong")], False),
        ([(b"authorization", f"Basic {TOKEN}".encode())], False),
        ([(b"authorization", f"Bearer {TOKEN}x".encode())], False),
        ([(b"authorization", f"Bearer {TOKEN}".encode()), (b"authorization", b"Bearer x")], False),
    ],
)
def test_only_the_right_bearer_token_reaches_the_server(
    headers: list[tuple[bytes, bytes]], allowed: bool
) -> None:
    reached, sent = call(headers)
    assert reached is allowed
    if not allowed:
        assert sent[0]["status"] == 401
        assert (b"www-authenticate", b'Bearer realm="realmarket"') in sent[0]["headers"]
        assert TOKEN.encode() not in b"".join(m.get("body", b"") for m in sent)


def test_lifespan_passes_through_so_the_server_can_start() -> None:
    reached, sent = call([], scope_type="lifespan")
    assert reached and not sent


def test_the_real_endpoint_refuses_without_the_token_and_serves_with_it() -> None:
    app = server.http_app(server.build_server(), "127.0.0.1", TOKEN).app
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        refused = client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)
        assert refused.status_code == 401
        auth = {**MCP_HEADERS, "authorization": f"Bearer {TOKEN}"}
        served = client.post("/mcp", json=INITIALIZE, headers=auth)
        assert served.status_code == 200, served.text
        assert "realmarket" in served.text  # the initialize result names the server


def test_without_a_token_the_endpoint_is_unchanged() -> None:
    app = server.http_app(server.build_server(), "127.0.0.1", None).app
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS).status_code == 200


def test_main_refuses_to_expose_the_server_without_a_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(http_auth.TOKEN_ENV, raising=False)
    served: list[int] = []
    monkeypatch.setattr(server._HttpApp, "run", lambda self, port: served.append(port))
    with pytest.raises(SystemExit) as exited:
        server.main(["--transport", "http", "--host", "0.0.0.0"])
    assert exited.value.code == 2 and http_auth.TOKEN_ENV in capsys.readouterr().err

    monkeypatch.setenv(http_auth.TOKEN_ENV, "short")
    with pytest.raises(SystemExit):
        server.main(["--transport", "http", "--host", "0.0.0.0"])

    monkeypatch.setenv(http_auth.TOKEN_ENV, TOKEN)
    server.main(["--transport", "http", "--host", "0.0.0.0", "--port", "9001"])
    monkeypatch.delenv(http_auth.TOKEN_ENV)
    server.main(["--transport", "http", "--host", "0.0.0.0", "--allow-unauthenticated"])
    server.main(["--transport", "http"])  # loopback without a token, as before
    assert served == [9001, 8000, 8000]
