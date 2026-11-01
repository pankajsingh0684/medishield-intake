"""Build labels.jsonl from the frozen dataset metadata and truth files."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.enums import DocType
from packages.eval.labels import LabelFields, LabelRecord

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data" / "synthetic" / "dataset"
OUTPUT_PATH = ROOT / "data" / "synthetic" / "labels.jsonl"

DOC_TYPES = {
    "claim_forms": DocType.CLAIM_FORM,
    "id_documents": DocType.ID_DOCUMENT,
    "discharge_summaries": DocType.DISCHARGE_SUMMARY,
    "prescriptions": DocType.PRESCRIPTION,
    "policy_amendments": DocType.POLICY_AMENDMENT,
    "unknown": DocType.UNKNOWN,
}


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value)[:10])


def _scenario(metadata: dict[str, Any], truth: dict[str, Any]) -> str | None:
    fraud_reason = metadata.get("fraud_reason")
    if fraud_reason:
        return fraud_reason
    if truth.get("tampered"):
        return "tampered_id"
    if truth.get("expired"):
        return "expired_id"
    edge_flags = metadata.get("edge_flags", [])
    if "expiring_soon_id" in edge_flags:
        return "expiring_soon_id"
    if "uncovered_procedure" in edge_flags:
        return "uncovered_procedure"
    if truth.get("missing_field_type") or truth.get("missing_field"):
        return "missing_field"
    if metadata["doc_id"].endswith("_dup"):
        return "duplicate_claim"
    if metadata["category"] == "policy_amendments":
        return "policy_amendment"
    if metadata["category"] == "unknown":
        return "unknown"
    if metadata["category"] in DOC_TYPES:
        return "valid_clean"
    return None


def _fields(category: str, truth: dict[str, Any]) -> LabelFields:
    missing_field_type = truth.get("missing_field_type") or truth.get("missing_field")
    if category in {"claim_forms", "discharge_summaries"}:
        icd10_codes = list(truth.get("icd10_codes", []))
        if missing_field_type == "diag_code":
            icd10_codes = []
        icd10_code = None if missing_field_type == "diag_code" else truth.get("icd10_code")
        cpt_codes = list(truth.get("cpt_codes", []))
    else:
        icd10_codes = None
        icd10_code = None
        cpt_codes = None

    provider_npi = truth.get("provider_npi")
    if provider_npi and provider_npi.startswith("NPI-"):
        provider_npi = provider_npi[4:]

    return LabelFields(
        claim_amount=truth.get("claim_amount"),
        icd10_codes=icd10_codes,
        icd10_code=icd10_code,
        cpt_codes=cpt_codes,
        provider_npi=provider_npi,
        service_date=_as_date(truth.get("service_date")),
        admit_date=_as_date(truth.get("admit_date")),
        discharge_date=_as_date(truth.get("discharge_date")),
        rx_date=_as_date(truth.get("rx_date")),
        drug_names=truth.get("drug_names"),
        signature_present=truth.get("signature_present"),
        printed_name=truth.get("printed_name"),
        printed_expiry_date=_as_date(truth.get("printed_expiry_date")),
        expired=truth.get("expired"),
        tampered=truth.get("tampered"),
        missing_field_type=missing_field_type,
    )


def build_labels(
    metadata_rows: list[dict[str, Any]], truth_by_doc: dict[str, dict[str, Any]]
) -> tuple[list[LabelRecord], list[str]]:
    labels: list[LabelRecord] = []
    unmatched: list[str] = []

    for metadata in metadata_rows:
        truth = truth_by_doc[metadata["doc_id"]]
        category = metadata["category"]
        doc_type = DOC_TYPES[category]
        scenario = _scenario(metadata, truth)
        if scenario is None:
            unmatched.append(metadata["doc_id"])

        kyc_expected = None
        if doc_type == DocType.ID_DOCUMENT:
            kyc_expected = "FAIL" if truth.get("expired") else "PASS"

        coverage_expected = None
        if doc_type == DocType.CLAIM_FORM:
            coverage_expected = "uncovered_procedure" not in metadata.get("edge_flags", [])

        fraud_expected = "FLAGGED" if metadata["fraud_label"] else "LOW"
        reference_date = _as_date(truth.get("reference_date"))
        labels.append(
            LabelRecord(
                doc_id=metadata["doc_id"],
                file=f"dataset/{metadata['file_path'].replace(chr(92), '/')}",
                doc_type=doc_type,
                cluster_id=truth.get("cluster_id"),
                patient_id=truth.get("patient_id"),
                fields=_fields(category, truth),
                kyc_expected=kyc_expected,
                coverage_expected=coverage_expected,
                fraud_expected=fraud_expected,
                fraud_reason=metadata.get("fraud_reason"),
                decision_expected=metadata["expected_decision"],
                scenario=scenario,
                reference_date=reference_date,
            )
        )

    return labels, unmatched


def main() -> None:
    metadata_rows = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    truth_by_doc = json.loads((DATASET_DIR / "truth.json").read_text(encoding="utf-8"))
    labels, unmatched = build_labels(metadata_rows, truth_by_doc)
    OUTPUT_PATH.write_text(
        "".join(f"{label.model_dump_json()}\n" for label in labels),
        encoding="utf-8",
    )
    print(f"Wrote {len(labels)} labels to {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"Unmatched scenarios: {unmatched}")


if __name__ == "__main__":
    main()
