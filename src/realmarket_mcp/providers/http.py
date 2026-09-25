"""One small HTTP GET helper for providers, mapping transport failures onto contract errors."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from realmarket_mcp.contract import ErrorCode, ToolError

Fetch = Callable[[str, Mapping[str, str]], bytes]


def get(url: str, headers: Mapping[str, str], *, source: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "realmarket-mcp", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body: bytes = response.read()
            return body
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ToolError(
                ErrorCode.RATE_LIMITED,
                f"{source} rate limit reached.",
                "Wait a minute before calling again.",
            ) from None
        raise unavailable(source, f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise unavailable(source, type(exc).__name__) from None


def unavailable(source: str, reason: str) -> ToolError:
    return ToolError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        f"{source} could not be reached ({reason}).",
        "Retry once shortly; if it keeps failing the service may be down.",
    )
