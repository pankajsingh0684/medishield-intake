import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "dataset"
EXPECTED_COUNTS = {
    "claim_forms": 31,
    "id_documents": 30,
    "discharge_summaries": 30,
    "prescriptions": 30,
    "policy_amendments": 30,
    "unknown": 4,
}


def load_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def as_date(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    return date.fromisoformat(str(value)[:10])


def as_amount(value):
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def main():
    metadata = load_json(DATASET_DIR / "metadata.json")
    truth = load_json(DATASET_DIR / "truth.json")
    clusters = load_json(DATASET_DIR / "clusters.json")

    mismatch_counts = Counter()
    examples = defaultdict(list)

    def report(kind, doc_id, detail):
        mismatch_counts[kind] += 1
        if len(examples[kind]) < 10:
            examples[kind].append((doc_id, detail))

    cluster_by_id = {}
    duplicate_cluster_ids = set()
    for cluster in clusters:
        cluster_id = cluster.get("cluster_id")
        if cluster_id in cluster_by_id:
            duplicate_cluster_ids.add(cluster_id)
        cluster_by_id[cluster_id] = cluster
    for cluster_id in sorted(duplicate_cluster_ids):
        report(
            "duplicate_cluster_id",
            cluster_id,
            "clusters.json contains this cluster_id more than once",
        )

    metadata_ids = [entry.get("doc_id") for entry in metadata]
    metadata_id_counts = Counter(metadata_ids)
    unknown_ids = [
        entry.get("doc_id")
        for entry in metadata
        if entry.get("category") == "unknown" or str(entry.get("doc_id", "")).startswith("unknown_")
    ]
    unknown_id_counts = Counter(unknown_ids)

    for doc_id, count in metadata_id_counts.items():
        if count > 1:
            report("duplicate_metadata_doc_id", doc_id, f"metadata.json contains {count} entries")
    for doc_id, count in unknown_id_counts.items():
        if count > 1:
            report(
                "duplicate_unknown_entry", doc_id, f"metadata.json contains {count} unknown entries"
            )

    category_counts = Counter(entry.get("category") for entry in metadata)
    for category, expected in EXPECTED_COUNTS.items():
        actual = category_counts.get(category, 0)
        if actual != expected:
            report(
                "category_count", f"<category:{category}>", f"expected {expected}, found {actual}"
            )

    for entry in metadata:
        doc_id = entry.get("doc_id")
        category = entry.get("category")
        is_unknown = category == "unknown" or str(doc_id).startswith("unknown_")
        relative_path = entry.get("file_path")
        if relative_path:
            stored_path = Path(relative_path)
            absolute_path = stored_path if stored_path.is_absolute() else DATASET_DIR / stored_path
            absolute_path = absolute_path.resolve()
            if not absolute_path.is_file():
                report("missing_file", doc_id, f"file does not exist: {absolute_path}")
        else:
            report("missing_file_path", doc_id, "metadata entry has no file_path")

        truth_entry = truth.get(doc_id)
        if truth_entry is None:
            report("missing_truth_doc_id", doc_id, "doc_id is absent from truth.json")
            continue

        metadata_cluster_id = entry.get("case_cluster_id")
        truth_cluster_id = truth_entry.get("cluster_id")
        if metadata_cluster_id != truth_cluster_id:
            report(
                "cluster_id_mismatch",
                doc_id,
                f"metadata={metadata_cluster_id!r}, truth={truth_cluster_id!r}",
            )

        for metadata_key, truth_key in (
            ("patient_id", "patient_id"),
            ("policy_number", "policy_number"),
        ):
            metadata_value = entry.get(metadata_key)
            truth_value = truth_entry.get(truth_key)
            if metadata_value != truth_value:
                report(
                    f"{metadata_key}_mismatch",
                    doc_id,
                    f"metadata={metadata_value!r}, truth={truth_value!r}",
                )

        cluster = cluster_by_id.get(truth_cluster_id)
        if is_unknown:
            if truth_cluster_id is not None:
                report(
                    "unknown_cluster_mismatch",
                    doc_id,
                    f"unknown document has cluster {truth_cluster_id!r}",
                )
            continue
        if cluster is None:
            report(
                "missing_cluster_id",
                doc_id,
                f"cluster_id {truth_cluster_id!r} is absent from clusters.json",
            )
            continue

        for truth_key, cluster_key in (("patient_id", "patient_id"), ("policy_number", "policy")):
            truth_value = truth_entry.get(truth_key)
            cluster_value = cluster.get(cluster_key)
            if truth_value != cluster_value:
                report(
                    f"{truth_key}_mismatch",
                    doc_id,
                    f"truth={truth_value!r}, cluster={cluster_value!r}",
                )

        treatment_date = as_date(cluster.get("treatment_date"))
        if "reference_date" not in truth_entry:
            report("reference_date_mismatch", doc_id, "truth is missing required reference_date")
        elif as_date(truth_entry.get("reference_date")) != treatment_date:
            report(
                "reference_date_mismatch",
                doc_id,
                f"truth={truth_entry.get('reference_date')!r}, cluster={cluster.get('treatment_date')!r}",
            )

        edge_flags = set(cluster.get("edge_flags", []))
        if category == "id_documents":
            expected_name = cluster.get("id_display_name", cluster.get("name"))
            if truth_entry.get("printed_name") != expected_name:
                report(
                    "id_name_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('printed_name')!r}, cluster={expected_name!r}",
                )
            expected_tampered = "tampered_id" in edge_flags
            expected_expired = "expired_id" in edge_flags
            if truth_entry.get("tampered") is not expected_tampered:
                report(
                    "tampered_flag_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('tampered')!r}, cluster edge flag={expected_tampered}",
                )
            if truth_entry.get("expired") is not expected_expired:
                report(
                    "expired_flag_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('expired')!r}, cluster edge flag={expected_expired}",
                )
            expiry = as_date(truth_entry.get("printed_expiry_date"))
            if (
                expiry is not None
                and treatment_date is not None
                and not expected_tampered
                and (expiry < treatment_date) != expected_expired
            ):
                report(
                    "id_expiry_mismatch",
                    doc_id,
                    f"printed expiry={expiry}, treatment date={treatment_date}, expired flag={expected_expired}",
                )

        if category == "claim_forms":
            expected_codes = [item[0] for item in cluster.get("cpt_list", [])]
            if cluster.get("fraud_reason") == "amount_under_10k":
                expected_codes.append("99999")
                expected_amount = Decimal("9875.00")
            else:
                expected_amount = sum(
                    (Decimal(str(item[2])) for item in cluster.get("cpt_list", [])), Decimal(0)
                )
                if entry.get("claim_form_type") == "UB04":
                    expected_amount += Decimal(3) * Decimal("1250.00")
            actual_amount = as_amount(truth_entry.get("claim_amount"))
            if actual_amount != expected_amount:
                report(
                    "amount_mismatch", doc_id, f"truth={actual_amount}, expected={expected_amount}"
                )
            if truth_entry.get("cpt_codes") != expected_codes:
                report(
                    "code_mismatch",
                    doc_id,
                    f"truth CPT={truth_entry.get('cpt_codes')!r}, expected CPT={expected_codes!r}",
                )

            missing_type = cluster.get("missing_field_type")
            actual_missing_type = truth_entry.get(
                "missing_field_type", truth_entry.get("missing_field")
            )
            if actual_missing_type != missing_type:
                report(
                    "missing_field_type_mismatch",
                    doc_id,
                    f"truth={actual_missing_type!r}, cluster={missing_type!r}",
                )

            expected_icd = None if missing_type == "diag_code" else cluster.get("icd_code")
            if truth_entry.get("icd10_code") != expected_icd:
                report(
                    "code_mismatch",
                    doc_id,
                    f"truth ICD={truth_entry.get('icd10_code')!r}, expected ICD={expected_icd!r}",
                )
            if missing_type == "diag_code":
                expected_icd_codes = []
            elif entry.get("claim_form_type", cluster.get("claim_type")) == "UB04":
                expected_icd_codes = [cluster.get("icd_code"), cluster.get("secondary_icd_code")]
            else:
                expected_icd_codes = [cluster.get("icd_code")]
            if truth_entry.get("icd10_codes") != expected_icd_codes:
                report(
                    "icd10_codes_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('icd10_codes')!r}, expected printed codes={expected_icd_codes!r}",
                )
            if missing_type == "diag_code":
                if (
                    truth_entry.get("icd10_codes") != []
                    or truth_entry.get("icd10_code") is not None
                ):
                    report(
                        "icd10_missing_field_mismatch",
                        doc_id,
                        "diag_code missing-field records require icd10_codes=[] and icd10_code=null",
                    )
            elif not truth_entry.get("icd10_codes") or truth_entry["icd10_codes"][
                0
            ] != truth_entry.get("icd10_code"):
                report(
                    "icd10_primary_mismatch",
                    doc_id,
                    "icd10_codes must be non-empty and start with icd10_code",
                )
            expected_npi = None if missing_type is not None else cluster.get("npi")
            if truth_entry.get("provider_npi") != expected_npi:
                report(
                    "npi_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('provider_npi')!r}, expected={expected_npi!r}",
                )
            if as_date(truth_entry.get("service_date")) != treatment_date:
                report(
                    "date_mismatch",
                    doc_id,
                    f"claim service_date={truth_entry.get('service_date')!r}, treatment_date={cluster.get('treatment_date')!r}",
                )

        elif category == "discharge_summaries":
            readmission = cluster.get("fraud_reason") == "readmission_30d"
            admit_date = as_date(truth_entry.get("admit_date"))
            discharge_date = as_date(truth_entry.get("discharge_date"))
            if not readmission and admit_date != treatment_date:
                report(
                    "date_mismatch",
                    doc_id,
                    f"admit_date={truth_entry.get('admit_date')!r}, expected treatment date={treatment_date}",
                )
            if readmission:
                prior_cluster_date = as_date(cluster.get("prior_discharge_date"))
                prior_truth_date = as_date(truth_entry.get("prior_discharge_date"))
                if prior_cluster_date != prior_truth_date:
                    report(
                        "readmission_prior_date_mismatch",
                        doc_id,
                        f"cluster prior_discharge_date={prior_cluster_date}, truth={prior_truth_date}",
                    )
                prior_gap = (
                    (admit_date - prior_cluster_date).days
                    if admit_date and prior_cluster_date
                    else None
                )
                if prior_gap is None or not 5 <= prior_gap <= 20:
                    report(
                        "readmission_prior_date_range_mismatch",
                        doc_id,
                        f"admit_date={admit_date}, prior_discharge_date={prior_cluster_date}, gap_days={prior_gap}; expected 5-20 days",
                    )
            if (
                admit_date is None
                or discharge_date is None
                or not 2 <= (discharge_date - admit_date).days <= 5
            ):
                report(
                    "date_mismatch",
                    doc_id,
                    f"admit_date={admit_date}, discharge_date={discharge_date}, expected stay of 2-5 days",
                )
            expected_codes = [item[0] for item in cluster.get("cpt_list", [])]
            if truth_entry.get("cpt_codes") != expected_codes or truth_entry.get(
                "icd10_code"
            ) != cluster.get("icd_code"):
                report(
                    "code_mismatch",
                    doc_id,
                    f"truth CPT/ICD={truth_entry.get('cpt_codes')!r}/{truth_entry.get('icd10_code')!r}, "
                    f"expected={expected_codes!r}/{cluster.get('icd_code')!r}",
                )
            expected_icd_codes = [cluster.get("icd_code"), cluster.get("secondary_icd_code")]
            if truth_entry.get("icd10_codes") != expected_icd_codes:
                report(
                    "icd10_codes_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('icd10_codes')!r}, expected printed codes={expected_icd_codes!r}",
                )
            if not truth_entry.get("icd10_codes") or truth_entry["icd10_codes"][
                0
            ] != truth_entry.get("icd10_code"):
                report(
                    "icd10_primary_mismatch",
                    doc_id,
                    "icd10_codes must be non-empty and start with icd10_code",
                )

        elif category == "prescriptions":
            expected_missing = cluster.get("rx_missing_field_type")
            if truth_entry.get("missing_field") != expected_missing:
                report(
                    "missing_field_type_mismatch",
                    doc_id,
                    f"truth={truth_entry.get('missing_field')!r}, cluster={expected_missing!r}",
                )
            expected_drugs = [item[0] for item in cluster.get("rx_list", [])]
            if truth_entry.get("drug_names") != expected_drugs:
                report(
                    "code_mismatch",
                    doc_id,
                    f"truth drug_names={truth_entry.get('drug_names')!r}, expected={expected_drugs!r}",
                )
            rx_date = as_date(truth_entry.get("rx_date"))
            if cluster.get("fraud_reason") == "date_conflict":
                claim_service_date = as_date(truth_entry.get("claim_service_date"))
                if claim_service_date != treatment_date:
                    report(
                        "date_mismatch",
                        doc_id,
                        f"claim_service_date={truth_entry.get('claim_service_date')!r}, expected={treatment_date}",
                    )
                date_conflict_gap = (
                    (rx_date - claim_service_date)
                    if rx_date is not None and claim_service_date is not None
                    else None
                )
                if date_conflict_gap is None or date_conflict_gap.days <= 30:
                    report(
                        "date_conflict_threshold_mismatch",
                        doc_id,
                        f"rx_date={rx_date}, claim_service_date={claim_service_date}, gap_days={date_conflict_gap.days if date_conflict_gap else None}; expected >30 days",
                    )
                if (
                    rx_date is None
                    or treatment_date is None
                    or not 46 <= (rx_date - treatment_date).days <= 60
                ):
                    report(
                        "date_mismatch",
                        doc_id,
                        f"date-conflict rx_date={rx_date}, treatment_date={treatment_date}",
                    )
            else:
                days_after = (rx_date - treatment_date).days if rx_date and treatment_date else None
                if days_after != cluster.get("los"):
                    report(
                        "date_mismatch",
                        doc_id,
                        f"rx_date={rx_date}, treatment_date={treatment_date}, expected offset={cluster.get('los')}",
                    )

    for doc_id in truth.keys() - set(metadata_ids):
        report(
            "truth_without_metadata",
            doc_id,
            "truth.json contains a doc_id absent from metadata.json",
        )

    print(f"Dataset: {DATASET_DIR}")
    print(
        f"Metadata documents: {len(metadata)}; truth entries: {len(truth)}; clusters: {len(clusters)}"
    )
    if not mismatch_counts:
        print("No mismatches found.")
        return

    print(f"Mismatch types: {len(mismatch_counts)}")
    for kind in sorted(mismatch_counts):
        print(
            f"\n{kind}: {mismatch_counts[kind]} mismatch(es); showing first {len(examples[kind])}"
        )
        for doc_id, detail in examples[kind]:
            print(f"  doc_id={doc_id}: {detail}")


if __name__ == "__main__":
    main()
