"""Run and print a grounded sample policy decision."""

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from packages.agents.policy.agent import PolicyAgent
from packages.core.clients import create_qdrant_client
from packages.core.config import Settings
from packages.core.db.repositories import MemberRepo, PolicyExclusionRepo
from packages.core.db.session import create_database_engine
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.gateway import build_gateway
from packages.core.models import ClaimFields, ClaimsResult, KycResult, OcrPayload
from packages.rag.embeddings import LocalSentenceTransformerEmbedder
from packages.rag.retrieve import (
    CrossEncoderReranker,
    DeterministicReranker,
    QdrantHybridRetriever,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a policy decision for a sample claim.")
    parser.add_argument("--member-id", default="PT_19116")
    parser.add_argument("--cpt", action="append")
    parser.add_argument("--icd", action="append", default=[])
    parser.add_argument("--service-date", type=date.fromisoformat, default=date(2025, 12, 15))
    args = parser.parse_args()
    if args.cpt is None:
        args.cpt = ["90837"]

    settings = Settings()
    engine = create_database_engine(settings.database_url)
    client = create_qdrant_client(settings)
    gateway = build_gateway(settings)
    now = datetime.now(UTC)
    try:
        kyc = KycResult(
            agent="kyc",
            agent_version="sample",
            status=AgentStatus.OK,
            confidence=0.95,
            started_at=now,
            finished_at=now,
            kyc_passed=True,
            flags=[],
            member_ref=args.member_id,
        )
        claims = ClaimsResult(
            agent="claims",
            agent_version="sample",
            status=AgentStatus.OK,
            confidence=0.95,
            started_at=now,
            finished_at=now,
            extracted_fields=ClaimFields(
                claim_amount=None,
                icd10_codes=args.icd,
                cpt_codes=args.cpt,
                provider_npi=None,
                service_date=args.service_date,
            ),
            schema_valid=True,
            validation_errors=[],
        )
        ocr = OcrPayload(
            agent="ocr",
            agent_version="sample",
            status=AgentStatus.OK,
            confidence=0.95,
            started_at=now,
            finished_at=now,
            fields=[],
            raw_text="",
            bounding_boxes=[],
            pages=1,
            used_text_layer=True,
        )
        with Session(engine) as session:
            agent = PolicyAgent(
                MemberRepo(session),
                PolicyExclusionRepo(session),
                gateway,
                settings,
                QdrantHybridRetriever(
                    client, LocalSentenceTransformerEmbedder(settings.embedding_model)
                ),
                (
                    DeterministicReranker()
                    if settings.llm_provider == "stub"
                    else CrossEncoderReranker()
                ),
            )
            result = agent.evaluate(
                DocType.CLAIM_FORM,
                kyc,
                claims,
                ocr,
                datetime.combine(args.service_date, datetime.min.time(), tzinfo=UTC),
            )
        print(f"Decision: covered={result.covered} confidence={result.confidence:.2f}")
        print(f"Coverage percentage: {result.coverage_percentage}")
        print(f"Status: {result.status.value}{f' ({result.error})' if result.error else ''}")
        if result.policy_clause:
            print(
                f"Clause: {result.policy_clause.section} (page {result.policy_clause.page}) "
                f"[score {result.policy_clause.score:.2f}]\n{result.policy_clause.text}"
            )
        for exclusion in result.exclusions:
            print(f"Exclusion: {exclusion.section} (page {exclusion.page})\n{exclusion.text}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
    finally:
        gateway.close()
        client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
