"""The response contract every realmarket-mcp tool follows.

This module is the executable form of ``docs/tool-contract.md``. Tools never return a bare
dict: they return a :class:`ToolResult` (success) or raise a :class:`ToolError` (failure), and
both serialize to one stable JSON shape an LLM can rely on across every tool.

The three rules this module enforces, not merely documents:

* **Every number has a source.** A result without at least one :class:`Provenance` entry is
  refused at construction.
* **Missing is ``None``, never NaN.** Non-finite floats anywhere in ``data`` are refused, because
  ``NaN``/``Infinity`` are not valid JSON and an LLM reads them as real values.
* **Failures are actionable.** A :class:`ToolError` carries a stable code, a human message, a
  concrete hint telling the caller what to do next, and whether retrying can help.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CONTRACT_VERSION = "1"

DISCLAIMER = (
    "Informational research output computed from third-party market data. "
    "Not investment advice and not a recommendation to buy or sell any asset."
)

# Upper bound on the number of points a single series may carry in one response. Larger
# requests must be downsampled or paginated by the tool so a response fits an LLM context.
MAX_SERIES_POINTS = 500


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "invalid_argument"
    UNKNOWN_SYMBOL = "unknown_symbol"
    NO_DATA_IN_RANGE = "no_data_in_range"
    MISSING_API_KEY = "missing_api_key"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED = "unsupported"
    INTERNAL = "internal"


RETRYABLE_CODES = frozenset({ErrorCode.PROVIDER_UNAVAILABLE, ErrorCode.RATE_LIMITED})


class ContractViolation(ValueError):
    """A tool tried to return something the contract forbids. This is a bug in the tool."""


@dataclass(frozen=True)
class Provenance:
    """Where one block of numbers came from."""

    provider: str
    dataset: str
    symbols: tuple[str, ...]
    period_start: str
    period_end: str
    retrieved_at: str
    data_version: str
    adjustment: str

    def __post_init__(self) -> None:
        for name in ("provider", "dataset", "period_start", "period_end", "retrieved_at"):
            if not getattr(self, name):
                raise ContractViolation(f"Provenance.{name} must be non-empty")
        if not self.data_version:
            raise ContractViolation("Provenance.data_version must identify the exact data used")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "dataset": self.dataset,
            "symbols": list(self.symbols),
            "period_start": self.period_start,
            "period_end": self.period_end,
            "retrieved_at": self.retrieved_at,
            "data_version": self.data_version,
            "adjustment": self.adjustment,
        }


@dataclass(frozen=True)
class QualityFlag:
    """A data-quality finding the caller must see before trusting the numbers."""

    code: str
    severity: Severity
    message: str
    affected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "affected": list(self.affected),
        }


@dataclass(frozen=True)
class ToolResult:
    """A successful tool response."""

    tool: str
    data: Mapping[str, Any]
    provenance: tuple[Provenance, ...]
    quality_flags: tuple[QualityFlag, ...] = ()
    notes: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.tool:
            raise ContractViolation("ToolResult.tool must name the tool")
        if not self.provenance:
            raise ContractViolation(f"{self.tool}: a result must cite at least one Provenance")
        _check_json_safe(self.data, path=f"{self.tool}.data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "tool": self.tool,
            "data": dict(self.data),
            "provenance": [p.to_dict() for p in self.provenance],
            "quality_flags": [f.to_dict() for f in self.quality_flags],
            "notes": list(self.notes),
            "disclaimer": DISCLAIMER,
        }


@dataclass(frozen=True)
class ToolError(Exception):
    """A failed tool call, shaped so the caller knows what to do next."""

    code: ErrorCode
    message: str
    hint: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message or not self.hint:
            raise ContractViolation("ToolError needs both a message and an actionable hint")
        _check_json_safe(self.details, path="ToolError.details")

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "hint": self.hint,
                "retryable": self.retryable,
                "details": dict(self.details),
            },
        }


def _check_json_safe(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, bool | str | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractViolation(f"{path}: non-finite float {value!r}; use None for missing")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractViolation(f"{path}: mapping keys must be strings, got {key!r}")
            _check_json_safe(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence):
        if len(value) > MAX_SERIES_POINTS:
            raise ContractViolation(
                f"{path}: {len(value)} items exceeds MAX_SERIES_POINTS={MAX_SERIES_POINTS}"
            )
        for index, item in enumerate(value):
            _check_json_safe(item, path=f"{path}[{index}]")
        return
    raise ContractViolation(f"{path}: {type(value).__name__} is not JSON-safe")
