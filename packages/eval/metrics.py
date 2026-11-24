"""Scoring and aggregation for synthetic evaluation runs."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from packages.eval.labels import LabelRecord


def _accuracy(rows: list[dict[str, Any]], expected_key: str, actual_key: str) -> dict[str, Any]:
    eligible = [row for row in rows if row.get(expected_key) is not None]
    correct = sum(row.get(actual_key) == row[expected_key] for row in eligible)
    return {
        "correct": correct,
        "sample_size": len(eligible),
        "accuracy": correct / len(eligible) if eligible else None,
    }


def _field_matches(expected: Any, actual: Any, field: str) -> bool:
    if expected is None:
        return False
    if field == "claim_amount":
        try:
            return abs(float(expected) - float(actual)) <= 0.01
        except (TypeError, ValueError):
            return False
    if field in {"cpt_codes", "icd10_codes", "drug_names"}:
        return isinstance(actual, (list, tuple, set)) and set(expected) == set(actual)
    if hasattr(expected, "isoformat") and isinstance(actual, str):
        return expected.isoformat() == actual
    return expected == actual


def _group_breakdown(
    rows: list[dict[str, Any]], group_key: str, expected_key: str, actual_key: str
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group = row.get(group_key) or "unclassified"
        groups[str(group)].append(row)
    return {
        group: _accuracy(group_rows, expected_key, actual_key)
        for group, group_rows in sorted(groups.items())
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calculate_metrics(
    rows: list[dict[str, Any]], labels_by_id: dict[str, LabelRecord]
) -> dict[str, Any]:
    """Score normalized prediction rows; every aggregate carries its denominator."""
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    extraction_correct = 0
    extraction_total = 0

    for row in rows:
        label = labels_by_id[row["doc_id"]]
        expected_decision = label.decision_expected.value
        predicted_decision = row.get("decision")
        confusion[expected_decision][str(predicted_decision or "NO_DECISION")] += 1

        if label.doc_type.value == "CLAIM_FORM":
            actual_fields = row.get("fields") or {}
            for field in (
                "icd10_codes",
                "cpt_codes",
                "claim_amount",
                "provider_npi",
                "service_date",
            ):
                expected = getattr(label.fields, field)
                if expected is None:
                    continue
                extraction_total += 1
                extraction_correct += _field_matches(expected, actual_fields.get(field), field)

    decision_rows = [
        {**row, "decision_expected": labels_by_id[row["doc_id"]].decision_expected.value}
        for row in rows
    ]
    classification_rows = [
        {**row, "doc_type_expected": labels_by_id[row["doc_id"]].doc_type.value} for row in rows
    ]
    decision_rows = [
        {**row, "doc_type_expected": labels_by_id[row["doc_id"]].doc_type.value}
        for row in decision_rows
    ]
    decisions = _accuracy(decision_rows, "decision_expected", "decision")
    classification = _accuracy(classification_rows, "doc_type_expected", "doc_type")
    extraction = {
        "correct": extraction_correct,
        "sample_size": extraction_total,
        "completeness": extraction_correct / extraction_total if extraction_total else None,
    }
    latency_values = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]

    result: dict[str, Any] = {
        "sample_size": len(rows),
        "classification": classification,
        "extraction": extraction,
        "decision": decisions,
        "confusion_matrix": {
            expected: dict(sorted(predicted.items()))
            for expected, predicted in sorted(confusion.items())
        },
        "breakdowns": {
            "scenario": _group_breakdown(
                decision_rows, "scenario", "decision_expected", "decision"
            ),
            "document_category": _group_breakdown(
                decision_rows, "doc_type_expected", "decision_expected", "decision"
            ),
            "split": _group_breakdown(decision_rows, "split", "decision_expected", "decision"),
        },
        "latency_ms": {
            "sample_size": len(latency_values),
            "p50": _percentile(latency_values, 0.50),
            "p95": _percentile(latency_values, 0.95),
        },
    }

    calibrated = [
        row
        for row in decision_rows
        if row.get("confidence") is not None and row.get("decision") is not None
    ]
    if calibrated:
        bins: list[dict[str, Any]] = []
        for bin_index in range(5):
            bin_rows = [
                row for row in calibrated if min(int(float(row["confidence"]) * 5), 4) == bin_index
            ]
            if bin_rows:
                bins.append(
                    {
                        "lower": bin_index / 5,
                        "upper": (bin_index + 1) / 5,
                        "sample_size": len(bin_rows),
                        "mean_confidence": sum(float(row["confidence"]) for row in bin_rows)
                        / len(bin_rows),
                        "accuracy": _accuracy(bin_rows, "decision_expected", "decision")[
                            "accuracy"
                        ],
                    }
                )
        ece = sum(
            item["sample_size"] / len(calibrated) * abs(item["mean_confidence"] - item["accuracy"])
            for item in bins
        )
        result["calibration"] = {"sample_size": len(calibrated), "bins": bins, "ece": ece}
    else:
        result["calibration"] = None
    return result
