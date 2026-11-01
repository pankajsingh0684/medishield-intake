"""MediShield evaluation package."""

from datetime import date

DATASET_AS_OF_DATE = date(2025, 12, 31)


def reference_date_for_run(reference_date: date | None) -> date:
    return reference_date or DATASET_AS_OF_DATE
