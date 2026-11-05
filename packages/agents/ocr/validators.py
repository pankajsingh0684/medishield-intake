"""Shape and plausibility validators for OCR-extracted values."""

from collections.abc import Callable
from datetime import date, datetime

from packages.core import validation as _validation
from packages.core.validation import (
    DEFAULT_CLAIM_AMOUNT_MAX,
    is_valid_amount,
    is_valid_cpt,
    is_valid_icd10,
    is_valid_npi,
)

CPT_PATTERN = _validation.CPT_PATTERN
ICD10_PATTERN = _validation.ICD10_PATTERN
NPI_PATTERN = _validation.NPI_PATTERN
MAX_CLAIM_AMOUNT = DEFAULT_CLAIM_AMOUNT_MAX
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y")
DEFAULT_YEARS = (2000, 2035)
YEAR_RANGES = {"dob": (1900, 2035), "id_expiry": (2000, 2045)}


def parse_date(value: str) -> date | None:
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _date_validator(key: str) -> Callable[[str], bool]:
    low, high = YEAR_RANGES.get(key, DEFAULT_YEARS)

    def check(value: str) -> bool:
        parsed = parse_date(value)
        return parsed is not None and low <= parsed.year <= high

    return check


FIELD_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "icd10": is_valid_icd10,
    "cpt": is_valid_cpt,
    "provider_npi": is_valid_npi,
    "claim_amount": is_valid_amount,
    **{
        key: _date_validator(key)
        for key in ("dob", "id_expiry", "service_date", "admit_date", "discharge_date", "rx_date")
    },
}


def is_valid(key: str, value: str) -> bool:
    """Fields without a validator are accepted unchanged."""
    validator = FIELD_VALIDATORS.get(key)
    return True if validator is None else validator(value)
