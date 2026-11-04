"""Shape and plausibility validators for OCR-extracted values."""

import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ICD10_PATTERN = re.compile(r"[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?")
CPT_PATTERN = re.compile(r"\d{4}[0-9FT]")
NPI_PATTERN = re.compile(r"\d{10}")
MAX_CLAIM_AMOUNT = Decimal(1000000)
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


def is_valid_icd10(value: str) -> bool:
    return ICD10_PATTERN.fullmatch(value) is not None


def is_valid_cpt(value: str) -> bool:
    return CPT_PATTERN.fullmatch(value) is not None


def is_valid_npi(value: str) -> bool:
    return NPI_PATTERN.fullmatch(value) is not None


def is_valid_amount(value: str) -> bool:
    try:
        amount = Decimal(value.replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return False
    return Decimal(0) < amount <= MAX_CLAIM_AMOUNT


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
