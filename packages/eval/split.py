"""Deterministic cluster-level stratified development/holdout split."""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.eval.labels import LabelRecord

SPLIT_SEED = 5_202_611
HOLDOUT_FRACTION = 0.30
ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = ROOT / "data" / "synthetic" / "labels.jsonl"
OUTPUT_PATH = ROOT / "data" / "synthetic" / "split.json"

_SCENARIO_PRIORITY = {
    "readmission_30d": 0,
    "date_conflict": 0,
    "proc_diag_mismatch": 0,
    "amount_under_10k": 0,
    "duplicate_claim": 0,
    "name_mismatch": 0,
    "tampered_id": 1,
    "expired_id": 2,
    "expiring_soon_id": 3,
    "uncovered_procedure": 4,
    "missing_field": 5,
    "policy_amendment": 7,
    "unknown": 8,
    "valid_clean": 9,
}


def _cluster_scenario(labels: list[LabelRecord]) -> str:
    scenarios = [label.scenario for label in labels if label.scenario is not None]
    return min(scenarios, key=lambda value: (_SCENARIO_PRIORITY.get(value, 6), value))


def build_split(labels: list[LabelRecord]) -> dict[str, Any]:
    cluster_labels: dict[str, list[LabelRecord]] = defaultdict(list)
    for label in labels:
        if label.cluster_id is not None:
            cluster_labels[label.cluster_id].append(label)

    strata: dict[str, list[str]] = defaultdict(list)
    for cluster_id, records in cluster_labels.items():
        strata[_cluster_scenario(records)].append(cluster_id)

    target_holdout = round(len(cluster_labels) * HOLDOUT_FRACTION)
    allocations = {
        scenario: len(cluster_ids) * HOLDOUT_FRACTION for scenario, cluster_ids in strata.items()
    }
    holdout_counts = {scenario: int(allocation) for scenario, allocation in allocations.items()}
    remaining = target_holdout - sum(holdout_counts.values())
    remainder_order = sorted(
        strata,
        key=lambda scenario: (-(allocations[scenario] % 1), scenario),
    )
    for scenario in remainder_order[:remaining]:
        holdout_counts[scenario] += 1

    randomizer = random.Random(SPLIT_SEED)
    cluster_assignments: dict[str, str] = {}
    for scenario in sorted(strata):
        cluster_ids = sorted(strata[scenario])
        randomizer.shuffle(cluster_ids)
        holdout_ids = set(cluster_ids[: holdout_counts[scenario]])
        for cluster_id in cluster_ids:
            cluster_assignments[cluster_id] = "holdout" if cluster_id in holdout_ids else "dev"

    document_assignments: dict[str, str] = {}
    unclustered_by_scenario: dict[str, list[str]] = defaultdict(list)
    for label in labels:
        if label.cluster_id is None:
            unclustered_by_scenario[label.scenario or "unmatched"].append(label.doc_id)
        else:
            document_assignments[label.doc_id] = cluster_assignments[label.cluster_id]
    for scenario, doc_ids in sorted(unclustered_by_scenario.items()):
        randomizer.shuffle(doc_ids)
        holdout_count = round(len(doc_ids) * HOLDOUT_FRACTION)
        holdout_ids = set(doc_ids[:holdout_count])
        for doc_id in doc_ids:
            document_assignments[doc_id] = "holdout" if doc_id in holdout_ids else "dev"
    scenario_clusters: dict[str, set[str]] = defaultdict(set)
    scenario_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for label in labels:
        if label.scenario is None:
            continue
        if label.cluster_id is not None:
            scenario_clusters[label.scenario].add(label.cluster_id)
        scenario_counts[label.scenario][document_assignments[label.doc_id]] += 1

    return {
        "seed": SPLIT_SEED,
        "holdout_fraction": HOLDOUT_FRACTION,
        "clusters": cluster_assignments,
        "documents": document_assignments,
        "scenario_counts": {
            scenario: {
                "dev": counts["dev"],
                "holdout": counts["holdout"],
                "clusters": len(scenario_clusters[scenario]),
            }
            for scenario, counts in sorted(scenario_counts.items())
        },
        "single_cluster_scenarios": sorted(
            scenario for scenario, cluster_ids in scenario_clusters.items() if len(cluster_ids) == 1
        ),
    }


def load_labels(path: Path = LABELS_PATH) -> list[LabelRecord]:
    return [LabelRecord.model_validate_json(line) for line in path.read_text().splitlines()]


def write_split(labels_path: Path = LABELS_PATH, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    split = build_split(load_labels(labels_path))
    output_path.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    return split


if __name__ == "__main__":
    result = write_split()
    print(json.dumps(result["scenario_counts"], indent=2))
    print(f"Single-cluster scenarios: {result['single_cluster_scenarios']}")
