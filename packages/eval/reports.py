"""Evaluation report and retrieval review-sheet writers."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KNOWN_DIVERGENCES = [
    {
        "doc_id": "claim_PT_16658",
        "expected": "REJECT",
        "known_engine_result": "ESCALATE",
        "rule": "R2",
        "reason": "The $9,950 uncovered claim is in the near-threshold band; R2 fires before R3.",
    }
]


def report_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    decision = metrics["decision"]
    weighted = report["weighted_score"]
    lines = [
        f"# Evaluation: {report['run']['provider']} / {report['run']['split']}",
        "",
        f"- Run: `{report['run']['run_id']}`",
        f"- Documents: {metrics['sample_size']}",
        f"- Decision correctness: {_metric_text(decision)}",
        f"- Automated weighted score: {weighted['score']:.3f} ({weighted['sample_size']} scored metrics)",
        f"- Weighted score method: {weighted['method']}",
        "",
        "## Metrics",
        "",
        f"- Classification accuracy: {_metric_text(metrics['classification'])}",
        f"- Extraction completeness: {_metric_text(metrics['extraction'], 'completeness')}",
        f"- Decision correctness: {_metric_text(decision)}",
        f"- Latency p50 / p95: {_latency_text(metrics['latency_ms'])}",
        "",
        "## Confusion Matrix",
        "",
        "```json",
        json.dumps(metrics["confusion_matrix"], indent=2, sort_keys=True),
        "```",
        "",
        "## Breakdowns",
        "",
    ]
    for group_name, group_rows in metrics["breakdowns"].items():
        lines.extend(
            [
                f"### {group_name.replace('_', ' ').title()}",
                "",
                "| Group | Accuracy | Correct / N |",
                "| --- | ---: | ---: |",
            ]
        )
        lines.extend(
            f"| {name} | {_percent(value['accuracy'])} | {value['correct']} / {value['sample_size']} |"
            for name, value in group_rows.items()
        )
        lines.append("")
    lines.extend(["## Decision Mismatches", ""])
    mismatches = report.get("decision_mismatches", [])
    if not mismatches:
        lines.append("None.")
    else:
        for mismatch in mismatches:
            lines.extend(
                [
                    f"### `{mismatch['doc_id']}`",
                    "",
                    (
                        f"- Expected: **{mismatch['expected']}**; actual: **{mismatch['actual']}**; "
                        f"decision confidence: {mismatch['decision_confidence']:.3f}"
                    ),
                    "- Fired rules: "
                    + (
                        "; ".join(rule["summary"] for rule in mismatch["fired_rules"])
                        if mismatch["fired_rules"]
                        else "none recorded"
                    ),
                    f"- Minimum-confidence agent: **{mismatch['minimum_confidence_agent'] or 'n/a'}**",
                    "",
                    "| Agent | Status | Confidence |",
                    "| --- | --- | ---: |",
                ]
            )
            lines.extend(
                f"| {agent['agent']}{' **MIN**' if agent['is_minimum_confidence'] else ''} | "
                f"{agent['status']} | "
                f"{'n/a' if agent['confidence'] is None else f'{agent["confidence"]:.3f}'} |"
                for agent in mismatch["agents"]
            )
            lines.extend(
                [
                    "",
                    "Rule trace:",
                    "",
                    "```json",
                    json.dumps(mismatch["rule_trace"], indent=2),
                    "```",
                    "",
                ]
            )
    usage = report.get("groq_usage")
    if usage is not None:
        lines.extend(
            [
                "## Groq Usage",
                "",
                f"- HTTP calls by model: `{json.dumps(usage.get('calls_by_model', {}), sort_keys=True)}`",
                f"- HTTP 429 responses: {usage.get('rate_limit_responses_429', 0)}",
                f"- 429 retries: {usage.get('retries_429', 0)}",
                f"- Total wait: {usage.get('seconds_waited', 0.0):.2f} seconds",
                f"- Estimated tokens by model: `{json.dumps(usage.get('estimated_tokens_by_model', {}), sort_keys=True)}`",
                f"- Daily estimated tokens used: {usage.get('daily_tokens_used', 0)}",
                f"- Cache hits: {usage.get('cache_hits', 0)}",
                "- Usage by prompt: `"
                + json.dumps(usage.get("usage_by_prompt", {}), sort_keys=True)
                + "`",
                "",
            ]
        )
    if report.get("daily_budget_stop"):
        lines.extend(["## Partial Run", "", report["daily_budget_stop"], ""])
    lines.extend(["## Calibration", ""])
    calibration = metrics.get("calibration")
    if calibration:
        lines.extend(
            [
                f"- ECE: {calibration['ece']:.4f} (n={calibration['sample_size']})",
                "",
                "| Bin | Mean confidence | Accuracy | N |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            f"| {item['lower']:.1f}-{item['upper']:.1f} | {item['mean_confidence']:.3f} | "
            f"{item['accuracy']:.3f} | {item['sample_size']} |"
            for item in calibration["bins"]
        )
    else:
        lines.append("Not available (no confidence values).")
    lines.extend(["", "## Failures", ""])
    failures = report.get("failures", [])
    if failures:
        lines.extend(
            f"- `{failure['doc_id']}` ({failure['agent']}): {failure['message']}"
            for failure in failures
        )
    else:
        lines.append("None.")
    lines.extend(["", "## Known Divergences", ""])
    divergences = report.get("known_divergences") or KNOWN_DIVERGENCES
    lines.extend(
        f"- `{item['doc_id']}`: expected **{item['expected']}**, known engine result **"
        f"{item['known_engine_result']}** via {item['rule']}. {item['reason']} "
        f"Observed in this run: {item.get('observed') or 'not evaluated'}."
        for item in divergences
    )
    lines.extend(
        ["", "## Retrieval Review", "", f"Review sheet: `{report['run']['retrieval_csv']}`", ""]
    )
    return "\n".join(lines)


def _metric_text(value: dict[str, Any], value_key: str = "accuracy") -> str:
    metric = value.get(value_key)
    return f"{_percent(metric)} ({value['correct']} / {value['sample_size']})"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _latency_text(value: dict[str, Any]) -> str:
    if value["sample_size"] == 0:
        return "n/a / n/a (n=0)"
    return f"{value['p50']:.1f} ms / {value['p95']:.1f} ms (n={value['sample_size']})"


def write_reports(
    report: dict[str, Any],
    retrieval_rows: list[dict[str, Any]],
    reports_dir: Path,
    run_id: str | None = None,
) -> tuple[Path, Path, Path]:
    stamp = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"eval_{stamp}.json"
    markdown_path = reports_dir / f"eval_{stamp}.md"
    csv_path = reports_dir / f"eval_{stamp}_retrieval.csv"
    report["run"]["run_id"] = stamp
    report["run"]["retrieval_csv"] = csv_path.name
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(report_markdown(report) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as sheet:
        columns = ["doc_id", "cpt_code", "retrieved_clause", "cited_clause", "covered"]
        writer = csv.DictWriter(sheet, fieldnames=columns)
        writer.writeheader()
        writer.writerows(retrieval_rows)
    return json_path, markdown_path, csv_path
