"""Run the deterministic fraud agent on dev-split labels and write a comparison report."""

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from packages.agents.fraud.agent import FraudAgent
from packages.core.config import Settings
from packages.core.db.repositories import ClaimHistoryRepo
from packages.core.db.session import create_database_engine
from packages.core.enums import AgentStatus, DocType
from packages.core.models import ClaimFields, ClaimsResult, KycFlag, KycResult, OcrField, OcrPayload
from packages.eval.split import load_labels
from packages.graph.routing import ROUTING_TABLE
from scripts.seed import seed_database

ROOT = Path(__file__).resolve().parents[1]
CASE_NAMESPACE = "medishield:dataset:case:{}"
FRAUD_DETECTORS = (
    "DUPLICATE_CLAIM",
    "FREQUENCY_SPIKE",
    "PROVIDER_BILLING_OUTLIER",
    "AMOUNT_OUTLIER",
    "CODE_MISMATCH",
    "TAMPER_SIGNAL",
    "IDENTITY_MISMATCH",
    "NEAR_THRESHOLD",
    "DATE_CONFLICT",
    "READMISSION_30D",
)


def _build_inputs(label, cluster_by_patient):
    fields = label.fields
    cluster = cluster_by_patient.get(label.patient_id or "", {})
    claim_fields = ClaimFields(
        claim_amount=fields.claim_amount,
        icd10_codes=fields.icd10_codes or [],
        cpt_codes=fields.cpt_codes or [],
        provider_npi=fields.provider_npi,
        service_date=fields.service_date,
        claim_number=cluster.get("claim_number"),
        admit_date=fields.admit_date,
        discharge_date=fields.discharge_date,
        extra={"rx_date": fields.rx_date.isoformat()} if fields.rx_date else {},
    )
    now = datetime.combine(label.reference_date or datetime.now(UTC).date(), time.min, tzinfo=UTC)
    claims = ClaimsResult(
        agent="claims",
        agent_version="dev-check",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        extracted_fields=claim_fields,
        schema_valid=True,
        validation_errors=[],
    )
    flags = []
    if label.fraud_reason == "name_mismatch":
        flags.append(
            KycFlag(
                code="NAME_MISMATCH", severity="HIGH", evidence="generator name-mismatch scenario"
            )
        )
    if fields.tampered:
        flags.append(
            KycFlag(
                code="TAMPER_SUSPECTED", severity="MEDIUM", evidence="generator tamper scenario"
            )
        )
    kyc = KycResult(
        agent="kyc",
        agent_version="dev-check",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        kyc_passed=True,
        flags=flags,
        member_ref=label.patient_id,
    )
    ocr_fields = []
    if fields.tampered:
        ocr_fields.append(OcrField(key="tamper_signal", value="true", confidence=0.9, page=1))
    ocr = OcrPayload(
        agent="ocr",
        agent_version="dev-check",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        fields=ocr_fields,
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )
    return claims, kyc, ocr, now


def generate_report() -> str:
    labels = load_labels()
    split = json.loads((ROOT / "data/synthetic/split.json").read_text(encoding="utf-8"))
    clusters = json.loads(
        (ROOT / "data/synthetic/dataset/clusters.json").read_text(encoding="utf-8")
    )
    cluster_by_patient = {row["patient_id"]: row for row in clusters}
    dev_labels = [row for row in labels if split["documents"].get(row.doc_id) == "dev"]
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    detector_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"fired_labeled": 0, "fired_clean": 0}
    )
    results = []
    processed_claims: dict[str, list[dict[str, str]]] = defaultdict(list)
    try:
        with Session(engine) as session, session.begin():
            seed_database(session, settings.seed_test_user_password.get_secret_value())
        with Session(engine) as session:
            agent = FraudAgent(ClaimHistoryRepo(session), settings)
            for label in dev_labels:
                expected_fraud = label.fraud_expected == "FLAGGED"
                if not ROUTING_TABLE[label.doc_type].fraud:
                    continue
                claims, kyc, ocr, received_at = _build_inputs(label, cluster_by_patient)
                prior_processed = processed_claims[label.patient_id or ""]
                result = agent.score(
                    label.doc_type,
                    label.patient_id,
                    claims,
                    kyc,
                    ocr,
                    received_at,
                    prior_processed_claims=prior_processed,
                )
                fired = {anomaly.type for anomaly in result.anomalies}
                for detector in FRAUD_DETECTORS:
                    if detector in fired:
                        key = "fired_labeled" if expected_fraud else "fired_clean"
                        detector_totals[detector][key] += 1
                results.append((label, result, expected_fraud))
                if label.doc_type == DocType.CLAIM_FORM and label.patient_id:
                    processed_claims[label.patient_id].append(
                        {
                            "member_id": label.patient_id,
                            "claim_number": claims.extracted_fields.claim_number or "",
                            "case_id": str(
                                uuid5(NAMESPACE_URL, CASE_NAMESPACE.format(label.doc_id))
                            ),
                        }
                    )
    finally:
        engine.dispose()

    clean_claims = [
        (label, result)
        for label, result, expected_fraud in results
        if label.doc_type == DocType.CLAIM_FORM and label.scenario == "valid_clean"
    ]
    clean_over_threshold = [
        (label, result)
        for label, result in clean_claims
        if result.fraud_score >= settings.threshold_fraud_escalate
    ]
    labeled_fraud_count = sum(expected for _, _, expected in results)
    report = [
        "# Fraud Agent Dev Check",
        "",
        "Deterministic FraudAgent run on dev-split labels only. Scores are not tuned against this report.",
        f"Documents scored on fraud-routed types: {len(results)}; labeled fraud: {labeled_fraud_count}; clean `valid_clean` claims: {len(clean_claims)}.",
        "",
        "## Detector Results",
        "",
        "| Detector | Fired on labeled fraud | Fired on clean |",
        "|---|---:|---:|",
    ]
    for detector in FRAUD_DETECTORS:
        counts = detector_totals[detector]
        report.append(f"| {detector} | {counts['fired_labeled']} | {counts['fired_clean']} |")
    report.extend(["", "## Clean Dev Claim Threshold Check", ""])
    if clean_over_threshold:
        report.append(
            f"Failed: {len(clean_over_threshold)} clean dev claims scored at or above {settings.threshold_fraud_escalate:.2f}."
        )
        report.extend(
            f"- `{label.doc_id}`: score={result.fraud_score:.4f}, risk={result.risk_level.value}, detectors={','.join(item.type for item in result.anomalies) or 'none'}"
            for label, result in clean_over_threshold
        )
    else:
        report.append(
            f"Passed: all {len(clean_claims)} clean dev claims scored below {settings.threshold_fraud_escalate:.2f}."
        )
        nonfraud_edges = [
            (label, result)
            for label, result, expected_fraud in results
            if label.doc_type == DocType.CLAIM_FORM
            and not expected_fraud
            and label.scenario != "valid_clean"
            and result.fraud_score >= settings.threshold_fraud_escalate
        ]
        if nonfraud_edges:
            report.extend(
                [
                    "",
                    "Non-fraud edge scenarios are listed separately because their defined signals may fire by design:",
                ]
            )
            report.extend(
                f"- `{label.doc_id}` scenario={label.scenario} score={result.fraud_score:.4f} detectors={','.join(item.type for item in result.anomalies)}"
                for label, result in nonfraud_edges
            )
    report.extend(["", "## Per-Document Results", ""])
    for label, result, expected in results:
        report.append(
            f"- `{label.doc_id}` expected={'FLAGGED' if expected else 'LOW'} score={result.fraud_score:.4f} risk={result.risk_level.value} detectors={','.join(item.type for item in result.anomalies) or 'none'}"
        )
    return "\n".join(report) + "\n"


def main() -> None:
    report = generate_report()
    output = ROOT / "reports/fraud_dev_check.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    print(report)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
