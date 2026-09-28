"""Facts: Turkish sentences that carry each figure with its meaning, dates and sign.

A result's raw ``data`` leaves the model to turn fractions into percentages, pick the window a
figure belongs to and put numbers side by side. Small models get that wrong in ways no single
rule catches (a portfolio's own return presented as its lead over an index; a 0.313 written as
"%313"). A fact does that work once, in code: the model relays sentences instead of composing
them. Every figure in a fact is formatted from the same value as the ``data`` field beside it.

Numbers follow Turkish style: "+%71,0", "42.475,50 TL", "3 Haziran 2024".
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

MONTHS = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def number(value: float, digits: int = 2) -> str:
    """1234567.891 -> '1.234.567,89'."""
    text = f"{abs(value):,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return "-" + text if value < 0 and round(abs(value), digits) else text


def pct(value: float, *, signed: bool = True) -> str:
    """0.71 -> '+%71,0'; small moves keep two decimals: 0.0078 -> '+%0,78'."""
    digits = 2 if abs(value) < 0.1 else 1
    body = "%" + number(abs(value) * 100, digits)
    if not signed:
        return ("-" if value < 0 else "") + body
    return ("-" if value < 0 else "+") + body


def points(value: float) -> str:
    """A difference between two returns: 0.488 -> '+48,8 puan'."""
    digits = 2 if abs(value) < 0.1 else 1
    return ("-" if value < 0 else "+") + number(abs(value) * 100, digits) + " puan"


def money(value: float, currency: str, *, signed: bool = False) -> str:
    unit = "TL" if currency.upper() in {"TRY", "TL"} else currency.upper()
    sign = ("-" if value < 0 else "+") if signed else ("-" if value < 0 else "")
    return f"{sign}{number(abs(value))} {unit}"


def date(value: str | dt.date, *, weekday: bool = False) -> str:
    day = dt.date.fromisoformat(value) if isinstance(value, str) else value
    text = f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    return f"{text} {WEEKDAYS[day.weekday()]}" if weekday else text


def month(value: str) -> str:
    """'2026-08' -> 'Ağustos 2026'."""
    year, number_ = value.split("-")[:2]
    return f"{MONTHS[int(number_) - 1]} {year}"


def _ahead(value: float) -> str:
    return "önde" if value > 0 else "geride" if value < 0 else "aynı seviyede"


# --- analyze_portfolio ------------------------------------------------------------------------


def portfolio(
    data: Mapping[str, Any],
    *,
    splits: Sequence[tuple[str, dt.date, float]],
    dated: Sequence[tuple[str, str, dt.date]],
    prices_assumed: bool,
    unentered_dividends: Mapping[str, float],
) -> list[str]:
    cur = str(data["currency"])
    totals = data["totals"]
    facts: list[str] = []
    if dated:
        listed = ", ".join(
            f"{symbol} {'alışı' if kind == 'buy' else 'satışı' if kind == 'sell' else kind} "
            f"{date(day)}"
            for kind, symbol, day in dated
        )
        facts.append(f"Yalnızca ay verildiği için ayın ilk işlem günü kullanıldı: {listed}.")
    if prices_assumed:
        facts.append("Fiyatı verilmeyen işlemlerde o günün kapanış fiyatı kullanıldı.")
    for symbol, day, ratio in splits:
        facts.append(
            f"{symbol}: {date(day)} tarihinde bedelsiz/bölünme oldu (1 hisse karşılığı toplam "
            f"{number(ratio, 0 if float(ratio).is_integer() else 2)} hisse); elde tutulan adet "
            "buna göre artırıldı."
        )

    total_line = (
        f"Hesap özeti ({date(data['as_of'])} itibarıyla): alışlar toplamı "
        f"{money(totals['purchases'], cur)}, satışlardan gelen "
        f"{money(totals['sale_proceeds'], cur)}, elde kalan hisselerin değeri "
        f"{money(totals['market_value'], cur)}. Toplam kâr/zarar "
        f"{money(totals['total_pnl'], cur, signed=True)}"
    )
    if totals["total_return_on_purchases"] is not None:
        total_line += f" (alışlara oranla {pct(totals['total_return_on_purchases'])})"
    if totals["dividends_received"]:
        total_line += f"; girilen {money(totals['dividends_received'], cur)} temettü dahil"
    total_line += "."
    if totals["money_weighted_return_annualized"] is not None:
        total_line += (
            " Paranın ne zaman girip çıktığını hesaba katan yıllık getiri "
            f"{pct(totals['money_weighted_return_annualized'])}."
        )
    facts.append(total_line)

    for h in data["holdings"]:
        symbol = h["symbol"]
        if float(h["quantity"]) > 0:
            line = (
                f"{symbol}: {number(h['quantity'], 0 if float(h['quantity']).is_integer() else 4)}"
                f" adet, ortalama maliyet {money(h['average_cost'], cur)}, son fiyat "
                f"{money(h['price'], h['currency'])}, değeri {money(h['market_value'], cur)} "
                f"(hesaptaki payı {pct(h['weight'], signed=False)}). "
            )
        else:
            line = f"{symbol}: pozisyon tamamen satıldı. "
        line += f"Toplam sonucu {money(h['total_pnl'], cur, signed=True)}"
        if h["total_return_on_purchases"] is not None:
            line += f" (bu hisseye yapılan alışlara oranla {pct(h['total_return_on_purchases'])})"
        parts = []
        if h["realized_pnl"]:
            parts.append(f"satışlardan gerçekleşen {money(h['realized_pnl'], cur, signed=True)}")
        if h["dividends_received"]:
            parts.append(f"girilen temettü {money(h['dividends_received'], cur)}")
        if parts:
            line += "; bunun içinde " + " ve ".join(parts) + " var"
        facts.append(line + ".")
        if symbol in unentered_dividends:
            facts.append(
                f"{symbol} elde tutulurken temettü dağıttı (bu hisseler için yaklaşık "
                f"{money(unentered_dividends[symbol], cur)} brüt); işlemlerde temettü girilmediği "
                "için yukarıdaki sonuçlara dahil değil."
            )

    compared = [h for h in data["holdings"] if h.get("comparison")]
    for h in compared:
        c = h["comparison"]
        until = "satış günü" if float(h["quantity"]) <= 0 else "son seans"
        facts.append(
            f"{h['symbol']} fiyatı ilk alış ({date(c['from'])}) ile {until} ({date(c['to'])}) "
            f"arasında {pct(c['holding_price_return'])} değişti; aynı dönemde {c['with']} "
            f"{pct(c['comparison_return'])} değişti. Fark {points(c['difference'])}: bu dönemde "
            f"{h['symbol']}, {c['with']} karşısında {_ahead(c['difference'])}. İkisi de "
            "temettü hariç fiyat değişimidir; bu rakam hissenin yukarıdaki toplam sonucundan "
            "farklıdır."
        )
    if "account_comparison" in data:
        a = data["account_comparison"]
        if a and a["difference"] is not None:
            facts.append(
                f"Hesabın tamamı: paranın girip çıktığı günler hesaba katıldığında hesabın yıllık "
                f"getirisi {pct(a['money_weighted_return_annualized'])}. {a['with']} fiyatının "
                f"aynı günlerdeki değişimi aynı tutarlara uygulandığında yıllık getiri "
                f"{pct(a['comparison_money_weighted_return_annualized'])} olurdu "
                f"({date(a['from'])} – {date(a['to'])}). Fark {points(a['difference'])}: hesap "
                f"{a['with']} karşısında {_ahead(a['difference'])}. {a['with']} temettü içermez; "
                "hesabın getirisi yalnızca işlemlerde girilen temettüleri içerir."
            )
        else:
            facts.append("Hesabın tamamı için karşılaştırma hesaplanamadı (uyarılara bakın).")
    return facts


# --- explain_price_move -----------------------------------------------------------------------


def price_move(
    data: Mapping[str, Any],
    *,
    asked: dt.date,
    today: dt.date,
    lookback: int,
    news_available: bool,
) -> list[str]:
    symbol, cur = data["symbol"], str(data["currency"])
    session = dt.date.fromisoformat(data["session"])
    facts: list[str] = []
    if session != asked:
        when = f"Bugün ({date(asked)})" if asked == today else date(asked)
        facts.append(
            f"{when} için tamamlanmış seans yok; aşağıdaki rakamlar "
            f"{date(session, weekday=True)} seansına aittir."
        )
    facts.append(
        f"{symbol}, {date(session, weekday=True)} seansını {money(data['price'], cur)} ile "
        f"kapattı; önceki seansa ({date(data['previous_session'])}, kapanış "
        f"{money(data['previous_price'], cur)}) göre {pct(data['move'])} değişti."
    )
    bench = data["benchmark"]
    if bench["move"] is not None:
        facts.append(
            f"Aynı seansta {bench['symbol']} {pct(bench['move'])} değişti; {symbol} ile arasındaki "
            f"fark {points(data['difference_from_benchmark'])}."
        )
    if data["move_in_sigmas"] is not None:
        facts.append(
            f"Bu günlük değişim, önceki {lookback} seansta hissenin tipik günlük değişiminin "
            f"{number(abs(data['move_in_sigmas']), 1)} katı büyüklüğündeydi."
        )
    if data["volume_ratio"] is not None:
        facts.append(
            f"İşlem hacmi önceki 20 seansın ortalamasının {number(data['volume_ratio'], 2)} "
            "katıydı."
        )
    if data["ex_dividend_amount"]:
        facts.append(
            f"Bu seans temettü kesme günüydü: hisse başına {money(data['ex_dividend_amount'], cur)}"
            " temettü fiyattan düşüldü."
        )
    if data["news"]:
        facts.append(
            f"{date(data['previous_session'])} ile seanstan sonraki gün arasında "
            f"{len(data['news'])} haber veya açıklama bulundu (başlıklar ve tarihleri news "
            "alanında); yakın tarihli olmaları hareketin nedeni oldukları anlamına gelmez."
        )
    elif news_available:
        facts.append(
            "Bu tarihler için haber veya açıklama bulunamadı; bu, bir şey olmadığı anlamına gelmez."
        )
    else:
        facts.append("Haber kaynağına ulaşılamadı; haberler kontrol edilemedi.")
    facts.append("Bu veriler hareketin nedenini göstermez.")
    return facts


# --- compare_real_return ----------------------------------------------------------------------


def real_return(data: Mapping[str, Any]) -> list[str]:
    symbol, cur = data["symbol"], str(data["currency"])
    first, last = date(data["first_date"]), date(data["last_date"])
    facts: list[str] = []
    window_end = data["inflation_window_end"]
    if data["real_return"] is not None and window_end:
        end = date(window_end)
        verdict = (
            "enflasyonun önünde kaldı" if data["real_return"] > 0 else "enflasyonun gerisinde kaldı"
        )
        facts.append(
            f"{symbol}, {first} – {end} arasında nominal "
            f"{pct(data['nominal_return_in_inflation_window'])} getirdi; aynı dönemde tüketici "
            f"fiyatları ({data['inflation_region']}) {pct(data['cumulative_inflation'])} arttı. "
            f"Reel (enflasyondan arındırılmış) getiri {pct(data['real_return'])}: hisse "
            f"{verdict}."
        )
        if data["last_date"] > window_end:
            facts.append(
                f"Enflasyon verisi {end} tarihine kadar yayımlandığı için reel getiri bu tarihe "
                f"kadardır. Fiyatlar {last} tarihine kadar var: {first} – {last} arasında "
                f"nominal getiri {pct(data['nominal_return'])}."
            )
    else:
        facts.append(
            f"{symbol}, {first} – {last} arasında nominal {pct(data['nominal_return'])} getirdi. "
            "Bu dönem için enflasyon karşılaştırması yapılamadı."
        )
    nominal = pct(data["nominal_return"])
    if data["usd_return"] is not None:
        facts.append(f"{first} – {last} arasında dolar cinsinden getiri {pct(data['usd_return'])}.")
    if data["gold_return_in_currency"] is not None:
        line = (
            f"Aynı para {first} tarihinde altına yatırılsaydı {last} tarihine kadar "
            f"{cur if cur != 'TRY' else 'TL'} olarak {pct(data['gold_return_in_currency'])} "
            f"getirirdi; hisse aynı dönemde {nominal}."
        )
        if data["gram_gold_try_start"] is not None:
            line += (
                f" Gram altın {money(data['gram_gold_try_start'], 'TRY')} seviyesinden "
                f"{money(data['gram_gold_try_end'], 'TRY')} seviyesine çıktı."
            )
        facts.append(line)
    if data["deposit_return_after_tax"] is not None:
        facts.append(
            f"32 günlük TL mevduat {first} – {last} arasında stopaj sonrası "
            f"{pct(data['deposit_return_after_tax'])} getirirdi (stopaj öncesi "
            f"{pct(data['deposit_return'])}); hisse aynı dönemde {nominal}."
        )
    if data["deposit_real_return_after_tax"] is not None and window_end:
        facts.append(
            f"Mevduatın stopaj sonrası reel getirisi ({first} – {date(window_end)}) "
            f"{pct(data['deposit_real_return_after_tax'])}."
        )
    if data.get("minimum_wage_growth") is not None:
        wages = data["return_in_minimum_wages"]
        verdict = (
            "hisse asgari ücretin önünde kaldı"
            if wages > 0
            else "hisse asgari ücretin gerisinde kaldı"
        )
        facts.append(
            f"Net asgari ücret {first} – {last} arasında {pct(data['minimum_wage_growth'])} "
            f"arttı; hisse aynı dönemde {nominal}. Asgari ücret cinsinden hisse "
            f"{pct(wages)}: {verdict}."
        )
    house = data.get("house_prices")
    if house:
        line = (
            f"Konut fiyat endeksi ({house['area']}) {month(house['from_month'])} – "
            f"{month(house['to_month'])} arasında {pct(house['house_price_return'])} değişti"
        )
        if house.get("house_price_real_return") is not None:
            line += f" (reel {pct(house['house_price_real_return'])})"
        if house.get("asset_return_same_months") is not None:
            line += f"; hisse aynı aylarda {pct(house['asset_return_same_months'])}"
        facts.append(line + ".")
    return facts


def amount(value: float, currency: str) -> str:
    """Large amounts in words: 398991384885 TL -> '398,99 milyar TL'."""
    for size, word in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(value) >= size:
            unit = "TL" if currency.upper() in {"TRY", "TL"} else currency.upper()
            return f"{number(value / size)} {word} {unit}"
    return money(value, currency)


def _years(first: str, last: str) -> float:
    return (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days / 365.25


def _performance(symbol: str, m: Mapping[str, Any]) -> list[str]:
    """Return, volatility and drawdown of one asset over its own window."""
    first, last = date(m["first_date"]), date(m["last_date"])
    # Closes without a unit: an index's level is in points, not in its currency.
    line = (
        f"{symbol}, {first} – {last} arasında ({m['sessions']} seans): ilk kapanış "
        f"{number(m['first_close'])}, son kapanış {number(m['last_close'])}; toplam getiri "
        f"{pct(m['total_return'])}"
    )
    if m.get("annualized_return") is not None and _years(m["first_date"], m["last_date"]) >= 1:
        line += f", yıllık ortalama {pct(m['annualized_return'])}"
    facts = [line + "."]
    if m.get("annualized_volatility") is not None:
        facts.append(
            f"{symbol} fiyatının yıllık oynaklığı (fiyatın ne kadar dalgalandığının ölçüsü) bu "
            f"dönemde {pct(m['annualized_volatility'], signed=False)}."
        )
    if m.get("max_drawdown"):
        facts.append(
            f"{symbol} bu dönemdeki en büyük düşüşünü {date(m['max_drawdown_peak_date'])} "
            f"zirvesinden {date(m['max_drawdown_trough_date'])} dibine yaşadı: "
            f"{pct(m['max_drawdown'])}."
        )
    return facts


# --- get_price_summary ------------------------------------------------------------------------


def price_summary(data: Mapping[str, Any]) -> list[str]:
    symbol, cur = data["symbol"], str(data["currency"])
    facts: list[str] = []
    requested = dt.date.fromisoformat(data["requested_start"])
    if (dt.date.fromisoformat(data["first_date"]) - requested).days > 7:
        facts.append(
            f"İstenen başlangıç {date(requested)}, ancak {symbol} verileri "
            f"{date(data['first_date'])} tarihinde başlıyor; rakamlar bu tarihten itibarendir."
        )
    facts += _performance(symbol, data)
    if data.get("dividend_payments"):
        facts.append(
            f"Bu dönemde hisse başına toplam {money(data['dividends_per_share'], cur)} temettü "
            f"ödendi ({data['dividend_payments']} ödeme). Fiyat değişimi "
            f"{pct(data['price_return'])}, temettülerin getiriye katkısı "
            f"{pct(data['dividend_return'])}."
        )
    if data.get("dividend_yield_trailing_12m"):
        facts.append(
            "Son 12 ayda ödenen temettülerin son fiyata oranı (temettü verimi) "
            f"{pct(data['dividend_yield_trailing_12m'], signed=False)}."
        )
    return facts


# --- compare_assets ---------------------------------------------------------------------------


def comparison(data: Mapping[str, Any]) -> list[str]:
    assets = [a for a in data["assets"] if a.get("metrics")]
    facts = [
        f"Karşılaştırma {date(data['window_start'])} – {date(data['window_end'])} dönemini "
        "kapsıyor; her varlık aynı dönemle ölçüldü."
    ]
    for a in assets:
        facts += _performance(a["symbol"], a["metrics"])
    ranked = sorted(assets, key=lambda a: -float(a["metrics"]["total_return"]))
    if len(ranked) > 1:
        facts.append(
            "Toplam getiriye göre sıralama: "
            + ", ".join(f"{a['symbol']} {pct(a['metrics']['total_return'])}" for a in ranked)
            + "."
        )
    currencies = sorted({str(a["currency"]) for a in assets})
    if len(currencies) > 1:
        facts.append(
            "Varlıklar farklı para birimlerinde ("
            + ", ".join(currencies)
            + "); her getiri kendi para birimindedir, doğrudan karşılaştırılamaz."
        )
    return facts


# --- get_valuation ----------------------------------------------------------------------------


def valuation(data: Mapping[str, Any]) -> list[str]:
    symbol, cur = data["symbol"], str(data["trading_currency"])
    facts = [
        f"{symbol}, {date(data['price_date'])} kapanışı {money(data['price'], cur)}; piyasa "
        f"değeri {amount(data['market_cap'], cur)}."
    ]
    basis = {
        "trailing_four_quarters": "son dört çeyreğin toplamı",
        "trailing_twelve_months_reported": "şirketin son raporunda verdiği son 12 aylık rakam",
        "latest_fiscal_year": "son tam mali yıl",
    }.get(str(data.get("earnings_basis")), "")
    periods = data.get("periods_used") or []
    when = f" ({date(periods[0])} – {date(periods[-1])} dönem sonları)" if len(periods) > 1 else ""
    ratios = []
    if data["price_to_earnings"] is not None:
        ratios.append(f"F/K {number(data['price_to_earnings'])}")
    if data["price_to_book"] is not None:
        ratios.append(f"PD/DD {number(data['price_to_book'])}")
    if data["price_to_sales"] is not None:
        ratios.append(f"F/S {number(data['price_to_sales'])}")
    if ratios:
        line = ", ".join(ratios) + "."
        if basis and (data["price_to_earnings"] is not None or data["price_to_sales"] is not None):
            line += f" Kâr ve satışlar {basis}{when}."
        if data.get("equity_as_of") and data["price_to_book"] is not None:
            line += f" Özsermaye {date(data['equity_as_of'])} tarihli."
        facts.append(line)
    for key, name, figure in (
        ("pe", "F/K", "earnings"),
        ("pb", "PD/DD", "equity"),
        ("ps", "F/S", "sales"),
    ):
        if key not in data.get("not_meaningful", {}):
            continue
        value = data.get(figure)
        if value is not None and value <= 0:
            reason = "ilgili rakam sıfır ya da negatif (örneğin zarar)"
        else:
            reason = "kaynak gereken rakamı vermiyor"
        facts.append(f"{name} bu veriyle hesaplanamıyor: {reason}.")
    if data.get("restated_to_money_of"):
        facts.append(
            "Finansallar enflasyon muhasebesine (TMS 29) göre "
            f"{month(str(data['restated_to_money_of']))} parasıyla düzeltilmiş rakamlardır."
        )
    if data.get("reporting_currency") and data["reporting_currency"] != cur:
        facts.append(
            f"Şirket finansallarını {data['reporting_currency']} olarak raporluyor; oranlar için "
            f"{number(data['fx_to_trading_currency'], 4)} kuruyla {cur} cinsine çevrildi."
        )
    if data.get("dividend_yield_trailing_12m"):
        facts.append(
            "Son 12 ayda ödenen temettülerin son fiyata oranı (temettü verimi) "
            f"{pct(data['dividend_yield_trailing_12m'], signed=False)}."
        )
    facts.append(
        "Oranlar bugünkü fiyatı geçmiş sonuçlarla karşılaştırır; ucuz ya da pahalı "
        "olduğu anlamına gelmez."
    )
    return facts
