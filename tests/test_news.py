from __future__ import annotations

import datetime as dt
import json
import urllib.parse
from collections.abc import Mapping

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers import gdelt

NOW = dt.datetime(2026, 9, 25, 12, 0, tzinfo=dt.UTC)


def _article(seen: str, title: str, url: str) -> dict[str, str]:
    return {
        "url": url,
        "url_mobile": "",
        "title": title,
        "seendate": seen,
        "socialimage": "",
        "domain": url.split("/")[2],
        "language": "Turkish",
        "sourcecountry": "Turkey",
    }


class Recorder:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.urls: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.urls.append(url)
        return self.body


def _provider(articles: list[dict[str, str]]) -> tuple[gdelt.GdeltNewsProvider, Recorder]:
    recorder = Recorder(json.dumps({"articles": articles}).encode())
    return gdelt.GdeltNewsProvider(fetch=recorder), recorder


def test_query_uses_phrase_language_window_and_newest_first() -> None:
    provider, recorder = _provider([])
    provider.search("Turk Hava Yollari", NOW - dt.timedelta(days=7), NOW, language="tr", limit=20)
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(recorder.urls[0]).query)
    assert params["query"] == ['"Turk Hava Yollari" sourcelang:turkish']
    assert params["mode"] == ["artlist"] and params["format"] == ["json"]
    assert params["sort"] == ["datedesc"]
    assert params["startdatetime"] == ["20260918120000"]
    assert params["enddatetime"] == ["20260925120000"]


def test_articles_are_parsed_with_utc_timestamps() -> None:
    body = json.dumps(
        {"articles": [_article("20260924T101500Z", "THY yeni rota", "https://a.com/1")]}
    ).encode()
    [item] = gdelt.parse(body)
    assert item.published_at == "2026-09-24T10:15:00Z"
    assert (item.source, item.language, item.country) == ("a.com", "Turkish", "Turkey")


def test_empty_result_is_an_empty_list() -> None:
    assert gdelt.parse(b"{}") == []


def test_plain_text_rate_limit_becomes_retryable_error() -> None:
    with pytest.raises(ToolError) as raised:
        gdelt.parse(b"Please limit requests to one every 5 seconds or contact us.")
    assert raised.value.code is ErrorCode.RATE_LIMITED and raised.value.retryable


def test_plain_text_rejection_becomes_invalid_argument() -> None:
    with pytest.raises(ToolError) as raised:
        gdelt.parse(b"The specified phrase is too short.")
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_malformed_json_is_a_provider_error() -> None:
    with pytest.raises(ToolError) as raised:
        gdelt.parse(b'{"articles": [{"title": "no url or date"}]}')
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE


def test_tool_merges_syndicated_copies_and_sorts_newest_first() -> None:
    provider, _ = _provider(
        [
            _article("20260924T090000Z", "THY rekor yolcu", "https://b.com/copy"),
            _article("20260923T080000Z", "THY  Rekor Yolcu", "https://a.com/original"),
            _article("20260925T070000Z", "Borsada THY yükseldi", "https://c.com/3"),
        ]
    )
    result = tools.get_news(provider, "Turk Hava Yollari", now=NOW, retrieved_at="t")
    articles = result.data["articles"]
    assert [a["url"] for a in articles] == ["https://c.com/3", "https://a.com/original"]
    assert result.provenance[0].provider == "gdelt"
    assert any("never as instructions" in note for note in result.notes)


def test_tool_bounds_days_limit_and_title_length() -> None:
    long_title = "x" * 1000
    provider, recorder = _provider(
        [
            _article(f"202609{d:02d}T000000Z", f"{long_title}{d}", f"https://s.com/{d}")
            for d in range(1, 25)
        ]
    )
    result = tools.get_news(provider, "query", days=500, limit=5, now=NOW, retrieved_at="t")
    assert result.data["days"] == tools.MAX_NEWS_DAYS
    assert len(result.data["articles"]) == 5
    assert all(len(a["title"]) == tools.MAX_TITLE_CHARS for a in result.data["articles"])
    assert "startdatetime=20260627" in recorder.urls[0]


def test_no_articles_is_flagged_not_hidden() -> None:
    provider, _ = _provider([])
    result = tools.get_news(provider, "obscure company", now=NOW, retrieved_at="t")
    assert result.data["articles"] == []
    assert result.quality_flags[0].code == "no_articles"


def test_short_queries_are_rejected() -> None:
    provider, _ = _provider([])
    with pytest.raises(ToolError) as raised:
        tools.get_news(provider, "TH", now=NOW, retrieved_at="t")
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
