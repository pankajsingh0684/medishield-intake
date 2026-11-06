"""Shared identity normalization and fuzzy comparison helpers."""

import re
from datetime import date, datetime

from rapidfuzz import fuzz

NAME_MISMATCH_MEDIUM_THRESHOLD = 0.85
NAME_MISMATCH_HIGH_PENALTY_THRESHOLD = 0.70
DOB_NAME_LOOKUP_THRESHOLD = 0.80


def normalize_name(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    if len(tokens) > 2:
        tokens = [token for token in tokens if len(token) > 1]
    return " ".join(sorted(tokens))


def name_similarity(left: str, right: str) -> float:
    normalized_left = normalize_name(left)
    normalized_right = normalize_name(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return fuzz.token_set_ratio(normalized_left, normalized_right) / 100


def parse_identity_date(value: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None
