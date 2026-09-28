"""Bring-your-own-data adapter (API v1), against a fake adapter in memory."""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
from collections.abc import Mapping
from typing import Any

import pytest

from realmarket_mcp import config
from realmarket_mcp.contract import ATTRIBUTIONS, ErrorCode, ToolError
from realmarket_mcp.providers import http_adapter
from realmarket_mcp.providers.http_adapter import HttpAdapterProvider

STAMP = "2026-09-27T00:00:00Z"
BASE = "https://adapter.example.internal/v1"
META = {
    "api_version": 1,
    "name": "acme-feed",
    "attribution": "Source: ACME licensed feed.",
    "gold_usd_symbol": "XAUUSD",
    "fx_symbol": "{base}{quote}",
    "benchmarks": {"TRY": "XU100"},
}
ASSETS = [{"symbol": "THYAO", "name": "Turk Hava Yollari", "asset_class": "equity",
           "currency": "try", "exchange": "BIST"}]  # fmt: skip
BARS = {
    "symbol": "THYAO",
    "currency": "TRY",
    "adjustment": "split_and_dividend",
    "bars": [
        {"date": "2026-09-24", "open": 290, "high": 295, "low": 288, "close": 292, "volume": 1e6},
        {"date": "2026-09-25", "open": 292, "high": 300, "low": 291, "close": None, "volume": 0},
    ],
}


class FakeAdapter:
    def __init__(self, **overrides: Any) -> None:
        self.responses: dict[str, Any] = {"/meta": META, "/search": {"assets": ASSETS},
                                          "/bars": BARS, **overrides}  # fmt: skip
        self.calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.removeprefix(urllib.parse.urlparse(BASE).path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        self.calls.append((path, params, dict(headers)))
        response = self.responses.get(path)
        if isinstance(response, ToolError):
            raise response
        if response is None:
            raise ToolError(ErrorCode.NO_DATA_IN_RANGE, "Not found.", "Check the symbol.")
        return json.dumps(response).encode()


@pytest.fixture(autouse=True)
def _fresh_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_adapter, "_meta_cache", {})


def provider(fake: FakeAdapter, token: str | None = "tok") -> HttpAdapterProvider:
    return HttpAdapterProvider(BASE, token=token, retrieved_at=STAMP, fetch=fake)


def test_meta_defines_the_source_and_its_conventions() -> None:
    fake = FakeAdapter()
    p = provider(fake)
    assert (p.name, p.gold_usd_symbol, p.fx_symbol("USD", "TRY")) == (
        "adapter:acme-feed",
        "XAUUSD",
        "USDTRY",
    )
    assert p.default_benchmark("THYAO") == "XU100"
    assert ATTRIBUTIONS["adapter:acme-feed"] == "Source: ACME licensed feed."
    assert fake.calls[0][2] == {"Authorization": "Bearer tok"}  # the token goes in a header only
    assert all("tok" not in json.dumps(params) for _, params, _ in fake.calls)


def test_bars_are_validated_and_normalized() -> None:
    series = provider(FakeAdapter()).daily_bars("THYAO", dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert (series.currency, series.adjustment, series.provider) == (
        "TRY",
        "split_and_dividend",
        "adapter:acme-feed",
    )
    assert [b.close for b in series.bars] == [292.0, None]  # a missing close stays missing


@pytest.mark.parametrize(
    ("bars", "problem"),
    [
        ({**BARS, "symbol": "OTHER"}, "answered for"),
        ({**BARS, "currency": "TL"}, "3-letter currency"),
        ({**BARS, "currency": "GBp"}, "major unit"),
        ({**BARS, "bars": [{**BARS["bars"][0], "close": "292"}]}, "not a finite number"),
        ({**BARS, "bars": [BARS["bars"][1], BARS["bars"][0]]}, "ascending"),
        ({k: v for k, v in BARS.items() if k != "adjustment"}, "/bars"),
    ],
)
def test_malformed_bars_are_errors_not_repairs(bars: dict[str, Any], problem: str) -> None:
    with pytest.raises(ToolError) as raised:
        provider(FakeAdapter(**{"/bars": bars})).daily_bars(
            "THYAO", dt.date(2026, 9, 1), dt.date(2026, 9, 30)
        )
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert problem in raised.value.message and "adapter-api.md" in raised.value.hint


def test_unknown_symbol_and_bad_meta() -> None:
    fake = FakeAdapter(**{"/bars": None})
    with pytest.raises(ToolError) as raised:
        provider(fake).daily_bars("NOPE", dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert raised.value.code is ErrorCode.UNKNOWN_SYMBOL
    for meta in ({**META, "api_version": 2}, {**META, "fx_symbol": "{base}"}, {**META, "name": ""}):
        with pytest.raises(ToolError):
            http_adapter._meta_cache.clear()
            provider(FakeAdapter(**{"/meta": meta}))


def test_financials_optional_and_validated() -> None:
    statements = {
        "currency": "try",
        "industry": "Airlines",
        "quarterly": [{"end": "2026-06-30", "values": {"revenue": 7.2e9, "net_income": None}}],
        "annual": [],
    }
    st = provider(FakeAdapter(**{"/financials": statements})).financials("THYAO")
    assert (st.currency, st.provider, st.quarterly[0].values["revenue"]) == (
        "TRY",
        "adapter:acme-feed",
        7.2e9,
    )
    with pytest.raises(ToolError) as raised:
        provider(FakeAdapter()).financials("THYAO")  # adapter serves prices only
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE
    broken = {**statements, "quarterly": [{"end": "2026-06-30", "values": {"revenue": "7.2e9"}}]}
    with pytest.raises(ToolError) as raised:
        provider(FakeAdapter(**{"/financials": broken})).financials("THYAO")
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE


def test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.PROVIDER_ENV, "http")
    with pytest.raises(ToolError) as raised:
        config.load_price_provider(retrieved_at=STAMP)
    assert (
        raised.value.code is ErrorCode.MISSING_API_KEY and http_adapter.URL_ENV in raised.value.hint
    )
    setup = config.describe_setup({config.PROVIDER_ENV: "http"})
    assert setup["price_data"] == {"provider": "http", "enabled": False}
    assert any("REALMARKET_HTTP_URL" in m for m in setup["missing"])
    ready = config.describe_setup({config.PROVIDER_ENV: "http", http_adapter.URL_ENV: BASE})
    assert ready["price_data"]["enabled"] is True and ready["missing"][:1] != ["Prices are off"]


def test_credentials_do_not_follow_redirects() -> None:
    from realmarket_mcp.providers import http

    request = http.build_request("https://a.example/x", {"Authorization": "Bearer t", "key": "k"})
    assert set(request.headers) == {"User-agent"}  # all a redirect would copy
    assert request.unredirected_hdrs.keys() == {"Authorization", "Key"}
    assert request.get_header("User-agent", "").startswith("realmarket-mcp/")


def test_news_from_the_adapter() -> None:
    from realmarket_mcp.providers.http_adapter import HttpAdapterNewsProvider

    articles = [
        {
            "published_at": "2026-09-20T07:30:00Z",
            "title": "THYAO: yeni uçak siparişi",
            "url": "https://www.kap.org.tr/tr/Bildirim/1",
            "source": "KAP",
            "language": "tr",
        },
        {
            "published_at": "2026-06-01T07:30:00Z",
            "title": "THYAO: eski haber",
            "url": "https://www.kap.org.tr/tr/Bildirim/2",
            "source": "KAP",
            "language": "tr",
        },
    ]
    fake = FakeAdapter(**{"/news": {"articles": articles}})
    news = HttpAdapterNewsProvider(provider(fake))
    found = news.search(
        "THYAO",
        dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        dt.datetime(2026, 9, 27, tzinfo=dt.UTC),
        language="tr",
        limit=10,
    )
    assert [n.source for n in found] == ["KAP"]  # outside the window is dropped
    assert news.name == "adapter:acme-feed"
    path, params, _ = fake.calls[-1]
    assert (
        path == "/news" and params["language"] == "tr" and params["start"] == "2026-09-01T00:00:00Z"
    )
    with pytest.raises(ToolError) as raised:
        HttpAdapterNewsProvider(provider(FakeAdapter())).search(
            "THYAO", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 27), language=None, limit=5
        )
    assert raised.value.code is ErrorCode.UNSUPPORTED  # the adapter serves no news
    broken = FakeAdapter(**{"/news": {"articles": [{**articles[0], "url": "javascript:x"}]}})
    with pytest.raises(ToolError) as raised:
        HttpAdapterNewsProvider(provider(broken)).search(
            "THYAO", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 27), language=None, limit=5
        )
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE


def test_news_provider_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.NEWS_PROVIDER_ENV, "http")
    with pytest.raises(ToolError) as raised:
        config.load_news_provider()
    assert http_adapter.URL_ENV in raised.value.hint
    setup = config.describe_setup({config.NEWS_PROVIDER_ENV: "http"})
    assert setup["news"] == "http" and any("REALMARKET_HTTP_URL" in m for m in setup["missing"])


def test_adapter_check_reports_each_endpoint() -> None:
    from realmarket_mcp import adapter_check

    today = dt.date(2026, 9, 27)
    results = adapter_check.run_checks(lambda: provider(FakeAdapter()), "THYAO", today=today)
    status = {r.name: r.status for r in results}
    assert status["/meta"] == status["/search"] == "PASS"
    assert status["/bars"] == "WARN"  # served, but with a missing close
    assert status["/bars exchange rate"] == "WARN"  # the fake serves THYAO bars only
    assert status["price summary"] == "FAIL"  # two bars, one usable: a real finding
    assert status["/financials"] == "SKIP" and status["/news"] == "SKIP"  # optional, absent
    assert "1 check(s) failed" in adapter_check.render(results)

    http_adapter._meta_cache.clear()  # /meta is cached per URL for an hour
    bad_meta = adapter_check.run_checks(
        lambda: provider(FakeAdapter(**{"/meta": {**META, "api_version": 9}})), "THYAO", today=today
    )
    assert [(r.name, r.status) for r in bad_meta] == [("/meta", "FAIL")]
    assert "failed" in adapter_check.render(bad_meta)
