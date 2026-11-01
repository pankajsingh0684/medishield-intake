from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, delete, func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from packages.core.db.models import (
    AuditEvent,
    Case,
    ClaimHistory,
    Member,
    Policy,
    PolicyExclusion,
    User,
)
from packages.core.db.repositories import (
    AuditRepo,
    CaseRepo,
    ClaimHistoryRepo,
    MemberRepo,
    PolicyExclusionRepo,
)
from packages.core.enums import CaseStatus, ClaimHistoryKind, DocType, UserRole
from scripts.seed import MEMBER_ID_PREFIX, seed_database


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.example"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    test_database_url: str


TEST_DATABASE_URL = DatabaseTestSettings().test_database_url


@pytest.fixture(scope="module")
def database_engine():
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(alembic_config, "762e1c97c741")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "762e1c97c741"
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


def test_migrations_create_all_spec_tables_and_step_5b_columns(database_engine) -> None:
    table_names = set(inspect(database_engine).get_table_names())

    assert {
        "cases",
        "agent_runs",
        "decisions",
        "overrides",
        "audit_events",
        "members",
        "claim_history",
        "policy_exclusions",
        "policies",
        "users",
        "alembic_version",
    } <= table_names
    cases_columns = {column["name"] for column in inspect(database_engine).get_columns("cases")}
    history_columns = {
        column["name"] for column in inspect(database_engine).get_columns("claim_history")
    }
    assert "received_at" in cases_columns
    assert {"kind", "claim_number", "admit_date", "discharge_date"} <= history_columns
    kind_column = next(
        column
        for column in inspect(database_engine).get_columns("claim_history")
        if column["name"] == "kind"
    )
    assert kind_column["type"].__class__.__name__.lower() == "text"
    assert any(
        constraint["name"] == "ck_claim_history_kind"
        for constraint in inspect(database_engine).get_check_constraints("claim_history")
    )


def test_repositories_round_trip_case_member_claim_and_audit(database_engine) -> None:
    case_id = uuid4()
    member_id = f"REPO-TEST-{uuid4()}"
    policy_number = f"POL-REPO-{uuid4()}"

    with Session(database_engine) as session, session.begin():
        case = Case(
            case_id=case_id,
            status=CaseStatus.RECEIVED,
            doc_type=DocType.CLAIM_FORM,
            object_key="raw/test/original.pdf",
            sha256="a" * 64,
            mime_type="application/pdf",
        )
        CaseRepo(session).add(case)

        member = Member(
            member_id=member_id,
            full_name="Synthetic Test Member",
            date_of_birth=date(1980, 1, 1),
            policy_number=policy_number,
            status="ACTIVE",
        )
        MemberRepo(session).add(member)

        claim = ClaimHistory(
            claim_id=uuid4(),
            member_id=member_id,
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            claim_number=f"CLM-{uuid4()}",
            provider_npi="0123456789",
            cpt_codes=["99213"],
            icd10_codes=["I10"],
            amount=Decimal("125.50"),
            service_date=date(2026, 1, 15),
            submitted_at=datetime(2026, 1, 20, tzinfo=UTC),
        )
        ClaimHistoryRepo(session).add(claim)
        claim_number = claim.claim_number
        policy_id = uuid4()
        session.add(Policy(policy_id=policy_id, name="Test policy"))
        exclusion = PolicyExclusion(
            exclusion_id=uuid4(),
            policy_id=policy_id,
            range_start="1000",
            range_end="1999",
            category="Test category",
            basis="Test basis",
            page=4,
        )
        session.add(exclusion)
        exclusion_id = exclusion.exclusion_id
        alpha_exclusion = PolicyExclusion(
            exclusion_id=uuid4(),
            policy_id=policy_id,
            range_start="V1000",
            range_end="V2999",
            category="Vision",
            basis="Test range",
            page=5,
        )
        session.add(alpha_exclusion)
        alpha_exclusion_id = alpha_exclusion.exclusion_id
        event = AuditRepo(session).append(
            case_id=case_id,
            actor_type="AGENT",
            actor="classifier",
            event_type="NODE_END",
            payload={"status": "OK"},
        )
        event_id = event.event_id

    with Session(database_engine) as session:
        stored_case = CaseRepo(session).get(case_id)
        assert stored_case is not None
        assert stored_case.received_at is not None
        assert CaseRepo(session).list(status=CaseStatus.RECEIVED, limit=100)
        assert MemberRepo(session).get(member_id) is not None
        assert MemberRepo(session).get_by_policy_number(policy_number) is not None
        history = ClaimHistoryRepo(session).for_member(
            member_id,
            service_date_from=date(2026, 1, 1),
            service_date_to=date(2026, 1, 31),
        )
        assert len(history) == 1
        assert history[0].amount == Decimal("125.50")
        assert history[0].kind is ClaimHistoryKind.PRIOR_CLAIM
        assert [
            row.claim_id
            for row in ClaimHistoryRepo(session).for_member_and_kind(
                member_id, ClaimHistoryKind.PRIOR_CLAIM
            )
        ] == [history[0].claim_id]
        assert [
            row.claim_id for row in ClaimHistoryRepo(session).by_claim_number(claim_number)
        ] == [history[0].claim_id]
        assert [
            row.exclusion_id for row in PolicyExclusionRepo(session).lookup(policy_id, "1500")
        ] == [exclusion_id]
        assert [
            row.exclusion_id for row in PolicyExclusionRepo(session).lookup(policy_id, "V1500")
        ] == [alpha_exclusion_id]
        assert PolicyExclusionRepo(session).lookup(policy_id, "2000") == []
        assert [
            row.exclusion_id for row in PolicyExclusionRepo(session).lookup(policy_id, "v2100")
        ] == [alpha_exclusion_id]
        events = AuditRepo(session).for_case(case_id)
        assert [audit_event.event_id for audit_event in events] == [event_id]


def test_claim_history_kind_check_rejects_unknown_value(database_engine) -> None:
    with (
        pytest.raises(DBAPIError, match="ck_claim_history_kind"),
        database_engine.begin() as connection,
    ):
        connection.exec_driver_sql(
            "INSERT INTO claim_history (claim_id, kind) VALUES "
            "('00000000-0000-0000-0000-000000000099', 'UNKNOWN')"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event_id: (
            update(AuditEvent).where(AuditEvent.event_id == event_id).values(actor="changed")
        ),
        lambda event_id: delete(AuditEvent).where(AuditEvent.event_id == event_id),
    ],
    ids=("update", "delete"),
)
def test_audit_events_reject_update_and_delete(database_engine, mutation) -> None:
    case_id = uuid4()
    with Session(database_engine) as session, session.begin():
        event = AuditRepo(session).append(
            case_id=case_id,
            actor_type="SYSTEM",
            actor="test",
            event_type="STATUS",
            payload={"status": "RECEIVED"},
        )
        event_id = event.event_id

    with Session(database_engine) as session:
        with pytest.raises(DBAPIError, match="audit_events is append-only"):
            session.execute(mutation(event_id))
            session.commit()
        session.rollback()

    with Session(database_engine) as session:
        assert session.get(AuditEvent, event_id) is not None


def test_seed_is_idempotent_and_passwords_are_argon2_hashed(database_engine) -> None:
    test_password = "isolated-database-test-password"

    with Session(database_engine) as session, session.begin():
        seed_database(session, test_password)

    with Session(database_engine) as session:
        member_count = session.scalar(
            select(func.count())
            .select_from(Member)
            .where(Member.member_id.like(f"{MEMBER_ID_PREFIX}%"))
        )
        claim_count = session.scalar(
            select(func.count())
            .select_from(ClaimHistory)
            .where(ClaimHistory.member_id.like(f"{MEMBER_ID_PREFIX}%"))
        )
        users = list(session.scalars(select(User).where(User.email.like("%@medishield.test"))))

    assert member_count == 40
    assert claim_count == 200
    assert {user.role for user in users} == set(UserRole)
    assert all(user.password_hash.startswith("$argon2id$") for user in users)

    first_counts = (member_count, claim_count, len(users))
    with Session(database_engine) as session, session.begin():
        seed_database(session, test_password)

    with Session(database_engine) as session:
        repeated_member_count = session.scalar(
            select(func.count())
            .select_from(Member)
            .where(Member.member_id.like(f"{MEMBER_ID_PREFIX}%"))
        )
        repeated_claim_count = session.scalar(
            select(func.count())
            .select_from(ClaimHistory)
            .where(ClaimHistory.member_id.like(f"{MEMBER_ID_PREFIX}%"))
        )
        repeated_user_count = session.scalar(
            select(func.count()).select_from(User).where(User.email.like("%@medishield.test"))
        )

    assert (repeated_member_count, repeated_claim_count, repeated_user_count) == first_counts
