"""Build deterministic stub fixtures for claims extraction by document type."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agents.claims.validators import REQUIRED_FIELDS
from packages.core.enums import DocType
from packages.core.llm.fixtures import FixtureStore, fixture_key

CLAIMS_MESSAGE = (
    "Document type: {doc_type}. Extract only these fields: {fields}. Return compact JSON only."
)
CATEGORIES = {
    "claim_forms": DocType.CLAIM_FORM,
    "discharge_summaries": DocType.DISCHARGE_SUMMARY,
    "prescriptions": DocType.PRESCRIPTION,
}
FIXTURE_VALUES: dict[DocType, dict[str, Any]] = {
    DocType.CLAIM_FORM: {
        "claim_amount": "1250.00",
        "service_date": "2025-01-15",
        "icd10_codes": ["I25.10"],
        "cpt_codes": ["99213"],
        "provider_npi": "1234567893",
        "signature_present": True,
    },
    DocType.DISCHARGE_SUMMARY: {
        "admit_date": "2025-01-10",
        "discharge_date": "2025-01-15",
        "icd10_codes": ["I25.10"],
        "signature_present": True,
    },
    DocType.PRESCRIPTION: {
        "drug_name": "Example Medication",
        "sig": "Take one tablet daily",
        "refills": 1,
        "prescriber_npi": "1234567893",
        "dea_number": "AB1234563",
        "rx_date": "2025-01-15",
    },
}


def load_metadata(dataset_dir: Path) -> list[dict[str, Any]]:
    try:
        entries = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read dataset metadata from {dataset_dir}") from error
    if not isinstance(entries, list):
        raise TypeError("Dataset metadata must contain a list of entries")
    return entries


def generate_fixtures(dataset_dir: Path, output_dir: Path) -> list[Path]:
    entries = load_metadata(dataset_dir)
    store = FixtureStore(output_dir)
    written: list[Path] = []
    for category, doc_type in CATEGORIES.items():
        matches = sorted(
            (entry for entry in entries if entry.get("category") == category),
            key=lambda entry: entry["file_path"],
        )
        if not matches:
            raise ValueError(f"Dataset contains no documents for category {category}")
        relative = Path(matches[0]["file_path"].replace("\\", "/"))
        try:
            image = (dataset_dir / relative).read_bytes()
        except OSError as error:
            raise ValueError(f"Dataset image is missing: {dataset_dir / relative}") from error
        needed = REQUIRED_FIELDS[doc_type]
        message = {
            "role": "user",
            "content": CLAIMS_MESSAGE.format(
                doc_type=doc_type.value,
                fields=", ".join(needed),
            ),
        }
        key = fixture_key("claims_extract", [message], [image])
        values = FIXTURE_VALUES[doc_type]
        response = {
            "fields": {
                field: {
                    "value": values[field],
                    "confidence": 0.95,
                    "page": 1,
                    "bbox": {
                        "text": str(values[field]),
                        "page": 1,
                        "x": 0.1,
                        "y": 0.1,
                        "w": 0.2,
                        "h": 0.03,
                    },
                }
                for field in needed
            }
        }
        store.write(key, response)
        written.append(store.path_for(key))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate offline claims extraction fixtures.")
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/synthetic/dataset"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/fixtures/llm"))
    args = parser.parse_args()
    paths = generate_fixtures(args.dataset_dir, args.output_dir)
    print(f"Wrote {len(paths)} claims fixtures to {args.output_dir}.")


if __name__ == "__main__":
    main()
