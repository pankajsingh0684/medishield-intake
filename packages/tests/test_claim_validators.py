from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.agents.claims.validators import (
    has_confirmed_absence,
    normalize_amount,
    normalize_code,
    normalize_date,
    normalize_npi,
    validate_claim,
)
from packages.core.enums import DocType
from packages.core.models import ClaimFields

RECEIVED_AT = datetime(2025, 5, 15, tzinfo=UTC)


def claim_fields(**overrides) -> ClaimFields:
    values = {
        "claim_amount": Decimal("250.00"),
        "icd10_codes": ["I25.10"],
        "cpt_codes": ["99213"],
        "provider_npi": "1234567893",
        "service_date": date(2025, 5, 1),
        "signature_present": True,
    }
    values.update(overrides)
    return ClaimFields(**values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("$1,234.50", Decimal("1234.50")),
        (Decimal("12.50"), Decimal("12.50")),
        ("", None),
        ("not money", None),
        (None, None),
    ],
)
def test_normalize_amount(value, expected):
    assert normalize_amount(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" i25.10 ", "I25.10"), ("npi-1234567893", "1234567893")],
)
def test_normalize_code_and_npi(value, expected):
    if value.lower().startswith("npi"):
        assert normalize_npi(value) == expected
    else:
        assert normalize_code(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-05-01", date(2025, 5, 1)),
        ("05/01/2025", date(2025, 5, 1)),
        ("05-01-2025", date(2025, 5, 1)),
        (datetime(2025, 5, 1, tzinfo=UTC), date(2025, 5, 1)),
        (date(2025, 5, 1), date(2025, 5, 1)),
        ("not a date", None),
        (None, None),
    ],
)
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("TOTAL CHARGES:\n", "claim_amount", True),
        ("NPI: [NPI MISSING]", "provider_npi", True),
        ("NPI: 123", "provider_npi", False),
        ("Nothing about an NPI here", "provider_npi", False),
        ("TOTAL CHARGES: 12.00", "unknown_field", False),
        ("Unrelated line", "claim_amount", False),
    ],
)
def test_confirmed_absence_requires_label_and_blank_or_missing_marker(text, field, expected):
    assert has_confirmed_absence(text, field) is expected


@pytest.mark.parametrize(
    ("changes", "error_code"),
    [
        ({"icd10_codes": ["K35.8?"]}, "ICD10_CODE"),
        ({"cpt_codes": ["1234A"]}, "CPT_CODE"),
        ({"claim_amount": Decimal(0)}, "CLAIM_AMOUNT"),
        ({"claim_amount": Decimal("1000000.01")}, "CLAIM_AMOUNT"),
        ({"service_date": date(2025, 5, 16)}, "SERVICE_DATE"),
        ({"service_date": date(2024, 5, 14)}, "SERVICE_DATE"),
        ({"provider_npi": "12"}, "NPI_FORMAT"),
    ],
)
def test_claim_validation_rejects_invalid_values(changes, error_code):
    errors, _ = validate_claim(claim_fields(**changes), DocType.CLAIM_FORM, RECEIVED_AT)
    assert any(error.startswith(f"{error_code}:") for error in errors)


def test_lowercase_codes_and_npi_prefix_are_normalizable_and_validated():
    fields = claim_fields(
        icd10_codes=["i25.10"], cpt_codes=["99213"], provider_npi="NPI-1234567893"
    )

    errors, warnings = validate_claim(fields, DocType.CLAIM_FORM, RECEIVED_AT)

    assert not errors
    assert warnings == []


def test_bad_npi_luhn_is_warning_unless_strict():
    fields = claim_fields(provider_npi="1234567890")

    errors, warnings = validate_claim(fields, DocType.CLAIM_FORM, RECEIVED_AT)
    strict_errors, strict_warnings = validate_claim(
        fields, DocType.CLAIM_FORM, RECEIVED_AT, luhn_strict=True
    )

    assert errors == []
    assert warnings[0].startswith("NPI_CHECKSUM:")
    assert strict_errors[0].startswith("NPI_CHECKSUM:")
    assert strict_warnings == []


def test_missing_required_fields_and_schema_are_reported():
    fields = claim_fields(
        claim_amount=None,
        service_date=None,
        icd10_codes=[],
        cpt_codes=[],
        provider_npi=None,
        signature_present=None,
    )

    errors, _ = validate_claim(fields, DocType.CLAIM_FORM, RECEIVED_AT)

    assert any(error.startswith("CLAIM_AMOUNT:") for error in errors)
    assert any(error.startswith("SCHEMA:") for error in errors)


def test_amount_maximum_can_be_configured():
    errors, _ = validate_claim(
        claim_fields(claim_amount=Decimal(500)),
        DocType.CLAIM_FORM,
        RECEIVED_AT,
        claim_amount_max=Decimal(499),
    )
    assert any(error.startswith("CLAIM_AMOUNT:") for error in errors)


def test_discharge_summary_rejects_admit_after_discharge():
    fields = claim_fields(
        admit_date=date(2025, 5, 10),
        discharge_date=date(2025, 5, 9),
    )

    errors, _ = validate_claim(fields, DocType.DISCHARGE_SUMMARY, RECEIVED_AT)

    assert any(error.startswith("DATE_ORDER:") for error in errors)


def test_prescription_does_not_require_cpt_or_claim_amount():
    fields = claim_fields(
        claim_amount=None,
        cpt_codes=[],
        provider_npi=None,
        service_date=None,
        extra={
            "drug_name": "Medication",
            "sig": "Daily",
            "refills": 2,
            "prescriber_npi": "1234567893",
            "dea_number": "AB1234563",
            "rx_date": date(2025, 5, 1),
        },
    )

    errors, _ = validate_claim(fields, DocType.PRESCRIPTION, RECEIVED_AT)

    assert not any(error.startswith(("CLAIM_AMOUNT:", "CPT_CODE:")) for error in errors)


@pytest.mark.parametrize(
    ("npi", "error_code", "warning_code"),
    [
        ("12", "NPI_FORMAT", None),
        ("1234567890", None, "NPI_CHECKSUM"),
    ],
)
def test_prescriber_npi_validation(npi, error_code, warning_code):
    fields = claim_fields(
        claim_amount=None,
        extra={
            "drug_name": "Medication",
            "sig": "Daily",
            "refills": 1,
            "prescriber_npi": npi,
            "dea_number": "AB1234563",
            "rx_date": date(2025, 5, 1),
        },
    )

    errors, warnings = validate_claim(fields, DocType.PRESCRIPTION, RECEIVED_AT)

    if error_code:
        assert any(error.startswith(f"{error_code}:") for error in errors)
    if warning_code:
        assert any(warning.startswith(f"{warning_code}:") for warning in warnings)


def test_non_claim_document_has_no_required_claim_fields():
    errors, _ = validate_claim(claim_fields(), DocType.ID_DOCUMENT, RECEIVED_AT)
    assert any(error.startswith("SCHEMA:") for error in errors)
