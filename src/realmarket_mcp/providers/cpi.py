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
from realmarket_mcp.deposits import DepositRates, rates_from_rows
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
    request = http.build_request(url, headers)  # the API key never follows a redirect
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
    return evds_monthly_index(
        EVDS_SERIES, "TR", "evds", start, end, env=env, fetch=fetch, retrieved_at=retrieved_at
    )


# TCMB's residential property price index (KFE, EVDS group bie_kfe, monthly from 2010,
# verified 2026-09-27): Türkiye and the three largest cities.
EVDS_HOUSE_SERIES = {
    "TR": "TP.KFE.TR",
    "ISTANBUL": "TP.KFE.TR10",
    "ANKARA": "TP.KFE.TR51",
    "IZMIR": "TP.KFE.TR31",
}


def evds_house_prices(
    area: str,
    start: dt.date,
    end: dt.date,
    *,
    env: Mapping[str, str],
    fetch: Fetch = http_fetch,
    retrieved_at: str,
) -> CpiSeries:
    series = EVDS_HOUSE_SERIES.get(area.upper())
    if series is None:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"No house price index for {area!r}.",
            f"Use one of {', '.join(EVDS_HOUSE_SERIES)}.",
        )
    if not env.get(EVDS_KEY_ENV, "").strip():
        raise ToolError(
            ErrorCode.MISSING_API_KEY,
            "The house price index needs a TCMB EVDS key.",
            f"Set {EVDS_KEY_ENV} (free key: https://evds3.tcmb.gov.tr), the 'TCMB EVDS API key' "
            "setting of the plugin or extension, then restart the app.",
        )
    return evds_monthly_index(
        series,
        area.upper(),
        "evds_house_price",
        start,
        end,
        env=env,
        fetch=fetch,
        retrieved_at=retrieved_at,
    )


def evds_monthly_index(
    series: str,
    region: str,
    source: str,
    start: dt.date,
    end: dt.date,
    *,
    env: Mapping[str, str],
    fetch: Fetch = http_fetch,
    retrieved_at: str,
) -> CpiSeries:
    """A monthly index level series from TCMB EVDS (CPI, house prices)."""
    key = _require_key(env, EVDS_KEY_ENV, "TR", "https://evds3.tcmb.gov.tr")
    base = env.get(EVDS_URL_ENV, EVDS_URL)
    if not base.endswith("/"):
        base += "/"
    url = (
        f"{base}series={series}&startDate=01-{start.month:02d}-{start.year}"
        f"&endDate=01-{end.month:02d}-{end.year}&type=json&frequency=5"
    )
    body = fetch(url, {"key": key})  # EVDS expects the key as a request header
    column = series.replace(".", "_")
    try:
        items: list[dict[str, Any]] = json.loads(body)["items"]
        rows = [(str(item["Tarih"]), str(item.get(column) or "")) for item in items]
    except (KeyError, TypeError, ValueError) as exc:
        raise _bad_payload("EVDS", exc) from None
    if not any(value.strip() for _, value in rows):
        raise ToolError(
            ErrorCode.NO_DATA_IN_RANGE,
            f"EVDS has no {series} values for {start:%Y-%m} to {end:%Y-%m}.",
            "The series may start later than the requested period; use a later start date.",
        )
    try:
        return series_from_rows(
            rows, region=region, source=source, series_id=series, retrieved_at=retrieved_at
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _bad_payload("EVDS", exc) from None


# Weighted average annual rate on new TL deposits with maturity up to 3 months (weekly, flow),
# which covers the common 32-day deposit (EVDS data group bie_mt100h, verified 2026-09-27).
# TCMB's weekly weighted average rates on new TL deposits, EVDS group bie_mt100h (verified
# 2026-09-27). The usual saver's product, a 32-day deposit, falls in the "up to 3 months"
# bucket (1-3 months; the "up to 1 month" bucket pays less throughout). Savings deposits
# (individuals) are the saver's comparison; the all-deposits series also includes commercial
# deposits, which paid up to 5 points more in 2024. Savings rates start in July 2012; a period
# that starts earlier uses the all-deposits series throughout rather than a spliced one.
EVDS_DEPOSIT_SERIES: dict[str, tuple[tuple[str, dt.date | None], ...]] = {
    "TRY": (("TP.TRYTAS.MT02", dt.date(2012, 7, 6)), ("TP.TRY.MT02", None)),
}


def evds_deposit_rates(
    currency: str,
    start: dt.date,
    end: dt.date,
    *,
    env: Mapping[str, str],
    fetch: Fetch = http_fetch,
    retrieved_at: str,
) -> DepositRates:
    choices = EVDS_DEPOSIT_SERIES.get(currency.upper())
    if choices is None:
        raise ToolError(
            ErrorCode.UNSUPPORTED,
            f"No deposit rate series for {currency}.",
            "Deposit comparisons cover Turkish lira (TRY) only.",
            {"currency": currency},
        )
    key = env.get(EVDS_KEY_ENV, "").strip()
    if not key:
        raise ToolError(
            ErrorCode.MISSING_API_KEY,
            "Deposit rates need a TCMB EVDS key.",
            f"Set {EVDS_KEY_ENV} (free key: https://evds3.tcmb.gov.tr), the 'TCMB EVDS API key' "
            "setting of the plugin or extension, then restart the app.",
        )
    base = env.get(EVDS_URL_ENV, EVDS_URL)
    if not base.endswith("/"):
        base += "/"
    first = start - dt.timedelta(days=14)  # the rate in force on the start day
    series = next(code for code, since in choices if since is None or since <= first)
    url = f"{base}series={series}&startDate={first:%d-%m-%Y}&endDate={end:%d-%m-%Y}&type=json"
    body = fetch(url, {"key": key})
    column = series.replace(".", "_")
    try:
        items: list[dict[str, Any]] = json.loads(body)["items"]
        rows = [(str(item["Tarih"]), str(item.get(column) or "")) for item in items]
        return rates_from_rows(
            rows,
            currency=currency.upper(),
            source="evds_deposit",
            series_id=series,
            retrieved_at=retrieved_at,
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
