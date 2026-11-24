import json
import subprocess
from pathlib import Path

from data.synthetic.generators.generate_docs import CPT_POOL, ICD10_POOL, UNCOVERED_CPT
from packages.core.db.repositories import code_in_range
from packages.rag.ingest import _extract_exclusions
from scripts.dataset_coverage import SCENARIOS, build_coverage

ROOT = Path(__file__).resolve().parents[2]


def test_coverage_has_all_requested_scenario_rows() -> None:
    coverage = build_coverage()
    assert set(coverage["counts"]) == set(SCENARIOS)
    assert len(SCENARIOS) == 19


def test_existing_matrix_reports_derived_counts() -> None:
    coverage = build_coverage()
    assert coverage["counts"]["valid"]["dev"] == 78
    assert coverage["counts"]["valid"]["holdout"] == 66
    assert coverage["counts"]["rotated"]["dev"] == 3
    assert coverage["counts"]["rotated"]["holdout"] == 3
    assert coverage["counts"]["prompt_injection"]["holdout"] == 1
    assert coverage["counts"]["blank_page"]["holdout"] == 1


def test_prompt_injection_claim_is_uncovered_and_rejected() -> None:
    metadata = json.loads(Path("data/synthetic/dataset/metadata.json").read_text(encoding="utf-8"))
    rows = [row for row in metadata if row.get("prompt_injection")]
    assert rows
    assert all("uncovered_procedure" in row["edge_flags"] for row in rows)
    assert all(row["expected_decision"] == "REJECT" for row in rows)


def test_existing_labels_and_split_assignments_are_preserved() -> None:
    original = subprocess.check_output(["git", "show", "HEAD:data/synthetic/labels.jsonl"])
    current = Path("data/synthetic/labels.jsonl").read_bytes()
    assert current.replace(b"\r\n", b"\n").startswith(original.replace(b"\r\n", b"\n"))


def test_near_threshold_no_claim_safety() -> None:
    with Path("data/synthetic/dataset/metadata.json").open(encoding="utf-8") as file:
        metadata = json.load(file)
    with Path("data/synthetic/dataset/truth.json").open(encoding="utf-8") as file:
        truth = json.load(file)
    for row in metadata:
        if row["category"] != "claim_forms" or "extra" not in row["doc_id"]:
            continue
        amount = truth[row["doc_id"]].get("claim_amount")
        if amount is not None:
            value = float(amount)
            if 9500 <= value < 10000:
                assert row["fraud_label"] or row.get("fraud_reason") == "amount_under_10k"


def test_extras_generator_is_deterministic() -> None:
    from data.synthetic.generators.extras.generate_extras import base_cluster, npi_luhn

    assert base_cluster(31, "dev", "rotated") == base_cluster(31, "dev", "rotated")
    assert npi_luhn(31) == npi_luhn(31)


def test_reference_tables_cover_all_codes_in_the_frozen_dataset() -> None:
    labels = [
        json.loads(line)
        for line in (ROOT / "data/synthetic/labels.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    dataset_cpt = {
        str(code) for label in labels for code in (label.get("fields", {}).get("cpt_codes") or [])
    }
    dataset_icd = {
        str(code) for label in labels for code in (label.get("fields", {}).get("icd10_codes") or [])
    }
    cpt_descriptions = json.loads((ROOT / "data/cpt_descriptions.json").read_text(encoding="utf-8"))
    icd_descriptions = json.loads(
        (ROOT / "data/icd10_descriptions.json").read_text(encoding="utf-8")
    )
    cpt_prices = json.loads((ROOT / "data/cpt_reference_prices.json").read_text(encoding="utf-8"))
    plausibility = json.loads((ROOT / "data/icd_cpt_plausibility.json").read_text(encoding="utf-8"))

    assert dataset_cpt <= cpt_descriptions.keys()
    assert dataset_cpt <= cpt_prices.keys()
    assert dataset_cpt <= set(plausibility["cpt_codes"])
    assert dataset_icd <= icd_descriptions.keys()
    assert dataset_icd <= set(plausibility["icd10_codes"])

    generator_cpt_codes = {code for code, *_ in CPT_POOL} | {code for code, *_ in UNCOVERED_CPT}
    generator_icd_codes = {code for code, *_ in ICD10_POOL}
    assert generator_cpt_codes | {"59400", "99999"} >= dataset_cpt
    assert generator_icd_codes >= dataset_icd

    generator_excluded_codes = {code for code, *_ in UNCOVERED_CPT}
    for policy_path in sorted((ROOT / "data/policies").glob("*.pdf")):
        exclusions = _extract_exclusions(policy_path.read_bytes())
        assert all(
            any(code_in_range(code, row.range_start, row.range_end) for row in exclusions)
            for code in generator_excluded_codes
        ), policy_path.name
