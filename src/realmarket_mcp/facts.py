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


MARKETS = {"tr": "Borsa İstanbul", "us": "ABD borsaları"}


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


def _ahead_by(value: float) -> str:
    """'48,8 puan önünde kaldı', after a genitive; the gap is between two returns."""
    if not value:
        return "ile aynı kaldı"
    digits = 2 if abs(value) < 0.1 else 1
    size = number(abs(value) * 100, digits) + " puan"
    return f"{size} önünde kaldı" if value > 0 else f"{size} gerisinde kaldı"


def _ahead_noun(value: float) -> str:
    """'önünde kaldı' / 'gerisinde kaldı', after a genitive: 'altının önünde kaldı'."""
    return "önünde kaldı" if value > 0 else "gerisinde kaldı" if value < 0 else "ile aynı kaldı"


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
    moved: Sequence[tuple[str, str, dt.date]] = (),
) -> list[str]:
    cur = str(data["currency"])
    totals = data["totals"]
    facts: list[str] = []

    def listed(events: Sequence[tuple[str, str, dt.date]]) -> str:
        return ", ".join(
            f"{symbol} {'alışı' if kind == 'buy' else 'satışı' if kind == 'sell' else kind} "
            f"{date(day)}"
            for kind, symbol, day in events
        )

    if dated:
        facts.append(f"Yalnızca ay verildiği için ayın ilk işlem günü kullanıldı: {listed(dated)}.")
    if moved:
        facts.append(
            "Borsanın kapalı olduğu bir güne yazılan işlem, bir sonraki işlem gününün kapanış "
            f"fiyatıyla hesaplandı: {listed(moved)}."
        )
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
        f"{money(totals['market_value'], cur)}"
    )
    received = totals["sale_proceeds"] + totals["dividends_received"]
    if received:
        # What the money paid in amounts to now: what is still held plus what came back.
        total_line += (
            f"; alışların bugünkü karşılığı, satışlardan ve girilen temettülerden gelenle "
            f"birlikte {money(totals['market_value'] + received, cur)}"
        )
    total_line += f". Toplam kâr/zarar {money(totals['total_pnl'], cur, signed=True)}"
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
    # Each holding's share of the account's result: arithmetic, stated so that a summary of
    # "what made the result" rests on these figures rather than on a reason.
    holdings = sorted(data["holdings"], key=lambda h: -float(h["total_pnl"]))
    if len(holdings) > 1:
        facts.append(
            f"Hesabın toplam sonucu ({money(totals['total_pnl'], cur, signed=True)}) hisselere "
            "göre: "
            + ", ".join(
                f"{h['symbol']} {money(h['total_pnl'], cur, signed=True)}" for h in holdings
            )
            + "."
        )

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
                "için yukarıdaki sonuçlara dahil değil. Bu temettüler alındıysa "
                f"{symbol} toplam sonucu yaklaşık "
                f"{money(float(h['total_pnl']) + unentered_dividends[symbol], cur, signed=True)}"
                " olur."
            )
    if unentered_dividends and len(data["holdings"]) > 1:
        # "How much did I make?" with dividends the user did not list: the sum, stated here so
        # it is not added up in the answer.
        paid = sum(unentered_dividends.values())
        facts.append(
            f"Kaynağın bildirdiği ve girilmeyen temettüler (toplam yaklaşık {money(paid, cur)} "
            "brüt) alındıysa hesabın toplam sonucu yaklaşık "
            f"{money(float(totals['total_pnl']) + paid, cur, signed=True)} olur."
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
        when = (
            f"Bugün ({date(asked, weekday=True)})" if asked == today else date(asked, weekday=True)
        )
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
    paid_in = float(data["amount"]) if data.get("amount") else None

    def worth(growth: float) -> str:
        """With an amount, what the same money would have become: the question asks it in money
        and a model otherwise multiplies the percentage itself."""
        if paid_in is None:
            return ""
        return f" ({money(paid_in, cur)} → {money(paid_in * (1 + growth), cur)})"

    if data.get("amount"):
        # "I put 20,000 TL in": the same figures, in money.
        paid = float(data["amount"])
        line = (
            f"Yatırılan {money(paid, cur)} {last} itibarıyla "
            f"{money(paid * (1 + data['nominal_return']), cur)} değerinde."
        )
        if data["real_return"] is not None and window_end:
            line += (
                f" Aynı tutarın {date(window_end)} itibarıyla enflasyona göre karşılığı "
                f"{money(paid * (1 + data['cumulative_inflation']), cur)}; o tarihte hissedeki "
                f"değer {money(paid * (1 + data['nominal_return_in_inflation_window']), cur)}."
            )
        facts.append(line)
    if data["usd_return"] is not None:
        facts.append(f"{first} – {last} arasında dolar cinsinden getiri {pct(data['usd_return'])}.")
    if data["gold_return_in_currency"] is not None:
        line = (
            f"Aynı para {first} tarihinde altına yatırılsaydı {last} tarihine kadar "
            f"{cur if cur != 'TRY' else 'TL'} olarak {pct(data['gold_return_in_currency'])} "
            f"getirirdi{worth(data['gold_return_in_currency'])}; hisse aynı dönemde {nominal}: "
            "hisse altının "
            f"{_ahead_by(data['nominal_return'] - data['gold_return_in_currency'])}."
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
            f"{pct(data['deposit_return_after_tax'])} getirirdi"
            f"{worth(data['deposit_return_after_tax'])} (stopaj öncesi "
            f"{pct(data['deposit_return'])}); hisse aynı dönemde {nominal}: hisse stopaj "
            f"sonrası mevduatın "
            f"{_ahead_by(data['nominal_return'] - data['deposit_return_after_tax'])}."
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
            f"arttı{worth(data['minimum_wage_growth'])}; hisse aynı dönemde {nominal}, yani "
            "asgari ücret artışının "
            f"{_ahead_by(data['nominal_return'] - data['minimum_wage_growth'])}. Asgari ücret "
            f"cinsinden hisse {pct(wages)}: {verdict}."
        )
    house = data.get("house_prices")
    if house:
        line = (
            f"Konut fiyat endeksi ({house['area']}) {month(house['from_month'])} – "
            f"{month(house['to_month'])} arasında {pct(house['house_price_return'])} değişti"
            f"{worth(house['house_price_return'])}"
        )
        if house.get("house_price_real_return") is not None:
            line += f" (reel {pct(house['house_price_real_return'])})"
        if house.get("asset_return_same_months") is not None:
            gap = house["asset_return_same_months"] - house["house_price_return"]
            line += (
                f"; hisse aynı aylarda {pct(house['asset_return_same_months'])}: hisse konut "
                f"fiyatlarının {_ahead_by(gap)}"
            )
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
            f"tarihindeki zirveden {date(m['max_drawdown_trough_date'])} tarihine kadar "
            f"yaşadı: {pct(m['max_drawdown'])}."
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
    if data.get("low_price") is not None:
        low, high = date(data["low_date"]), date(data["high_date"])
        facts.append(
            f"Dönemin en düşük kapanışı {money(data['low_price'], cur)} ({low}), en yüksek "
            f"kapanışı {money(data['high_price'], cur)} ({high}). Son kapanış en düşüğün "
            f"{pct(data['last_vs_low'], signed=False)} üstünde, en yükseğin "
            f"{pct(-data['last_vs_high'], signed=False)} altında."
        )
        facts.append(
            "Fiyatın dönemin en düşüğüne yakın ya da uzak olması, bundan sonra düşüp "
            "yükseleceğini göstermez."
        )
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
    currencies = sorted({str(a["currency"]).upper() for a in assets})
    common = data.get("common_currency")
    if len(currencies) > 1 and not common:
        # Returns in different currencies are not one measure: no ranking, no gaps.
        facts.append(
            "Varlıklar farklı para birimlerinde (" + ", ".join(currencies) + ") ve ortak bir "
            "para birimine çevrilemedi; getirileri karşılaştırılamaz, sıralama yapılmadı."
        )
        return facts

    def measure(a: Mapping[str, Any]) -> float:
        value = a.get("return_in_common_currency") if common else None
        return float(value if value is not None else a["metrics"]["total_return"])

    ranked = sorted(assets, key=lambda a: -measure(a))
    unit = "TL" if common == "TRY" else common
    if common:
        converted = [a for a in assets if str(a["currency"]).upper() != common]
        if converted:
            facts.append(
                f"Varlıklar farklı para birimlerinde ({', '.join(currencies)}); kıyas için "
                f"hepsi {unit} cinsinden ölçüldü: "
                + ", ".join(
                    f"{a['symbol']} {unit} cinsinden {pct(a['return_in_common_currency'])}"
                    for a in converted
                )
                + " (kendi para biriminde yukarıdaki getiriler)."
            )
    if len(ranked) > 1:
        label = f" ({unit} cinsinden)" if common else ""
        facts.append(
            f"Toplam getiriye göre sıralama{label}: "
            + ", ".join(f"{a['symbol']} {pct(measure(a))}" for a in ranked)
            + "."
        )
        leader = ranked[0]
        for a in ranked[1:]:
            gap = measure(leader) - measure(a)
            facts.append(
                f"{a['symbol']}, {leader['symbol']} ile arasındaki getiri farkında{label} "
                f"{_ahead_by(-gap)}."
            )
    return facts


# --- get_valuation ----------------------------------------------------------------------------


def valuation(data: Mapping[str, Any]) -> list[str]:
    symbol, cur = data["symbol"], str(data["trading_currency"])
    # First, because a model that drops later sentences keeps the first: the answer to "is it
    # cheap?" these figures can give. Low or high, a ratio is not a verdict.
    facts = [
        f"Bu sonuç {symbol} hissesinin ucuz ya da pahalı olduğunu söylemez; oranları ve "
        "kıyasları verir. Bir oranın düşük ya da yüksek olması tek başına ucuzluk ya da "
        "pahalılık anlamına gelmez.",
        f"{symbol}, {date(data['price_date'])} kapanışı {money(data['price'], cur)}; piyasa "
        f"değeri {amount(data['market_cap'], cur)}.",
    ]
    basis = {
        "trailing_four_quarters": "son dört çeyreğin toplamı",
        "trailing_twelve_months_reported": "şirketin son raporunda verdiği son 12 aylık rakam",
        "latest_fiscal_year": "son tam mali yıl",
    }.get(str(data.get("earnings_basis")), "")
    periods = data.get("periods_used") or []
    when = f" ({date(periods[0])} – {date(periods[-1])} dönem sonları)" if len(periods) > 1 else ""
    # Each ratio with its two sides, so its meaning is in the sentence rather than left to
    # the reader: "market value is 0.77 times the equity".
    rc = data.get("reporting_currency") or cur
    if data["price_to_earnings"] is not None:
        r = number(data["price_to_earnings"])
        earnings = amount(data["earnings"], rc)
        facts.append(f"F/K {r}: piyasa değeri, net kârın ({earnings}) {r} katı.")
    if data["price_to_book"] is not None:
        r = number(data["price_to_book"])
        on = f", {date(data['equity_as_of'])} tarihli" if data.get("equity_as_of") else ""
        facts.append(
            f"PD/DD {r}: piyasa değeri, özsermayenin ({amount(data['equity'], rc)}{on}) {r} katı."
        )
        # 1 is the one level a ratio has a plain meaning at; say it and what it does not show.
        pb = float(data["price_to_book"])
        if pb != 1:
            side = "altında" if pb < 1 else "üstünde"
            lower = "düşük" if pb < 1 else "yüksek"
            facts.append(
                f"PD/DD 1'in {side}: piyasa değeri özsermayeden {lower}. Oran bunun nedenini "
                "söylemez; hissenin ucuz ya da pahalı olduğunu göstermez."
            )
    if data["price_to_sales"] is not None:
        r = number(data["price_to_sales"])
        facts.append(f"F/S {r}: piyasa değeri, satışların ({amount(data['sales'], rc)}) {r} katı.")
    if basis and (data["price_to_earnings"] is not None or data["price_to_sales"] is not None):
        facts.append(f"Kâr ve satışlar {basis}{when}.")
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
    peers = data.get("industry_comparison")
    if peers:
        market = MARKETS.get(str(peers["market"]), str(peers["market"]))

        if peers.get("level") == "sector":
            group = (
                f'kaynağın "{peers["industry"]}" sektöründe yeterli şirket olmadığı için daha '
                f'geniş "{peers["group"]}" grubu'
            )
        else:
            group = f'kaynağın "{peers["group"]}" sektörü'
        if peers.get("price_to_book_basis") == "computed":
            basis = (
                "Diğer şirketler kaynağın kendi PD/DD hesabıyla; hisse için yukarıdaki hesap "
                "kullanıldı, çünkü kaynağın bu hisse için verdiği oran fiyatı ve özsermayeyi "
                "farklı para birimlerinde bölüyor"
            )
        else:
            basis = (
                "Her şirket kaynağın kendi PD/DD hesabıyla, bu yüzden hissenin değeri "
                "yukarıdakinden biraz farklı olabilir"
            )
        # Counted from the company's side, so which way "lower" points is not left to read.
        facts.append(
            f"Sektör kıyası ({market}, {group}, aynı gün). "
            f"{basis}: {symbol} {number(peers['price_to_book'])}; "
            f"sektörde {symbol} dışındaki {peers['peer_count']} şirketin ortancası (sıralamada "
            f"ortadaki değer) {number(peers['peer_median_price_to_book'])}. Bu "
            f"{peers['peer_count']} şirketten PD/DD'si {symbol} hissesine göre daha düşük olan "
            f"{peers['peers_lower']}, daha yüksek olan {peers['peers_higher']} şirket var."
            + (
                f" Fiyatı ve finansalları farklı para birimlerinde olan "
                f"{peers['excluded_mixed_currency']} şirket, kaynağın oranı bu durumda "
                "güvenilir olmadığı için kıyasa alınmadı."
                if peers.get("excluded_mixed_currency")
                else ""
            )
        )
        facts.append(
            "Sektör kıyası yalnızca PD/DD'yi sıralar; şirketler arasındaki kârlılık, borç ve "
            "büyüme farklarını hesaba katmaz. Şirketin kendi geçmişiyle kıyas bu sonuçta yok."
        )
    else:
        facts.append(
            "Oranlar bugünkü fiyatı geçmiş sonuçlarla karşılaştırır; ucuz ya da pahalı "
            "olduğu anlamına gelmez. Ucuz ya da pahalı demek bir kıyas gerektirir (şirketin "
            "kendi geçmişi ya da benzer şirketler); bu hisse için böyle bir kıyas bu araçlarda "
            "yok."
        )
    return facts


# --- get_event_reaction -----------------------------------------------------------------------


def event_reaction(data: Mapping[str, Any]) -> list[str]:
    symbol, bench = data["symbol"], data.get("benchmark")
    facts = [
        f"Olay tarihi {date(data['event_date'])}. Getiriler, olaydan önceki son kapanıştan "
        f"({date(data['base_date'])}, {number(data['base_close'])}) itibaren ölçüldü."
    ]

    def line(r: Mapping[str, Any]) -> str:
        close = float(data["base_close"]) * (1 + float(r["return"]))
        text = f"{symbol} {pct(r['return'])} (kapanış {number(close)})"
        if bench and r.get("benchmark_return") is not None:
            text += (
                f"; aynı sürede {bench} {pct(r['benchmark_return'])}, {symbol} için endekse göre "
                f"göreli getiri {pct(r['excess_return'])}"
            )
        return text

    drift = data.get("pre_event_drift")
    if drift and drift.get("return") is not None and drift.get("from"):
        facts.append(
            f"Olaydan önceki {drift['sessions']} seansta ({date(drift['from'])} – "
            f"{date(data['base_date'])}): {line(drift)}."
        )
    for r in data["reaction"]:
        if r.get("date") is None or r.get("return") is None:
            facts.append(f"Olaydan sonraki {r['sessions']}. seans henüz tamamlanmadı.")
            continue
        facts.append(
            f"Olaydan sonraki {r['sessions']}. seans ({date(r['date'])}) sonunda: {line(r)}."
        )
    facts.append(
        "Bu rakamlar olaydan önceki kapanıştan itibaren fiyat değişimini ölçer; hareketin "
        "nedenini göstermez."
    )
    return facts


# --- portfolio_real_return --------------------------------------------------------------------

ALTERNATIVES = {
    "USD": "dolar",
    "GOLD": "altın",
    "DEPOSIT": "32 günlük TL mevduat",
    "HOUSE": "Türkiye konut fiyat endeksi",
}


def portfolio_real(data: Mapping[str, Any]) -> list[str]:
    cur = str(data["currency"])
    facts = [
        f"Toplam {money(data['invested'], cur)} yatırıldı; {date(data['as_of'])} itibarıyla değeri "
        f"{money(data['value_now'], cur)}, getiri {pct(data['return'])}."
    ]
    if data.get("annualized_money_weighted") is not None:
        facts[0] += (
            " Paranın ne zaman girdiğini hesaba katan yıllık getiri "
            f"{pct(data['annualized_money_weighted'])}."
        )
    for lot in data["lots"]:
        facts.append(
            f"{lot['symbol']}: {date(lot['date'])} tarihinde {money(lot['amount'], cur)}; bugün "
            f"{money(lot['value_now'], cur)}, getiri {pct(lot['return'])}."
        )
    if len(data["lots"]) > 1:
        gains = sorted(
            ((lot["symbol"], lot["value_now"] - lot["amount"]) for lot in data["lots"]),
            key=lambda g: -g[1],
        )
        facts.append(
            f"Toplam kazanç ({money(data['value_now'] - data['invested'], cur, signed=True)}) "
            "alımlara göre: "
            + ", ".join(f"{symbol} {money(gain, cur, signed=True)}" for symbol, gain in gains)
            + "."
        )
    if data.get("real_return") is not None:
        verdict = (
            "birikim enflasyonun önünde"
            if data["real_return"] > 0
            else "birikim enflasyonun gerisinde"
        )
        facts.append(
            f"Enflasyon verisi {date(data['real_return_as_of'])} tarihine kadar yayımlandı. O "
            f"tarihte değer {money(data['value_at_real_return_date'], cur)}; o tarihe kadar "
            "yapılan ödemelerin o tarihteki satın alma gücüyle karşılığı "
            f"{money(data['invested_in_money_of_real_return_date'], cur)}. Reel getiri "
            f"{pct(data['real_return'])}: {verdict}."
        )
    for alt in data.get("alternatives", []):
        name = ALTERNATIVES.get(str(alt["alternative"]), str(alt["alternative"]))
        when = date(alt["valued_as_of"])
        if alt["alternative"] == "HOUSE":
            line = (
                "Aynı ödemeler Türkiye konut fiyat endeksindeki değişimle büyüseydi "
                f"{when} itibarıyla {money(alt['value_now'], cur)} olurdu "
                f"(getiri {pct(alt['return'])})"
            )
        else:
            line = (
                f"Aynı ödemeler aynı günlerde {name} olarak tutulsaydı {when} itibarıyla "
                f"{money(alt['value_now'], cur)} olurdu (getiri {pct(alt['return'])})"
            )
        if alt.get("value_now_after_tax") is not None:
            line += (
                f"; stopaj sonrası {money(alt['value_now_after_tax'], cur)} (getiri "
                f"{pct(alt['return_after_tax'])})"
            )
        compared = alt.get("value_now_after_tax") or alt["value_now"]
        at_cpi_date = data.get("value_at_real_return_date")
        if alt["valued_as_of"] == data.get("real_return_as_of") and at_cpi_date is not None:
            gap = at_cpi_date - compared
            side = "önde" if gap > 0 else "geride" if gap < 0 else "eşit"
            line += (
                f". Birikim {when} itibarıyla {money(at_cpi_date, cur)}: bu alternatife göre "
                f"{money(abs(gap), cur)} {side}"
            )
        elif alt["valued_as_of"] == data["as_of"]:
            gap = data["value_now"] - compared
            side = "önde" if gap > 0 else "geride" if gap < 0 else "eşit"
            line += (
                f". Birikim bugün {money(data['value_now'], cur)}: bu alternatife göre "
                f"{money(abs(gap), cur)} {side}"
            )
        facts.append(line + ".")
    return facts


# --- get_financials ---------------------------------------------------------------------------

LINES = (
    ("revenue", "satışlar"),
    ("gross_profit", "brüt kâr"),
    ("operating_income", "faaliyet kârı"),
    ("net_income", "net kâr"),
)
GROWTH = (
    ("quarter_on_quarter", "Önceki çeyreğe göre"),
    ("year_on_year", "Geçen yılın aynı çeyreğine göre"),
    ("annual", "Önceki yıla göre"),
)


def financials(data: Mapping[str, Any]) -> list[str]:
    symbol, cur = data["symbol"], str(data["reporting_currency"])
    restated = str(data.get("inflation_accounting", "")).startswith("TMS 29")
    facts = [
        f"{symbol} finansallarını {cur} olarak raporluyor"
        + (
            "; 2023 yıl sonundan itibaren rakamlar enflasyon muhasebesine (TMS 29) göre "
            "düzeltilmiştir."
            if restated
            else "; enflasyon muhasebesi uygulanmamıştır."
        )
    ]
    for key, label in (("latest_quarter", "Son çeyrek"), ("latest_year", "Son mali yıl")):
        p = data.get(key)
        if not p:
            continue
        figures = [f"{name} {amount(p[k], cur)}" for k, name in LINES if p.get(k) is not None]
        margins = [
            f"{name} {pct(p[k], signed=False)}"
            for k, name in (
                ("gross_margin", "brüt marj"),
                ("operating_margin", "faaliyet marjı"),
                ("net_margin", "net marj"),
            )
            if p.get(k) is not None
        ]
        text = f"{label} ({date(p['end'])} dönem sonu): " + ", ".join(figures)
        if margins:
            text += "; " + ", ".join(margins)
        facts.append(text + ".")
    q = data.get("latest_quarter") or {}
    if q.get("total_assets") is not None:
        text = (
            f"{date(q['end'])} itibarıyla toplam varlıklar {amount(q['total_assets'], cur)}, "
            f"özsermaye {amount(q['total_equity'], cur)}"
        )
        if q.get("total_debt") is not None:
            text += f", toplam finansal borç {amount(q['total_debt'], cur)}"
        if q.get("debt_to_equity") is not None:
            text += f"; borç/özsermaye {number(q['debt_to_equity'])}"
        facts.append(text + ".")
    for key, label in GROWTH:
        g = (data.get("growth") or {}).get(key)
        if not g:
            continue
        # Under TMS 29 the company restates the earlier period itself: one figure, already real.
        company_restated = str(g.get("real_method", "")).startswith("company-restated")
        parts = []
        for k, name in LINES:
            v = g.get(k)
            if not v:
                continue
            if v.get("as_reported") is None:
                parts.append(f"{name} hesaplanamıyor (dönemlerden biri zarar ya da sıfır)")
                continue
            text = f"{name} {pct(v['as_reported'])}"
            if v.get("real") is not None and not company_restated:
                text += f" (enflasyondan arındırılmış {pct(v['real'])})"
            parts.append(text)
        if parts:
            note = (
                " (şirketin enflasyona göre düzeltilmiş karşılaştırma rakamlarıyla)"
                if company_restated
                else ""
            )
            facts.append(
                f"{label} ({date(g['from'])} → {date(g['to'])}){note}: " + "; ".join(parts) + "."
            )
    if symbol.upper().endswith(".IS"):
        facts.append(
            "Kaynak resmi değildir; önemli rakamlar şirketin KAP'taki kendi raporlarından "
            "doğrulanmalıdır."
        )
    return facts


# --- check_setup ------------------------------------------------------------------------------


def _source(value: str) -> str:
    names = {
        "yahoo": "Yahoo Finance",
        "http": "kurumun veri adaptörü",
        "fixture": "yerel test verisi",
        "sec_edgar": "SEC EDGAR (resmi)",
        "esef": "ESEF (resmi)",
        "evds": "TCMB EVDS",
        "fred": "FRED",
        "oecd": "OECD (birkaç ay gecikmeli)",
        "csv": "kullanıcının CSV dosyası",
        "gdelt": "GDELT",
        "none": "kapalı",
    }
    return names.get(value, "yok" if value.startswith("unavailable") else value)


def setup(data: Mapping[str, Any]) -> list[str]:
    price = data["price_data"]
    fin = data["financial_statements"]
    infl = data["inflation"]
    # Each source with the tools it serves: a model that checks the setup first then knows
    # which tool answers the question, instead of stopping at the list of sources.
    on = price["enabled"]
    facts = [
        "Fiyat verisi: "
        + (
            f"açık ({_source(price['provider'])}); fiyat, getiri, karşılaştırma, hareket, olay "
            "ve portföy soruları için get_price_summary, compare_assets, explain_price_move, "
            "get_event_reaction, analyze_portfolio ve portfolio_real_return."
            if on
            else "kapalı."
        ),
        f"Finansal tablolar ve değerleme: Türkiye ve diğer piyasalar için "
        f"{_source(fin['other_markets'])}, ABD şirketleri için {_source(fin['us_companies'])}, "
        f"AB ve İngiltere şirketleri için {_source(fin['eu_uk_companies_by_lei'])}. Satış, kâr, "
        "marj ve borç için get_financials; piyasa değeri, F/K, PD/DD ve temettü verimi için "
        "get_valuation.",
        f"Enflasyon: Türkiye için {_source(infl['TR'])}, ABD için {_source(infl['US'])}; reel "
        "getiri için compare_real_return ve portfolio_real_return.",
        f"TL mevduat karşılaştırması: {_source(data['deposit_rates']['TRY'])}; konut fiyatları: "
        f"{_source(data['house_prices']['TR'])}.",
        f"Haberler: {_source(str(data['news']))}; get_news.",
    ]
    if data["missing"]:
        facts.append(
            f"Eksik {len(data['missing'])} ayar var; bunlar olmadan ilgili araçlar çalışmaz "
            "(ayrıntılar missing alanında)."
        )
    else:
        facts.append("Eksik ayar yok: bütün araçlar kullanılabilir.")
    if data.get("improvements"):
        facts.append(
            f"İsteğe bağlı {len(data['improvements'])} iyileştirme var; araçlar bunlar olmadan "
            "da çalışır (ayrıntılar improvements alanında)."
        )
    return facts
