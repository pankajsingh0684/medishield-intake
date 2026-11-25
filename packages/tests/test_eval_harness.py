import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from packages.core.config import Settings
from packages.core.enums import DecisionKind, DocType
from packages.eval.cache import EvaluationResponseCache, response_cache_key
from packages.eval.labels import LabelRecord
from packages.eval.reports import write_reports
from packages.eval.run import (
    automated_weighted_score,
    build_decision_mismatch,
    evaluation_exit_code,
    has_initial_configuration_failures,
    main,
    ordered_labels,
    received_at_override,
    set_case_received_at,
    stratified_sample_labels,
)


def _label(doc_id: str, *, cluster_id: str | None = "C_001", reference_date=None):
    return LabelRecord(
        doc_id=doc_id,
        file=f"claim_forms/{doc_id}.png",
        doc_type=DocType.CLAIM_FORM,
        cluster_id=cluster_id,
        patient_id="P_001" if cluster_id else None,
        fields={},
        kyc_expected=None,
        coverage_expected=None,
        fraud_expected=None,
        fraud_reason=None,
        decision_expected=DecisionKind.APPROVE,
        scenario="valid_clean",
        reference_date=reference_date,
    )


def test_response_cache_key_includes_prompt_identity_and_version() -> None:
    base = response_cache_key("input-hash", "claims_extract", "v1")

    assert response_cache_key("input-hash", "claims_extract", "v2") != base
    assert response_cache_key("input-hash", "classifier", "v1") != base
    assert response_cache_key("other-input", "claims_extract", "v1") != base


def test_response_cache_key_separates_provider_and_model(tmp_path: Path) -> None:
    cache = EvaluationResponseCache(tmp_path)
    args = ("system", [{"role": "user", "content": "input"}], [b"image"], "classifier", "v1")

    assert cache.key_for(*args, provider="stub", model="vision-a") != cache.key_for(
        *args, provider="groq", model="vision-a"
    )
    assert cache.key_for(*args, provider="stub", model="vision-a") != cache.key_for(
        *args, provider="stub", model="vision-b"
    )


def test_ordered_labels_place_original_before_duplicate() -> None:
    duplicate = _label("claim_001_dup")
    original = _label("claim_001")

    assert [label.doc_id for label in ordered_labels([duplicate, original])] == [
        "claim_001",
        "claim_001_dup",
    ]


def test_received_at_is_only_overridden_when_enabled() -> None:
    disabled = Settings.model_construct(app_env="development", allow_received_at_override=False)
    enabled = Settings.model_construct(app_env="development", allow_received_at_override=True)
    label = _label("claim_001", reference_date=date(2025, 6, 2))

    assert received_at_override(label, disabled) is None
    assert received_at_override(label, enabled) == datetime(2025, 6, 2, tzinfo=UTC)
    assert received_at_override(_label("unknown", cluster_id=None), enabled) == datetime(
        2025, 12, 31, tzinfo=UTC
    )

    class CaseStub:
        received_at = datetime(2026, 1, 1, tzinfo=UTC)

    class SessionStub:
        case = CaseStub()
        calls = 0

        def get(self, *_):
            self.calls += 1
            return self.case

    session = SessionStub()
    original_received_at = session.case.received_at
    assert set_case_received_at(session, "case-id", label, disabled) is None
    assert session.calls == 0
    assert session.case.received_at == original_received_at
    assert set_case_received_at(session, "case-id", label, enabled) == datetime(
        2025, 6, 2, tzinfo=UTC
    )
    assert session.case.received_at == datetime(2025, 6, 2, tzinfo=UTC)


def test_received_at_override_refuses_production() -> None:
    settings = Settings.model_construct(app_env="production", allow_received_at_override=True)

    with pytest.raises(ValueError, match="forbidden in production"):
        received_at_override(_label("claim_001", reference_date=date(2025, 1, 1)), settings)


def test_report_generation_writes_json_markdown_and_retrieval_csv(tmp_path: Path) -> None:
    report = {
        "run": {"provider": "stub", "split": "dev", "run_id": "test-run"},
        "metrics": {
            "sample_size": 1,
            "classification": {"correct": 1, "sample_size": 1, "accuracy": 1.0},
            "extraction": {"correct": 0, "sample_size": 0, "completeness": None},
            "decision": {"correct": 0, "sample_size": 1, "accuracy": 0.0},
            "confusion_matrix": {"APPROVE": {"REJECT": 1}},
            "breakdowns": {"scenario": {}, "document_category": {}, "split": {}},
            "latency_ms": {"sample_size": 1, "p50": 2.0, "p95": 2.0},
            "calibration": None,
        },
        "weighted_score": {"score": 0.5, "sample_size": 2, "method": "test method"},
        "known_divergences": [],
        "decision_mismatches": [
            {
                "doc_id": "id_001",
                "expected": "APPROVE",
                "actual": "ESCALATE",
                "decision_confidence": 0.45,
                "fired_rules": [
                    {
                        "rule": "R1_AGENT_RELIABILITY",
                        "summary": "R1 LOW_CONFIDENCE:kyc",
                        "inputs": {},
                    }
                ],
                "rule_trace": [{"rule": "R1_AGENT_RELIABILITY", "fired": True, "inputs": {}}],
                "minimum_confidence_agent": "kyc",
                "agents": [
                    {
                        "agent": "classifier",
                        "status": "OK",
                        "confidence": 0.92,
                        "is_minimum_confidence": False,
                    },
                    {
                        "agent": "kyc",
                        "status": "OK",
                        "confidence": 0.45,
                        "is_minimum_confidence": True,
                    },
                ],
            }
        ],
        "groq_usage": {
            "calls_by_model": {"model-a": 2},
            "rate_limit_responses_429": 1,
            "retries_429": 1,
            "seconds_waited": 3.0,
            "estimated_tokens_by_model": {"model-a": 4200},
            "daily_tokens_used": 4200,
            "cache_hits": 1,
        },
        "daily_budget_stop": "Groq daily token budget stop at 90% threshold.",
        "failures": [
            {"doc_id": "claim_001", "agent": "classifier", "message": "HTTP 404 model missing"}
        ],
        "predictions": [],
    }
    rows = [
        {
            "doc_id": "claim_001",
            "cpt_code": "97110",
            "retrieved_clause": "Clause A",
            "cited_clause": "Clause A",
            "covered": True,
        }
    ]

    json_path, markdown_path, csv_path = write_reports(report, rows, tmp_path, "test-run")

    assert json.loads(json_path.read_text(encoding="utf-8"))["metrics"]["sample_size"] == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Known Divergences" in markdown
    assert "claim_PT_16658" in markdown
    assert "claim_001" in markdown
    assert "HTTP 404 model missing" in markdown
    assert "HTTP 429 responses: 1" in markdown
    assert "Cache hits: 1" in markdown
    assert "model-a" in markdown and "4200" in markdown
    assert "Partial Run" in markdown
    assert "90% threshold" in markdown
    assert "Decision Mismatches" in markdown
    assert "Expected: **APPROVE**; actual: **ESCALATE**" in markdown
    assert "kyc **MIN**" in markdown
    with csv_path.open(encoding="utf-8", newline="") as sheet:
        assert next(iter(csv.DictReader(sheet)))["cpt_code"] == "97110"


@pytest.mark.parametrize(
    ("decision", "weighted", "expected"),
    [(0.60, 0.70, 0), (0.59, 0.90, 1), (0.90, 0.69, 1)],
)
def test_evaluation_exit_code_enforces_both_gates(decision, weighted, expected) -> None:
    metrics = {"decision": {"accuracy": decision}}
    score = {"score": weighted}

    assert evaluation_exit_code(metrics, score) == expected


def test_holdout_requires_explicit_split_and_warns_final_only(
    monkeypatch, capsys, tmp_path
) -> None:
    from packages.eval import run as eval_run

    with pytest.raises(SystemExit):
        eval_run._parser().parse_args(["--provider", "stub"])

    report = {
        "metrics": {"sample_size": 0, "decision": {"accuracy": None}},
        "weighted_score": {"score": 0.0},
    }
    paths = (tmp_path / "run.json", tmp_path / "run.md", tmp_path / "run.csv")
    monkeypatch.setattr(eval_run, "run_evaluation", lambda *_: (report, 1, paths))

    assert main(["--provider", "stub", "--split", "holdout"]) == 1
    assert "holdout is for final numbers only" in capsys.readouterr().err


def test_below_decision_correctness_gate_returns_nonzero() -> None:
    assert evaluation_exit_code({"decision": {"accuracy": 0.59}}, {"score": 0.90}) == 1
    assert (
        evaluation_exit_code(
            {"decision": {"accuracy": 1.0}}, {"score": 1.0}, daily_budget_stopped=True
        )
        == 2
    )


def test_harness_fails_fast_after_three_configuration_errors() -> None:
    assert has_initial_configuration_failures([True, True, True])
    assert not has_initial_configuration_failures([True, True, False])
    assert not has_initial_configuration_failures([True, True])


def test_build_decision_mismatch_labels_rules_and_minimum_agent() -> None:
    mismatch = build_decision_mismatch(
        doc_id="id_001",
        expected="APPROVE",
        actual="ESCALATE",
        confidence=0.45,
        rule_trace=[
            {
                "rule": "R1_AGENT_RELIABILITY",
                "fired": True,
                "inputs": {"low_confidence_agents": ["kyc"]},
            },
            {"rule": "R2_FRAUD_SCORE", "fired": False, "inputs": {"fraud_score": 0.0}},
            {"rule": "R3_REJECTION", "fired": False, "inputs": {"rejection_reasons": []}},
        ],
        agent_runs=[
            {"agent": "classifier", "status": "OK", "confidence": 0.92},
            {"agent": "kyc", "status": "OK", "confidence": 0.45},
        ],
    )

    assert mismatch["fired_rules"][0]["summary"] == "R1 LOW_CONFIDENCE:kyc"
    assert mismatch["minimum_confidence_agent"] == "kyc"
    assert mismatch["agents"][1]["is_minimum_confidence"] is True


def test_automated_weighted_score_renormalizes_available_scored_metrics() -> None:
    metrics = {
        "classification": {"accuracy": 1.0, "sample_size": 2},
        "extraction": {"completeness": None, "sample_size": 0},
        "decision": {"accuracy": 0.5, "sample_size": 2},
    }

    assert automated_weighted_score(metrics)["score"] == pytest.approx(
        (1 * 0.2 + 0.5 * 0.25) / 0.45
    )


def test_stratified_selection_covers_scenarios_and_keeps_duplicates_together() -> None:
    labels = [
        _label("claim_001", cluster_id="C_001"),
        _label("claim_001_dup", cluster_id="C_001"),
        _label("claim_002", cluster_id="C_002"),
    ]
    labels[0].scenario = "valid_clean"
    labels[1].scenario = "duplicate_claim"
    labels[2].scenario = "missing_field"

    first = stratified_sample_labels(labels, 3)
    second = stratified_sample_labels(labels, 3)
    assert first[0] == second[0]
    selected_ids = {label.doc_id for label in first[0]}
    assert {"claim_001", "claim_001_dup"}.issubset(selected_ids) or "claim_001" not in selected_ids
    assert set(first[2]) == {"valid_clean", "duplicate_claim", "missing_field"}
