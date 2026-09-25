from __future__ import annotations

import json
import math
import socket

import pytest

from realmarket_mcp.contract import (
    CONTRACT_VERSION,
    DISCLAIMER,
    MAX_SERIES_POINTS,
    ContractViolation,
    ErrorCode,
    Provenance,
    QualityFlag,
    Severity,
    ToolError,
    ToolResult,
)


def _provenance() -> Provenance:
    return Provenance(
        provider="fixture",
        dataset="daily_ohlc",
        symbols=("AAA",),
        period_start="2024-01-02",
        period_end="2024-12-31",
        retrieved_at="2025-01-01T00:00:00Z",
        data_version="sha256:abc123",
        adjustment="split_and_dividend",
    )


def test_result_serializes_to_the_documented_envelope() -> None:
    result = ToolResult(
        tool="get_price_summary",
        data={"total_return": 0.12, "max_drawdown": -0.08, "missing": None},
        provenance=(_provenance(),),
        quality_flags=(
            QualityFlag("gap", Severity.WARNING, "12-day gap in bars", ("2024-05-01",)),
        ),
    )

    payload = json.loads(json.dumps(result.to_dict(), allow_nan=False))

    assert payload["ok"] is True
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["provenance"][0]["data_version"] == "sha256:abc123"
    assert payload["quality_flags"][0]["severity"] == "warning"
    assert payload["data"]["missing"] is None


def test_result_without_provenance_is_refused() -> None:
    with pytest.raises(ContractViolation, match="Provenance"):
        ToolResult(tool="t", data={"x": 1}, provenance=())


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_refused_even_when_nested(bad: float) -> None:
    with pytest.raises(ContractViolation, match="non-finite"):
        ToolResult(tool="t", data={"series": [{"v": 1.0}, {"v": bad}]}, provenance=(_provenance(),))


def test_oversized_series_is_refused() -> None:
    with pytest.raises(ContractViolation, match="MAX_SERIES_POINTS"):
        ToolResult(
            tool="t",
            data={"series": list(range(MAX_SERIES_POINTS + 1))},
            provenance=(_provenance(),),
        )


def test_non_json_types_are_refused() -> None:
    with pytest.raises(ContractViolation, match="not JSON-safe"):
        ToolResult(tool="t", data={"when": object()}, provenance=(_provenance(),))


def test_provenance_requires_a_data_version() -> None:
    with pytest.raises(ContractViolation, match="data_version"):
        Provenance("p", "d", (), "2024-01-01", "2024-01-02", "2024-01-03T00:00:00Z", "", "none")


def test_error_envelope_carries_code_hint_and_retryability() -> None:
    error = ToolError(
        ErrorCode.RATE_LIMITED,
        "Provider rate limit reached",
        "Wait about 60 seconds, then retry the same call.",
        {"retry_after_seconds": 60},
    )

    payload = error.to_dict()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "rate_limited"
    assert payload["error"]["retryable"] is True
    assert payload["error"]["hint"].startswith("Wait")


def test_non_transient_errors_are_not_retryable() -> None:
    error = ToolError(ErrorCode.UNKNOWN_SYMBOL, "No such symbol: XYZ", "Call search_assets first.")
    assert error.retryable is False


def test_error_without_a_hint_is_refused() -> None:
    with pytest.raises(ContractViolation, match="hint"):
        ToolError(ErrorCode.INTERNAL, "boom", "")


def test_the_suite_cannot_reach_the_network() -> None:
    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("example.com", 443))
