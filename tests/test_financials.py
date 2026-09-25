"""get_financials, with fixtures shaped like the live source.

Verified against official results on 2026-09-25 (see docs/providers.md): for Turkish companies
under TMS 29 the source carries the prior-year quarter and year as restated by the company in
its latest filing, while the previous quarter keeps the value first reported in that quarter's
purchasing power.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers.fixture import FixtureProvider

TODAY = dt.date(2026, 9, 1)
CPI = {(2024, 12): 80.0, (2025, 12): 130.0, (2026, 3): 140.0, (2026, 6): 150.0}
RESTATED = "company-restated comparative (TMS 29), used as reported"
CPI_METHOD = "earlier figure restated with CPI"


def approx(value: float) -> object:
    return pytest.approx(value, abs=1e-6)


def _loader(_region: str, _start: dt.date, _end: dt.date) -> CpiSeries:
    return CpiSeries("TR", "test", "TEST.CPI", "t", CPI)


def _period(end: str, revenue: float | None, **extra: float) -> dict[str, Any]:
    return {"end": end, "values": {"revenue": revenue, **extra}}


def _provider(tmp_path: Path, name: str, spec: dict[str, Any]) -> FixtureProvider:
    (tmp_path / "financials").mkdir(exist_ok=True)
    (tmp_path / "financials" / f"{name}.json").write_text(json.dumps(spec))
    (tmp_path / "assets.json").write_text("[]")
    return FixtureProvider(tmp_path)


def _retailer(latest_revenue: float = 1650, **overrides: Any) -> dict[str, Any]:
    spec = {
        "currency": "TRY",
        "sector": "Consumer Defensive",
        "industry": "Discount Stores",
        "quarterly": [
            _period("2025-06-30", 1500),  # restated comparative, June 2026 money
            _period("2025-09-30", 1250),
            _period("2025-12-31", 1300),
            _period("2026-03-31", 1400),  # first reported, March 2026 money
            _period(
                "2026-06-30",
                latest_revenue,
                gross_profit=330,
                operating_income=165,
                net_income=99,
                total_debt=500,
                total_equity=1000,
            ),
        ],
        "annual": [_period("2024-12-31", 4000), _period("2025-12-31", 5200)],
    }
    spec.update(overrides)
    return spec


def _bank(annual_2025: float = 400) -> dict[str, Any]:
    ends = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
    return {
        "currency": "TRY",
        "industry": "Banks - Regional",
        "quarterly": [_period(end, 100) for end in ends],
        "annual": [_period("2024-12-31", 300), _period("2025-12-31", annual_2025)],
    }


def test_tms29_company_uses_restated_comparatives_and_restates_the_previous_quarter(
    tmp_path: Path,
) -> None:
    growth = tools.get_financials(
        _provider(tmp_path, "RET", _retailer()), _loader, "RET", today=TODAY
    ).data["growth"]

    yoy = growth["year_on_year"]
    assert yoy["real_method"] == RESTATED
    assert yoy["revenue"] == {"as_reported": approx(0.1), "real": approx(0.1)}  # 1650 / 1500

    qoq = growth["quarter_on_quarter"]
    assert qoq["real_method"] == CPI_METHOD
    assert qoq["revenue"]["as_reported"] == approx(1650 / 1400 - 1)
    assert qoq["revenue"]["real"] == approx(0.1)  # 1650 / (1400 x 150/140)

    annual = growth["annual"]
    assert annual["real_method"] == RESTATED
    assert annual["revenue"]["real"] == approx(0.3)  # 5200 / 4000, both company-restated


def test_bank_growth_is_deflated_with_cpi(tmp_path: Path) -> None:
    data = tools.get_financials(
        _provider(tmp_path, "BNK", _bank()), _loader, "BNK", today=TODAY
    ).data
    annual = data["growth"]["annual"]
    assert annual["real_method"] == CPI_METHOD
    assert annual["revenue"]["as_reported"] == approx(400 / 300 - 1)
    assert annual["revenue"]["real"] == approx(400 / (300 * 130 / 80) - 1)
    assert data["inflation_accounting"].startswith("not applied")


def test_latest_quarter_margins_and_leverage(tmp_path: Path) -> None:
    latest = tools.get_financials(
        _provider(tmp_path, "RET", _retailer()), _loader, "RET", today=TODAY
    ).data["latest_quarter"]
    assert latest["end"] == "2026-06-30"
    assert (latest["gross_margin"], latest["operating_margin"]) == (0.2, 0.1)
    assert latest["net_margin"] == approx(0.06)
    assert latest["debt_to_equity"] == 0.5


def test_non_restating_quarters_must_reconcile_with_the_year(tmp_path: Path) -> None:
    ok = tools.get_financials(_provider(tmp_path, "B1", _bank()), _loader, "B1", today=TODAY)
    assert "quarters_do_not_add_up" not in {f.code for f in ok.quality_flags}

    bad = tools.get_financials(_provider(tmp_path, "B2", _bank(500)), _loader, "B2", today=TODAY)
    flag = next(f for f in bad.quality_flags if f.code == "quarters_do_not_add_up")
    assert "-20.0%" in flag.message


def test_tms29_years_are_not_reconciled(tmp_path: Path) -> None:
    spec = _retailer(
        quarterly=[
            _period(e, 100) for e in ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
        ],
        annual=[_period("2025-12-31", 999)],
    )
    result = tools.get_financials(_provider(tmp_path, "MIX", spec), _loader, "MIX", today=TODAY)
    assert "quarters_do_not_add_up" not in {f.code for f in result.quality_flags}


def test_missing_quarter_is_flagged(tmp_path: Path) -> None:
    spec = _retailer()
    spec["quarterly"] = [q for q in spec["quarterly"] if q["end"] != "2025-09-30"]
    flags = tools.get_financials(
        _provider(tmp_path, "GAP", spec), _loader, "GAP", today=TODAY
    ).quality_flags
    assert "missing_quarter" in {f.code for f in flags}


def test_implausible_jump_is_flagged(tmp_path: Path) -> None:
    spec = _retailer(latest_revenue=3000)  # real +100% in one quarter
    flags = tools.get_financials(
        _provider(tmp_path, "JMP", spec), _loader, "JMP", today=TODAY
    ).quality_flags
    assert "unusual_change" in {f.code for f in flags}


def test_losses_give_no_growth_rate(tmp_path: Path) -> None:
    spec = _retailer()
    spec["quarterly"][-2]["values"]["net_income"] = -50
    data = tools.get_financials(_provider(tmp_path, "LOS", spec), _loader, "LOS", today=TODAY).data
    net = data["growth"]["quarter_on_quarter"]["net_income"]
    assert net == {"as_reported": None, "real": None}


def test_without_cpi_the_cpi_based_comparisons_have_no_real_value(tmp_path: Path) -> None:
    def no_cpi(_r: str, _s: dt.date, _e: dt.date) -> CpiSeries:
        raise ToolError(ErrorCode.PROVIDER_UNAVAILABLE, "down", "retry")

    result = tools.get_financials(
        _provider(tmp_path, "RET", _retailer()), no_cpi, "RET", today=TODAY
    )
    growth = result.data["growth"]
    assert growth["quarter_on_quarter"]["revenue"]["real"] is None
    assert growth["year_on_year"]["revenue"]["real"] == approx(0.1)  # needs no CPI
    assert "inflation_unavailable" in {f.code for f in result.quality_flags}


def test_unknown_company(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as raised:
        tools.get_financials(_provider(tmp_path, "X", {}), _loader, "NOPE", today=TODAY)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE
