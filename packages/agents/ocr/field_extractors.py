"""Regex-based field extraction from OCR text."""

import re
from collections import Counter
from dataclasses import dataclass

from packages.agents.ocr.validators import is_valid, parse_date

# Canonical field vocabulary from spec 7.3
CANONICAL_FIELDS = {
    "member_id",
    "member_name",
    "dob",
    "policy_number",
    "id_number",
    "id_expiry",
    "claim_amount",
    "icd10",
    "cpt",
    "provider_npi",
    "service_date",
    "provider_name",
    "diagnosis",
    "medication",
}


@dataclass
class ExtractedField:
    """A single extracted field with value and confidence."""

    key: str
    value: str
    confidence: float  # Tesseract word confidence or LLM confidence


def extract_member_id(text: str) -> str | None:
    """Extract member ID (format: M followed by 6 digits)."""
    match = re.search(r"\bM\d{6}\b", text, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def extract_dob(text: str) -> str | None:
    """Extract date of birth (MM/DD/YYYY or YYYY-MM-DD)."""
    match = re.search(
        r"\b(?:(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}"
        r"|(?:19|20)\d{2}-\d{2}-\d{2})\b",
        text,
    )
    if match:
        return match.group(0)
    return None


def extract_policy_number(text: str) -> str | None:
    """Extract a policy identifier only when it follows an explicit policy label."""
    match = re.search(
        r"\bPOLICY(?:\s+(?:NO|NUMBER|ID)\b\s*[:#]?\s*|\s*[:#]\s*)"
        r"([A-Z0-9]+(?:-[A-Z0-9]+)*)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    return None


def extract_id_number(text: str) -> str | None:
    """Extract ID document number (driver's license, passport, etc.)."""
    match = re.search(
        r"\b(?:ID|LICENSE|PASSPORT(?:\s*(?:NO|NUMBER))?)[:\s#-]+([A-Z0-9]{5,10})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    return None


def extract_id_expiry(text: str) -> str | None:
    """Extract ID expiry date."""
    # EXP or EXPIRES followed by date
    match = re.search(
        r"(?:EXP(?:IRES)?|VALID\s+UNTIL)[:\s]+"
        r"((?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2})",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def extract_claim_amount(text: str) -> str | None:
    """Extract a billed amount when it follows a claim or total-charge label."""
    match = re.search(
        r"\b(?:TOTAL\s+CHARGES?|TOTAL\s+AMOUNT|CLAIM\s+AMOUNT|"
        r"AMOUNT\s+BILLED|BILLED\s+AMOUNT)\s*[:$]?\s*\$?"
        r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def extract_service_date(text: str) -> str | None:
    """Extract service date (DOS)."""
    # DOS: or SERVICE DATE: followed by date
    match = re.search(
        r"(?:DOS|SERVICE\s+DATE)[:\s]+"
        r"((?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2})",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def extract_provider_npi(text: str) -> str | None:
    """Extract provider NPI (10 digits, may have NPI- prefix)."""
    # NPI can be prefixed with "NPI-" or "NPI "
    match = re.search(r"(?:NPI[:\s-]?\s*)?(\d{10})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


# Letter + two digits + any decimal tail, so malformed codes are caught by the validator, not truncated.
_ICD10_CANDIDATE = re.compile(r"\b[A-Z][0-9]{2}(?:\.[0-9A-Za-z]++)?\b")


def extract_icd10_codes(text: str, dropped: Counter[str] | None = None) -> list[str]:
    """Extract ICD-10 codes that match the spec pattern; invalid candidates are dropped."""
    codes: list[str] = []
    for candidate in _ICD10_CANDIDATE.findall(text):
        if is_valid("icd10", candidate):
            codes.append(candidate)
        elif dropped is not None:
            dropped["icd10"] += 1
    return list(dict.fromkeys(codes))


_CPT_LABEL = re.compile(
    r"\b(?:CPT|HCPCS|PROCEDURE(?:\s+CODES?)?|PROC(?:EDURE)?\s+CODES?)\b", re.IGNORECASE
)
_CPT_CANDIDATE = re.compile(r"\b\d{4}[0-9A-Z]\b")
_CPT_WINDOW = 250
_ID_LABELED_NUMBER = re.compile(
    r"\b(?:MEMBER\s*ID|PATIENT\s*ID|CLAIM\s*(?:NO|NUMBER|#)|ID)\b\.?\s*[:#]?\s*(\S+)",
    re.IGNORECASE,
)
_FIVE_DIGITS = re.compile(r"(?<!\d)\d{5}(?!\d)")
_STATES = [
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
]
_ZIP = re.compile(r"\b(?:" + "|".join(_STATES) + r")\s+(\d{5})(?:-\d{4})?\b")


def _non_cpt_numbers(text: str) -> set[str]:
    """Five-digit numbers that follow ID-style labels or a state abbreviation (ZIP)."""
    numbers = set(_ZIP.findall(text))
    for token in _ID_LABELED_NUMBER.findall(text):
        numbers.update(_FIVE_DIGITS.findall(token))
    return numbers


def extract_cpt_codes(text: str, dropped: Counter[str] | None = None) -> list[str]:
    """Extract CPT codes only near a CPT/procedure label, excluding ID and ZIP numbers."""
    excluded = _non_cpt_numbers(text)
    codes: list[str] = []
    for label in _CPT_LABEL.finditer(text):
        window = text[label.end() : label.end() + _CPT_WINDOW]
        for candidate in _CPT_CANDIDATE.findall(window):
            if candidate in excluded or not is_valid("cpt", candidate):
                if dropped is not None:
                    dropped["cpt"] += 1
            else:
                codes.append(candidate)
    return list(dict.fromkeys(codes))


_DATE_TOKEN = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")
_LABELED_DATES = {
    "rx_date": re.compile(r"\b(?:RX|PRESCRIPTION)\s+DATE\b\s*[:#-]?\s*", re.IGNORECASE),
    "admit_date": re.compile(
        r"\b(?:ADMIT|ADMISSION)\s+DATE\b\s*[:#-]?\s*|\bDATE\s+OF\s+ADMISSION\b\s*[:#-]?\s*",
        re.IGNORECASE,
    ),
    "discharge_date": re.compile(
        r"\b(?:DISCHARGE|DISCHARGED)\s+DATE\b\s*[:#-]?\s*|"
        r"\bDATE\s+OF\s+DISCHARGE\b\s*[:#-]?\s*",
        re.IGNORECASE,
    ),
}


def _labeled_date(text: str, key: str) -> str | None:
    for label in _LABELED_DATES[key].finditer(text):
        value = _DATE_TOKEN.search(text, label.end(), label.end() + 40)
        if value:
            return value.group()
    return None


def extract_admit_date(text: str) -> str | None:
    return _labeled_date(text, "admit_date")


def extract_discharge_date(text: str) -> str | None:
    return _labeled_date(text, "discharge_date")


def extract_rx_date(text: str) -> str | None:
    return _labeled_date(text, "rx_date")


def extract_member_name(text: str) -> str | None:
    """Extract a member or patient name, not a provider name."""
    match = re.search(
        r"(?<!PROVIDER )\b(?:MEMBER\s+|PATIENT\s+)?NAME[:\s]+"
        r"([A-Z][A-Za-z'-]+(?:\s+(?!PROVIDER\b)[A-Z][A-Za-z'-]+){0,3}(?:\s+\d+\b)?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().upper()
    return None


def extract_provider_name(text: str) -> str | None:
    """Extract a provider name when it follows an explicit provider label."""
    match = re.search(
        r"\bPROVIDER(?:\s+NAME)?[:\s]+"
        r"([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().upper()
    return None


def extract_diagnosis(text: str) -> str | None:
    """Extract diagnosis text."""
    # Look for DIAGNOSIS: followed by text
    match = re.search(r"DIAGNOSIS[:\s]+([^\n]*)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_medication(text: str) -> str | None:
    """Extract medication name."""
    # Look for MEDICATION/DRUG/RX followed by name
    match = re.search(r"(?:MEDICATION|DRUG|RX|PRESCRIPTION)[:\s]+([^\n]*)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_fields_from_text(
    text: str, dropped: Counter[str] | None = None
) -> dict[str, ExtractedField]:
    """
    Extract fields from raw OCR text using regex patterns.

    Values that fail their validator are dropped (and counted in `dropped`), so the field
    is reported as missing instead of carrying a wrong value.
    Confidence is set to 0.80 for regex matches (conservative estimate).
    """
    extractors = {
        "member_id": extract_member_id,
        "member_name": extract_member_name,
        "dob": extract_dob,
        "policy_number": extract_policy_number,
        "id_number": extract_id_number,
        "id_expiry": extract_id_expiry,
        "claim_amount": extract_claim_amount,
        "service_date": extract_service_date,
        "admit_date": extract_admit_date,
        "discharge_date": extract_discharge_date,
        "rx_date": extract_rx_date,
        "provider_npi": extract_provider_npi,
        "provider_name": extract_provider_name,
        "diagnosis": extract_diagnosis,
        "medication": extract_medication,
    }

    results: dict[str, ExtractedField] = {}

    for field_key, extractor in extractors.items():
        value = extractor(text)
        if not value:
            continue
        if is_valid(field_key, value):
            results[field_key] = ExtractedField(key=field_key, value=value, confidence=0.80)
        elif dropped is not None:
            dropped[field_key] += 1

    admit, discharge = results.get("admit_date"), results.get("discharge_date")
    if admit and discharge:
        admit_on, discharge_on = parse_date(admit.value), parse_date(discharge.value)
        if admit_on and discharge_on and discharge_on < admit_on:
            del results["admit_date"], results["discharge_date"]
            if dropped is not None:
                dropped.update({"admit_date": 1, "discharge_date": 1, "date_order": 1})

    icd10_codes = extract_icd10_codes(text, dropped)
    if icd10_codes:
        results["icd10"] = ExtractedField(key="icd10", value=icd10_codes[0], confidence=0.80)

    cpt_codes = extract_cpt_codes(text, dropped)
    if cpt_codes:
        results["cpt"] = ExtractedField(key="cpt", value=cpt_codes[0], confidence=0.80)

    return results
