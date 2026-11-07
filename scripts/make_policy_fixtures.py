"""Generate deterministic policy decision fixtures from development-split claims only."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from packages.agents.policy.agent import (
    build_policy_message,
    load_cpt_descriptions,
    load_icd10_descriptions,
)
from packages.core.clients import create_qdrant_client
from packages.core.config import Settings
from packages.core.db.repositories import PolicyExclusionRepo
from packages.core.db.session import create_database_engine
from packages.core.llm.fixtures import FixtureStore, fixture_key
from packages.rag.embeddings import LocalSentenceTransformerEmbedder
from packages.rag.retrieve import DeterministicReranker, QdrantHybridRetriever

ROOT = Path(__file__).resolve().parents[1]
POLICY_NAMESPACE = "medishield:plan:{}:synthetic-v1"


def _service_date(record: dict[str, object]) -> date:
    value = record.get("service_date") or record.get("reference_date")
    if not isinstance(value, str):
        raise TypeError("Development claim is missing service_date and reference_date")
    return date.fromisoformat(value[:10])


def generate_fixtures(
    dataset_dir: Path,
    split_path: Path,
    output_dir: Path,
) -> list[Path]:
    truth = json.loads((dataset_dir / "truth.json").read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    dev_documents = {
        doc_id for doc_id, partition in split["documents"].items() if partition == "dev"
    }
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    client = create_qdrant_client(settings)
    retriever = QdrantHybridRetriever(
        client, LocalSentenceTransformerEmbedder(settings.embedding_model)
    )
    reranker = DeterministicReranker()
    descriptions = load_cpt_descriptions()
    icd_descriptions = load_icd10_descriptions()
    fixture_store = FixtureStore(output_dir)
    written: dict[str, Path] = {}
    try:
        with Session(engine) as session:
            exclusions = PolicyExclusionRepo(session)
            for doc_id in sorted(dev_documents):
                if not doc_id.startswith("claim_"):
                    continue
                record = truth.get(doc_id, {})
                policy_number = record.get("policy_number")
                if not isinstance(policy_number, str):
                    continue
                plan_code = "SILVER" if policy_number.startswith("MED-SLV-") else "GOLD"
                policy_id = uuid5(NAMESPACE_URL, POLICY_NAMESPACE.format(plan_code))
                service_date = _service_date(record)
                queries = [
                    (
                        "CPT",
                        str(code),
                        descriptions.get(str(code), "unlisted procedure"),
                    )
                    for code in record.get("cpt_codes", [])
                    if not exclusions.lookup(policy_id, str(code))
                ] + [
                    (
                        "ICD-10",
                        str(code),
                        icd_descriptions.get(str(code), "diagnosis"),
                    )
                    for code in record.get("icd10_codes", [])
                ]
                for code_type, code, description in queries:
                    query = f"{description} covered service"
                    candidates = retriever.search(query, policy_id, service_date)
                    ranked = reranker.rerank(query, candidates)[:5]
                    if not ranked:
                        continue
                    supporting = next(
                        (chunk for chunk, _ in ranked if chunk.chunk_type == "coverage"),
                        None,
                    )
                    message = build_policy_message(
                        mode="claim",
                        code_type=code_type,
                        code=code,
                        description=description,
                        chunks=[item for item, _ in ranked],
                    )
                    key = fixture_key("policy_decide", [message], [])
                    fixture_store.write(
                        key,
                        {
                            "covered": True if supporting is not None else None,
                            "coverage_percentage": None,
                            "clause_id": supporting.point_id if supporting else None,
                            "policy_clause": supporting.text if supporting else None,
                            "exclusions": [],
                            "certainty": 0.85,
                        },
                    )
                    written[key] = fixture_store.path_for(key)
        active_paths = set(written.values())
        for stale_path in output_dir.glob("policy_decide.*.json"):
            if stale_path not in active_paths:
                stale_path.unlink()
        return list(written.values())
    finally:
        client.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate policy fixtures from dev claims only.")
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "data/synthetic/dataset")
    parser.add_argument("--split", type=Path, default=ROOT / "data/synthetic/split.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/fixtures/llm")
    args = parser.parse_args()
    paths = generate_fixtures(args.dataset_dir, args.split, args.output_dir)
    print(f"Wrote {len(paths)} policy fixtures from the dev split to {args.output_dir}.")


if __name__ == "__main__":
    main()
