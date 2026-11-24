"""Build deterministic stub fixtures for visual KYC tamper checks."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agents.kyc.agent import KYC_MESSAGE
from packages.core.llm.fixtures import FixtureStore, fixture_key

TAMPERED_DOCUMENT = "id_PT_57795"
EXPIRED_MEDICARE_DOCUMENT = "id_PT_20745"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read dataset file: {path}") from error


def generate_fixtures(dataset_dir: Path, output_dir: Path) -> list[Path]:
    metadata = load_json(dataset_dir / "metadata.json")
    truth = load_json(dataset_dir / "truth.json")
    id_documents = {
        entry["doc_id"]: entry for entry in metadata if entry.get("category") == "id_documents"
    }
    clean_ids = sorted(
        doc_id
        for doc_id in id_documents
        if not truth[doc_id].get("tampered")
        and not truth[doc_id].get("expired")
        and truth[doc_id].get("document_type") != "medicare_card"
    )
    if not clean_ids:
        raise ValueError("Dataset contains no clean non-Medicare ID document")
    selected = [clean_ids[0], TAMPERED_DOCUMENT, EXPIRED_MEDICARE_DOCUMENT]
    store = FixtureStore(output_dir)
    written: list[Path] = []
    for doc_id in selected:
        entry = id_documents.get(doc_id)
        if entry is None:
            raise ValueError(f"Dataset has no ID document {doc_id}")
        relative = Path(entry["file_path"].replace("\\", "/"))
        image_path = dataset_dir / relative
        try:
            image = image_path.read_bytes()
        except OSError as error:
            raise ValueError(f"Dataset image is missing: {image_path}") from error
        key = fixture_key("kyc_tamper", [dict(KYC_MESSAGE)], [image])
        is_medicare = truth[doc_id].get("document_type") == "medicare_card"
        response = {
            "tampering_detected": bool(truth[doc_id].get("tampered")),
            "confidence": 0.96,
            "evidence": "Visible alteration in the document image"
            if truth[doc_id].get("tampered")
            else None,
            "affected_page": 1,
            "affected_bbox": None,
            "expired_banner_visible": bool(truth[doc_id].get("expired")) if is_medicare else None,
        }
        store.write(key, response)
        written.append(store.path_for(key))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate offline KYC tamper fixtures.")
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/synthetic/dataset"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/fixtures/llm"))
    args = parser.parse_args()
    paths = generate_fixtures(args.dataset_dir, args.output_dir)
    print(f"Wrote {len(paths)} KYC fixtures to {args.output_dir}.")


if __name__ == "__main__":
    main()
