"""Oracle-check Phase B extras through the deterministic fraud and decision engines."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.agents.fraud.agent import FraudAgent
from packages.core.config import Settings
from packages.core.enums import AgentStatus, DecisionKind, DocType
from packages.core.models import (
    ClaimFields,
    ClaimsResult,
    Classification,
    KycFlag,
    KycResult,
    OcrPayload,
    PolicyResult,
)
from packages.decision.engine import decide
from packages.decision.thresholds import Thresholds

LABELS = ROOT / "data" / "synthetic" / "labels.jsonl"
CLUSTERS = ROOT / "data" / "synthetic" / "dataset" / "clusters.json"


class Row:
    def __init__(self, kind, **values):
        self.kind = kind
        for key, value in values.items():
            setattr(self, key, value)


class FakeHistory:
    def __init__(self, rows):
        self.rows = rows

    def for_member(self, member_id):
        return [row for row in self.rows if getattr(row, "member_id", None) == member_id]

    def all_prior_claims(self, since):
        return [row for row in self.rows if getattr(row, "member_id", None)]

    def earlier_processed_claims(self, member_id, received_at):
        return []


def main() -> None:
    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line]
    extras = [
        label
        for label in labels
        if "extra" in label["doc_id"] or label["cluster_id"] and str(label["cluster_id"]).isdigit()
    ]
    extras = [
        label
        for label in extras
        if str(label.get("cluster_id", "")).startswith("C_")
        and 31 <= int(str(label["cluster_id"])[2:]) <= 46
    ]
    clusters = {row["cluster_id"]: row for row in json.loads(CLUSTERS.read_text(encoding="utf-8"))}
    settings = Settings()
    cfg = Thresholds.from_settings(settings)
    mismatches = []
    print("scenario\tcluster\tdoc\texpected\tengine\tstatus")

    processed_by_member: dict[str, list[dict]] = {}
    for label in extras:
        cid = label["cluster_id"]
        cluster = clusters[cid]
        now = datetime.combine(date.fromisoformat(label["reference_date"]), time.min, tzinfo=UTC)
        fields = label["fields"]
        claim_fields = ClaimFields(
            claim_amount=Decimal(str(fields["claim_amount"]))
            if fields["claim_amount"] is not None
            else None,
            icd10_codes=fields["icd10_codes"] or [],
            cpt_codes=fields["cpt_codes"] or [],
            provider_npi=fields["provider_npi"],
            service_date=now.date(),
            claim_number=cluster.get("claim_number"),
            admit_date=now.date() if label["doc_type"] == "DISCHARGE_SUMMARY" else None,
            discharge_date=(now + __import__("datetime").timedelta(days=3)).date()
            if label["doc_type"] == "DISCHARGE_SUMMARY"
            else None,
            extra={"rx_date": fields["rx_date"]} if fields["rx_date"] else {},
        )
        missing = fields["missing_field_type"] is not None
        claims = ClaimsResult(
            agent="claims",
            agent_version="oracle",
            status=AgentStatus.OK,
            confidence=0.9,
            started_at=now,
            finished_at=now,
            extracted_fields=claim_fields,
            schema_valid=not missing,
            validation_errors=["missing field"] if missing else [],
        )
        kyc_flags = []
        if label["fraud_reason"] == "name_mismatch":
            kyc_flags.append(
                KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="oracle truth")
            )
        kyc = KycResult(
            agent="kyc",
            agent_version="oracle",
            status=AgentStatus.OK,
            confidence=0.9,
            started_at=now,
            finished_at=now,
            kyc_passed=True,
            flags=kyc_flags,
            member_ref=label["patient_id"],
        )
        ocr = OcrPayload(
            agent="ocr",
            agent_version="oracle",
            status=AgentStatus.OK,
            confidence=0.9,
            started_at=now,
            finished_at=now,
            fields=[],
            raw_text="",
            bounding_boxes=[],
            pages=1,
            used_text_layer=True,
        )

        rows = []
        if cluster["fraud_reason"] == "date_conflict":
            rows.append(
                Row(
                    __import__(
                        "packages.core.enums", fromlist=["ClaimHistoryKind"]
                    ).ClaimHistoryKind.EPISODE_CLAIM,
                    member_id=label["patient_id"],
                    service_date=now.date(),
                    claim_id="oracle",
                    provider_npi=claim_fields.provider_npi,
                    cpt_codes=claim_fields.cpt_codes,
                    amount=claim_fields.claim_amount,
                )
            )
        if cluster["fraud_reason"] == "readmission_30d":
            rows.append(
                Row(
                    __import__(
                        "packages.core.enums", fromlist=["ClaimHistoryKind"]
                    ).ClaimHistoryKind.PRIOR_STAY,
                    member_id=label["patient_id"],
                    discharge_date=(now - __import__("datetime").timedelta(days=12)).date(),
                    claim_id="oracle",
                    provider_npi=claim_fields.provider_npi,
                    cpt_codes=claim_fields.cpt_codes,
                    amount=claim_fields.claim_amount,
                )
            )
        fraud_agent = FraudAgent(FakeHistory(rows), settings)
        fraud = fraud_agent.score(
            DocType(label["doc_type"]),
            label["patient_id"],
            claims,
            kyc,
            ocr,
            now,
            prior_processed_claims=processed_by_member.get(label["patient_id"], []),
        )

        if label["doc_type"] == "CLAIM_FORM":
            processed_by_member.setdefault(label["patient_id"], []).append(
                {
                    "member_id": label["patient_id"],
                    "claim_number": cluster["claim_number"],
                    "case_id": "oracle" + cid,
                }
            )

        covered = label["coverage_expected"]
        policy = None
        if DocType(label["doc_type"]) in {DocType.CLAIM_FORM, DocType.POLICY_AMENDMENT}:
            policy = PolicyResult(
                agent="policy",
                agent_version="oracle",
                status=AgentStatus.OK,
                confidence=0.95,
                started_at=now,
                finished_at=now,
                covered=covered,
                coverage_percentage=100 if covered else 0,
                policy_clause=None,
            )

        state = {
            "classification": Classification(
                agent="classification",
                agent_version="oracle",
                status=AgentStatus.OK,
                confidence=0.95,
                started_at=now,
                finished_at=now,
                doc_type=DocType(label["doc_type"]),
            ),
            "ocr": ocr,
            "kyc": kyc,
            "claims": claims,
            "policy": policy,
            "fraud": fraud,
        }
        engine_decision, _, _ = decide(state, cfg)

        expected = DecisionKind(label["decision_expected"])
        status = "PASS" if engine_decision == expected else "MISMATCH"
        scenario = label["scenario"] or cluster["fraud_reason"] or "valid_clean"
        print(
            f"{scenario}\t{cid}\t{label['doc_id']}\t{expected.value}\t{engine_decision.value}\t{status}"
        )
        if status == "MISMATCH":
            mismatches.append((cid, label["doc_id"], expected.value, engine_decision.value))

    print(f"MISMATCHES={len(mismatches)}")
    for mismatch in mismatches:
        print("|".join(mismatch))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
