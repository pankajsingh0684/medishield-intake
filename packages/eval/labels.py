"""Validated labels derived from the frozen synthetic dataset."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from packages.core.enums import DecisionKind, DocType


class LabelFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_amount: Decimal | None = None
    icd10_codes: list[str] | None = None
    icd10_code: str | None = None
    cpt_codes: list[str] | None = None
    provider_npi: str | None = None
    service_date: date | None = None
    admit_date: date | None = None
    discharge_date: date | None = None
    rx_date: date | None = None
    drug_names: list[str] | None = None
    signature_present: bool | None = None
    printed_name: str | None = None
    printed_expiry_date: date | None = None
    expired: bool | None = None
    tampered: bool | None = None
    missing_field_type: str | None = None


class LabelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    file: str
    doc_type: DocType
    cluster_id: str | None
    patient_id: str | None
    fields: LabelFields
    kyc_expected: Literal["PASS", "FAIL"] | None
    coverage_expected: bool | None
    fraud_expected: Literal["LOW", "FLAGGED"] | None
    fraud_reason: str | None
    decision_expected: DecisionKind
    scenario: str | None
    reference_date: date | None
