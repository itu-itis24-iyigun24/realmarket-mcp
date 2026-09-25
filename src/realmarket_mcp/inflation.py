"""Monthly CPI series and the inflation arithmetic on top of them.

Convention (ported from the author's earlier research code, where it was tested): cumulative
inflation between two dates is ``CPI(month of end) / CPI(month of start) - 1``, using index
levels, never percent changes. Months the series does not contain are never estimated.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from realmarket_mcp.contract import ErrorCode, ToolError

Month = tuple[int, int]  # (year, month)


def month_of(day: dt.date) -> Month:
    return (day.year, day.month)


def month_str(month: Month) -> str:
    return f"{month[0]:04d}-{month[1]:02d}"


def last_day_of(month: Month) -> dt.date:
    year, number = month
    following = dt.date(year + (number == 12), number % 12 + 1, 1)
    return following - dt.timedelta(days=1)


def parse_month(text: str) -> Month:
    """Accept 'YYYY-MM', 'YYYY-M' and 'YYYY-MM-DD'."""
    parts = text.strip().split("-")
    if len(parts) < 2:
        raise ValueError(f"not a month: {text!r}")
    year, number = int(parts[0]), int(parts[1])
    if not 1 <= number <= 12:
        raise ValueError(f"not a month: {text!r}")
    return (year, number)


@dataclass(frozen=True)
class CpiSeries:
    region: str
    source: str
    series_id: str
    retrieved_at: str
    values: Mapping[Month, float]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError(f"{self.region}: empty CPI series")
        if not all(math.isfinite(v) and v > 0 for v in self.values.values()):
            raise ValueError(f"{self.region}: CPI index levels must be finite and positive")

    @property
    def first_month(self) -> Month:
        return min(self.values)

    @property
    def last_month(self) -> Month:
        return max(self.values)

    @property
    def data_version(self) -> str:
        rows = [[month_str(m), self.values[m]] for m in sorted(self.values)]
        payload = json.dumps({"series": self.series_id, "rows": rows}, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    def factor(self, start: Month, end: Month) -> float | None:
        """Price-level growth ``CPI(end) / CPI(start)``; ``None`` if either month is absent."""
        if start not in self.values or end not in self.values:
            return None
        return self.values[end] / self.values[start]


def series_from_rows(
    rows: Iterable[tuple[str, str]],
    *,
    region: str,
    source: str,
    series_id: str,
    retrieved_at: str,
) -> CpiSeries:
    """Build a series from (month, value) text pairs; blank or '.' values are skipped."""
    values: dict[Month, float] = {}
    for month_text, value_text in rows:
        value_text = (value_text or "").strip()
        if value_text in {"", "."}:
            continue
        month = parse_month(month_text)
        if month in values:
            raise ValueError(f"{region}: duplicate month {month_str(month)}")
        values[month] = float(value_text)
    return CpiSeries(region, source, series_id, retrieved_at, values)


def load_csv(path: Path, *, region: str, retrieved_at: str) -> CpiSeries:
    """CSV with columns ``month`` (YYYY-MM) and ``cpi_index`` (index level)."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not {"month", "cpi_index"} <= set(reader.fieldnames):
                raise ValueError("columns must include 'month' and 'cpi_index'")
            rows = [(row["month"], row["cpi_index"]) for row in reader]
        return series_from_rows(
            rows, region=region, source="csv", series_id=path.name, retrieved_at=retrieved_at
        )
    except (OSError, ValueError) as exc:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"The CPI file for {region} could not be used: {exc}.",
            f"Fix {path}: a header 'month,cpi_index', one row per month (YYYY-MM), "
            "positive index levels (not percent changes), no duplicate months.",
            {"region": region},
        ) from None
