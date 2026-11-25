"""Run the frozen synthetic dataset through the production API and graph."""

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.factory import create_app
from apps.api.settings import ApiSettings
from apps.worker.runtime import build_runtime
from packages.core.config import Settings
from packages.core.db.models import AgentRun, Case, Decision
from packages.core.llm.providers import GroqDailyTokenBudget
from packages.eval import DATASET_AS_OF_DATE, reference_date_for_run
from packages.eval.cache import EvaluationResponseCache
from packages.eval.labels import LabelRecord
from packages.eval.metrics import calculate_metrics
from packages.eval.reports import KNOWN_DIVERGENCES, write_reports
from packages.graph.builder import build_graph, initial_state
from scripts.seed_from_dataset import seed_dataset

ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = ROOT / "data" / "synthetic"
LABELS_PATH = DATASET_ROOT / "labels.jsonl"
SPLIT_PATH = DATASET_ROOT / "split.json"
REPORTS_DIR = ROOT / "reports"
PROVIDER_CHOICES = ("stub", "groq", "anthropic", "openai")
CONFIGURATION_ERROR_MARKERS = (
    "model_not_found",
    "unauthorized",
    "authentication",
    "invalid_api_key",
    "http 401",
    "http 403",
    "http 404",
)


def is_configuration_error(message: str) -> bool:
    return any(marker in message.casefold() for marker in CONFIGURATION_ERROR_MARKERS)


def has_initial_configuration_failures(call_failed_with_configuration_error: list[bool]) -> bool:
    return len(call_failed_with_configuration_error) >= 3 and all(
        call_failed_with_configuration_error[:3]
    )


def ordered_labels(labels: list[LabelRecord]) -> list[LabelRecord]:
    original_order = {label.doc_id: index for index, label in enumerate(labels)}
    return sorted(
        labels,
        key=lambda label: (
            label.cluster_id or f"~{label.doc_id}",
            label.doc_id.endswith("_dup"),
            original_order[label.doc_id],
        ),
    )


def received_at_override(label: LabelRecord, settings: Settings) -> datetime | None:
    if not settings.allow_received_at_override:
        return None
    if settings.app_env == "production":
        raise ValueError("Evaluation received_at overrides are forbidden in production")
    reference_date = reference_date_for_run(label.reference_date)
    return datetime.combine(reference_date, datetime_time.min, tzinfo=UTC)


def set_case_received_at(
    session: Session, case_id: str, label: LabelRecord, settings: Settings
) -> datetime | None:
    received_at = received_at_override(label, settings)
    if received_at is None:
        return None
    case = session.get(Case, case_id)
    if case is None:
        raise ValueError(f"Uploaded case does not exist: {case_id}")
    case.received_at = received_at
    return received_at


def automated_weighted_score(metrics: dict[str, Any]) -> dict[str, Any]:
    weighted_metrics = (
        ("classification", 0.20, "accuracy"),
        ("extraction", 0.20, "completeness"),
        ("decision", 0.25, "accuracy"),
    )
    available = [
        (metrics[name][value_key], weight)
        for name, weight, value_key in weighted_metrics
        if metrics[name][value_key] is not None and metrics[name]["sample_size"] > 0
    ]
    total_weight = sum(weight for _, weight in available)
    score = (
        sum(float(value) * weight for value, weight in available) / total_weight
        if total_weight
        else 0.0
    )
    return {
        "score": score,
        "sample_size": len(available),
        "method": "Available automated PRD weights (classification 20%, extraction 20%, decision 25%) renormalized to 100%; retrieval is manual, UI and code quality are unscored.",
    }


def evaluation_exit_code(
    metrics: dict[str, Any], weighted_score: dict[str, Any], *, daily_budget_stopped: bool = False
) -> int:
    if daily_budget_stopped:
        return 2
    decision_accuracy = metrics["decision"]["accuracy"]
    if decision_accuracy is None or decision_accuracy < 0.60 or weighted_score["score"] < 0.70:
        return 1
    return 0


def _read_dataset() -> tuple[list[LabelRecord], dict[str, str], dict[str, Any]]:
    labels = [
        LabelRecord.model_validate_json(line)
        for line in LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    split_data = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    return labels, split_data["documents"], split_data


def _prediction_row(
    label: LabelRecord,
    split_name: str,
    state: dict[str, Any],
    latency_ms: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    classification = state.get("classification")
    claims = state.get("claims")
    decision = state.get("decision")
    policy = state.get("policy")
    fields = claims.extracted_fields.model_dump(mode="json") if claims is not None else {}
    actual_doc_type = classification.doc_type.value if classification is not None else None
    actual_decision = decision.decision.value if decision is not None else None
    confidence = float(decision.confidence) if decision is not None else None
    row = {
        "doc_id": label.doc_id,
        "doc_type": actual_doc_type,
        "decision": actual_decision,
        "confidence": confidence,
        "fields": fields,
        "scenario": label.scenario,
        "split": split_name,
        "latency_ms": latency_ms,
        "terminal_status": state.get("terminal_status"),
        "_case_id": state.get("case_id"),
        "_pipeline_run": state.get("pipeline_run"),
    }
    row["failures"] = [
        {"agent": agent_name, "message": result.error or "Agent failed"}
        for agent_name in ("classification", "ocr", "kyc", "claims", "policy", "fraud", "decision")
        if (result := state.get(agent_name)) is not None
        and getattr(getattr(result, "status", None), "value", None) == "ERROR"
    ]
    retrieval_rows: list[dict[str, Any]] = []
    if claims is not None and policy is not None:
        retrieved_clause = (
            policy.policy_clause.retrieved_text
            if policy.policy_clause and policy.policy_clause.retrieved_text
            else ""
        )
        cited_clause = policy.policy_clause.text if policy.policy_clause else ""
        for cpt_code in claims.extracted_fields.cpt_codes:
            retrieval_rows.append(
                {
                    "doc_id": label.doc_id,
                    "cpt_code": cpt_code,
                    "retrieved_clause": retrieved_clause,
                    "cited_clause": cited_clause,
                    "covered": policy.covered,
                }
            )
    return row, retrieval_rows


def build_decision_mismatch(
    *,
    doc_id: str,
    expected: str,
    actual: str,
    confidence: float | None,
    rule_trace: list[dict[str, Any]],
    agent_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Shape a mismatch explanation using only persisted decision and agent-run data."""
    fired_rules: list[dict[str, Any]] = []
    for step in rule_trace:
        if not step.get("fired"):
            continue
        rule = str(step.get("rule", "UNKNOWN_RULE"))
        inputs = step.get("inputs") or {}
        if rule == "R1_AGENT_RELIABILITY":
            reasons = []
            for name in inputs.get("low_confidence_agents", []):
                reasons.append(f"LOW_CONFIDENCE:{name}")
            for name in inputs.get("error_agents", []):
                reasons.append(f"AGENT_ERROR:{name}")
            for name in inputs.get("missing_agents", []):
                reasons.append(f"MISSING_AGENT:{name}")
            label = "R1 " + (", ".join(reasons) or "AGENT_RELIABILITY")
        elif rule == "R2_FRAUD_SCORE":
            label = f"R2 FRAUD_SCORE:{inputs.get('fraud_score')}"
        elif rule == "R3_REJECTION":
            label = "R3 REJECTION:" + ",".join(inputs.get("rejection_reasons", []))
        else:
            label = rule
        fired_rules.append({"rule": rule, "summary": label, "inputs": inputs})

    scored_agents = [
        run
        for run in agent_runs
        if run.get("status") != "SKIPPED" and run.get("confidence") is not None
    ]
    minimum_agent = (
        min(scored_agents, key=lambda run: float(run["confidence"])) if scored_agents else None
    )
    for run in agent_runs:
        run["is_minimum_confidence"] = bool(
            minimum_agent is not None and run.get("agent") == minimum_agent.get("agent")
        )
    return {
        "doc_id": doc_id,
        "expected": expected,
        "actual": actual,
        "decision_confidence": confidence,
        "fired_rules": fired_rules,
        "rule_trace": rule_trace,
        "agents": agent_runs,
        "minimum_confidence_agent": minimum_agent.get("agent") if minimum_agent else None,
    }


def _stored_decision_mismatch(session: Session, label: LabelRecord, prediction: dict[str, Any]):
    if not prediction.get("_case_id") or not prediction.get("_pipeline_run"):
        return None
    decision = session.scalar(
        select(Decision).where(
            Decision.case_id == UUID(prediction["_case_id"]),
            Decision.pipeline_run == UUID(prediction["_pipeline_run"]),
        )
    )
    if decision is None or decision.decision.value == label.decision_expected.value:
        return None
    agent_runs = list(
        session.scalars(
            select(AgentRun).where(
                AgentRun.case_id == UUID(prediction["_case_id"]),
                AgentRun.pipeline_run == UUID(prediction["_pipeline_run"]),
            )
        )
    )
    agent_details = [
        {
            "agent": run.agent,
            "status": run.status,
            "confidence": float(run.confidence) if run.confidence is not None else None,
        }
        for run in agent_runs
    ]
    return build_decision_mismatch(
        doc_id=label.doc_id,
        expected=label.decision_expected.value,
        actual=decision.decision.value,
        confidence=float(decision.confidence),
        rule_trace=decision.rule_trace,
        agent_runs=agent_details,
    )


def run_evaluation(
    provider: str,
    split_name: str,
    sample: int | None = None,
    stratified: int | None = None,
    *,
    settings: Settings | None = None,
    api_settings: ApiSettings | None = None,
    reports_dir: Path = REPORTS_DIR,
) -> tuple[dict[str, Any], int, tuple[Path, Path, Path]]:
    if provider not in PROVIDER_CHOICES:
        raise ValueError(f"Unsupported provider: {provider}")
    if split_name not in {"dev", "holdout", "all"}:
        raise ValueError(f"Unsupported split: {split_name}")
    active_settings = settings or Settings()
    active_settings = active_settings.model_copy(
        update={"llm_provider": provider, "llm_fallback_provider": None}
    )
    active_settings = Settings.model_validate(active_settings.model_dump())
    active_api_settings = api_settings or ApiSettings()
    if active_settings.app_env == "production" or active_api_settings.app_env == "production":
        raise ValueError("The synthetic evaluation runner cannot run in production")
    if active_api_settings.service_token is None:
        active_api_settings = active_api_settings.model_copy(
            update={"service_token": SecretStr(uuid4().hex)}
        )

    labels, document_splits, _ = _read_dataset()
    selected_labels = [
        label
        for label in ordered_labels(labels)
        if split_name == "all" or document_splits[label.doc_id] == split_name
    ]
    if sample is not None and stratified is not None:
        raise ValueError("--sample and --stratified are mutually exclusive")
    if stratified is not None:
        selected_labels, _, _ = stratified_sample_labels(selected_labels, stratified)
    elif sample is not None:
        if sample < 1:
            raise ValueError("--sample must be at least 1")
        selected_labels = selected_labels[:sample]

    if stratified is not None:
        print("Stratified documents:")
        for label in selected_labels:
            print(
                f"  {label.doc_id}\tscenario={label.scenario or 'unmatched'}"
                f"\tsplit={document_splits.get(label.doc_id, 'unknown')}"
            )
        print(f"Stratified total: {len(selected_labels)}")

    cache = EvaluationResponseCache(ROOT / ".cache" / "eval" / "responses")
    daily_budget = (
        GroqDailyTokenBudget(
            active_settings.groq_tpd_limit,
            ROOT / ".cache" / "eval" / "groq_daily_usage.json",
        )
        if provider == "groq"
        else None
    )
    runtime = build_runtime(
        active_settings,
        response_cache=cache,
        groq_daily_budget=daily_budget,
    )
    try:
        with Session(runtime.engine) as session, session.begin():
            seed_dataset(session, active_settings.seed_test_user_password.get_secret_value())

        class NoopTask:
            def apply_async(self, **_: Any) -> None:
                return None

        api = create_app(
            active_api_settings,
            engine=runtime.engine,
            storage=runtime.storage,
            pipeline_task=NoopTask(),
            policy_task=NoopTask(),
        )
        graph = build_graph(runtime.graph)
        predictions: list[dict[str, Any]] = []
        retrieval_rows: list[dict[str, Any]] = []
        state_by_case_id: dict[str, dict[str, Any]] = {}
        initial_call_configuration_failures: list[bool] = []
        daily_budget_stop: str | None = None
        with TestClient(api) as client:
            for label in selected_labels:
                dataset_file = (DATASET_ROOT / label.file.replace("\\", "/")).resolve()
                if not dataset_file.is_relative_to(DATASET_ROOT.resolve()):
                    raise ValueError(f"Dataset label escapes the dataset directory: {label.doc_id}")
                content = dataset_file.read_bytes()
                for upload_attempt in range(4):
                    response = client.post(
                        "/api/v1/cases",
                        headers={
                            "Authorization": (
                                f"Bearer {active_api_settings.service_token.get_secret_value()}"
                            )
                        },
                        files={"file": (dataset_file.name, content, "application/octet-stream")},
                    )
                    if response.status_code != 429 or upload_attempt == 3:
                        break
                    time.sleep(int(response.headers.get("Retry-After", "60")))
                if response.status_code not in {200, 202}:
                    raise RuntimeError(
                        f"API upload failed for {label.doc_id}: HTTP {response.status_code}"
                    )
                upload_result = response.json()
                case_id = str(upload_result["case_id"])
                duplicate_of = upload_result.get("duplicate_of")
                split_for_label = document_splits[label.doc_id]

                if duplicate_of is not None and case_id in state_by_case_id:
                    row, retrieval = _prediction_row(
                        label,
                        split_for_label,
                        state_by_case_id[case_id],
                        0.0,
                    )
                    row["duplicate_of"] = str(duplicate_of)
                    predictions.append(row)
                    retrieval_rows.extend(retrieval)
                    continue

                with Session(runtime.engine) as session, session.begin():
                    set_case_received_at(session, case_id, label, active_settings)
                pipeline_run = str(uuid4())
                started = time.perf_counter()
                state = graph.invoke(initial_state(case_id, pipeline_run))
                latency_ms = (time.perf_counter() - started) * 1000
                state_by_case_id[case_id] = state
                classification = state.get("classification")
                if classification is not None:
                    error_message = classification.error or ""
                    initial_call_configuration_failures.append(
                        classification.status.value == "ERROR"
                        and is_configuration_error(error_message)
                    )
                if has_initial_configuration_failures(initial_call_configuration_failures):
                    raise RuntimeError(
                        "Evaluation aborted: the first three classifier calls failed with "
                        "provider configuration errors. "
                        f"Last case {label.doc_id}: {classification.error}"
                    )
                row, retrieval = _prediction_row(label, split_for_label, state, latency_ms)
                if daily_budget is not None and daily_budget.budget_exceeded:
                    daily_budget_stop = (
                        "Groq daily token budget stop at approximately 90% of "
                        f"GROQ_TPD_LIMIT ({daily_budget.used_tokens:,}/{active_settings.groq_tpd_limit:,} "
                        "estimated tokens). Rerun resumes successful model responses from cache."
                    )
                    row["failures"].append({"agent": "provider", "message": daily_budget_stop})
                predictions.append(row)
                retrieval_rows.extend(retrieval)
                if daily_budget_stop is not None:
                    break

        labels_by_id = {label.doc_id: label for label in selected_labels}
        metrics = calculate_metrics(predictions, labels_by_id)
        weighted = automated_weighted_score(metrics)
        decision_mismatches = []
        with Session(runtime.engine) as session:
            for prediction in predictions:
                mismatch = _stored_decision_mismatch(
                    session, labels_by_id[prediction["doc_id"]], prediction
                )
                if mismatch is not None:
                    decision_mismatches.append(mismatch)
        for prediction in predictions:
            prediction.pop("_case_id", None)
            prediction.pop("_pipeline_run", None)
        failures = [
            {"doc_id": row["doc_id"], **failure}
            for row in predictions
            for failure in row.get("failures", [])
        ]
        known_divergences = [
            {
                **item,
                "observed": next(
                    (
                        row.get("decision") or "NO_DECISION"
                        for row in predictions
                        if row["doc_id"] == item["doc_id"]
                    ),
                    "NOT_EVALUATED",
                ),
            }
            for item in KNOWN_DIVERGENCES
        ]
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{uuid4().hex[:8]}"
        report: dict[str, Any] = {
            "run": {
                "provider": provider,
                "split": split_name,
                "sample_requested": sample,
                "sample_size": len(predictions),
                "received_at_override": active_settings.allow_received_at_override,
                "data_as_of_date": DATASET_AS_OF_DATE.isoformat(),
                "run_id": run_id,
            },
            "metrics": metrics,
            "weighted_score": weighted,
            "decision_mismatches": decision_mismatches,
            "known_divergences": known_divergences,
            "failures": failures,
            "groq_usage": runtime.gateway.usage_summary() if provider == "groq" else None,
            "daily_budget_stop": daily_budget_stop,
            "partial": daily_budget_stop is not None,
            "predictions": predictions,
        }
        paths = write_reports(report, retrieval_rows, reports_dir, run_id=run_id)
        exit_code = evaluation_exit_code(
            metrics, weighted, daily_budget_stopped=daily_budget_stop is not None
        )
        return report, exit_code, paths
    finally:
        runtime.close()


def stratified_sample_labels(
    labels: list[LabelRecord], target_documents: int, *, seed: int = 5_202_611
) -> tuple[list[LabelRecord], list[str], dict[str, int]]:
    if target_documents < 1:
        raise ValueError("--stratified must be at least 1")

    randomizer = random.Random(seed)
    by_id = {label.doc_id: label for label in labels}
    scenario_units: list[list[LabelRecord]] = []

    for scenario in sorted({label.scenario for label in labels if label.scenario is not None}):
        candidates = [label for label in labels if label.scenario == scenario]
        randomizer.shuffle(candidates)
        chosen = candidates[0]
        if scenario == "duplicate_claim":
            original = by_id.get(chosen.doc_id.removesuffix("_dup"))
            unit = [original, chosen] if original is not None else [chosen]
            scenario_units.append(
                sorted(unit, key=lambda item: (item.doc_id.endswith("_dup"), item.doc_id))
            )
        else:
            scenario_units.append([chosen])

    scenario_units.sort(key=lambda unit: tuple(sorted(item.doc_id for item in unit)))

    type_units: list[list[LabelRecord]] = []
    selected_in_units = {item.doc_id for unit in scenario_units for item in unit}
    for doc_type in (
        "CLAIM_FORM",
        "ID_DOCUMENT",
        "PRESCRIPTION",
        "DISCHARGE_SUMMARY",
        "POLICY_AMENDMENT",
    ):
        candidates = [label for label in labels if label.doc_type.value == doc_type]
        pool = [label for label in candidates if label.scenario == "valid_clean"] or candidates
        randomizer.shuffle(pool)
        added = 0
        for label in pool:
            if label.doc_id in selected_in_units:
                continue
            type_units.append([label])
            selected_in_units.add(label.doc_id)
            added += 1
            if added == 2:
                break

    type_units.sort(key=lambda unit: tuple(sorted(item.doc_id for item in unit)))
    mandatory_units = scenario_units + type_units

    mandatory_ids = {item.doc_id for unit in mandatory_units for item in unit}
    remaining = [label for label in labels if label.doc_id not in mandatory_ids]
    randomizer.shuffle(remaining)
    ranked_units = mandatory_units + [[label] for label in remaining]

    selected_ids: set[str] = set()
    for unit in ranked_units:
        if len(selected_ids) >= target_documents:
            break
        unit_ids = {item.doc_id for item in unit}
        if len(selected_ids) + len(unit_ids) <= target_documents:
            selected_ids.update(unit_ids)

    selected_labels = ordered_labels([label for label in labels if label.doc_id in selected_ids])
    selected_ids_ordered = [label.doc_id for label in selected_labels]
    scenario_counts = dict(Counter(label.scenario or "unmatched" for label in selected_labels))
    return selected_labels, selected_ids_ordered, scenario_counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the synthetic MediShield dataset.")
    parser.add_argument("--provider", choices=PROVIDER_CHOICES, required=True)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), required=True)
    parser.add_argument("--sample", type=int)
    parser.add_argument("--stratified", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.split in {"holdout", "all"}:
        print(
            "WARNING: holdout is for final numbers only. Do not use it to tune prompts or models.",
            file=sys.stderr,
        )
    report, exit_code, paths = run_evaluation(
        args.provider, args.split, args.sample, args.stratified
    )
    metrics = report["metrics"]
    decision_accuracy = metrics["decision"]["accuracy"]
    decision_text = "n/a" if decision_accuracy is None else f"{decision_accuracy:.3f}"
    print(
        f"{args.split}: n={metrics['sample_size']}, decision={decision_text}, "
        f"automated_weighted={report['weighted_score']['score']:.3f}"
    )
    if report.get("daily_budget_stop"):
        print(report["daily_budget_stop"], file=sys.stderr)
    print(f"Report: {paths[1]}")
    print(f"JSON: {paths[0]}")
    print(f"Retrieval review: {paths[2]}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
