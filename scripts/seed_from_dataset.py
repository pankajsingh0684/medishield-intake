"""Seed members and claim history from the frozen synthetic dataset."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.core.db.models import ClaimHistory, Member, Policy, User
from packages.core.enums import ClaimHistoryKind, DocType, UserRole
from packages.eval.labels import LabelRecord
from scripts.build_labels import DATASET_DIR, build_labels

ROOT = Path(__file__).resolve().parents[1]
POLICY_NAMESPACE = "medishield:dataset:policy:"
HISTORY_NAMESPACE = "medishield:dataset:history:"
SILVER_MEMBER_ID = "MS-SILVER-RETRIEVAL"
SILVER_POLICY_NUMBER = "MED-SLV-RETRIEVAL"
SILVER_POLICY_ID = uuid5(NAMESPACE_URL, f"{POLICY_NAMESPACE}{SILVER_POLICY_NUMBER}")


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _dob(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").date()


def _source_id(doc_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{HISTORY_NAMESPACE}{doc_id}")


def _history_values(
    label: LabelRecord,
    member_id: str,
    kind: ClaimHistoryKind,
    *,
    admit_date: date | None = None,
    discharge_date: date | None = None,
) -> dict[str, Any]:
    fields = label.fields
    return {
        "claim_id": _source_id(f"{label.doc_id}:{kind.value}"),
        "member_id": member_id,
        "kind": kind,
        "claim_number": None,
        "provider_npi": fields.provider_npi,
        "cpt_codes": fields.cpt_codes,
        "icd10_codes": fields.icd10_codes,
        "amount": fields.claim_amount,
        "service_date": fields.service_date or admit_date,
        "submitted_at": None,
        "admit_date": admit_date,
        "discharge_date": discharge_date,
        "source_case_id": _source_id(label.doc_id),
    }


def seed_dataset(session: Session, test_user_password: str) -> None:
    metadata_rows = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    truth_by_doc = json.loads((DATASET_DIR / "truth.json").read_text(encoding="utf-8"))
    clusters = json.loads((DATASET_DIR / "clusters.json").read_text(encoding="utf-8"))
    labels, unmatched = build_labels(metadata_rows, truth_by_doc)
    if unmatched:
        raise ValueError(f"Cannot seed labels with unmatched scenarios: {unmatched}")

    labels_by_cluster: dict[str, dict[DocType, LabelRecord]] = {}
    for label in labels:
        if label.cluster_id is not None:
            documents = labels_by_cluster.setdefault(label.cluster_id, {})
            if label.doc_type not in documents or not label.doc_id.endswith("_dup"):
                documents[label.doc_type] = label

    policies_by_number: dict[str, dict[str, Any]] = {}
    members: list[dict[str, Any]] = []
    for cluster in clusters:
        policy_number = cluster["policy"]
        policy_id = uuid5(NAMESPACE_URL, f"{POLICY_NAMESPACE}{policy_number}")
        policies_by_number[policy_number] = {
            "policy_id": policy_id,
            "name": "MediShield Gold Plan",
            "version": "synthetic-v1",
        }
        id_label = labels_by_cluster[cluster["cluster_id"]][DocType.ID_DOCUMENT]
        members.append(
            {
                "member_id": cluster["patient_id"],
                "full_name": cluster["name"],
                "date_of_birth": _dob(cluster.get("dob")),
                "policy_number": policy_number,
                "policy_id": policy_id,
                "status": "ACTIVE",
                "id_doc_expiry": id_label.fields.printed_expiry_date,
            }
        )

    policies_by_number[SILVER_POLICY_NUMBER] = {
        "policy_id": SILVER_POLICY_ID,
        "name": "MediShield Silver Plan",
        "version": "synthetic-v1",
    }
    members.append(
        {
            "member_id": SILVER_MEMBER_ID,
            "full_name": "Silver Retrieval Test Member",
            "date_of_birth": date(1985, 6, 15),
            "policy_number": SILVER_POLICY_NUMBER,
            "policy_id": SILVER_POLICY_ID,
            "status": "ACTIVE",
            "id_doc_expiry": date(2030, 6, 15),
        }
    )

    policy_insert = insert(Policy).values(list(policies_by_number.values()))
    session.execute(
        policy_insert.on_conflict_do_update(
            index_elements=[Policy.policy_id],
            set_={"name": policy_insert.excluded.name, "version": policy_insert.excluded.version},
        )
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

    history: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        cluster_labels = labels_by_cluster[cluster_id]
        member_id = cluster["patient_id"]
        claim = cluster_labels[DocType.CLAIM_FORM]
        fraud_reason = cluster.get("fraud_reason")
        if fraud_reason == "date_conflict":
            row = _history_values(claim, member_id, ClaimHistoryKind.EPISODE_CLAIM)
            row["claim_number"] = cluster["claim_number"]
            history.append(row)
        elif fraud_reason == "duplicate_claim" or (
            fraud_reason is None and claim.scenario == "valid_clean"
        ):
            row = _history_values(claim, member_id, ClaimHistoryKind.PRIOR_CLAIM)
            row["claim_number"] = cluster["claim_number"]
            history.append(row)

        if fraud_reason == "readmission_30d":
            discharge = cluster_labels[DocType.DISCHARGE_SUMMARY]
            prior_discharge_date = _date(truth_by_doc[discharge.doc_id].get("prior_discharge_date"))
            row = _history_values(
                discharge,
                member_id,
                ClaimHistoryKind.PRIOR_STAY,
                admit_date=discharge.fields.admit_date,
                discharge_date=prior_discharge_date,
            )
            history.append(row)

    history_insert = insert(ClaimHistory).values(history)
    session.execute(
        history_insert.on_conflict_do_update(
            index_elements=[ClaimHistory.claim_id],
            set_={
                "member_id": history_insert.excluded.member_id,
                "kind": history_insert.excluded.kind,
                "claim_number": history_insert.excluded.claim_number,
                "provider_npi": history_insert.excluded.provider_npi,
                "cpt_codes": history_insert.excluded.cpt_codes,
                "icd10_codes": history_insert.excluded.icd10_codes,
                "amount": history_insert.excluded.amount,
                "service_date": history_insert.excluded.service_date,
                "submitted_at": history_insert.excluded.submitted_at,
                "admit_date": history_insert.excluded.admit_date,
                "discharge_date": history_insert.excluded.discharge_date,
                "source_case_id": history_insert.excluded.source_case_id,
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
