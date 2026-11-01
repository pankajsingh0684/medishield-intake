"""Seed deterministic synthetic members, claim history, and local test users."""

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from argon2 import PasswordHasher
from faker import Faker
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.db.models import ClaimHistory, Member, User
from packages.core.db.session import create_database_engine
from packages.core.enums import ClaimHistoryKind, UserRole
from scripts.seed_from_dataset import seed_dataset

SEED = 20261031
POLICY_ID_NAMESPACE = "medishield:synthetic:policy:"
MEMBER_ID_PREFIX = "MS-TEST-"


class SeedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.example"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str
    seed_test_user_password: SecretStr


def seed_random_population(session: Session, test_user_password: str) -> None:
    fake = Faker("en_US")
    fake.seed_instance(SEED)
    members: list[dict[str, object]] = []
    for member_number in range(1, 41):
        member_id = f"{MEMBER_ID_PREFIX}{member_number:04d}"
        members.append(
            {
                "member_id": member_id,
                "full_name": fake.name(),
                "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=80),
                "policy_number": f"POL-TEST-{member_number:05d}",
                "policy_id": uuid5(NAMESPACE_URL, f"{POLICY_ID_NAMESPACE}{member_number}"),
                "status": "ACTIVE",
                "id_doc_expiry": date(2028, 12, 31),
            }
        )

    member_insert = insert(Member).values(members)
    session.execute(
        member_insert.on_conflict_do_update(
            index_elements=[Member.member_id],
            set_={
                "full_name": member_insert.excluded.full_name,
                "date_of_birth": member_insert.excluded.date_of_birth,
                "policy_number": member_insert.excluded.policy_number,
                "policy_id": member_insert.excluded.policy_id,
                "status": member_insert.excluded.status,
                "id_doc_expiry": member_insert.excluded.id_doc_expiry,
            },
        )
    )

    claims: list[dict[str, object]] = []
    for claim_number in range(1, 201):
        member_number = ((claim_number - 1) % 40) + 1
        service_date = fake.date_between_dates(
            date_start=date(2024, 1, 1),
            date_end=date(2026, 10, 1),
        )
        claims.append(
            {
                "claim_id": uuid5(NAMESPACE_URL, f"medishield:synthetic:claim:{claim_number}"),
                "member_id": f"{MEMBER_ID_PREFIX}{member_number:04d}",
                "kind": ClaimHistoryKind.PRIOR_CLAIM,
                "claim_number": f"CLM-TEST-{claim_number:06d}",
                "provider_npi": f"{claim_number % 1_000_000_000:010d}",
                "cpt_codes": [fake.random_element(elements=("99213", "99214", "93000", "80053"))],
                "icd10_codes": [fake.random_element(elements=("A00.0", "E11.9", "I10", "J06.9"))],
                "amount": Decimal(f"{fake.random_int(min=2500, max=250000) / 100:.2f}"),
                "service_date": service_date,
                "submitted_at": datetime.combine(service_date, datetime.min.time(), tzinfo=UTC)
                + timedelta(days=fake.random_int(min=1, max=14)),
                "source_case_id": uuid5(NAMESPACE_URL, f"medishield:synthetic:case:{claim_number}"),
            }
        )

    claim_insert = insert(ClaimHistory).values(claims)
    session.execute(
        claim_insert.on_conflict_do_update(
            index_elements=[ClaimHistory.claim_id],
            set_={
                "member_id": claim_insert.excluded.member_id,
                "kind": claim_insert.excluded.kind,
                "claim_number": claim_insert.excluded.claim_number,
                "provider_npi": claim_insert.excluded.provider_npi,
                "cpt_codes": claim_insert.excluded.cpt_codes,
                "icd10_codes": claim_insert.excluded.icd10_codes,
                "amount": claim_insert.excluded.amount,
                "service_date": claim_insert.excluded.service_date,
                "submitted_at": claim_insert.excluded.submitted_at,
                "source_case_id": claim_insert.excluded.source_case_id,
            },
        )
    )

    role_emails = {role: f"{role.value.lower()}@medishield.test" for role in UserRole}
    existing_users = {
        user.email: user
        for user in session.scalars(select(User).where(User.email.in_(role_emails.values())))
    }
    password_hasher = PasswordHasher()
    for role, email in role_emails.items():
        existing_user = existing_users.get(email)
        if existing_user is None:
            session.add(
                User(
                    user_id=uuid5(NAMESPACE_URL, f"medishield:test-user:{role.value}"),
                    email=email,
                    password_hash=password_hasher.hash(test_user_password),
                    role=role,
                )
            )
        else:
            existing_user.role = role


def seed_database(session: Session, test_user_password: str) -> None:
    seed_dataset(session, test_user_password)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MediShield development data.")
    parser.add_argument(
        "--random",
        action="store_true",
        help="also seed the optional MS-TEST random population",
    )
    args = parser.parse_args()
    settings = SeedSettings()
    engine = create_database_engine(settings.database_url)
    with Session(engine) as session, session.begin():
        password = settings.seed_test_user_password.get_secret_value()
        seed_database(session, password)
        if args.random:
            seed_random_population(session, password)
    engine.dispose()
    print("Seeded dataset members, history, and 4 role users.")
    if args.random:
        print("Also seeded the optional random MS-TEST population.")


if __name__ == "__main__":
    main()
