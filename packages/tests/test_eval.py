import json
from collections import Counter
from pathlib import Path

from packages.core.enums import DocType
from packages.eval import DATASET_AS_OF_DATE, reference_date_for_run
from packages.eval.labels import LabelRecord
from packages.eval.split import LABELS_PATH, OUTPUT_PATH, build_split
from scripts.build_labels import DATASET_DIR, build_labels

ROOT = Path(__file__).resolve().parents[2]


def _source_data() -> tuple[list[dict], dict[str, dict]]:
    metadata = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    truth = json.loads((DATASET_DIR / "truth.json").read_text(encoding="utf-8"))
    return metadata, truth


def test_labels_validate_and_every_listed_file_exists() -> None:
    metadata, truth = _source_data()
    labels, unmatched = build_labels(metadata, truth)

    assert unmatched == []
    assert len(labels) == 155
    assert all(isinstance(label, LabelRecord) for label in labels)
    assert all((ROOT / "data" / "synthetic" / label.file).is_file() for label in labels)


def test_derived_label_and_split_artifacts_match_builders() -> None:
    metadata, truth = _source_data()
    labels, _ = build_labels(metadata, truth)

    assert LABELS_PATH.is_file()
    artifact_labels = [
        LabelRecord.model_validate_json(line)
        for line in LABELS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    assert artifact_labels == labels
    assert OUTPUT_PATH.is_file()
    assert json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) == build_split(labels)


def test_dataset_category_and_decision_counts() -> None:
    metadata, truth = _source_data()
    labels, _ = build_labels(metadata, truth)

    assert Counter(row["category"] for row in metadata) == {
        "claim_forms": 31,
        "id_documents": 30,
        "discharge_summaries": 30,
        "prescriptions": 30,
        "policy_amendments": 30,
        "unknown": 4,
    }
    assert Counter(label.decision_expected.value for label in labels) == {
        "APPROVE": 94,
        "ESCALATE": 43,
        "REJECT": 18,
    }


def test_labels_follow_expected_derivation_rules() -> None:
    metadata, truth = _source_data()
    labels, _ = build_labels(metadata, truth)
    by_id = {label.doc_id: label for label in labels}

    assert sum(label.doc_id.endswith("_dup") for label in labels) == 1
    duplicate = next(label for label in labels if label.doc_id.endswith("_dup"))
    assert duplicate.scenario == "duplicate_claim"
    assert duplicate.fraud_reason == "duplicate_claim"
    assert all(
        label.kyc_expected is None for label in labels if label.doc_type != DocType.ID_DOCUMENT
    )
    assert all(
        label.coverage_expected is None for label in labels if label.doc_type != DocType.CLAIM_FORM
    )
    assert all(
        label.reference_date is None for label in labels if label.doc_type == DocType.UNKNOWN
    )
    assert all(
        reference_date_for_run(label.reference_date) == DATASET_AS_OF_DATE
        for label in labels
        if label.doc_type == DocType.UNKNOWN
    )

    for metadata_row in metadata:
        label = by_id[metadata_row["doc_id"]]
        source = truth[label.doc_id]
        assert label.decision_expected.value == metadata_row["expected_decision"]
        assert label.fraud_expected == ("FLAGGED" if metadata_row["fraud_label"] else "LOW")
        assert label.fraud_reason == metadata_row.get("fraud_reason")
        if label.doc_type == DocType.ID_DOCUMENT:
            assert label.kyc_expected == ("FAIL" if source.get("expired") else "PASS")
        if label.doc_type == DocType.CLAIM_FORM:
            assert label.coverage_expected == (
                "uncovered_procedure" not in metadata_row.get("edge_flags", [])
            )
        if label.doc_type in {DocType.CLAIM_FORM, DocType.DISCHARGE_SUMMARY}:
            if source.get("missing_field_type") == "diag_code":
                assert label.fields.icd10_codes == []
                assert label.fields.icd10_code is None
            else:
                assert label.fields.icd10_codes == source.get("icd10_codes", [])
                assert label.fields.icd10_code == source.get("icd10_code")
        if source.get("provider_npi"):
            assert label.fields.provider_npi == source["provider_npi"].removeprefix("NPI-")


def test_policy_pdfs_are_present() -> None:
    assert (ROOT / "data" / "policies" / "medishield_gold_plan.pdf").is_file()
    assert (ROOT / "data" / "policies" / "medishield_silver_plan.pdf").is_file()


def test_split_is_deterministic_clustered_and_stratified() -> None:
    metadata, truth = _source_data()
    labels, _ = build_labels(metadata, truth)
    first = build_split(labels)
    second = build_split(labels)

    assert first == second
    assert len(first["clusters"]) == 30
    assert Counter(first["clusters"].values()) == {"dev": 21, "holdout": 9}
    assert len(first["documents"]) == 155
    assert first["scenario_counts"]
    assert first["single_cluster_scenarios"]
    for label in labels:
        if label.cluster_id is not None:
            assert first["documents"][label.doc_id] == first["clusters"][label.cluster_id]
