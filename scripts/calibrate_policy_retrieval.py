"""Calibrate retrieval-only reranker scores on dev-split policy labels."""

import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.clients import create_qdrant_client
from packages.core.config import Settings
from packages.core.db.session import create_database_engine
from packages.rag.embeddings import LocalSentenceTransformerEmbedder
from packages.rag.retrieve import CrossEncoderReranker, QdrantHybridRetriever

ROOT = Path(__file__).resolve().parents[1]
POLICY_NAMESPACE = "medishield:plan:{}:synthetic-v1"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise TypeError(f"Expected date string, got {type(value).__name__}")
    return date.fromisoformat(value[:10])


def _distribution(values: list[float]) -> str:
    if not values:
        return "n=0"
    return (
        f"n={len(values)}, min={min(values):.6f}, "
        f"median={statistics.median(values):.6f}, max={max(values):.6f}, "
        f"<0.35={sum(value < 0.35 for value in values)}, "
        f"<0.60={sum(value < 0.60 for value in values)}"
    )


def calibrate() -> str:
    labels = _read_jsonl(ROOT / "data/synthetic/labels.jsonl")
    split = json.loads((ROOT / "data/synthetic/split.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data/synthetic/dataset/truth.json").read_text(encoding="utf-8"))
    descriptions = json.loads((ROOT / "data/cpt_descriptions.json").read_text(encoding="utf-8"))
    icd_descriptions = json.loads(
        (ROOT / "data/icd10_descriptions.json").read_text(encoding="utf-8")
    )
    dev_claims = [
        row
        for row in labels
        if row.get("doc_type") == "CLAIM_FORM"
        and split["documents"].get(row.get("doc_id")) == "dev"
        and isinstance(row.get("coverage_expected"), bool)
    ]
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    client = create_qdrant_client(settings)
    retriever = QdrantHybridRetriever(
        client, LocalSentenceTransformerEmbedder(settings.embedding_model)
    )
    reranker = CrossEncoderReranker()
    query_scores: dict[bool, list[float]] = defaultdict(list)
    claim_scores: dict[bool, list[float]] = defaultdict(list)
    claims_without_match: dict[bool, list[tuple[str, list[str]]]] = defaultdict(list)
    score_details: dict[str, list[tuple[str, float]]] = {}
    try:
        for label in sorted(dev_claims, key=lambda row: str(row["doc_id"])):
            doc_id = str(label["doc_id"])
            record = truth[doc_id]
            policy_number = str(record["policy_number"])
            plan_code = "SILVER" if policy_number.startswith("MED-SLV-") else "GOLD"
            policy_id = uuid5(NAMESPACE_URL, POLICY_NAMESPACE.format(plan_code))
            service_date = _parse_date(record.get("service_date") or record.get("reference_date"))
            covered = bool(label["coverage_expected"])
            cpt_codes = [str(code) for code in record.get("cpt_codes", [])]
            icd_codes = [str(code) for code in record.get("icd10_codes", [])]
            code_scores: list[tuple[str, float]] = []
            queries = [
                (
                    f"CPT {code}",
                    f"{descriptions.get(code, 'unlisted procedure')} covered service",
                )
                for code in cpt_codes
            ] + [
                (
                    f"ICD-10 {code}",
                    f"{icd_descriptions.get(code, 'diagnosis')} covered service",
                )
                for code in icd_codes
            ]
            for code_label, query in queries:
                candidates = retriever.search(query, policy_id, service_date)
                ranked = reranker.rerank(query, candidates)
                score = ranked[0][1] if ranked else 0.0
                query_scores[covered].append(score)
                code_scores.append((code_label, score))
            top_score = max((score for _, score in code_scores), default=0.0)
            claim_scores[covered].append(top_score)
            score_details[doc_id] = code_scores
            if top_score < 0.35:
                claims_without_match[covered].append((doc_id, cpt_codes))

        expected_covered = len(claim_scores[True])
        expected_uncovered = len(claim_scores[False])
        report = [
            "# Policy Retrieval Calibration",
            "",
            "Retrieval-only calibration; no LLM decisions or deterministic exclusion short-circuiting were applied.",
            "Labels are `coverage_expected` on dev-split `CLAIM_FORM` rows in `labels.jsonl`.",
            "Each claim score is the maximum top reranker score across its per-CPT and per-ICD-10 queries; query-level distributions are also shown.",
            "The real `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker was loaded by this script only; scores are sigmoid-normalized to [0, 1].",
            "Threshold counts are counts below the threshold, not recommended changes.",
            "",
            "## Claim-Level Scores",
            "",
            f"Expected covered ({expected_covered} claims): {_distribution(claim_scores[True])}",
            f"Expected not covered ({expected_uncovered} claims): {_distribution(claim_scores[False])}",
            "",
            "## Per-Code Query Scores",
            "",
            f"Queries from expected-covered claims: {_distribution(query_scores[True])}",
            f"Queries from expected-not-covered claims: {_distribution(query_scores[False])}",
            "",
            "## Claims Below 0.35",
            "",
        ]
        unmatched = [item for group in (True, False) for item in claims_without_match[group]]
        if unmatched:
            report.extend(
                f"- `{doc_id}` (claim top={max((score for _, score in score_details[doc_id]), default=0.0):.6f}; "
                f"expected {'covered' if expected else 'not covered'}), CPT codes: "
                f"{', '.join(codes) if codes else '(none)'}"
                for expected, (doc_id, codes) in (
                    (group, item) for group in (True, False) for item in claims_without_match[group]
                )
            )
        else:
            report.append("None.")
        report.extend(["", "## Per-Claim Detail", ""])
        for covered in (True, False):
            report.append(f"### Expected {'Covered' if covered else 'Not Covered'}")
            for label in sorted(
                (row for row in dev_claims if bool(row["coverage_expected"]) is covered),
                key=lambda row: str(row["doc_id"]),
            ):
                doc_id = str(label["doc_id"])
                details = ", ".join(f"{code}={score:.6f}" for code, score in score_details[doc_id])
                report.append(
                    f"- `{doc_id}`: claim top={max((score for _, score in score_details[doc_id]), default=0.0):.6f}; {details}"
                )
        return "\n".join(report) + "\n"
    finally:
        client.close()
        engine.dispose()


def main() -> None:
    content = calibrate()
    output = ROOT / "reports/policy_calibration.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    print(content)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
