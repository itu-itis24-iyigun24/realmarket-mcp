"""One small HTTP GET helper for providers, mapping transport failures onto contract errors."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from realmarket_mcp import __version__
from realmarket_mcp.contract import ErrorCode, ToolError

Fetch = Callable[[str, Mapping[str, str]], bytes]

# A descriptive agent with a contact URL. Some services (FRED's CSV download, verified
# 2026-09-25) reset connections for unrecognised bare agent strings.
USER_AGENT = (
    f"realmarket-mcp/{__version__} (+https://github.com/itu-itis24-iyigun24/realmarket-mcp)"
)


def get(
    url: str,
    headers: Mapping[str, str],
    *,
    source: str,
    timeout: float = 30,
    not_found: ToolError | None = None,
) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
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
        if exc.code == 404 and not_found is not None:
            raise not_found from None
        raise unavailable(source, f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise unavailable(source, type(exc).__name__) from None


def unavailable(source: str, reason: str) -> ToolError:
    return ToolError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        f"{source} could not be reached ({reason}).",
        "Retry once shortly; if it keeps failing the service may be down.",
    )
