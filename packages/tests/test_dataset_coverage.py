from scripts.dataset_coverage import SCENARIOS, build_coverage


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
    import json
    from pathlib import Path

    metadata = json.loads(Path("data/synthetic/dataset/metadata.json").read_text(encoding="utf-8"))
    rows = [row for row in metadata if row.get("prompt_injection")]
    assert rows
    assert all("uncovered_procedure" in row["edge_flags"] for row in rows)
    assert all(row["expected_decision"] == "REJECT" for row in rows)


def test_existing_labels_and_split_assignments_are_preserved() -> None:
    import subprocess

    original = subprocess.check_output(["git", "show", "HEAD:data/synthetic/labels.jsonl"])
    current = __import__("pathlib").Path("data/synthetic/labels.jsonl").read_bytes()
    assert current.startswith(original)


def test_near_threshold_no_claim_safety() -> None:
    import json
    from pathlib import Path

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
    import hashlib
    import subprocess
    from pathlib import Path

    extra_files = sorted(
        path
        for path in Path("data/synthetic/dataset").rglob("*")
        if path.is_file() and ("extra" in path.name or "unknown_extra_" in path.name)
    )
    before = {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in extra_files
    }
    subprocess.run(
        [
            r"d:/training/codebasics/capston_project/medishield-intake/.venv/Scripts/python.exe",
            "data/synthetic/generators/extras/generate_extras.py",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    after = {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in extra_files}
    assert before == after
