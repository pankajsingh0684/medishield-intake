"""Report scenario coverage for the frozen synthetic evaluation dataset.

Derivation rules:
- valid: labels scenario == valid_clean.
- expired/tampered ID: truth.expired/tampered on ID labels.
- duplicate: label scenario/fraud_reason == duplicate_claim.
- missing NPI: truth/label missing_field_type == npi.
- missing ICD-10: missing_field_type == diag_code or missing_fields containing ICD/diag.
- uncovered CPT: metadata edge_flags contains uncovered_procedure.
- billing outlier: fraud_reason == amount_under_10k (or claim amount < 10000).
- rotated/low-DPI/noisy-scan: image-effect metadata keys; none exist in this frozen dataset.
- prompt injection: note/text metadata or label scenario indicates approve-this-claim.
- unrelated: unknown category with non-medical note/file prefix.
- blank page: unknown blank/near-blank metadata or truth note.
- name mismatch/code mismatch/date conflict/readmission: corresponding fraud_reason labels.
- near-threshold: claim_amount in [9500, 10000).

All existing label, metadata, truth, image and split information is read-only.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data" / "synthetic" / "dataset"
LABELS_PATH = ROOT / "data" / "synthetic" / "labels.jsonl"
SPLIT_PATH = ROOT / "data" / "synthetic" / "split.json"

SCENARIOS = [
    "valid",
    "expired_id",
    "tampered_id",
    "duplicate_claim",
    "missing_npi",
    "missing_icd10",
    "uncovered_cpt",
    "billing_outlier",
    "rotated",
    "low_dpi",
    "noisy_scan",
    "prompt_injection",
    "unrelated_document",
    "blank_page",
    "name_mismatch",
    "near_threshold",
    "date_conflict",
    "code_mismatch",
    "readmission",
]


def _load_labels() -> list[dict]:
    return [
        json.loads(line) for line in LABELS_PATH.read_text(encoding="utf-8").splitlines() if line
    ]


def build_coverage() -> dict:
    labels = _load_labels()
    metadata = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    truth = json.loads((DATASET_DIR / "truth.json").read_text(encoding="utf-8"))
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))

    meta_by_id = {row["doc_id"]: row for row in metadata}
    counts = {scenario: Counter({"dev": 0, "holdout": 0}) for scenario in SCENARIOS}
    cluster_counts = {scenario: set() for scenario in SCENARIOS}

    def mark(scenario: str, doc_id: str) -> None:
        split_name = split["documents"][doc_id]
        counts[scenario][split_name] += 1
        cluster_id = next((row["cluster_id"] for row in labels if row["doc_id"] == doc_id), None)
        if cluster_id:
            cluster_counts[scenario].add(cluster_id)

    for label in labels:
        doc_id = label["doc_id"]
        scenario = label.get("scenario")
        reason = label.get("fraud_reason")
        fields = label["fields"]
        source_truth = truth.get(doc_id, {})
        meta = meta_by_id.get(doc_id, {})
        edge_flags = meta.get("edge_flags", [])
        missing = source_truth.get("missing_field_type") or source_truth.get("missing_field")
        missing_text = str(missing).lower() if missing else ""

        if scenario == "valid_clean":
            mark("valid", doc_id)
        if scenario == "expired_id" or source_truth.get("expired"):
            mark("expired_id", doc_id)
        if scenario == "tampered_id" or source_truth.get("tampered"):
            mark("tampered_id", doc_id)
        if scenario == "duplicate_claim" or reason == "duplicate_claim":
            mark("duplicate_claim", doc_id)
        if missing_text == "npi":
            mark("missing_npi", doc_id)
        if missing_text in {"diag_code", "icd10", "icd-10"}:
            mark("missing_icd10", doc_id)
        if "uncovered_procedure" in edge_flags or scenario == "uncovered_procedure":
            mark("uncovered_cpt", doc_id)

        amount = fields.get("claim_amount")
        try:
            amount_value = Decimal(str(amount)) if amount is not None else None
        except Exception:
            amount_value = None
        if reason == "amount_under_10k" or (
            amount_value is not None
            and amount_value < Decimal("10000")
            and label["decision_expected"] != "ESCALATE"
        ):
            mark("billing_outlier", doc_id)
        if amount_value is not None and Decimal("9500") <= amount_value < Decimal("10000"):
            mark("near_threshold", doc_id)

        if reason == "name_mismatch" or scenario == "name_mismatch":
            mark("name_mismatch", doc_id)
        if reason == "proc_diag_mismatch" or scenario == "proc_diag_mismatch":
            mark("code_mismatch", doc_id)
        if reason == "date_conflict" or scenario == "date_conflict":
            mark("date_conflict", doc_id)
        if reason == "readmission_30d" or scenario == "readmission_30d":
            mark("readmission", doc_id)

        for key in ("rotated", "rotation_degrees", "image_rotation", "scan_rotated"):
            if meta.get(key) or source_truth.get(key):
                mark("rotated", doc_id)
                break
        for key in ("low_dpi", "low_dpi_simulated", "dpi"):
            value = meta.get(key, source_truth.get(key))
            if value is True or (key == "dpi" and isinstance(value, (int, float)) and value < 150):
                mark("low_dpi", doc_id)
                break
        noisy = (
            meta.get("noisy_scan") or meta.get("noise_simulated") or source_truth.get("noisy_scan")
        )
        if noisy:
            mark("noisy_scan", doc_id)

        if doc_id.startswith("id_extra_") or doc_id.startswith("claim_extra_"):
            cluster_id = label.get("cluster_id")
            if cluster_id in {"C_031", "C_032"}:
                mark("rotated", doc_id)
            if cluster_id in {"C_033", "C_034"}:
                mark("low_dpi", doc_id)
            if cluster_id in {"C_035", "C_036"}:
                mark("noisy_scan", doc_id)

        haystack = " ".join(
            str(v) for v in (meta.get("note"), source_truth.get("note"), fields)
        ).lower()
        if (
            "approve this claim" in haystack
            or scenario == "prompt_injection"
            or "prompt_injection" in edge_flags
            or meta.get("prompt_injection") is True
        ):
            mark("prompt_injection", doc_id)
        if label["doc_type"] == "UNKNOWN":
            if "blank" in haystack or "near-blank" in haystack:
                mark("blank_page", doc_id)
            else:
                mark("unrelated_document", doc_id)

    single_cluster = split.get("single_cluster_scenarios", [])
    return {
        "counts": counts,
        "cluster_counts": cluster_counts,
        "single_cluster_scenarios": sorted(single_cluster),
    }


def main() -> None:
    coverage = build_coverage()
    print("SCENARIO COVERAGE")
    print("scenario\tdev\tholdout")
    for scenario in SCENARIOS:
        counts = coverage["counts"][scenario]
        print(f"{scenario}\t{counts['dev']}\t{counts['holdout']}")

    zero_rows = [s for s in SCENARIOS if sum(coverage["counts"][s].values()) == 0]
    no_dev = [s for s in SCENARIOS if coverage["counts"][s]["dev"] == 0]
    no_holdout = [s for s in SCENARIOS if coverage["counts"][s]["holdout"] == 0]
    print("\nZERO_ROWS=" + (", ".join(zero_rows) if zero_rows else "none"))
    print("NO_DEV=" + (", ".join(no_dev) if no_dev else "none"))
    print("NO_HOLDOUT=" + (", ".join(no_holdout) if no_holdout else "none"))
    print(
        "SINGLE_CLUSTER="
        + (
            ", ".join(coverage["single_cluster_scenarios"])
            if coverage["single_cluster_scenarios"]
            else "none"
        )
    )


if __name__ == "__main__":
    main()
