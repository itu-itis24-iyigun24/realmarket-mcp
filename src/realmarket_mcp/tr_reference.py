"""Turkish reference tables that no API publishes: deposit withholding tax and the minimum wage.

Both are hand-maintained. Every row cites its legal source; rows supported by a single source
are marked ``weak`` and reported as such. The tables were last checked on ``CHECKED``: a date
after it may fall under a later decision this table does not know, and results say so.

How the rows were checked (2026-09-27): the Resmî Gazete and ministry sites could not be opened
from the build environment, so each row rests on at least two independent published summaries
(tax advisers' circulars, AA, the TCMB blog, bank notices) or a quoted decision text, and the
pre-2022 net minimum wages were recomputed from the gross amounts (all within 0.01 TL).
"""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass

CHECKED = dt.date(2026, 9, 27)


@dataclass(frozen=True)
class Row:
    effective_from: dt.date
    value: float
    source: str
    weak: bool = False  # a single source, or inferred from a lapse


# Withholding (stopaj) on the interest of TL time deposits of up to 6 months held by resident
# individuals, which includes the 32-day deposit (GVK geçici md. 67 and the decisions under
# it). A term is taxed at the rate in force on the day it is opened or renewed: every decision
# applies to accounts "açılan veya vadesi yenilenen" from its date.
DEPOSIT_WITHHOLDING: tuple[Row, ...] = (
    Row(dt.date(2006, 1, 1), 0.15, "GVK geçici md. 67 (5281 s. Kanun); BKK 2006/10731"),
    Row(dt.date(2018, 8, 31), 0.05, "CK 53 (RG 31.08.2018), for three months"),
    Row(dt.date(2018, 12, 1), 0.15, "CK 53 lapsed without extension", weak=True),
    Row(dt.date(2020, 9, 30), 0.05, "CK 3032 (RG 30.09.2020), extended to 30.04.2024"),
    Row(dt.date(2024, 5, 1), 0.075, "CK 8434 (RG 01.05.2024), extended by CK 8775"),
    Row(dt.date(2024, 11, 1), 0.10, "CK 9075 (RG 01.11.2024)"),
    Row(dt.date(2025, 2, 1), 0.15, "CK 9487 (RG 01.02.2025)"),
    Row(dt.date(2025, 7, 9), 0.175, "CK 10041 (RG 09.07.2025)"),
)

# Monthly net minimum wage for a single worker aged 16 or over, as the ministry publishes it
# (ÇSGB; Asgari Ücret Tespit Komisyonu decisions). Before 2022 the published net includes the
# minimum living allowance (AGİ) of a single worker; from 2022 the wage is exempt from income
# tax and stamp duty and net = gross x 0.85.
MINIMUM_WAGE_NET: tuple[Row, ...] = (
    Row(dt.date(2012, 1, 1), 701.13, "ÇSGB"),
    Row(dt.date(2012, 7, 1), 739.79, "ÇSGB"),
    Row(dt.date(2013, 1, 1), 773.01, "ÇSGB"),
    Row(dt.date(2013, 7, 1), 803.68, "ÇSGB"),
    Row(dt.date(2014, 1, 1), 846.00, "ÇSGB"),
    Row(dt.date(2014, 7, 1), 891.03, "ÇSGB"),
    Row(dt.date(2015, 1, 1), 949.07, "ÇSGB"),
    Row(dt.date(2015, 7, 1), 1000.54, "ÇSGB"),
    Row(dt.date(2016, 1, 1), 1300.99, "ÇSGB"),
    Row(dt.date(2017, 1, 1), 1404.06, "ÇSGB"),
    Row(dt.date(2018, 1, 1), 1603.12, "ÇSGB"),
    Row(dt.date(2019, 1, 1), 2020.90, "ÇSGB"),
    Row(dt.date(2020, 1, 1), 2324.71, "ÇSGB"),
    Row(dt.date(2021, 1, 1), 2825.90, "ÇSGB"),
    Row(dt.date(2022, 1, 1), 4253.40, "AÜTK (RG 17.12.2021)"),
    Row(dt.date(2022, 7, 1), 5500.35, "AÜTK (RG 01.07.2022)"),
    Row(dt.date(2023, 1, 1), 8506.80, "AÜTK (RG 29.12.2022)"),
    Row(dt.date(2023, 7, 1), 11402.32, "AÜTK (RG 24.06.2023)"),
    Row(dt.date(2024, 1, 1), 17002.12, "AÜTK 2023/2 (RG 30.12.2023)"),
    Row(dt.date(2025, 1, 1), 22104.67, "AÜTK 2024/1 (RG 27.12.2024)"),
    Row(dt.date(2026, 1, 1), 28075.50, "AÜTK 2025/1 (RG 26.12.2025)"),
)


def row_on(table: tuple[Row, ...], day: dt.date) -> Row | None:
    """The row in force on ``day``, or None before the table starts."""
    index = bisect.bisect_right([r.effective_from for r in table], day) - 1
    return table[index] if index >= 0 else None


def withholding_on(day: dt.date) -> float | None:
    row = row_on(DEPOSIT_WITHHOLDING, day)
    return None if row is None else row.value


def minimum_wage_on(day: dt.date) -> Row | None:
    """The net minimum wage in force on ``day``. None before 2012 and for any year after the
    last row's year once that year has ended, when a newer decision is likely."""
    row = row_on(MINIMUM_WAGE_NET, day)
    if row is None or day.year > MINIMUM_WAGE_NET[-1].effective_from.year:
        return None
    return row


def rows_between(table: tuple[Row, ...], start: dt.date, end: dt.date) -> list[Row]:
    """Rows in force at some point from ``start`` to ``end``."""
    first = row_on(table, start)
    return [r for r in table if r is first or start < r.effective_from <= end]
