"""With the data adapter, realmarket reaches no keyless source abroad unless allowed."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping

import pytest

from realmarket_mcp import config, facts
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers import cpi

STAMP = "2024-02-01T00:00:00Z"
FIRM = {config.PROVIDER_ENV: "http", "REALMARKET_HTTP_URL": "https://data.firm.internal/v1"}
LEI = "724500Y6DUVHQD6OXN27"  # any 20-character LEI


def never(url: str, headers: Mapping[str, str]) -> bytes:
    raise AssertionError(f"no request expected, got {url}")


@pytest.mark.parametrize(
    ("env", "allowed"),
    [
        ({}, True),
        ({config.USE_YAHOO_ENV: "true"}, True),
        (FIRM, False),
        ({**FIRM, config.FOREIGN_SOURCES_ENV: "on"}, True),
        ({config.USE_YAHOO_ENV: "true", config.FOREIGN_SOURCES_ENV: "off"}, False),
    ],
)
def test_sources_abroad_are_off_only_with_the_adapter(env: dict[str, str], allowed: bool) -> None:
    assert config.foreign_sources_allowed(env) is allowed


def test_news_defaults_to_the_adapter_and_an_explicit_choice_wins() -> None:
    assert config.news_provider_choice({}) == "gdelt"
    assert config.news_provider_choice(FIRM) == "http"
    assert config.news_provider_choice({**FIRM, config.NEWS_PROVIDER_ENV: "gdelt"}) == "gdelt"


@pytest.mark.parametrize(
    ("region", "key_env"), [("TR", cpi.EVDS_KEY_ENV), ("US", cpi.FRED_KEY_ENV)]
)
def test_inflation_without_a_configured_source_is_refused_not_fetched_abroad(
    region: str, key_env: str
) -> None:
    with pytest.raises(ToolError) as raised:
        config.load_cpi(
            region, dt.date(2024, 1, 1), dt.date(2024, 3, 1), retrieved_at=STAMP, env=FIRM,
            fetch=never,
        )  # fmt: skip
    assert raised.value.code is ErrorCode.MISSING_API_KEY
    assert key_env in raised.value.hint
    assert f"REALMARKET_CPI_CSV_{region}" in raised.value.hint
    assert config.FOREIGN_SOURCES_ENV in raised.value.hint


def test_configured_inflation_sources_still_work_with_the_adapter() -> None:
    def evds(url: str, headers: Mapping[str, str]) -> bytes:
        assert "tcmb.gov.tr" in url
        return json.dumps({"items": [{"Tarih": "2024-1", "TP_GENENDEKS_T1": "1"}]}).encode()

    series = config.load_cpi(
        "TR", dt.date(2024, 1, 1), dt.date(2024, 2, 1), retrieved_at=STAMP,
        env={**FIRM, cpi.EVDS_KEY_ENV: "k"}, fetch=evds,
    )  # fmt: skip
    assert series.source == "evds"


def test_official_european_reports_are_refused_with_the_adapter() -> None:
    with pytest.raises(ToolError) as raised:
        config.load_financials_provider(LEI, retrieved_at=STAMP, env=FIRM)
    assert raised.value.code is ErrorCode.UNSUPPORTED
    assert config.FOREIGN_SOURCES_ENV in raised.value.hint


def test_setup_reports_sources_abroad_as_off() -> None:
    setup = config.describe_setup({**FIRM, cpi.EVDS_KEY_ENV: "k"})
    assert setup["foreign_sources"] is False
    assert setup["news"] == "http"
    assert setup["inflation"] == {
        "TR": "evds",
        "US": "off",
        "other_oecd_members": "off",
        "evds_key_set": True,
        "fred_key_set": False,
        "csv_regions": [],
    }
    assert setup["financial_statements"]["eu_uk_companies_by_lei"] == "off"  # type: ignore[index]
    text = " ".join(facts.setup(setup))
    assert "Yurt dışı kaynaklar kapalı" in text
    assert "ABD için kapalı (yurt dışı kaynaklar kapalı)" in text

    bare = config.describe_setup(FIRM)
    assert any("REALMARKET_CPI_CSV_TR" in m and "OECD" not in m for m in bare["missing"])  # type: ignore[attr-defined]
    assert "Yurt dışı" not in " ".join(facts.setup(config.describe_setup({})))
