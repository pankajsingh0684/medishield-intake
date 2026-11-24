"""Run the frozen synthetic dataset through the production API and graph."""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from apps.api.factory import create_app
from apps.api.settings import ApiSettings
from apps.worker.runtime import build_runtime
from packages.core.config import Settings
from packages.core.db.models import Case
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


def evaluation_exit_code(metrics: dict[str, Any], weighted_score: dict[str, Any]) -> int:
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
    }
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


def run_evaluation(
    provider: str,
    split_name: str,
    sample: int | None = None,
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
    if sample is not None:
        if sample < 1:
            raise ValueError("--sample must be at least 1")
        selected_labels = selected_labels[:sample]

    cache = EvaluationResponseCache(ROOT / ".cache" / "eval" / "responses")
    runtime = build_runtime(active_settings, response_cache=cache)
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
                row, retrieval = _prediction_row(label, split_for_label, state, latency_ms)
                predictions.append(row)
                retrieval_rows.extend(retrieval)

        labels_by_id = {label.doc_id: label for label in selected_labels}
        metrics = calculate_metrics(predictions, labels_by_id)
        weighted = automated_weighted_score(metrics)
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
            "known_divergences": known_divergences,
            "predictions": predictions,
        }
        paths = write_reports(report, retrieval_rows, reports_dir, run_id=run_id)
        return report, evaluation_exit_code(metrics, weighted), paths
    finally:
        runtime.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the synthetic MediShield dataset.")
    parser.add_argument("--provider", choices=PROVIDER_CHOICES, required=True)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), required=True)
    parser.add_argument("--sample", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.split in {"holdout", "all"}:
        print(
            "WARNING: holdout is for final numbers only. Do not use it to tune prompts or models.",
            file=sys.stderr,
        )
    report, exit_code, paths = run_evaluation(args.provider, args.split, args.sample)
    metrics = report["metrics"]
    decision_accuracy = metrics["decision"]["accuracy"]
    decision_text = "n/a" if decision_accuracy is None else f"{decision_accuracy:.3f}"
    print(
        f"{args.split}: n={metrics['sample_size']}, decision={decision_text}, "
        f"automated_weighted={report['weighted_score']['score']:.3f}"
    )
    print(f"Report: {paths[1]}")
    print(f"JSON: {paths[0]}")
    print(f"Retrieval review: {paths[2]}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
