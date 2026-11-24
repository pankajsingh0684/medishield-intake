import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, delete, func, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from packages.agents.fraud.agent import FraudAgent
from packages.core.db import PolicyExclusionRepo
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
    code_in_range,
)
from packages.core.enums import AgentStatus, CaseStatus, ClaimHistoryKind, DocType, UserRole
from packages.core.models import ClaimFields, ClaimsResult, KycFlag, KycResult, OcrPayload
from packages.eval.split import load_labels
from scripts.seed import MEMBER_ID_PREFIX, seed_database
from scripts.seed_from_dataset import SILVER_MEMBER_ID


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str
    test_database_url: str

    @model_validator(mode="after")
    def reject_development_database(self) -> "DatabaseTestSettings":
        development_url = make_url(self.database_url)
        test_url = make_url(self.test_database_url)
        development_host = (development_url.host or "").casefold()
        test_host = (test_url.host or "").casefold()
        if development_host in {"localhost", "127.0.0.1", "::1"}:
            development_host = "loopback"
        if test_host in {"localhost", "127.0.0.1", "::1"}:
            test_host = "loopback"
        development_target = (
            development_url.get_backend_name(),
            development_host,
            development_url.port or 5432,
            development_url.database,
        )
        test_target = (
            test_url.get_backend_name(),
            test_host,
            test_url.port or 5432,
            test_url.database,
        )
        if test_target == development_target:
            raise ValueError("TEST_DATABASE_URL must target a database separate from DATABASE_URL")
        return self


def test_database_settings_require_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        DatabaseTestSettings(_env_file=None)


def test_database_settings_reject_development_database() -> None:
    with pytest.raises(ValidationError, match="separate from DATABASE_URL"):
        DatabaseTestSettings(
            _env_file=None,
            database_url="postgresql://user:dev@localhost:5432/medishield",
            test_database_url="postgresql+psycopg://other:pass@127.0.0.1:5432/medishield",
        )


@pytest.fixture(scope="module")
def database_engine():
    test_database_url = DatabaseTestSettings().test_database_url
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    engine = create_engine(test_database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "20261107_decision_idempotency"

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(alembic_config, "762e1c97c741")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "762e1c97c741"
    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "20261107_decision_idempotency"

    command.downgrade(alembic_config, "-1")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "20261107_plan_code"
    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "20261107_decision_idempotency"
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
    policies_columns = {
        column["name"] for column in inspect(database_engine).get_columns("policies")
    }
    assert "plan_code" in policies_columns
    cases_columns = {column["name"] for column in inspect(database_engine).get_columns("cases")}
    history_columns = {
        column["name"] for column in inspect(database_engine).get_columns("claim_history")
    }
    exclusion_columns = {
        column["name"] for column in inspect(database_engine).get_columns("policy_exclusions")
    }
    assert "received_at" in cases_columns
    assert {"kind", "claim_number", "admit_date", "discharge_date"} <= history_columns
    assert exclusion_columns == {
        "exclusion_id",
        "policy_id",
        "range_start",
        "range_end",
        "category",
        "basis",
        "page",
    }
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
    assert any(
        constraint["name"] == "uq_decisions_case_pipeline_run"
        for constraint in inspect(database_engine).get_unique_constraints("decisions")
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
            policy_id=uuid4(),
            status="ACTIVE",
        )
        MemberRepo(session).add(member)
        session.add(Policy(policy_id=member.policy_id, name="Repository policy"))

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
        assert MemberRepo(session).get_by_date_of_birth(date(1980, 1, 1))[0].member_id == member_id
        stored_member = MemberRepo(session).get(member_id)
        assert stored_member is not None
        stored_policy = MemberRepo(session).get_policy(stored_member)
        assert stored_policy is not None
        assert stored_policy.effective_from is None
        assert stored_policy.effective_to is None
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
            .where(Member.member_id.like("PT\\_%", escape="\\"))
        )
        claim_count = session.scalar(select(func.count()).select_from(ClaimHistory))
        users = list(session.scalars(select(User).where(User.email.like("%@medishield.test"))))
        silver_member = session.get(Member, SILVER_MEMBER_ID)
        history = list(session.scalars(select(ClaimHistory)))
        random_member_count = session.scalar(
            select(func.count())
            .select_from(Member)
            .where(Member.member_id.like(f"{MEMBER_ID_PREFIX}%"))
        )

    assert member_count == 46
    assert random_member_count == 0
    assert silver_member is not None
    assert silver_member.policy_number == "MED-SLV-RETRIEVAL"
    assert claim_count == len(history) > 0
    assert {user.role for user in users} == set(UserRole)
    assert all(user.password_hash.startswith("$argon2id$") for user in users)
    assert any(
        row.kind is ClaimHistoryKind.EPISODE_CLAIM and row.member_id == "PT_99733"
        for row in history
    )
    readmission = next(
        row
        for row in history
        if row.kind is ClaimHistoryKind.PRIOR_STAY and row.member_id == "PT_19116"
    )
    assert readmission.discharge_date is not None
    assert readmission.admit_date is not None
    assert 0 < (readmission.admit_date - readmission.discharge_date).days <= 30
    assert not any(
        row.member_id == "PT_20322" and row.kind is ClaimHistoryKind.PRIOR_CLAIM for row in history
    )

    dataset_history = [row for row in history if row.member_id and row.member_id.startswith("PT_")]
    normal_prior_claims = [
        row for row in dataset_history if row.kind is ClaimHistoryKind.PRIOR_CLAIM
    ]
    source_amounts = {
        label.fields.claim_amount
        for label in load_labels()
        if label.doc_type == DocType.CLAIM_FORM and label.fields.claim_amount is not None
    }
    assert all(row.amount in source_amounts for row in normal_prior_claims)
    date_conflict_rx = next(
        label
        for label in load_labels()
        if label.doc_type == DocType.PRESCRIPTION and label.scenario == "date_conflict"
    )
    episode_claim = next(
        row for row in dataset_history if row.kind is ClaimHistoryKind.EPISODE_CLAIM
    )
    assert date_conflict_rx.fields.rx_date is not None
    assert episode_claim.service_date is not None
    assert (date_conflict_rx.fields.rx_date - episode_claim.service_date).days > 30

    first_counts = (member_count, claim_count, len(users))
    with Session(database_engine) as session, session.begin():
        seed_database(session, test_password)

    with Session(database_engine) as session:
        repeated_member_count = session.scalar(
            select(func.count())
            .select_from(Member)
            .where(Member.member_id.like("PT\\_%", escape="\\"))
        )
        repeated_claim_count = session.scalar(select(func.count()).select_from(ClaimHistory))
        repeated_user_count = session.scalar(
            select(func.count()).select_from(User).where(User.email.like("%@medishield.test"))
        )

    assert (repeated_member_count, repeated_claim_count, repeated_user_count) == first_counts


@pytest.mark.parametrize(
    ("scenario", "expected_detector"),
    [
        ("duplicate_claim", "DUPLICATE_CLAIM"),
        ("date_conflict", "DATE_CONFLICT"),
        ("proc_diag_mismatch", "CODE_MISMATCH"),
        ("readmission_30d", "READMISSION_30D"),
        ("amount_under_10k", "NEAR_THRESHOLD"),
        ("name_mismatch", "IDENTITY_MISMATCH"),
    ],
)
def test_fraud_agent_detects_each_step_5c_seeded_scenario(
    database_engine, scenario: str, expected_detector: str
) -> None:
    with Session(database_engine) as seed_session, seed_session.begin():
        seed_database(seed_session, "fraud-seed-test-password")
    labels = load_labels()
    label = next(
        row for row in labels if row.fraud_expected == "FLAGGED" and row.fraud_reason == scenario
    )
    clusters = json.loads(
        (Path(__file__).resolve().parents[2] / "data/synthetic/dataset/clusters.json").read_text(
            encoding="utf-8"
        )
    )
    cluster = next(row for row in clusters if row["patient_id"] == label.patient_id)
    member_id = label.patient_id
    fields = ClaimFields(
        claim_amount=label.fields.claim_amount,
        icd10_codes=label.fields.icd10_codes or [],
        cpt_codes=label.fields.cpt_codes or [],
        provider_npi=label.fields.provider_npi,
        service_date=label.fields.service_date,
        claim_number=cluster.get("claim_number"),
        admit_date=label.fields.admit_date,
        discharge_date=label.fields.discharge_date,
        extra={"rx_date": label.fields.rx_date.isoformat()} if label.fields.rx_date else {},
    )
    now = datetime.combine(
        label.reference_date or date(2025, 1, 1), datetime.min.time(), tzinfo=UTC
    )
    claims = ClaimsResult(
        agent="claims",
        agent_version="test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        extracted_fields=fields,
        schema_valid=True,
        validation_errors=[],
    )
    flags = (
        [KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="seeded name mismatch")]
        if scenario == "name_mismatch"
        else []
    )
    kyc = KycResult(
        agent="kyc",
        agent_version="test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        kyc_passed=True,
        flags=flags,
        member_ref=member_id,
    )
    ocr = OcrPayload(
        agent="ocr",
        agent_version="test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )
    with Session(database_engine) as session:
        agent = FraudAgent(ClaimHistoryRepo(session), _fraud_test_settings())
        prior_processed = (
            [
                {
                    "member_id": label.patient_id,
                    "claim_number": cluster["claim_number"],
                    "case_id": "seeded-original",
                }
            ]
            if scenario == "duplicate_claim"
            else None
        )
        result = agent.score(
            label.doc_type,
            member_id,
            claims,
            kyc,
            ocr,
            now,
            prior_processed_claims=prior_processed,
        )

    assert result.status == AgentStatus.OK
    assert expected_detector in {anomaly.type for anomaly in result.anomalies}


def _fraud_test_settings():
    return SimpleNamespace(
        near_threshold_low=9500,
        near_threshold_high=10000,
        date_conflict_days=30,
        readmission_days=30,
        threshold_fraud_escalate=0.30,
        threshold_fraud_high=0.60,
    )


@pytest.mark.parametrize(
    ("scenario", "detector"),
    [
        ("duplicate_claim", "DUPLICATE_CLAIM"),
        ("date_conflict", "DATE_CONFLICT"),
        ("proc_diag_mismatch", "CODE_MISMATCH"),
        ("readmission_30d", "READMISSION_30D"),
        ("amount_under_10k", "NEAR_THRESHOLD"),
        ("name_mismatch", "IDENTITY_MISMATCH"),
    ],
)
def test_fraud_agent_detects_step_5c_seeded_scenarios(
    database_engine, scenario: str, detector: str
) -> None:
    with Session(database_engine) as seed_session, seed_session.begin():
        seed_database(seed_session, "fraud-seeded-scenario-test")

    labels = load_labels()
    label = next(
        item
        for item in labels
        if item.fraud_expected == "FLAGGED" and item.fraud_reason == scenario
    )
    cluster_rows = json.loads(
        (Path(__file__).resolve().parents[2] / "data/synthetic/dataset/clusters.json").read_text(
            encoding="utf-8"
        )
    )
    cluster = next(item for item in cluster_rows if item["patient_id"] == label.patient_id)
    values = label.fields
    fields = ClaimFields(
        claim_amount=values.claim_amount,
        icd10_codes=values.icd10_codes or [],
        cpt_codes=values.cpt_codes or [],
        provider_npi=values.provider_npi,
        service_date=values.service_date,
        claim_number=cluster.get("claim_number"),
        admit_date=values.admit_date,
        discharge_date=values.discharge_date,
        extra={"rx_date": values.rx_date.isoformat()} if values.rx_date else {},
    )
    reference_date = label.reference_date or date(2025, 1, 1)
    received_at = datetime.combine(reference_date, datetime.min.time(), tzinfo=UTC)
    claims = ClaimsResult(
        agent="claims",
        agent_version="seed-test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=received_at,
        finished_at=received_at,
        extracted_fields=fields,
        schema_valid=True,
        validation_errors=[],
    )
    kyc_flags = (
        [KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="seeded name mismatch")]
        if scenario == "name_mismatch"
        else []
    )
    kyc = KycResult(
        agent="kyc",
        agent_version="seed-test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=received_at,
        finished_at=received_at,
        kyc_passed=True,
        flags=kyc_flags,
        member_ref=label.patient_id,
    )
    ocr = OcrPayload(
        agent="ocr",
        agent_version="seed-test",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=received_at,
        finished_at=received_at,
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )
    with Session(database_engine) as session:
        result = FraudAgent(ClaimHistoryRepo(session), _fraud_test_settings()).score(
            label.doc_type,
            label.patient_id,
            claims,
            kyc,
            ocr,
            received_at,
            prior_processed_claims=(
                [
                    {
                        "member_id": label.patient_id,
                        "claim_number": cluster["claim_number"],
                        "case_id": "seeded-original-claim",
                    }
                ]
                if scenario == "duplicate_claim"
                else None
            ),
        )

    assert result.status == AgentStatus.OK
    assert detector in {anomaly.type for anomaly in result.anomalies}


EXCLUSION_RANGES = [
    ("15000", "15999"),
    ("15820", "15829"),
    ("17000", "17999"),
    ("0001T", "0099T"),
    ("V2100", "V2799"),
    ("D0100", "D9999"),
]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("00020", set()),
        ("0001T", {"0001T"}),
        ("0050T", {"0001T"}),
        ("V2100", {"V2100"}),
        ("V2799", {"V2100"}),
        ("D0500", {"D0100"}),
        ("17000", {"17000"}),
        ("15820", {"15000", "15820"}),
        ("99999", set()),
    ],
)
def test_code_in_range_requires_same_shape_class(code: str, expected: set[str]) -> None:
    matches = {start for start, end in EXCLUSION_RANGES if code_in_range(code, start, end)}

    assert matches == expected


def test_policy_exclusion_lookup_matches_by_shape_class(database_engine) -> None:
    policy_id = uuid4()
    with Session(database_engine) as session, session.begin():
        session.add(Policy(policy_id=policy_id, name="Shape class policy"))
        for start, end in EXCLUSION_RANGES:
            session.add(
                PolicyExclusion(
                    exclusion_id=uuid4(),
                    policy_id=policy_id,
                    range_start=start,
                    range_end=end,
                    category="Test",
                    basis="Test",
                    page=1,
                )
            )

    with Session(database_engine) as session:
        repo = PolicyExclusionRepo(session)
        assert repo.lookup(policy_id, "00020") == []
        assert {row.range_start for row in repo.lookup(policy_id, "0050t")} == {"0001T"}
        assert {row.range_start for row in repo.lookup(policy_id, "15820")} == {"15000", "15820"}
        assert {row.range_start for row in repo.lookup(policy_id, "D0500")} == {"D0100"}
        assert repo.lookup(policy_id, "99999") == []
