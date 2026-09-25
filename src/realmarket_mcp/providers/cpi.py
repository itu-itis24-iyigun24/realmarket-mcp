"""Official CPI sources: FRED (United States) and TCMB EVDS (Turkey).

Both need a free API key, read from the environment. HTTP goes through one injectable
``fetch`` callable so the parsers are tested offline. Both response formats were checked
against the live APIs on 2026-09-25 (see docs/providers.md).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries, series_from_rows
from realmarket_mcp.providers import http

Fetch = Callable[[str, Mapping[str, str]], bytes]

FRED_KEY_ENV = "REALMARKET_FRED_API_KEY"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = "CPIAUCNS"  # CPI-U, all items, US city average, not seasonally adjusted

EVDS_KEY_ENV = "REALMARKET_EVDS_API_KEY"
EVDS_URL_ENV = "REALMARKET_EVDS_BASE_URL"
# evds2.tcmb.gov.tr now redirects to evds3; the API gateway is this path (verified: it
# answers 401 "Invalid API Key" to a bad key, while other paths serve the web app).
EVDS_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
# TÜFE general index, 2003=100, chained across TÜİK's 2026 rebasing to 2025=100. The former
# code TP.FG.J0 was archived with its last value at 2026-01 (verified live on 2026-09-25); the
# two codes are identical through 2026-01.
EVDS_SERIES = "TP.GENENDEKS.T1"


def http_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": http.USER_AGENT, **headers})
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
    key = _require_key(env, EVDS_KEY_ENV, "TR", "https://evds3.tcmb.gov.tr")
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


# ---------------------------------------------------------------------------- keyless sources
# Both verified live on 2026-09-25 (see docs/providers.md).

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
OECD_URL = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
# ISO 3166 alpha-2 -> OECD alpha-3 for OECD members. Monthly national CPI was verified for TR,
# US, DE and GB; the OECD does not publish every member's monthly series in this dataflow.
OECD_REGIONS = {
    "AT": "AUT",
    "AU": "AUS",
    "BE": "BEL",
    "CA": "CAN",
    "CH": "CHE",
    "CL": "CHL",
    "CO": "COL",
    "CR": "CRI",
    "CZ": "CZE",
    "DE": "DEU",
    "DK": "DNK",
    "EE": "EST",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "GB": "GBR",
    "GR": "GRC",
    "HU": "HUN",
    "IE": "IRL",
    "IL": "ISR",
    "IS": "ISL",
    "IT": "ITA",
    "JP": "JPN",
    "KR": "KOR",
    "LT": "LTU",
    "LU": "LUX",
    "LV": "LVA",
    "MX": "MEX",
    "NL": "NLD",
    "NO": "NOR",
    "NZ": "NZL",
    "PL": "POL",
    "PT": "PRT",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
    "TR": "TUR",
    "US": "USA",
}


def fred_us_cpi_keyless(
    start: dt.date, *, fetch: Fetch | None = None, retrieved_at: str
) -> CpiSeries:
    """The same CPIAUCNS series as the API, from FRED's public CSV download (no key)."""
    query = urllib.parse.urlencode(
        {"id": FRED_SERIES, "cosd": dt.date(start.year, start.month, 1).isoformat()}
    )
    get = fetch or (lambda url, headers: http.get(url, headers, source="FRED"))
    body = get(f"{FRED_CSV_URL}?{query}", {})
    try:
        rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))
        if not rows or rows[0][:1] != ["observation_date"]:
            raise ValueError("unexpected header")
        return series_from_rows(
            ((r[0], r[1]) for r in rows[1:] if len(r) >= 2),
            region="US",
            source="fred_csv",
            series_id=FRED_SERIES,
            retrieved_at=retrieved_at,
        )
    except (IndexError, UnicodeDecodeError, ValueError) as exc:
        raise _bad_payload("FRED", exc) from None


def oecd_cpi(
    region: str, start: dt.date, *, fetch: Fetch | None = None, retrieved_at: str
) -> CpiSeries:
    """National monthly CPI (2015=100, not seasonally adjusted) from the OECD's public API."""
    iso3 = OECD_REGIONS[region]
    key = f"{iso3}.M.N.CPI.IX._T.N._Z"
    query = urllib.parse.urlencode(
        {
            "startPeriod": f"{start.year:04d}-{start.month:02d}",
            "dimensionAtObservation": "AllDimensions",
            "format": "csv",
        }
    )
    not_found = ToolError(
        ErrorCode.UNSUPPORTED,
        f"The OECD publishes no monthly CPI for {region} in this dataset.",
        f"Set REALMARKET_CPI_CSV_{region} to a monthly CPI CSV file (columns: month,cpi_index).",
        {"region": region},
    )
    get = fetch or (lambda url, headers: http.get(url, headers, source="OECD", not_found=not_found))
    body = get(f"{OECD_URL}/{key}?{query}", {})
    try:
        records = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
        return series_from_rows(
            ((r["TIME_PERIOD"], r["OBS_VALUE"]) for r in records),
            region=region,
            source="oecd",
            series_id=f"OECD PRICES_ALL {iso3} CPI 2015=100",
            retrieved_at=retrieved_at,
        )
    except (KeyError, UnicodeDecodeError, ValueError) as exc:
        raise _bad_payload("OECD", exc) from None
