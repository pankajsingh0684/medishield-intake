"""Deterministic history and claim-signal fraud scoring."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from packages.agents.fraud.weights import DETECTOR_WEIGHTS
from packages.core.db.repositories import ClaimHistoryRepo
from packages.core.enums import AgentStatus, ClaimHistoryKind, DocType, RiskLevel
from packages.core.models import Anomaly, ClaimsResult, FraudResult, KycResult, OcrPayload

FRAUD_AGENT = "fraud"
FRAUD_VERSION = "1.0.0"
REFERENCE_PRICES_PATH = Path(__file__).resolve().parents[3] / "data" / "cpt_reference_prices.json"
PLAUSIBILITY_PATH = Path(__file__).resolve().parents[3] / "data" / "icd_cpt_plausibility.json"


def noisy_or_score(anomalies: list[Anomaly]) -> float:
    remaining = 1.0
    for anomaly in anomalies:
        remaining *= 1.0 - anomaly.weight
    return round(min(1.0, max(0.0, 1.0 - remaining)), 4)


def risk_level_for_score(score: float, escalate_at: float, high_at: float) -> RiskLevel:
    if score < escalate_at:
        return RiskLevel.LOW
    if score < high_at:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path.name}")
    return value


class FraudAgent:
    def __init__(
        self,
        history_repo: ClaimHistoryRepo,
        settings,
        *,
        weights: dict[str, float] | None = None,
        reference_prices: dict[str, float | None] | None = None,
        plausibility: dict[str, Any] | None = None,
    ) -> None:
        self.history_repo = history_repo
        self.settings = settings
        self.weights = dict(weights or DETECTOR_WEIGHTS)
        self.reference_prices = reference_prices or _read_mapping(REFERENCE_PRICES_PATH)
        self.plausibility = plausibility or _read_mapping(PLAUSIBILITY_PATH)

    def score(
        self,
        doc_type: DocType,
        member_id: str | None,
        claims: ClaimsResult,
        kyc: KycResult,
        ocr: OcrPayload,
        received_at: datetime,
        *,
        prior_processed_claims: list[dict[str, Any]] | None = None,
        current_case_id: str | None = None,
    ) -> FraudResult:
        started = datetime.now(UTC)
        warnings: list[str] = []
        try:
            history = self.history_repo.for_member(member_id) if member_id else []
            global_history = self.history_repo.all_prior_claims(
                since=received_at.date() - timedelta(days=365)
            )
            earlier_cases = (
                self.history_repo.earlier_processed_claims(
                    member_id, received_at, exclude_case_id=current_case_id
                )
                if member_id
                else []
            )
        except Exception as error:  # noqa: BLE001
            return self._result(
                [],
                confidence=0.5,
                started=started,
                warnings=[f"HISTORY_QUERY_FAILED:{type(error).__name__}"],
            )

        fields = claims.extracted_fields
        anomalies: list[Anomaly] = []

        def add(kind: str, evidence: str, strength: float = 1.0) -> None:
            weight = self.weights[kind] * min(1.0, max(0.0, strength))
            anomalies.append(Anomaly(type=kind, evidence=evidence, weight=round(weight, 4)))

        if doc_type == DocType.ID_DOCUMENT:
            self._identity_and_tamper(kyc, ocr, add, warnings)
        elif doc_type == DocType.CLAIM_FORM:
            self._duplicate(fields, member_id, history, earlier_cases, prior_processed_claims, add)
            self._frequency(fields, member_id, history, global_history, received_at, add)
            self._provider_outlier(fields, history, global_history, add)
            self._amount_outlier(fields, add)
            self._code_mismatch(fields.cpt_codes, fields.icd10_codes, add)
            self._identity_and_tamper(kyc, ocr, add, warnings)
            if fields.claim_amount is not None:
                amount = float(fields.claim_amount)
                if self.settings.near_threshold_low <= amount < self.settings.near_threshold_high:
                    add("NEAR_THRESHOLD", f"claim_amount={amount:.2f}")
        elif doc_type == DocType.PRESCRIPTION:
            self._identity_and_tamper(kyc, ocr, add, warnings)
            self._date_conflict(fields, history, add)
        elif doc_type == DocType.DISCHARGE_SUMMARY:
            self._identity_and_tamper(kyc, ocr, add, warnings)
            self._readmission(fields, history, add)
        else:
            warnings.append(f"NO_FRAUD_DETECTORS_FOR_{doc_type.value}")

        score = noisy_or_score(anomalies)
        return self._result(
            anomalies,
            confidence=0.9
            if sum(row.kind == ClaimHistoryKind.PRIOR_CLAIM for row in history) >= 3
            else 0.7,
            started=started,
            score=score,
            warnings=warnings,
        )

    def _duplicate(
        self,
        fields,
        member_id: str | None,
        history,
        earlier_cases,
        prior_processed_claims,
        add,
    ) -> None:
        codes = set(fields.cpt_codes)
        for row in history:
            if row.kind != ClaimHistoryKind.PRIOR_CLAIM:
                continue
            if fields.claim_number and row.claim_number == fields.claim_number:
                add(
                    "DUPLICATE_CLAIM",
                    f"claim_number={fields.claim_number}; claim_id={row.claim_id}",
                )
                return
            if (
                fields.provider_npi
                and fields.service_date
                and row.provider_npi == fields.provider_npi
                and row.service_date == fields.service_date
                and set(row.cpt_codes or []) == codes
            ):
                add("DUPLICATE_CLAIM", f"claim_id={row.claim_id}; member={member_id}")
                return
        for earlier in earlier_cases:
            if isinstance(earlier, dict):
                continue
            case, run = earlier
            output = run.output
            extracted = output.get("extracted_fields", {}) if isinstance(output, dict) else {}
            if fields.claim_number and extracted.get("claim_number") == fields.claim_number:
                add(
                    "DUPLICATE_CLAIM",
                    f"earlier_case={case.case_id}; claim_number={fields.claim_number}",
                )
                return
            if (
                fields.provider_npi
                and fields.service_date
                and extracted.get("provider_npi") == fields.provider_npi
                and str(extracted.get("service_date", ""))[:10] == fields.service_date.isoformat()
                and set(extracted.get("cpt_codes") or []) == codes
            ):
                add("DUPLICATE_CLAIM", f"earlier_case={case.case_id}; member={member_id}")
                return
        for earlier in prior_processed_claims or []:
            if (
                isinstance(earlier, dict)
                and earlier.get("member_id") == member_id
                and fields.claim_number
                and earlier.get("claim_number") == fields.claim_number
            ):
                add(
                    "DUPLICATE_CLAIM",
                    f"earlier_case={earlier.get('case_id')}; claim_number={fields.claim_number}",
                )
                return

    def _frequency(self, fields, member_id, history, global_history, received_at, add) -> None:
        reference_day = received_at.date()
        lower = reference_day - timedelta(days=365)
        member_rows = [
            row
            for row in history
            if row.kind == ClaimHistoryKind.PRIOR_CLAIM
            and row.service_date is not None
            and lower <= row.service_date <= reference_day
        ]
        baseline_rows = [
            row
            for row in global_history
            if row.member_id != member_id
            and row.service_date is not None
            and lower <= row.service_date <= reference_day
        ]
        if not member_rows and not baseline_rows:
            return
        month_indexes = [
            reference_day.year * 12 + reference_day.month - 1 - offset for offset in range(12)
        ]
        month_keys = [(index // 12, index % 12 + 1) for index in reversed(month_indexes)]
        if len(member_rows) >= 3:
            member_month_counts = Counter(
                (row.service_date.year, row.service_date.month) for row in member_rows
            )
            counts = [member_month_counts.get(month, 0) for month in month_keys]
        else:
            per_member_counts: dict[str, Counter[tuple[int, int]]] = {}
            for row in baseline_rows:
                if row.member_id is None:
                    continue
                per_member_counts.setdefault(row.member_id, Counter())[
                    (row.service_date.year, row.service_date.month)
                ] += 1
            counts = [
                count
                for monthly in per_member_counts.values()
                for count in (monthly.get(month, 0) for month in month_keys)
            ]
        if not counts:
            return
        baseline_mean = mean(counts)
        baseline_sd = pstdev(counts) if len(counts) > 1 else 0.0
        recent_start = reference_day - timedelta(days=30)
        current_date = fields.service_date or reference_day
        recent_count = sum(
            1
            for row in member_rows
            if row.service_date is not None and recent_start < row.service_date <= reference_day
        )
        if recent_start < current_date <= reference_day:
            recent_count += 1
        spike_threshold = max(1.0, baseline_mean + 3 * baseline_sd)
        if recent_count > spike_threshold:
            add(
                "FREQUENCY_SPIKE",
                f"recent_30d_claims={recent_count}; monthly_mean={baseline_mean:.2f}; monthly_sd={baseline_sd:.2f}; threshold={spike_threshold:.2f}",
            )

    def _provider_outlier(self, fields, history, global_history, add) -> None:
        if not fields.provider_npi or fields.claim_amount is None or not fields.cpt_codes:
            return
        provider_rows = [
            row
            for row in global_history
            if row.kind == ClaimHistoryKind.PRIOR_CLAIM
            and row.provider_npi == fields.provider_npi
            and row.amount is not None
            and set(row.cpt_codes or []) & set(fields.cpt_codes)
        ]
        population = [
            row
            for row in global_history
            if row.provider_npi
            and row.amount is not None
            and set(row.cpt_codes or []) & set(fields.cpt_codes)
        ]
        if len(provider_rows) < 3 or len(population) < 3:
            return
        provider_avg = mean(float(row.amount) for row in provider_rows)
        values = [float(row.amount) for row in population]
        center = median(values)
        deviations = [abs(value - center) for value in values]
        mad = median(deviations)
        if mad > 0 and provider_avg > center + 3 * mad:
            add(
                "PROVIDER_BILLING_OUTLIER",
                f"provider_average={provider_avg:.2f}; median={center:.2f}; mad={mad:.2f}",
            )

    def _amount_outlier(self, fields, add) -> None:
        if fields.claim_amount is None:
            return
        prices = [
            float(self.reference_prices[code])
            for code in fields.cpt_codes
            if code in self.reference_prices and self.reference_prices[code] is not None
        ]
        if not prices:
            return
        current = float(fields.claim_amount)
        reference = sum(prices)
        room_board_allowance = float(self.reference_prices.get("__room_board_max__", 0.0) or 0.0)
        if current > (reference + room_board_allowance) * 3:
            add("AMOUNT_OUTLIER", f"claim_amount={current:.2f}; reference_total={reference:.2f}")

    def _code_mismatch(self, cpt_codes: list[str], icd_codes: list[str], add) -> None:
        obstetric = set(self.plausibility.get("obstetric_cpt_codes", []))
        obstetric_prefixes = tuple(self.plausibility.get("obstetric_icd10_prefixes", []))
        for cpt in cpt_codes:
            if cpt in obstetric and not any(
                code.upper().startswith(obstetric_prefixes) for code in icd_codes
            ):
                add(
                    "CODE_MISMATCH",
                    f"obstetric_cpt={cpt}; diagnoses={','.join(icd_codes) or 'none'}",
                )
                return

    def _identity_and_tamper(self, kyc, ocr, add, warnings: list[str]) -> None:
        if kyc.status == AgentStatus.ERROR:
            warnings.append("KYC_ERROR_IDENTITY_AND_TAMPER_SKIPPED")
            return
        mismatch = next((flag for flag in kyc.flags if flag.code == "NAME_MISMATCH"), None)
        if mismatch is not None:
            add("IDENTITY_MISMATCH", mismatch.evidence)
        tamper = next(
            (flag for flag in kyc.flags if flag.code in {"TAMPER_SUSPECTED", "ELA_ANOMALY"}),
            None,
        )
        if tamper is not None or any("tamper" in field.key.casefold() for field in ocr.fields):
            add("TAMPER_SIGNAL", tamper.evidence if tamper else "OCR/tamper signal present")

    def _date_conflict(self, fields, history, add) -> None:
        rx_value = fields.extra.get("rx_date")
        rx_date = rx_value if isinstance(rx_value, date) else None
        if isinstance(rx_value, str):
            try:
                rx_date = date.fromisoformat(rx_value[:10])
            except ValueError:
                rx_date = None
        if rx_date is None:
            return
        episodes = [
            row
            for row in history
            if row.kind == ClaimHistoryKind.EPISODE_CLAIM and row.service_date is not None
        ]
        for row in episodes:
            delta = (rx_date - row.service_date).days
            if delta > self.settings.date_conflict_days:
                add(
                    "DATE_CONFLICT",
                    f"rx_date={rx_date}; episode_service_date={row.service_date}; days={delta}",
                )
                return

    def _readmission(self, fields, history, add) -> None:
        if fields.admit_date is None:
            return
        stays = [
            row
            for row in history
            if row.kind == ClaimHistoryKind.PRIOR_STAY and row.discharge_date is not None
        ]
        for row in stays:
            delta = (fields.admit_date - row.discharge_date).days
            if 0 < delta <= self.settings.readmission_days:
                add(
                    "READMISSION_30D",
                    f"admit_date={fields.admit_date}; prior_discharge={row.discharge_date}; days={delta}",
                )
                return

    def _result(
        self,
        anomalies: list[Anomaly],
        *,
        confidence: float,
        started: datetime,
        score: float | None = None,
        warnings: list[str] | None = None,
    ) -> FraudResult:
        rounded_score = noisy_or_score(anomalies) if score is None else round(score, 4)
        return FraudResult(
            agent=FRAUD_AGENT,
            agent_version=FRAUD_VERSION,
            status=AgentStatus.OK,
            confidence=confidence,
            model=None,
            started_at=started,
            finished_at=datetime.now(UTC),
            error=None,
            fraud_score=rounded_score,
            anomalies=anomalies,
            risk_level=risk_level_for_score(
                rounded_score,
                self.settings.threshold_fraud_escalate,
                self.settings.threshold_fraud_high,
            ),
            warnings=warnings or [],
        )
