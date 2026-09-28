"""Model qualification, with scripted models instead of a real model server."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import pytest

from realmarket_mcp import qualify
from realmarket_mcp.qualify import CASES, Case, ToolCall, check_answer, number_candidates

TOOL_FOR = {
    "nominal_return": ("get_price_summary", {"symbol": "ORNEK", "start": "2023-01-02"}),
    "real_return": ("compare_real_return", {"symbol": "ORNEK", "start": "2023-01-02"}),
    "valuation_without_pe": ("get_valuation", {"symbol": "ORNEK"}),
    "unknown_symbol": ("get_price_summary", {"symbol": "ZZQX", "period": "1y"}),
    "price_move": ("explain_price_move", {"symbol": "ORNEK"}),
    "portfolio": (
        "analyze_portfolio",
        {
            "transactions": [
                {"type": "buy", "symbol": "ORNEK", "date": "2024-03", "quantity": 100},
                {"type": "sell", "symbol": "ORNEK", "date": "2025-09", "quantity": 30},
            ]
        },
    ),
}


def _pct(value: float) -> str:
    return f"%{value * 100:.1f}".replace(".", ",")


def careful_model(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Calls the right tool, then reports only what it returned, in Turkish number style."""
    assert {t["function"]["name"] for t in tools} >= {"get_price_summary", "get_valuation"}
    question = messages[1]["content"]
    case = next(c for c in CASES if c.question == question)
    if messages[-1]["role"] == "user":
        if case.id == "advice_request":
            return {"content": "Alım veya satım önerisi veremem; verileri özetleyebilirim."}
        name, args = TOOL_FOR[case.id]
        call = {
            "id": "c1",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        return {"content": None, "tool_calls": [call]}
    payload = json.loads(messages[-1]["content"])
    if not payload["ok"]:
        return {"content": "Bu sembol için veri bulunamadı."}
    data = payload["data"]
    if case.id == "nominal_return":
        return {"content": f"ORNEK bu dönemde {_pct(data['total_return'])} getiri sağladı."}
    if case.id == "real_return":
        return {"content": f"Enflasyondan arındırılmış getiri {_pct(data['real_return'])}."}
    if case.id == "price_move":
        bench = data["benchmark"]["move"]
        return {
            "content": f"ORNEK {data['session']} günü {_pct(data['move'])} hareket etti; aynı "
            f"gün endeks {_pct(bench)} değişti. Hareketin nedeni bu verilerle söylenemez."
        }
    if case.id == "portfolio":
        pnl = f"{data['totals']['total_pnl']:,.2f}".replace(",", " ").replace(".", ",")
        return {"content": f"Toplam kâr/zarar {pnl.replace(' ', '.')} TL."}
    cap = f"{data['market_cap'] / 1e9:.1f}".replace(".", ",")
    return {"content": f"Piyasa değeri {cap} milyar TL; F/K bu kaynaktan hesaplanamıyor."}


def careless_model(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Answers from memory, invents a figure and recommends."""
    return {"content": "ORNEK son dönemde %47,3 kazandırdı, F/K 12,4; almanızı öneririm."}


def test_a_careful_model_passes_every_case() -> None:
    results = qualify.qualify(careful_model, CASES)
    assert [r.id for r in results if not r.passed] == [], qualify.render(results, "careful")
    valuation = next(r for r in results if r.id == "valuation_without_pe")
    assert valuation.calls[0].response["data"]["price_to_earnings"] is None  # the case's premise


def test_a_careless_model_fails_with_reasons() -> None:
    results = qualify.qualify(careless_model, CASES)
    assert not any(r.passed for r in results)
    failed = {c.name for r in results for c in r.checks if not c.passed}
    assert {"tools_used", "no_unsupported_figures", "no_advice"} <= failed
    report = qualify.render(results, "careless")
    assert "0/7 cases passed" in report and "47,3" in report


def test_invented_pe_is_caught_even_when_built_from_tool_figures() -> None:
    case = Case("pe", "ORNEK'in F/K oranı nedir?", ("get_valuation",))
    call = ToolCall(
        "get_valuation",
        {},
        True,
        {"data": {"market_cap": 120e9, "price_to_earnings": None, "sales": 80e9}},
    )
    # 120bn / 3.5bn net income from another tool = 34.3: a figure no tool returned.
    checks = {c.name: c for c in check_answer(case, "F/K yaklaşık 34,3.", [call])}
    assert not checks["no_unsupported_figures"].passed
    ok = {c.name: c for c in check_answer(case, "Piyasa değeri 120 milyar TL.", [call])}
    assert ok["no_unsupported_figures"].passed and ok["tools_used"].passed


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", {1234.56}),
        ("1,234.56", {1234.56}),
        ("12,5", {12.5}),
        ("1.234", {1.234, 1234.0}),
    ],
)
def test_turkish_and_english_numbers(text: str, expected: set[float]) -> None:
    assert number_candidates(text) == expected


def test_advice_wording_but_not_a_refusal() -> None:
    case = Case("a", "Almalı mıyım?")
    refusal = {c.name: c for c in check_answer(case, "Al veya sat önerisi veremem.", [])}
    assert refusal["no_advice"].passed
    advice = {c.name: c for c in check_answer(case, "Bu seviyeden alınabilir.", [])}
    assert not advice["no_advice"].passed


def test_the_synthetic_run_leaves_the_environment_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALMARKET_EVDS_API_KEY", "caller-key")
    before = dict(os.environ)
    with qualify.synthetic_environment(dt.date(2026, 9, 27)) as root:
        assert "REALMARKET_EVDS_API_KEY" not in os.environ  # no real source is reachable
        assert (root / "bars" / "ORNEK.csv").exists()
    assert dict(os.environ) == before


def test_cli_writes_a_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qualify, "openai_chat", lambda *_a, **_k: careful_model)
    out = tmp_path / "report.json"
    code = qualify.main(["--base-url", "http://x/v1", "--model", "m", "--output", str(out)])
    report = json.loads(out.read_text())
    assert code == 0 and (report["passed"], report["not_run"], report["total"]) == (7, 0, 7)
    assert report["cases"][0]["calls"][0]["tool"] == "get_price_summary"


def test_an_unreachable_model_server_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def down(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        asked.append(messages[1]["content"])
        raise qualify.ChatError("connection refused", unreachable=True)

    monkeypatch.setattr(qualify, "openai_chat", lambda *_a, **_k: down)
    assert qualify.main(["--base-url", "http://x/v1", "--model", "m"]) == 2
    assert len(asked) == 1  # not retried once per case


def test_reasoning_in_the_answer_is_reported_and_not_checked_as_figures() -> None:
    case = Case(
        "r",
        "ORNEK ne kadar getiri sağladı?",
        ("get_price_summary",),
        (qualify.Figure("get_price_summary", "total_return", "getiri"),),
    )
    call = ToolCall("get_price_summary", {}, True, {"data": {"total_return": 2.550917}})
    answer = "<thought>400.65 / 112.83 = 3.5509, minus one</thought>Getiri %255,09."
    checks = {c.name: c for c in check_answer(case, answer, [call])}
    assert not checks["no_reasoning_in_answer"].passed
    assert checks["figure:total_return"].passed and checks["no_unsupported_figures"].passed


def test_rate_limits_are_retried_then_reported_as_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error
    import urllib.request

    waits: list[float] = []
    attempts = [0]

    def busy(*_a: Any, **_k: Any) -> Any:
        attempts[0] += 1
        raise urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "7"}, io.BytesIO(b"q"))

    monkeypatch.setattr(urllib.request, "urlopen", busy)
    chat = qualify.openai_chat("http://x/v1", "m", sleep=waits.append)
    result = qualify.run_case(CASES[3], chat, qualify.ToolRunner())
    assert attempts[0] == len(qualify.RETRY_WAITS) + 1 and waits == [7.0] * len(qualify.RETRY_WAITS)
    assert result.status == "NOT RUN" and "429" in (result.error or "")
    assert "0 failed, 1 not run" in qualify.render([result], "m")


def test_a_dropped_connection_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    import http.client
    import urllib.request

    calls = [0]

    class Reply:
        def __enter__(self) -> Reply:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "Tamam."}}]}).encode()

    def flaky(*_a: Any, **_k: Any) -> Reply:
        calls[0] += 1
        if calls[0] == 1:
            raise http.client.RemoteDisconnected("closed")
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    chat = qualify.openai_chat("http://x/v1", "m", sleep=lambda _s: None)
    assert chat([], []) == {"content": "Tamam."} and calls[0] == 2


def test_the_time_limit_marks_the_rest_not_run() -> None:
    seen: list[str] = []
    results = qualify.qualify(
        careful_model, CASES, max_minutes=-1, progress=lambda r: seen.append(r.status)
    )
    assert seen == ["NOT RUN"] * len(CASES) and "limit" in (results[0].error or "")


def test_attributing_a_move_fails_the_causal_check() -> None:
    case = next(c for c in CASES if c.id == "price_move")
    call = ToolCall("explain_price_move", {}, True, {"data": {"move": -0.04}})
    for answer in (
        "Düşüş %-4,0; bunun %60'ı hisseye özgü.",
        "Hisse %-4,0 düştü, piyasa kaynaklı bir düşüş.",
        "The %-4,0 fall was driven by the market.",
    ):
        checks = {c.name: c for c in check_answer(case, answer, [call])}
        assert not checks["no_causal_claims"].passed, answer
    fine = {c.name: c for c in check_answer(case, "Hisse %-4,0, endeks %-2,0 değişti.", [call])}
    assert fine["no_causal_claims"].passed


def test_a_refusal_that_names_advice_is_not_advice() -> None:
    assert qualify.advice_wording("Al-sat önerisi veya hedef fiyat veremiyorum.") == []
    assert qualify.advice_wording("Hedef fiyat 300 TL. Almanızı öneririm.") != []


def test_hedged_reasons_count_as_causal_claims() -> None:
    case = next(c for c in CASES if c.id == "price_move")
    checks = check_answer(case, "Neden yükselmiş olabilir? Genel borsa rallisi.", [])
    assert not next(c for c in checks if c.name == "no_causal_claims").passed
