"""Shared validation primitives for document fields."""

import re
from decimal import Decimal, InvalidOperation

ICD10_PATTERN = re.compile(r"[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?")
CPT_PATTERN = re.compile(r"\d{4}[0-9FT]")
NPI_PATTERN = re.compile(r"\d{10}")
DEFAULT_CLAIM_AMOUNT_MAX = Decimal(1_000_000)


def parse_amount(value: str, maximum: Decimal = DEFAULT_CLAIM_AMOUNT_MAX) -> Decimal | None:
    try:
        amount = Decimal(value.replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return None
    return amount if Decimal(0) < amount <= maximum else None


def is_valid_icd10(value: str) -> bool:
    return ICD10_PATTERN.fullmatch(value) is not None


def is_valid_cpt(value: str) -> bool:
    return CPT_PATTERN.fullmatch(value) is not None


def is_valid_npi(value: str) -> bool:
    return NPI_PATTERN.fullmatch(value) is not None


def is_valid_amount(value: str, maximum: Decimal = DEFAULT_CLAIM_AMOUNT_MAX) -> bool:
    return parse_amount(value, maximum) is not None


def has_valid_npi_luhn(value: str) -> bool:
    """Check the NPI checksum by applying Luhn to its 80840-prefixed form."""
    if not is_valid_npi(value):
        return False
    digits = [int(digit) for digit in f"80840{value}"]
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0
