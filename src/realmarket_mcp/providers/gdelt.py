"""News article search via the GDELT DOC 2.0 API (free, no key; https://www.gdeltproject.org).

GDELT indexes online news worldwide, including Turkish-language sources, and returns article
metadata only: title, link, source domain, language, country and first-seen time. It covers
roughly the most recent three months. Written from GDELT's public documentation; the JSON
shape must be verified against the live API before release (see docs/providers.md).
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import NewsItem
from realmarket_mcp.providers import http

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCE = "GDELT"
MAX_RECORDS = 250
# GDELT's language operator takes language names; we accept ISO 639-1 codes.
LANGUAGES = {"tr": "turkish", "en": "english", "de": "german", "fr": "french", "es": "spanish"}


def _stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y%m%d%H%M%S")


def _seen(value: str) -> str:
    """'20260924T101500Z' -> '2026-09-24T10:15:00Z'."""
    parsed = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


class GdeltNewsProvider:
    name = "gdelt"

    def __init__(self, fetch: http.Fetch | None = None) -> None:
        self._fetch = fetch or (lambda url, headers: http.get(url, headers, source=SOURCE))

    def search(
        self,
        query: str,
        start: dt.datetime,
        end: dt.datetime,
        *,
        language: str | None,
        limit: int,
    ) -> list[NewsItem]:
        terms = f'"{query}"' if " " in query and not query.startswith('"') else query
        if language:
            terms += f" sourcelang:{LANGUAGES[language]}"
        params = urllib.parse.urlencode(
            {
                "query": terms,
                "mode": "artlist",
                "format": "json",
                "sort": "datedesc",
                "maxrecords": min(limit, MAX_RECORDS),
                "startdatetime": _stamp(start),
                "enddatetime": _stamp(end),
            }
        )
        body = self._fetch(f"{URL}?{params}", {})
        return parse(body)


def parse(body: bytes) -> list[NewsItem]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text.startswith("{"):
        # GDELT reports problems as plain text with HTTP 200.
        if "limit requests" in text.lower():
            raise ToolError(
                ErrorCode.RATE_LIMITED,
                "GDELT asks clients to slow down.",
                "Wait at least 5 seconds between news searches.",
            )
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"GDELT rejected the search: {text[:200]}",
            "Use a longer, more specific query such as the full company name.",
        )
    try:
        articles: list[dict[str, Any]] = json.loads(text).get("articles", [])
        return [
            NewsItem(
                published_at=_seen(article["seendate"]),
                title=str(article.get("title") or "").strip(),
                url=str(article["url"]),
                source=str(article.get("domain") or ""),
                language=article.get("language") or None,
                country=article.get("sourcecountry") or None,
            )
            for article in articles
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            f"GDELT returned data in an unexpected format ({type(exc).__name__}).",
            "The API may have changed; report the issue.",
        ) from None
