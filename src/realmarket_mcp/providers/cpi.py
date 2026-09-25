"""Official CPI sources: FRED (United States) and TCMB EVDS (Turkey).

Both need a free API key, read from the environment. HTTP goes through one injectable
``fetch`` callable so the parsers are tested offline. Response formats were written from the
providers' public documentation; verify against the live APIs before relying on them.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries, series_from_rows

Fetch = Callable[[str, Mapping[str, str]], bytes]

FRED_KEY_ENV = "REALMARKET_FRED_API_KEY"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = "CPIAUCNS"  # CPI-U, all items, US city average, not seasonally adjusted

EVDS_KEY_ENV = "REALMARKET_EVDS_API_KEY"
EVDS_URL_ENV = "REALMARKET_EVDS_BASE_URL"
EVDS_URL = "https://evds2.tcmb.gov.tr/service/evds/"
EVDS_SERIES = "TP.FG.J0"  # TÜFE, general index (2003=100)


def http_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "realmarket-mcp", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body: bytes = response.read()
            return body
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ToolError(
                ErrorCode.RATE_LIMITED,
                "The CPI provider's rate limit was reached.",
                "Wait a minute before calling again.",
            ) from None
        if exc.code in {401, 403}:
            raise ToolError(
                ErrorCode.MISSING_API_KEY,
                f"The CPI provider rejected the API key (HTTP {exc.code}).",
                "Check the API key environment variable in the MCP server's configuration.",
            ) from None
        raise _unavailable(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise _unavailable(type(exc).__name__) from None


def _unavailable(reason: str) -> ToolError:
    return ToolError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        f"The CPI provider could not be reached ({reason}).",
        "Retry once shortly. Offline alternative: supply the series as a CSV file "
        "(see the realmarket://methodology resource).",
    )


def _bad_payload(source: str, exc: Exception) -> ToolError:
    return ToolError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        f"{source} returned data in an unexpected format ({type(exc).__name__}).",
        "The provider may have changed its API. Use a CSV CPI file meanwhile and report the issue.",
    )


def _require_key(env: Mapping[str, str], name: str, region: str, signup: str) -> str:
    key = env.get(name, "").strip()
    if not key:
        raise ToolError(
            ErrorCode.MISSING_API_KEY,
            f"No CPI source is configured for region {region}.",
            f"Set {name} (free key: {signup}) in the MCP server's environment, or set "
            f"REALMARKET_CPI_CSV_{region} to a monthly CPI CSV file.",
            {"region": region},
        )
    return key


def fred_us_cpi(
    start: dt.date, *, env: Mapping[str, str], fetch: Fetch = http_fetch, retrieved_at: str
) -> CpiSeries:
    key = _require_key(env, FRED_KEY_ENV, "US", "https://fred.stlouisfed.org/docs/api/api_key.html")
    query = urllib.parse.urlencode(
        {
            "series_id": FRED_SERIES,
            "api_key": key,
            "file_type": "json",
            "observation_start": dt.date(start.year, start.month, 1).isoformat(),
        }
    )
    body = fetch(f"{FRED_URL}?{query}", {})
    try:
        observations: list[dict[str, Any]] = json.loads(body)["observations"]
        rows = [(obs["date"], obs["value"]) for obs in observations]
        return series_from_rows(
            rows, region="US", source="fred", series_id=FRED_SERIES, retrieved_at=retrieved_at
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _bad_payload("FRED", exc) from None


def evds_tr_cpi(
    start: dt.date,
    end: dt.date,
    *,
    env: Mapping[str, str],
    fetch: Fetch = http_fetch,
    retrieved_at: str,
) -> CpiSeries:
    key = _require_key(env, EVDS_KEY_ENV, "TR", "https://evds2.tcmb.gov.tr")
    base = env.get(EVDS_URL_ENV, EVDS_URL)
    if not base.endswith("/"):
        base += "/"
    url = (
        f"{base}series={EVDS_SERIES}&startDate=01-{start.month:02d}-{start.year}"
        f"&endDate=01-{end.month:02d}-{end.year}&type=json&frequency=5"
    )
    body = fetch(url, {"key": key})  # EVDS expects the key as a request header
    column = EVDS_SERIES.replace(".", "_")
    try:
        items: list[dict[str, Any]] = json.loads(body)["items"]
        rows = [(str(item["Tarih"]), str(item.get(column) or "")) for item in items]
        return series_from_rows(
            rows, region="TR", source="evds", series_id=EVDS_SERIES, retrieved_at=retrieved_at
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _bad_payload("EVDS", exc) from None
