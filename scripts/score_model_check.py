"""Score a model check: each answer against the tool calls that produced it.

    python scripts/score_model_check.py --questions evals/customer_questions.json \\
        --log run/calls.jsonl --answers run/answers --output run/report

The log is what scripts/call_tool.py --log --case wrote; each answer is <answers>/<id>.md.
The checks are realmarket-qualify's: the expected tools were called, every figure in the
answer appears in a result (its data or its facts), no advice wording, no causal wording.
Writes <output>.json (every check) and <output>.md (per category, then each failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from realmarket_mcp import qualify
from realmarket_mcp.qualify import Case, ToolCall


def score(questions: list[dict[str, Any]], log: Path, answers: Path) -> list[dict[str, Any]]:
    calls: dict[str, list[ToolCall]] = defaultdict(list)
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            response = record["response"]
            calls[record["case"]].append(
                ToolCall(record["tool"], record["arguments"], bool(response.get("ok")), response)
            )
    results = []
    for q in questions:
        case = Case(
            id=q["id"],
            question=q["question"],
            expect_tools=tuple(q.get("expect_tools", ())),
            purpose=q.get("purpose", ""),
            no_causal_claims=bool(q.get("no_causal_claims", False)),
        )
        path = answers / f"{q['id']}.md"
        answer = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        checks = (
            qualify.check_answer(case, answer, calls[q["id"]])
            if answer
            else [qualify.Check("answered", False, "no answer file")]
        )
        results.append(
            {
                "id": q["id"],
                "category": q["category"],
                "question": q["question"],
                "passed": all(c.passed for c in checks),
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks
                ],
                "tools": [c.tool for c in calls[q["id"]]],
                "answer": answer,
            }
        )
    return results


def render(results: list[dict[str, Any]]) -> str:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r)
    passed = sum(r["passed"] for r in results)
    lines = [f"# Model check: {passed}/{len(results)} answers passed", ""]
    lines += ["| Category | Passed |", "|---|---|"]
    for category, rows in by_category.items():
        lines.append(f"| {category} | {sum(r['passed'] for r in rows)}/{len(rows)} |")
    lines += ["", "## Failures", ""]
    for r in results:
        if r["passed"]:
            continue
        failed = [f"{c['name']}: {c['detail']}" for c in r["checks"] if not c["passed"]]
        lines += [
            f"### {r['id']} — {r['question']}",
            f"- tools: {', '.join(r['tools']) or '—'}",
            *[f"- ✗ {f}" for f in failed],
            "",
            "> " + r["answer"].replace("\n", "\n> "),
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="score_model_check", description=__doc__.split("\n")[0])
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="path without extension")
    parser.add_argument("--only", help="comma-separated question ids to score")
    args = parser.parse_args(argv)
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    results = score(questions, args.log, args.answers)
    args.output.with_suffix(".json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    report = render(results)
    args.output.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report.split("\n## Failures")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
