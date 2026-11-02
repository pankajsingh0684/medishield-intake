"""Build deterministic stub fixtures for the six classifier document types."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agents.classifier.agent import CLASSIFIER_MESSAGE
from packages.core.enums import DocType
from packages.core.llm.fixtures import FixtureStore, fixture_key

CATEGORY_TYPES = {
    "claim_forms": DocType.CLAIM_FORM,
    "id_documents": DocType.ID_DOCUMENT,
    "discharge_summaries": DocType.DISCHARGE_SUMMARY,
    "prescriptions": DocType.PRESCRIPTION,
    "policy_amendments": DocType.POLICY_AMENDMENT,
    "unknown": DocType.UNKNOWN,
}


def load_metadata(dataset_dir: Path) -> list[dict[str, Any]]:
    metadata_path = dataset_dir / "metadata.json"
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read dataset metadata: {metadata_path}") from error
    if not isinstance(data, list):
        raise TypeError("Dataset metadata must contain a list of entries")
    return data


def select_fixture_entries(entries: list[dict[str, Any]]) -> list[tuple[Path, DocType, float]]:
    categorized: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORY_TYPES}
    for entry in entries:
        category = entry.get("category")
        if category in categorized:
            categorized[category].append(entry)

    selections: list[tuple[Path, DocType, float]] = []
    for category, doc_type in CATEGORY_TYPES.items():
        category_entries = sorted(categorized[category], key=lambda entry: entry["file_path"])
        if not category_entries:
            raise ValueError(f"Dataset contains no documents for category {category}")
        selections.append((Path(category_entries[0]["file_path"]), doc_type, 0.99))

    claim_entries = sorted(categorized["claim_forms"], key=lambda entry: entry["file_path"])
    if len(claim_entries) < 2:
        raise ValueError("Dataset needs two distinct claim forms for the low-confidence fixture")
    selections.append((Path(claim_entries[1]["file_path"]), DocType.CLAIM_FORM, 0.4))
    return selections


def generate_fixtures(dataset_dir: Path, output_dir: Path) -> list[Path]:
    entries = load_metadata(dataset_dir)
    store = FixtureStore(output_dir)
    written: list[Path] = []
    seen_keys: set[str] = set()
    for relative_path, doc_type, confidence in select_fixture_entries(entries):
        normalized_path = (
            Path(*relative_path.parts)
            if "\\" not in str(relative_path)
            else Path(*str(relative_path).replace("\\", "/").split("/"))
        )
        image_path = dataset_dir / normalized_path
        try:
            image = image_path.read_bytes()
        except OSError as error:
            raise ValueError(f"Dataset image is missing: {image_path}") from error
        key = fixture_key("classifier", [dict(CLASSIFIER_MESSAGE)], [image])
        if key in seen_keys:
            raise ValueError("Selected classifier fixture inputs are not unique")
        seen_keys.add(key)
        path = store.path_for(key)
        store.write(
            key,
            {
                "doc_type": doc_type.value,
                "confidence": confidence,
                "routing_tags": [],
            },
        )
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate offline classifier fixtures.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/synthetic/dataset"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/fixtures/llm"))
    args = parser.parse_args()

    paths = generate_fixtures(args.dataset_dir, args.output_dir)
    print(f"Wrote {len(paths)} classifier fixtures to {args.output_dir}.")


if __name__ == "__main__":
    main()
