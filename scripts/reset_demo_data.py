"""Reset explicitly marked demo cases; never infer ownership of unmarked records."""

import argparse
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, aliased

from apps.api.settings import ApiSettings
from packages.core.db.models import (
    AgentRun,
    AuditEvent,
    Case,
    ClaimHistory,
    Decision,
    Override,
    User,
)
from packages.core.db.session import create_database_engine
from packages.core.enums import CaseStatus, DecisionKind, DocType, UserRole
from packages.core.storage import S3Storage

CHANNEL = "DEMO_RESET"
PREFIX = "demo/reset/"
NAMES = ("approved", "rejected", "escalated", "review", "overridden")
ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "data/synthetic/dataset/claim_forms/claim_extra_PT_EX0031.png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="apply changes to marked demo cases")
    args = parser.parse_args()
    settings = ApiSettings()
    if settings.app_env == "production" or make_url(settings.database_url).host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise SystemExit("Demo reset requires a local, non-production database.")
    engine = create_database_engine(settings.database_url)
    other_case = aliased(Case)
    with Session(engine) as session, session.begin():
        candidates = list(
            session.scalars(
                select(Case).where(
                    Case.channel == CHANNEL,
                    Case.object_key.startswith(PREFIX),
                    ~select(Decision.case_id).where(Decision.case_id == Case.case_id).exists(),
                    ~select(Override.case_id).where(Override.case_id == Case.case_id).exists(),
                    ~select(ClaimHistory.claim_id)
                    .where(ClaimHistory.source_case_id == Case.case_id)
                    .exists(),
                    ~select(other_case.case_id)
                    .where(other_case.duplicate_of == Case.case_id)
                    .exists(),
                )
            )
        )
        ids = [case.case_id for case in candidates]
        print(
            f"{'Applying' if args.yes else 'Dry run'}: {len(ids)} marked decisionless cases eligible; "
            f"ensure {len(NAMES)} demo cases. Unmarked cases are untouched."
        )
        if not args.yes:
            return
        reviewer = session.scalar(select(User).where(User.role == UserRole.REVIEWER).limit(1))
        if reviewer is None:
            raise SystemExit("A seeded reviewer is required; no changes made.")
        content = DOCUMENT.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        storage = S3Storage(
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
            bucket=settings.s3_bucket,
        )
        try:
            storage.put(
                key=PREFIX + "claim.png", content=content, content_type="image/png", sha256=digest
            )
        finally:
            storage.close()
        if ids:
            session.execute(delete(AgentRun).where(AgentRun.case_id.in_(ids)))
            session.execute(delete(AuditEvent).where(AuditEvent.case_id.in_(ids)))
            session.execute(delete(Case).where(Case.case_id.in_(ids)))
            session.flush()
        for name in NAMES:
            case_id = uuid5(NAMESPACE_URL, f"medishield:demo-reset:case:{name}")
            existing = session.get(Case, case_id)
            if existing:
                if existing.channel != CHANNEL or not existing.object_key.startswith(PREFIX):
                    raise ValueError(
                        "A demo ID belongs to an unmarked case; refusing to overwrite."
                    )
                continue
            now = datetime.now(UTC)
            status = (
                CaseStatus.NEEDS_REVIEW
                if name == "review"
                else (CaseStatus.OVERRIDDEN if name == "overridden" else CaseStatus.DECIDED)
            )
            session.add(
                Case(
                    case_id=case_id,
                    status=status,
                    channel=CHANNEL,
                    doc_type=DocType.CLAIM_FORM,
                    object_key=PREFIX + "claim.png",
                    sha256=digest,
                    mime_type="image/png",
                )
            )
            session.flush()
            session.add(
                AuditEvent(
                    case_id=case_id,
                    actor_type="SYSTEM",
                    actor="demo_reset",
                    event_type="DEMO_SEED",
                    payload={},
                )
            )
            if name != "review":
                decision = {
                    "approved": DecisionKind.APPROVE,
                    "rejected": DecisionKind.REJECT,
                    "escalated": DecisionKind.ESCALATE,
                    "overridden": DecisionKind.ESCALATE,
                }[name]
                pipeline = uuid5(NAMESPACE_URL, f"medishield:demo-reset:run:{name}")
                session.add(
                    AgentRun(
                        case_id=case_id,
                        pipeline_run=pipeline,
                        agent="classifier",
                        agent_version="demo",
                        status="OK",
                        confidence=Decimal("0.99"),
                        output={},
                        started_at=now,
                        finished_at=now,
                    )
                )
                session.add(
                    Decision(
                        case_id=case_id,
                        pipeline_run=pipeline,
                        decision=decision,
                        confidence=Decimal("0.99"),
                        justification="Synthetic demo decision.",
                        rule_trace=[],
                        config_snapshot={},
                    )
                )
                if name == "overridden":
                    session.add(
                        Override(
                            case_id=case_id,
                            user_id=reviewer.user_id,
                            from_decision=decision,
                            to_decision=DecisionKind.APPROVE,
                            reason="Synthetic demo review.",
                        )
                    )
    engine.dispose()


if __name__ == "__main__":
    main()
