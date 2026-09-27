"""News article search via the GDELT DOC 2.0 API (free, no key; https://www.gdeltproject.org).

GDELT indexes online news worldwide, including Turkish-language sources, and returns article
metadata only: title, link, source domain, language, country and first-seen time. It covers
roughly the most recent three months. The response shape was verified against the live API on
2026-09-26 (see docs/providers.md).

GDELT asks for at most one request every 5 seconds per client and answers faster requests with
a plain-text "Please limit requests" (or HTTP 429). Requests from this process are therefore
spaced at least MIN_INTERVAL_SECONDS apart, and a rate-limited request is retried once after
RETRY_WAIT_SECONDS; a second refusal is reported to the caller.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import NewsItem
from realmarket_mcp.providers import http

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCE = "GDELT"
MAX_RECORDS = 250
# GDELT's language operator takes language names; we accept ISO 639-1 codes.
LANGUAGES = {"tr": "turkish", "en": "english", "de": "german", "fr": "french", "es": "spanish"}
MIN_INTERVAL_SECONDS = 5.5
RETRY_WAIT_SECONDS = 6.0

_lock = threading.Lock()
_last_request = 0.0


def _stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y%m%d%H%M%S")


def _seen(value: str) -> str:
    """'20260924T101500Z' -> '2026-09-24T10:15:00Z'."""
    parsed = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


class GdeltNewsProvider:
    name = "gdelt"

    def __init__(
        self,
        fetch: http.Fetch | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch or (lambda url, headers: http.get(url, headers, source=SOURCE))
        self._sleep, self._clock = sleep, clock

    def _paced(self, url: str) -> bytes:
        global _last_request
        with _lock:
            wait = _last_request + MIN_INTERVAL_SECONDS - self._clock()
            if wait > 0:
                self._sleep(wait)
            try:
                return self._fetch(url, {})
            finally:
                _last_request = self._clock()

    def _get(self, url: str) -> list[NewsItem]:
        try:
            return parse(self._paced(url))
        except ToolError as error:
            if error.code is not ErrorCode.RATE_LIMITED:
                raise
            self._sleep(RETRY_WAIT_SECONDS)
            return parse(self._paced(url))

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
        return self._get(f"{URL}?{params}")


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
