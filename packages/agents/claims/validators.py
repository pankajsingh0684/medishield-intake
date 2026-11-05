"""Normalization and validation for claim submission fields."""

import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from packages.core.enums import DocType
from packages.core.models import ClaimFields
from packages.core.validation import (
    has_valid_npi_luhn,
    is_valid_cpt,
    is_valid_icd10,
    is_valid_npi,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "schemas" / "claim_submission_standard.v1.json"
)
REQUIRED_FIELDS: dict[DocType, tuple[str, ...]] = {
    DocType.CLAIM_FORM: (
        "claim_amount",
        "service_date",
        "icd10_codes",
        "cpt_codes",
        "provider_npi",
        "signature_present",
    ),
    DocType.DISCHARGE_SUMMARY: (
        "admit_date",
        "discharge_date",
        "icd10_codes",
        "signature_present",
    ),
    DocType.PRESCRIPTION: (
        "drug_name",
        "sig",
        "refills",
        "prescriber_npi",
        "dea_number",
        "rx_date",
    ),
}
FIELD_ALIASES = {
    "icd10": "icd10_codes",
    "cpt": "cpt_codes",
    "medication": "drug_name",
    "dosage": "sig",
    "dea": "dea_number",
}
LABELS = {
    "claim_amount": r"(?:CLAIM\s+AMOUNT|TOTAL\s+CHARGES?|AMOUNT\s+BILLED)",
    "service_date": r"(?:SERVICE\s+DATE|DOS)",
    "icd10_codes": r"(?:ICD\s*[- ]?10|DIAGNOS(?:IS|ES))",
    "cpt_codes": r"(?:CPT|PROCEDURE\s+CODE)",
    "provider_npi": r"(?:PROVIDER\s+)?NPI",
    "signature_present": r"SIGNATURE",
    "admit_date": r"(?:ADMIT|ADMISSION)\s+DATE|DATE\s+OF\s+ADMISSION",
    "discharge_date": r"(?:DISCHARGE|DISCHARGED)\s+DATE|DATE\s+OF\s+DISCHARGE",
    "drug_name": r"(?:MEDICATION|DRUG|PRESCRIPTION)",
    "sig": r"(?:SIG|DOSAGE\s+INSTRUCTIONS?)",
    "refills": r"REFILLS?",
    "prescriber_npi": r"(?:PRESCRIBER\s+)?NPI",
    "dea_number": r"DEA(?:\s+(?:NO|NUMBER))?",
    "rx_date": r"(?:RX|PRESCRIPTION)\s+DATE",
}


def normalize_code(value: str) -> str:
    return value.strip().upper()


def normalize_npi(value: str) -> str:
    return re.sub(r"^\s*NPI\s*-?\s*", "", value, flags=re.IGNORECASE).strip()


def normalize_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return None


def normalize_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    return None


def has_confirmed_absence(raw_text: str, field: str) -> bool:
    label = LABELS.get(field)
    if label is None:
        return False
    match = re.search(rf"\b(?:{label})\b\s*[:#-]?\s*(?P<value>[^\r\n]*)", raw_text, re.IGNORECASE)
    if match is None:
        return False
    value = match.group("value").strip()
    return not value or re.search(r"\[\s*.*?\bMISSING\b.*?\]", value, re.IGNORECASE) is not None


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_claim(
    fields: ClaimFields,
    doc_type: DocType,
    received_at: datetime,
    *,
    luhn_strict: bool = False,
    claim_amount_max: Decimal = Decimal(1_000_000),
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_FIELDS.get(doc_type, ()):
        value = (
            fields.extra.get(field)
            if field in REQUIRED_FIELDS[DocType.PRESCRIPTION]
            else getattr(fields, field, None)
        )
        if value is None or value == "" or value == []:
            errors.append(f"{field.upper()}: required field is missing")

    for code in fields.icd10_codes:
        normalized = normalize_code(code)
        if not is_valid_icd10(normalized):
            errors.append(f"ICD10_CODE: invalid ICD-10 code {code!r}")
    for code in fields.cpt_codes:
        normalized = normalize_code(code)
        if not is_valid_cpt(normalized):
            errors.append(f"CPT_CODE: invalid CPT code {code!r}")

    for key in ("provider_npi",):
        npi = getattr(fields, key)
        if npi:
            normalized_npi = normalize_npi(npi)
            if not is_valid_npi(normalized_npi):
                errors.append("NPI_FORMAT: NPI must contain 10 digits")
            elif not has_valid_npi_luhn(normalized_npi):
                (errors if luhn_strict else warnings).append(
                    "NPI_CHECKSUM: NPI failed Luhn checksum"
                )
    prescriber_npi = fields.extra.get("prescriber_npi")
    if prescriber_npi:
        normalized_npi = normalize_npi(str(prescriber_npi))
        if not is_valid_npi(normalized_npi):
            errors.append("NPI_FORMAT: prescriber NPI must contain 10 digits")
        elif not has_valid_npi_luhn(normalized_npi):
            (errors if luhn_strict else warnings).append("NPI_CHECKSUM: NPI failed Luhn checksum")

    if fields.claim_amount is not None and not Decimal(0) < fields.claim_amount <= claim_amount_max:
        errors.append(
            "CLAIM_AMOUNT: amount must be greater than 0 and within the configured maximum"
        )
    if fields.service_date is not None:
        reference_date = received_at.date()
        if fields.service_date > reference_date:
            errors.append("SERVICE_DATE: date cannot be later than case received_at")
        elif fields.service_date < reference_date - timedelta(days=365):
            errors.append("SERVICE_DATE: date cannot be more than 365 days before case received_at")
    if (
        doc_type == DocType.DISCHARGE_SUMMARY
        and fields.admit_date is not None
        and fields.discharge_date is not None
        and fields.admit_date > fields.discharge_date
    ):
        errors.append("DATE_ORDER: admit_date must be on or before discharge_date")

    schema_fields = fields.model_dump(
        mode="json", exclude={"field_confidence", "field_source", "claim_number"}
    )
    schema_fields["claim_amount"] = (
        float(fields.claim_amount) if fields.claim_amount is not None else None
    )
    schema_data = {
        "doc_type": doc_type.value,
        "extracted_fields": schema_fields,
    }
    for schema_error in sorted(
        _schema_validator().iter_errors(schema_data), key=lambda error: list(error.absolute_path)
    ):
        path = ".".join(str(part) for part in schema_error.absolute_path) or "CLAIM"
        errors.append(f"SCHEMA: {path}: {schema_error.message}")
    return errors, warnings
