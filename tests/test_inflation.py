from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from realmarket_mcp import config, inflation
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers import cpi

STAMP = "2024-02-01T00:00:00Z"
FIXTURES = Path(__file__).parent / "fixtures"


def test_factor_uses_index_levels() -> None:
    series = inflation.CpiSeries("TR", "t", "s", STAMP, {(2023, 1): 100.0, (2024, 1): 164.8})
    assert series.factor((2023, 1), (2024, 1)) == pytest.approx(1.648)
    assert series.factor((2022, 12), (2024, 1)) is None  # never estimated


def test_months_parse_in_all_provider_spellings() -> None:
    assert inflation.parse_month("2024-01") == (2024, 1)
    assert inflation.parse_month("2024-1") == (2024, 1)  # EVDS
    assert inflation.parse_month("2024-01-01") == (2024, 1)  # FRED
    assert inflation.last_day_of((2024, 2)) == dt.date(2024, 2, 29)


def test_csv_loader_skips_blanks_and_rejects_bad_files(tmp_path: Path) -> None:
    good = tmp_path / "cpi.csv"
    good.write_text("month,cpi_index\n2024-01,100\n2024-02,\n2024-03,103.5\n")
    series = inflation.load_csv(good, region="TR", retrieved_at=STAMP)
    assert series.values == {(2024, 1): 100.0, (2024, 3): 103.5}

    bad = tmp_path / "bad.csv"
    bad.write_text("month,rate\n2024-01,3.2\n")
    with pytest.raises(ToolError) as raised:
        inflation.load_csv(bad, region="TR", retrieved_at=STAMP)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


class Recorder:
    def __init__(self, body: object) -> None:
        self.body = json.dumps(body).encode()
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.calls.append((url, headers))
        return self.body


def test_fred_parser_skips_missing_values() -> None:
    fetch = Recorder(
        {
            "observations": [
                {"date": "2024-01-01", "value": "308.417"},
                {"date": "2024-02-01", "value": "."},
            ]
        }
    )
    series = cpi.fred_us_cpi(
        dt.date(2024, 1, 15), env={cpi.FRED_KEY_ENV: "k"}, fetch=fetch, retrieved_at=STAMP
    )
    assert series.values == {(2024, 1): 308.417}
    assert "series_id=CPIAUCNS" in fetch.calls[0][0]
    assert "observation_start=2024-01-01" in fetch.calls[0][0]


def test_evds_parser_reads_its_column_and_sends_the_key_as_a_header() -> None:
    fetch = Recorder(
        {
            "items": [
                {"Tarih": "2024-1", "TP_GENENDEKS_T1": "1984.02", "UNIXTIME": {"$numberLong": "1"}},
                {"Tarih": "2024-2", "TP_GENENDEKS_T1": None},
            ]
        }
    )
    series = cpi.evds_tr_cpi(
        dt.date(2024, 1, 1),
        dt.date(2024, 2, 1),
        env={cpi.EVDS_KEY_ENV: "k"},
        fetch=fetch,
        retrieved_at=STAMP,
    )
    assert series.values == {(2024, 1): 1984.02}
    url, headers = fetch.calls[0]
    assert headers == {"key": "k"} and "k" not in url.split("series=")[1].split("&type")[0]
    assert "series=TP.GENENDEKS.T1" in url
    assert url.startswith("https://evds3.tcmb.gov.tr/igmevdsms-dis/series=")


def test_evds_uses_the_live_series_not_the_archived_one() -> None:
    # Regression: TP.FG.J0 was archived at 2026-01 when TÜİK rebased CPI to 2025=100, so every
    # real return for TR stopped there. The live-shaped fixture keeps both columns; only the
    # continued 2003=100 series reaches 2026-08.
    fetch = Recorder(json.loads((FIXTURES / "evds" / "series_rebased.json").read_text()))
    series = cpi.evds_tr_cpi(
        dt.date(2025, 12, 1),
        dt.date(2026, 8, 31),
        env={cpi.EVDS_KEY_ENV: "k"},
        fetch=fetch,
        retrieved_at=STAMP,
    )
    assert series.series_id == "TP.GENENDEKS.T1"
    assert series.last_month == (2026, 8)
    assert series.values == {
        (2025, 12): 100.0,
        (2026, 1): 105.0,
        (2026, 2): 110.0,
        (2026, 8): 120.0,
    }
    assert series.factor((2025, 12), (2026, 8)) == pytest.approx(1.2)
    assert "startDate=01-12-2025&endDate=01-08-2026" in fetch.calls[0][0]


def test_fred_parser_reads_the_live_response_envelope() -> None:
    # Live shape: metadata keys around "observations"; "." marks a month BLS did not publish
    # (October 2025). The gap is kept, never filled.
    fetch = Recorder(json.loads((FIXTURES / "fred" / "observations.json").read_text()))
    series = cpi.fred_us_cpi(
        dt.date(2025, 9, 1), env={cpi.FRED_KEY_ENV: "k"}, fetch=fetch, retrieved_at=STAMP
    )
    assert series.values == {(2025, 9): 200.0, (2025, 11): 202.0}
    assert series.factor((2025, 9), (2025, 10)) is None
    assert series.factor((2025, 9), (2025, 11)) == pytest.approx(1.01)


def test_api_keys_never_appear_in_error_text() -> None:
    def failing(url: str, headers: Mapping[str, str]) -> bytes:
        raise cpi._unavailable("HTTP 500")

    for call in (
        lambda: cpi.fred_us_cpi(
            dt.date(2024, 1, 1),
            env={cpi.FRED_KEY_ENV: "SECRETKEY"},
            fetch=failing,
            retrieved_at=STAMP,
        ),
        lambda: cpi.evds_tr_cpi(
            dt.date(2024, 1, 1),
            dt.date(2024, 2, 1),
            env={cpi.EVDS_KEY_ENV: "SECRETKEY"},
            fetch=failing,
            retrieved_at=STAMP,
        ),
    ):
        with pytest.raises(ToolError) as raised:
            call()
        assert "SECRETKEY" not in json.dumps(raised.value.to_dict())


def test_unexpected_payload_is_a_provider_error() -> None:
    with pytest.raises(ToolError) as raised:
        cpi.fred_us_cpi(
            dt.date(2024, 1, 1),
            env={cpi.FRED_KEY_ENV: "k"},
            fetch=Recorder({"oops": 1}),
            retrieved_at=STAMP,
        )
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE


def test_missing_key_explains_both_options() -> None:
    with pytest.raises(ToolError) as raised:
        config.load_cpi("TR", dt.date(2024, 1, 1), dt.date(2024, 2, 1), retrieved_at=STAMP, env={})
    assert raised.value.code is ErrorCode.MISSING_API_KEY
    assert cpi.EVDS_KEY_ENV in raised.value.hint and "REALMARKET_CPI_CSV_TR" in raised.value.hint


def test_csv_override_wins_over_api(tmp_path: Path) -> None:
    path = tmp_path / "tr.csv"
    path.write_text("month,cpi_index\n2024-01,1\n")
    series = config.load_cpi(
        "tr",
        dt.date(2024, 1, 1),
        dt.date(2024, 1, 2),
        retrieved_at=STAMP,
        env={"REALMARKET_CPI_CSV_TR": str(path), cpi.EVDS_KEY_ENV: "k"},
    )
    assert series.source == "csv"


def test_unsupported_region_suggests_a_csv() -> None:
    with pytest.raises(ToolError) as raised:
        config.load_cpi("EA", dt.date(2024, 1, 1), dt.date(2024, 2, 1), retrieved_at=STAMP, env={})
    assert raised.value.code is ErrorCode.UNSUPPORTED
    assert "REALMARKET_CPI_CSV_EA" in raised.value.hint


def test_non_finite_cpi_values_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cpi.csv"
    path.write_text("month,cpi_index\n2024-01,100\n2024-02,nan\n")
    with pytest.raises(ToolError) as raised:
        inflation.load_csv(path, region="TR", retrieved_at=STAMP)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
