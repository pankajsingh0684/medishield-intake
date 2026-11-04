#!/usr/bin/env python
"""Measure OCR extraction against the frozen synthetic dataset without using an LLM."""

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import pytesseract

from packages.agents.ocr import agent as ocr_module
from packages.agents.ocr.agent import (
    KEY_FIELDS,
    LOW_CONFIDENCE_THRESHOLD,
    OCR_VERSION,
    OCRAgent,
)
from packages.agents.ocr.cache import OcrCache
from packages.agents.ocr.field_extractors import (
    extract_cpt_codes,
    extract_icd10_codes,
    extract_provider_npi,
)
from packages.agents.ocr.tesseract_wrapper import configure_tesseract
from packages.core.config import Settings
from packages.core.enums import DocType
from packages.core.models import OcrField

CATEGORY_LABELS = {
    "claim_forms": "claim form",
    "id_documents": "ID",
    "discharge_summaries": "discharge summary",
    "prescriptions": "prescription",
    "policy_amendments": "amendment",
    "unknown": "unknown",
}
TRUTH_FIELDS_BY_CATEGORY = {
    "claim_forms": (
        "claim_amount",
        "cpt_codes",
        "icd10_codes",
        "provider_npi",
        "service_date",
    ),
    "id_documents": ("printed_name", "printed_expiry_date"),
    "discharge_summaries": (
        "cpt_codes",
        "icd10_codes",
        "admit_date",
        "discharge_date",
    ),
    "prescriptions": ("rx_date",),
    "policy_amendments": (),
    "unknown": (),
}
FIELD_KEYS = {
    "claim_amount": "claim_amount",
    "service_date": "service_date",
    "printed_name": "member_name",
    "printed_expiry_date": "id_expiry",
    "admit_date": "admit_date",
    "discharge_date": "discharge_date",
    "rx_date": "rx_date",
}
CATEGORY_DOC_TYPES = {
    "claim_forms": DocType.CLAIM_FORM,
    "id_documents": DocType.ID_DOCUMENT,
    "discharge_summaries": DocType.DISCHARGE_SUMMARY,
    "prescriptions": DocType.PRESCRIPTION,
    "policy_amendments": DocType.POLICY_AMENDMENT,
    "unknown": DocType.UNKNOWN,
}
SPLIT_PATH = REPOSITORY_ROOT / "data" / "synthetic" / "split.json"
CHANGED_FIELDS = (
    "claim_amount",
    "cpt_codes",
    "icd10_codes",
    "service_date",
    "printed_expiry_date",
    "admit_date",
    "discharge_date",
    "rx_date",
)
DROP_LABELS = {
    "cpt": "cpt_codes",
    "icd10": "icd10_codes",
    "claim_amount": "claim_amount",
    "service_date": "service_date",
    "id_expiry": "printed_expiry_date",
    "dob": "dob",
    "provider_npi": "provider_npi",
    "admit_date": "admit_date",
    "discharge_date": "discharge_date",
    "rx_date": "rx_date",
    "date_order": "discharge before admit (pairs)",
}
DATE_VALUE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")


class _ForbiddenGateway:
    """Sentinel gateway: any accidental fallback call fails instead of reaching a model."""

    def complete_json(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("LLM fallback is disabled in the OCR baseline report")


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    match = DATE_VALUE.search(text)
    if match and match.group() != text:
        return _normalize_date(match.group())
    return text


def _normalize_amount(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return f"{Decimal(text):.2f}"
    except InvalidOperation:
        return text


def _best_fields(payload_fields: Sequence[OcrField]) -> dict[str, OcrField]:
    best: dict[str, OcrField] = {}
    for field in payload_fields:
        if field.key not in best or field.confidence > best[field.key].confidence:
            best[field.key] = field
    return best


def _truth_value(truth: Mapping[str, Any], key: str) -> Any:
    return truth.get(key)


def _prediction(
    truth_key: str,
    truth: Mapping[str, Any],
    fields: Mapping[str, str],
    raw_text: str,
) -> Any:
    if truth_key == "cpt_codes":
        return _unique(extract_cpt_codes(raw_text))
    if truth_key == "icd10_codes":
        return _unique(extract_icd10_codes(raw_text))
    if truth_key == "provider_npi":
        value = fields.get("provider_npi") or extract_provider_npi(raw_text)
        return re.sub(r"^NPI\s*[-:]\s*", "", value.strip(), flags=re.IGNORECASE) if value else None
    mapped_key = FIELD_KEYS.get(truth_key)
    if mapped_key is not None:
        return fields.get(mapped_key)
    if truth_key == "service_date":
        return fields.get("service_date")
    return truth.get(truth_key)


def _normalize_pair(key: str, expected: Any, actual: Any) -> tuple[Any, Any]:
    if key in {"claim_amount"}:
        return _normalize_amount(expected), _normalize_amount(actual)
    if key in {"service_date", "printed_expiry_date", "rx_date", "admit_date", "discharge_date"}:
        return _normalize_date(expected), _normalize_date(actual)
    if key == "provider_npi":

        def strip_prefix(value: Any) -> str | None:
            if value is None:
                return None
            return re.sub(r"^NPI\s*[-:]\s*", "", str(value).strip(), flags=re.IGNORECASE)

        return strip_prefix(expected), strip_prefix(actual)
    if key in {"cpt_codes", "icd10_codes"}:
        return _unique(expected or []), _unique(actual or [])
    if expected is None or actual is None:
        return expected, actual
    return str(expected).strip().upper(), str(actual).strip().upper()


def _format_value(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text.replace("|", "\\|").replace("\n", " ")


def _run_document(
    agent: OCRAgent,
    content: bytes,
    mime_type: str,
    doc_type: DocType | None = None,
    cache: OcrCache | None = None,
    dropped: Counter[str] | None = None,
) -> dict[str, Any]:
    """Run text-layer then Tesseract only; capture word confidence without invoking fallback."""
    text_payload = agent._try_text_layer(content) if mime_type == "application/pdf" else None
    if text_payload is not None:
        return {
            "payload": text_payload,
            "raw_text": text_payload.raw_text,
            "fields": _best_fields(text_payload.fields),
            "confidence": text_payload.confidence,
            "used_text_layer": True,
            "fallback": False,
            "status": "OK",
        }

    pages = cache.get(content) if cache is not None else None
    if pages is None:
        pages = agent._ocr_pages(content, mime_type)
        if cache is not None:
            cache.put(content, pages)
    word_confidences = [word.confidence for word in pages[0]]
    agent._tesseract_results = None
    payload = agent._try_tesseract(content, mime_type, doc_type, pages=pages, dropped=dropped)

    mean_confidence = sum(word_confidences) / len(word_confidences) if word_confidences else 0.0
    if payload is not None:
        fields = _best_fields(payload.fields)
        raw_text = payload.raw_text
        status = "OK"
    else:
        stored = agent._tesseract_results
        stored_fields, _, words = stored if stored is not None else ({}, 0.0, [])
        raw_text = " ".join(word.text for word in words)
        fields = {
            key: OcrField(
                key=key,
                value=field.value,
                confidence=field.confidence,
                page=page_num,
            )
            for key, (field, page_num) in stored_fields.items()
        }
        status = "NO TEXT" if not words else "LOW CONFIDENCE"

    required_fields = ocr_module.DOC_TYPE_KEY_FIELDS.get(doc_type, KEY_FIELDS)
    trigger = mean_confidence < LOW_CONFIDENCE_THRESHOLD or not required_fields.issubset(fields)
    return {
        "payload": payload,
        "raw_text": raw_text,
        "fields": fields,
        "confidence": mean_confidence,
        "used_text_layer": False,
        "fallback": trigger,
        "status": status,
    }


def _stratified_dev_sample(
    metadata: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, str],
    size: int,
    seed: int,
) -> list[Mapping[str, Any]]:
    """Fixed per-category sample drawn only from dev documents."""
    by_category: dict[str, list[Mapping[str, Any]]] = {}
    for row in sorted(metadata, key=lambda item: item["doc_id"]):
        if assignments.get(row["doc_id"]) == "dev":
            by_category.setdefault(row["category"], []).append(row)
    total = sum(len(rows) for rows in by_category.values())
    size = min(size, total)
    quotas = {name: size * len(rows) / total for name, rows in by_category.items()}
    counts = {name: int(quota) for name, quota in quotas.items()}
    by_remainder = sorted(quotas, key=lambda name: (-(quotas[name] - counts[name]), name))
    for name in by_remainder[: size - sum(counts.values())]:
        counts[name] += 1
    rng = random.Random(seed)
    picked: set[str] = set()
    for name in sorted(by_category):
        rows = list(by_category[name])
        rng.shuffle(rows)
        picked.update(row["doc_id"] for row in rows[: counts[name]])
    assert all(assignments[doc_id] == "dev" for doc_id in picked)
    return [row for row in metadata if row["doc_id"] in picked]


def _field_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    metrics: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = metrics.setdefault(
            row["field"], {"exact": 0, "wrong": 0, "missing": 0, "applicable": 0}
        )
        entry["applicable"] += 1
        entry["exact" if row["exact"] else "missing" if row["missing"] else "wrong"] += 1
    return metrics


def _dropped_lines(dropped: Mapping[str, int]) -> list[str]:
    lines = [
        "",
        "## Dropped Values",
        "",
        (
            "Extracted values that failed their validator (or a code exclusion rule) and "
            "were dropped instead of reported. A dropped value cannot win the fallback merge."
        ),
        "",
        "| Field | Dropped |",
        "|---|---:|",
    ]
    lines.extend(f"| `{label}` | {dropped.get(key, 0)} |" for key, label in DROP_LABELS.items())
    return lines


def _before_after_lines(
    before: Mapping[str, Mapping[str, int]], after: Mapping[str, Mapping[str, int]]
) -> list[str]:
    empty = {"exact": 0, "wrong": 0, "missing": 0, "applicable": 0}
    lines = [
        "",
        "## Before and After (changed fields only)",
        "",
        "Wrong = a non-empty value that differs from truth; missing = nothing extracted.",
        "",
        "| Field | Exact | Wrong | Missing | Applicable |",
        "|---|---:|---:|---:|---:|",
    ]
    total_before = total_after = 0
    for field in CHANGED_FIELDS:
        if field not in after:
            continue
        old, new = before.get(field, empty), after[field]
        total_before += old["wrong"]
        total_after += new["wrong"]
        lines.append(
            f"| `{field}` | {old['exact']} -> {new['exact']} | {old['wrong']} -> {new['wrong']} "
            f"| {old['missing']} -> {new['missing']} | {new['applicable']} |"
        )
    lines.append(f"| **total wrong** | | {total_before} -> {total_after} | | |")
    return lines


def _build_report(
    dataset_dir: Path,
    *,
    sample: int | None = None,
    cache_dir: Path | None = None,
    metrics_path: Path | None = None,
    before_path: Path | None = None,
) -> str:
    metadata = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    truth_by_id = json.loads((dataset_dir / "truth.json").read_text(encoding="utf-8"))
    if sample is not None:
        split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
        metadata = _stratified_dev_sample(metadata, split["documents"], sample, split["seed"])
    settings = Settings()
    configure_tesseract(settings.tesseract_cmd)
    tesseract_version = _tesseract_version()
    if tesseract_version is None:
        return _build_unavailable_report(metadata)

    agent = OCRAgent(_ForbiddenGateway(), settings)
    cache = OcrCache(cache_dir, OCR_VERSION) if cache_dir is not None else None
    dropped: Counter[str] = Counter()
    document_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    total_started = time.perf_counter()

    for metadata_row in metadata:
        doc_id = metadata_row["doc_id"]
        category = metadata_row["category"]
        truth = truth_by_id.get(doc_id, {})
        source_path = dataset_dir / Path(metadata_row["file_path"].replace("\\", "/"))
        started = time.perf_counter()
        try:
            result = _run_document(
                agent,
                source_path.read_bytes(),
                "image/png",
                CATEGORY_DOC_TYPES.get(category),
                cache,
                dropped,
            )
            fields = result["fields"]
            field_values = {key: value.value for key, value in fields.items()}
            raw_text = result["raw_text"]
            status = result["status"]
            confidence = float(result["confidence"])
            fallback = bool(result["fallback"])
            tier = "text layer" if result["used_text_layer"] else "Tesseract"
        except (OSError, ValueError, RuntimeError) as error:
            fields = {}
            field_values = {}
            raw_text = ""
            status = f"ERROR: {type(error).__name__}"
            confidence = 0.0
            fallback = True
            tier = "Tesseract"

        elapsed = time.perf_counter() - started
        document_rows.append(
            {
                "doc_id": doc_id,
                "category": category,
                "tier": tier,
                "status": status,
                "confidence": confidence,
                "fallback": fallback,
                "seconds": elapsed,
            }
        )

        for truth_key in TRUTH_FIELDS_BY_CATEGORY.get(category, ()):
            if truth_key not in truth:
                continue
            expected = _truth_value(truth, truth_key)
            predicted = _prediction(truth_key, truth, field_values, raw_text)
            expected_normalized, predicted_normalized = _normalize_pair(
                truth_key, expected, predicted
            )
            comparison_rows.append(
                {
                    "doc_id": doc_id,
                    "category": category,
                    "field": truth_key,
                    "expected": expected_normalized,
                    "actual": predicted_normalized,
                    "exact": expected_normalized == predicted_normalized,
                    "missing": predicted_normalized is None or predicted_normalized == [],
                }
            )

    total_seconds = time.perf_counter() - total_started
    category_order = tuple(CATEGORY_LABELS)
    title = "# OCR 9b Sample (dev split only)" if sample is not None else "# OCR Baseline"
    report_lines = [
        title,
        "",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"Tesseract: {tesseract_version} | OCR code version: {OCR_VERSION}",
        "",
        (
            "This report runs PDF text-layer extraction and OpenCV/Tesseract only. "
            "The vision fallback is disabled and guarded by a gateway that raises if called. "
            "The synthetic dataset is read-only."
        ),
        "",
        f"Documents: {len(document_rows)} | Total processing time: {total_seconds:.2f} s",
        "",
        "## Category Summary",
        "",
        "| Category | Documents | Mean OCR confidence | Would trigger fallback |",
        "|---|---:|---:|---:|",
    ]

    for category in category_order:
        rows = [row for row in document_rows if row["category"] == category]
        count = len(rows)
        mean_confidence = sum(row["confidence"] for row in rows) / count if count else 0.0
        fallback_count = sum(row["fallback"] for row in rows)
        trigger_share = fallback_count / count if count else 0.0
        report_lines.append(
            f"| {CATEGORY_LABELS[category]} | {count} | {mean_confidence:.3f} | "
            f"{fallback_count}/{count} ({trigger_share:.1%}) |"
        )

    report_lines.extend(
        [
            "",
            (
                "Mean confidence is the text-layer payload confidence for Tier 1 and the "
                "word-weighted Tesseract confidence for Tier 2. Fallback share applies the "
                "current OCR trigger: mean confidence below 0.70 or no extracted key field."
            ),
            "",
            "## Exact-Match Rates",
            "",
            (
                "Rates use only documents in that category whose truth record contains the field. "
                "Null truth values are compared as expected absence. Code lists are compared "
                "as ordered, de-duplicated uppercase lists; dates and amounts are normalized "
                "before exact comparison."
            ),
            "",
            "| Category | Truth field | Exact | Wrong | Missing | Applicable | Rate |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )

    for category in category_order:
        for truth_key in TRUTH_FIELDS_BY_CATEGORY[category]:
            rows = [
                row
                for row in comparison_rows
                if row["category"] == category and row["field"] == truth_key
            ]
            exact_count = sum(row["exact"] for row in rows)
            wrong_count = sum(not row["exact"] and not row["missing"] for row in rows)
            missing_count = sum(not row["exact"] and row["missing"] for row in rows)
            count = len(rows)
            rate = exact_count / count if count else 0.0
            report_lines.append(
                f"| {CATEGORY_LABELS[category]} | `{truth_key}` | {exact_count} | "
                f"{wrong_count} | {missing_count} | {count} | {rate:.1%} |"
            )

    after_metrics = _field_metrics(comparison_rows)
    report_lines.extend(_dropped_lines(dropped))
    if before_path is not None:
        before = json.loads(before_path.read_text(encoding="utf-8"))["fields"]
        report_lines.extend(_before_after_lines(before, after_metrics))
    if metrics_path is not None:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(
                {
                    "fields": after_metrics,
                    "dropped": dict(dropped),
                    "doc_ids": [row["doc_id"] for row in document_rows],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    document_errors: dict[str, list[dict[str, Any]]] = {}
    for row in comparison_rows:
        if not row["exact"]:
            document_errors.setdefault(row["doc_id"], []).append(row)
    compared_per_doc: dict[str, int] = {}
    for row in comparison_rows:
        compared_per_doc[row["doc_id"]] = compared_per_doc.get(row["doc_id"], 0) + 1
    document_by_id = {row["doc_id"]: row for row in document_rows}
    ranked_ids = sorted(
        compared_per_doc,
        key=lambda doc_id: (
            -len(document_errors.get(doc_id, [])),
            -len(document_errors.get(doc_id, [])) / compared_per_doc[doc_id],
            document_by_id[doc_id]["confidence"],
            doc_id,
        ),
    )[:10]

    report_lines.extend(
        [
            "",
            "## Ten Worst Documents",
            "",
            (
                "Ranked by number of wrong/missing truth fields, then error rate, then lower "
                "OCR confidence. A missing prediction is shown as `null`."
            ),
            "",
            "| doc_id | Category | Confidence | Wrong or missing fields |",
            "|---|---|---:|---|",
        ]
    )
    for doc_id in ranked_ids:
        document = document_by_id[doc_id]
        mismatches = document_errors.get(doc_id, [])
        details = (
            "<br>".join(
                f"`{row['field']}` expected {_format_value(row['expected'])}, "
                f"got {_format_value(row['actual'])}"
                for row in mismatches
            )
            or "No mismatch among applicable truth fields"
        )
        report_lines.append(
            f"| `{doc_id}` | {CATEGORY_LABELS[document['category']]} | "
            f"{document['confidence']:.3f} | {details} |"
        )

    report_lines.extend(
        [
            "",
            "## Runtime Per Document",
            "",
            "| doc_id | Category | Tier | Status | Seconds |",
            "|---|---|---|---|---:|",
        ]
    )
    for row in document_rows:
        report_lines.append(
            f"| `{row['doc_id']}` | {CATEGORY_LABELS[row['category']]} | {row['tier']} | "
            f"{row['status']} | {row['seconds']:.3f} |"
        )
    report_lines.extend(["", f"Total runtime: **{total_seconds:.3f} seconds**", ""])
    return "\n".join(report_lines)


def _tesseract_version() -> str | None:
    try:
        return str(pytesseract.get_tesseract_version()).splitlines()[0]
    except (OSError, pytesseract.TesseractNotFoundError):
        return None


def _build_unavailable_report(metadata: Sequence[Mapping[str, Any]]) -> str:
    counts = {
        category: sum(row.get("category") == category for row in metadata)
        for category in CATEGORY_LABELS
    }
    lines = [
        "# OCR Baseline (Blocked)",
        "",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        (
            "**Tier 2 measurements were not run:** the Tesseract executable is not installed or "
            "not available on PATH. `pytesseract` alone is only a Python wrapper. This script "
            "does not install software, access the network, or call an LLM."
        ),
        "",
        f"Dataset documents: {len(metadata)} | Tesseract processing time: 0.000 s",
        "",
        "## Category Summary",
        "",
        "| Category | Documents | Mean OCR confidence | Would trigger fallback |",
        "|---|---:|---:|---:|",
    ]
    for category, label in CATEGORY_LABELS.items():
        lines.append(f"| {label} | {counts[category]} | not measured | not measured |")
    lines.extend(
        [
            "",
            "## Exact-Match Rates",
            "",
            (
                "Exact-match rates are not measured because no image text was extracted. "
                "Reporting zero here would incorrectly describe a missing runtime as OCR output."
            ),
            "",
            "| Category | Truth field | Exact | Applicable | Rate |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for category, label in CATEGORY_LABELS.items():
        for truth_key in TRUTH_FIELDS_BY_CATEGORY[category]:
            lines.append(f"| {label} | `{truth_key}` | N/A | N/A | N/A |")
    unmeasured_docs = [
        row["doc_id"] for row in metadata if TRUTH_FIELDS_BY_CATEGORY.get(row.get("category"), ())
    ][:10]
    lines.extend(
        [
            "",
            "## Ten Worst Documents",
            "",
            (
                "Cannot rank documents until Tier 2 runs. These are the first ten documents "
                "with applicable OCR truth fields, listed only to make the blocked sample explicit:"
            ),
            "",
        ]
    )
    lines.extend(f"- `{doc_id}`: not measured" for doc_id in unmeasured_docs)
    lines.extend(
        [
            "",
            "## Runtime Per Document",
            "",
            "| doc_id | Category | Status | Seconds |",
            "|---|---|---|---:|",
        ]
    )
    lines.extend(
        f"| `{row['doc_id']}` | {CATEGORY_LABELS.get(row.get('category'), row.get('category'))} "
        "| skipped: Tesseract unavailable | N/A |"
        for row in metadata
    )
    lines.extend(["", "Total OCR runtime: **not run (Tesseract unavailable)**", ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "synthetic" / "dataset",
        help="Dataset directory containing metadata.json, truth.json, and documents",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "reports" / "ocr_baseline.md",
        help="Markdown report output path",
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="Fixed per-category sample of N dev-split documents (holdout is never read)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=REPOSITORY_ROOT / "reports" / ".ocr_cache",
        help="On-disk cache of raw OCR output keyed by image hash and OCR code version",
    )
    parser.add_argument("--metrics-json", type=Path, help="Write per-field metrics as JSON")
    parser.add_argument("--before-json", type=Path, help="Metrics JSON for a before/after table")
    args = parser.parse_args(argv)
    report = _build_report(
        args.dataset,
        sample=args.sample,
        cache_dir=args.cache_dir,
        metrics_path=args.metrics_json,
        before_path=args.before_json,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8", newline="\n")
    print(f"OCR baseline written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
