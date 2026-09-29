"""A shared bearer token in front of the Streamable HTTP endpoint.

A firm runs realmarket as a service its model calls over HTTP. Anyone who can reach that
address could otherwise call the tools, and through them read the firm's licensed data. With
``REALMARKET_SERVER_TOKEN`` set, every HTTP request must carry ``Authorization: Bearer
<token>``; any other request gets 401 before it reaches the MCP server. Only the system that
runs the firm's model knows the token.

This authenticates the calling system, not the firm's customer: who the customer is stays
the firm's application's business. stdio (a desktop client starting the server) has no
network address and is unaffected.

Exposure is closed by default: serving on an address other than loopback without a token is
refused at startup, unless the operator says so explicitly (``--allow-unauthenticated``, for
a deployment whose gateway authenticates every request itself).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

TOKEN_ENV = "REALMARKET_SERVER_TOKEN"
MIN_TOKEN_LENGTH = 32
GENERATE_HINT = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class AuthConfigError(ValueError):
    """The server must not start with this configuration; the message says what to change."""


def server_token(env: Mapping[str, str] | None = None) -> str | None:
    """The configured token, or None. A token too short to resist guessing is refused."""
    token = (os.environ if env is None else env).get(TOKEN_ENV, "").strip()
    if not token:
        return None
    if len(token) < MIN_TOKEN_LENGTH:
        raise AuthConfigError(
            f"{TOKEN_ENV} is shorter than {MIN_TOKEN_LENGTH} characters. Generate one with: "
            f"{GENERATE_HINT}"
        )
    return token


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a host name that is not "localhost": treat as reachable


def check_exposure(host: str, token: str | None, *, allow_unauthenticated: bool) -> None:
    """Refuse to serve beyond this machine without a token, unless explicitly allowed."""
    if token or is_loopback(host) or allow_unauthenticated:
        return
    raise AuthConfigError(
        f"Serving on {host} would let anyone who can reach it call the tools. Set {TOKEN_ENV} "
        f"(generate one with: {GENERATE_HINT}) and give it to the system that runs the model, "
        "or, if your gateway authenticates every request itself, pass --allow-unauthenticated."
    )


class BearerTokenMiddleware:
    """ASGI middleware: HTTP requests without the right bearer token get 401. Lifespan and
    other non-HTTP scopes pass through, so the wrapped app still starts and stops."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._authorized(scope):
            await self._app(scope, receive, send)
            return
        body = json.dumps({"error": "unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="realmarket"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, scope: Scope) -> bool:
        values = [v for k, v in scope.get("headers", ()) if k.lower() == b"authorization"]
        if len(values) != 1:  # none, or ambiguous
            return False
        scheme, _, credentials = bytes(values[0]).strip().partition(b" ")
        if scheme.lower() != b"bearer":
            return False
        # Constant-time comparison: the time taken says nothing about how much matched.
        return hmac.compare_digest(credentials.strip(), self._expected)
