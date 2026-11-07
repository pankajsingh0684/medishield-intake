import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packages.agents.fraud.agent import FraudAgent, noisy_or_score
from packages.agents.fraud.weights import DETECTOR_WEIGHTS
from packages.core.enums import AgentStatus, ClaimHistoryKind, DocType, RiskLevel
from packages.core.models import (
    Anomaly,
    ClaimFields,
    ClaimsResult,
    KycFlag,
    KycResult,
    OcrPayload,
)


class FakeHistoryRepo:
    def __init__(self, rows=None, earlier=None) -> None:
        self.rows = rows or []
        self.earlier = earlier or []

    def for_member(self, member_id, **kwargs):
        return [row for row in self.rows if row.member_id == member_id]

    def all_prior_claims(self, **kwargs):
        return list(self.rows)

    def earlier_processed_claims(self, member_id, before):
        return list(self.earlier)


def envelopes(
    *,
    claim_number: str,
    member_id: str = "MEM-1",
    claim_amount: Decimal = Decimal(100),
    service_date: date = date(2025, 1, 10),
    cpt_codes: list[str] | None = None,
    npi: str = "1234567890",
):
    now = datetime(2025, 1, 11, tzinfo=UTC)
    fields = ClaimFields(
        claim_amount=claim_amount,
        icd10_codes=["I10"],
        cpt_codes=cpt_codes or ["99213"],
        provider_npi=npi,
        service_date=service_date,
        claim_number=claim_number,
    )
    claims = ClaimsResult(
        agent="claims",
        agent_version="1",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        extracted_fields=fields,
        schema_valid=True,
        validation_errors=[],
    )
    kyc = KycResult(
        agent="kyc",
        agent_version="1",
        status=AgentStatus.OK,
        confidence=0.9,
        started_at=now,
        finished_at=now,
        kyc_passed=True,
        flags=[],
        member_ref=member_id,
    )
    ocr = OcrPayload(
        agent="ocr",
        agent_version="1",
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
    return claims, kyc, ocr, now


def settings(**overrides):
    values = {
        "near_threshold_low": 9500,
        "near_threshold_high": 10000,
        "date_conflict_days": 30,
        "readmission_days": 30,
        "threshold_fraud_escalate": 0.30,
        "threshold_fraud_high": 0.60,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_agent(repo=None, *, weights=None, config=None, prices=None, plausibility=None):
    return FraudAgent(
        repo or FakeHistoryRepo(),
        config or settings(),
        weights=weights,
        reference_prices=prices or {"99213": 100.0, "59400": 3500.0},
        plausibility=plausibility
        or {"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    )


def test_original_then_duplicate_and_reverse_order_duplicate_detection():
    agent = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        reference_prices={"99213": 100.0},
        plausibility={"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    )
    original_claim, kyc, ocr, received = envelopes(claim_number="CLM-1")
    original = agent.score(DocType.CLAIM_FORM, "MEM-1", original_claim, kyc, ocr, received)
    assert all(anomaly.type != "DUPLICATE_CLAIM" for anomaly in original.anomalies)

    prior = SimpleNamespace(
        claim_id="prior-1",
        kind=ClaimHistoryKind.PRIOR_CLAIM,
        member_id="MEM-1",
        claim_number="CLM-1",
        provider_npi="1234567890",
        service_date=date(2025, 1, 10),
        cpt_codes=["99213"],
        amount=Decimal(100),
    )
    duplicate_agent = FraudAgent(
        FakeHistoryRepo([prior]),
        settings(),
        reference_prices={"99213": 100.0},
        plausibility={"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    )
    duplicate = duplicate_agent.score(
        DocType.CLAIM_FORM, "MEM-1", original_claim, kyc, ocr, received
    )
    assert any(anomaly.type == "DUPLICATE_CLAIM" for anomaly in duplicate.anomalies)

    reverse = agent.score(
        DocType.CLAIM_FORM,
        "MEM-1",
        original_claim,
        kyc,
        ocr,
        received,
        prior_processed_claims=[
            {
                "member_id": "MEM-1",
                "claim_number": "CLM-1",
                "case_id": "earlier-case",
            }
        ],
    )
    assert any(anomaly.type == "DUPLICATE_CLAIM" for anomaly in reverse.anomalies)


@pytest.mark.parametrize(
    ("detector", "claim_values", "kyc_flags", "doc_type"),
    [
        ("NEAR_THRESHOLD", {"claim_amount": Decimal("9999.99")}, [], DocType.CLAIM_FORM),
        (
            "CODE_MISMATCH",
            {"cpt_codes": ["59400"], "icd10_codes": ["K35.80"]},
            [],
            DocType.CLAIM_FORM,
        ),
        (
            "IDENTITY_MISMATCH",
            {},
            [KycFlag(code="NAME_MISMATCH", severity="LOW", evidence="name differs")],
            DocType.CLAIM_FORM,
        ),
        (
            "TAMPER_SIGNAL",
            {},
            [KycFlag(code="TAMPER_SUSPECTED", severity="MEDIUM", evidence="tamper signal")],
            DocType.CLAIM_FORM,
        ),
    ],
)
def test_binary_detectors_fire_alone(detector, claim_values, kyc_flags, doc_type):
    claim, kyc, ocr, received = envelopes(claim_number=f"CASE-{detector}")
    claim = claim.model_copy(
        update={"extracted_fields": claim.extracted_fields.model_copy(update=claim_values)}
    )
    if kyc_flags:
        kyc = kyc.model_copy(update={"flags": kyc_flags})
    agent = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        reference_prices={"99213": 1000000, "59400": 3500},
        plausibility={"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    )

    result = agent.score(doc_type, "MEM-1", claim, kyc, ocr, received)

    assert [item.type for item in result.anomalies] == [detector]
    assert result.fraud_score == DETECTOR_WEIGHTS[detector]


def test_id_document_runs_only_identity_and_tamper_detectors():
    claim, kyc, ocr, received = envelopes(claim_number="ID-ONLY")
    kyc = kyc.model_copy(
        update={
            "flags": [
                KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="name mismatch"),
                KycFlag(code="TAMPER_SUSPECTED", severity="MEDIUM", evidence="tamper"),
            ]
        }
    )
    result = FraudAgent(FakeHistoryRepo(), settings()).score(
        DocType.ID_DOCUMENT, "MEM-1", claim, kyc, ocr, received
    )
    assert {item.type for item in result.anomalies} == {"IDENTITY_MISMATCH", "TAMPER_SIGNAL"}


def test_kyc_error_skips_identity_and_tamper_and_warns():
    claim, kyc, ocr, received = envelopes(claim_number="KYC-ERROR")
    kyc = kyc.model_copy(
        update={
            "status": AgentStatus.ERROR,
            "error": "fixture error",
            "flags": [KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="mismatch")],
        }
    )
    result = FraudAgent(FakeHistoryRepo(), settings()).score(
        DocType.ID_DOCUMENT, "MEM-1", claim, kyc, ocr, received
    )
    assert result.anomalies == []
    assert result.warnings == ["KYC_ERROR_IDENTITY_AND_TAMPER_SKIPPED"]


def test_obstetric_code_with_non_obstetric_diagnosis_is_mismatch():
    claim, kyc, ocr, received = envelopes(claim_number="OBSTETRIC")
    claim = claim.model_copy(
        update={
            "extracted_fields": claim.extracted_fields.model_copy(
                update={"cpt_codes": ["59400"], "icd10_codes": ["K35.80"]}
            )
        }
    )
    result = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        reference_prices={"59400": 3500},
        plausibility={"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    ).score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    assert [item.type for item in result.anomalies] == ["CODE_MISMATCH"]


def test_amount_outlier_skips_codes_without_reference_price():
    claim, kyc, ocr, received = envelopes(claim_number="NO-REFERENCE", claim_amount=Decimal(500000))
    claim = claim.model_copy(
        update={
            "extracted_fields": claim.extracted_fields.model_copy(update={"cpt_codes": ["99999"]})
        }
    )
    result = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        reference_prices={"99999": None},
        plausibility={"obstetric_cpt_codes": [], "obstetric_icd10_prefixes": ["O"]},
    ).score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    assert "AMOUNT_OUTLIER" not in {item.type for item in result.anomalies}


def test_generator_authored_tables_cover_dataset_cpt_codes():
    root = Path(__file__).resolve().parents[2]
    truth = json.loads((root / "data/synthetic/dataset/truth.json").read_text(encoding="utf-8"))
    prices = json.loads((root / "data/cpt_reference_prices.json").read_text(encoding="utf-8"))
    plausibility = json.loads((root / "data/icd_cpt_plausibility.json").read_text(encoding="utf-8"))
    codes = {str(code) for row in truth.values() for code in row.get("cpt_codes", [])}

    assert codes <= prices.keys()
    assert codes <= set(plausibility["cpt_codes"])
    assert prices["99999"] is None
    assert "59400" in plausibility["obstetric_cpt_codes"]


def test_clean_case_does_not_trigger_frequency_or_provider_billing():
    claim, kyc, ocr, received = envelopes(claim_number="CLEAN", claim_amount=Decimal(100))
    history = [
        SimpleNamespace(
            claim_id=f"history-{i}",
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            member_id=f"OTHER-{i}",
            claim_number=f"other-{i}",
            provider_npi=f"99999999{i:02d}",
            service_date=date(2025, 1, 1),
            cpt_codes=["99213"],
            amount=Decimal(100),
        )
        for i in range(10)
    ]
    result = FraudAgent(
        FakeHistoryRepo(history),
        settings(),
        reference_prices={"99213": 100},
        plausibility={"obstetric_cpt_codes": [], "obstetric_icd10_prefixes": ["O"]},
    ).score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    assert "FREQUENCY_SPIKE" not in {item.type for item in result.anomalies}
    assert "PROVIDER_BILLING_OUTLIER" not in {item.type for item in result.anomalies}


def test_frequency_spike_uses_30_day_count_and_received_at_anchor():
    claim, kyc, ocr, received = envelopes(claim_number="FREQUENCY")
    history = [
        SimpleNamespace(
            claim_id=f"prior-{index}",
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            member_id="MEM-1",
            claim_number=f"prior-{index}",
            provider_npi=f"90000000{index:02d}",
            service_date=date(2025, 1, 5 + index),
            cpt_codes=["93000"],
            amount=Decimal(100),
        )
        for index in range(3)
    ]
    # Prior history is old relative to the supplied received_at clock, regardless of wall time.
    received = datetime(2026, 1, 1, tzinfo=UTC)
    result = make_agent(FakeHistoryRepo(history)).score(
        DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received
    )
    assert "FREQUENCY_SPIKE" not in {item.type for item in result.anomalies}

    recent = [
        SimpleNamespace(
            claim_id=f"recent-{index}",
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            member_id="MEM-1",
            claim_number=f"recent-{index}",
            provider_npi=f"91000000{index:02d}",
            service_date=date(2025, 12, 10 + index),
            cpt_codes=["93000"],
            amount=Decimal(100),
        )
        for index in range(3)
    ]
    result = make_agent(FakeHistoryRepo(recent)).score(
        DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received
    )
    assert "FREQUENCY_SPIKE" in {item.type for item in result.anomalies}
    anomaly = next(item for item in result.anomalies if item.type == "FREQUENCY_SPIKE")
    assert anomaly.weight == DETECTOR_WEIGHTS["FREQUENCY_SPIKE"]


def test_provider_billing_outlier_uses_three_mad_rule():
    claim, kyc, ocr, received = envelopes(
        claim_number="PROVIDER", claim_amount=Decimal(300), npi="1111111111"
    )
    population = [
        SimpleNamespace(
            claim_id=f"pop-{index}",
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            member_id=f"P-{index}",
            claim_number=f"p-{index}",
            provider_npi="1111111111" if index < 3 else f"22222222{index:02d}",
            service_date=date(2025, 1, index + 1),
            cpt_codes=["99213"],
            amount=Decimal(str(value)),
        )
        for index, value in enumerate([300, 300, 300, 100, 110, 120, 130, 140])
    ]
    result = make_agent(FakeHistoryRepo(population)).score(
        DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received
    )
    anomaly = next(item for item in result.anomalies if item.type == "PROVIDER_BILLING_OUTLIER")
    assert anomaly.weight == DETECTOR_WEIGHTS["PROVIDER_BILLING_OUTLIER"]


def test_amount_outlier_uses_reference_prices_and_full_strength():
    claim, kyc, ocr, received = envelopes(
        claim_number="AMOUNT", claim_amount=Decimal(500), cpt_codes=["99213"]
    )
    result = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        reference_prices={"99213": 100},
        plausibility={"obstetric_cpt_codes": [], "obstetric_icd10_prefixes": ["O"]},
    ).score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    anomaly = next(item for item in result.anomalies if item.type == "AMOUNT_OUTLIER")
    assert anomaly.weight == DETECTOR_WEIGHTS["AMOUNT_OUTLIER"]


def test_date_conflict_and_readmission_use_configured_received_at_windows():
    claim, kyc, ocr, received = envelopes(claim_number="TIME-WINDOWS")
    claim = claim.model_copy(
        update={
            "extracted_fields": claim.extracted_fields.model_copy(
                update={
                    "extra": {"rx_date": "2025-03-15"},
                    "admit_date": date(2025, 3, 10),
                }
            )
        }
    )
    history = [
        SimpleNamespace(
            claim_id="episode",
            kind=ClaimHistoryKind.EPISODE_CLAIM,
            member_id="MEM-1",
            claim_number="episode",
            provider_npi=None,
            service_date=date(2025, 2, 1),
            cpt_codes=[],
            amount=None,
            discharge_date=None,
        ),
        SimpleNamespace(
            claim_id="stay",
            kind=ClaimHistoryKind.PRIOR_STAY,
            member_id="MEM-1",
            claim_number=None,
            provider_npi=None,
            service_date=None,
            cpt_codes=[],
            amount=None,
            discharge_date=date(2025, 3, 1),
        ),
    ]
    result = make_agent(
        FakeHistoryRepo(history), config=settings(date_conflict_days=30, readmission_days=30)
    ).score(DocType.PRESCRIPTION, "MEM-1", claim, kyc, ocr, received)
    assert "DATE_CONFLICT" in {item.type for item in result.anomalies}
    discharge_result = make_agent(
        FakeHistoryRepo(history), config=settings(date_conflict_days=30, readmission_days=30)
    ).score(DocType.DISCHARGE_SUMMARY, "MEM-1", claim, kyc, ocr, received)
    assert "READMISSION_30D" in {item.type for item in discharge_result.anomalies}


def test_combined_detectors_use_noisy_or():
    claim, kyc, ocr, received = envelopes(
        claim_number="COMBINED", claim_amount=Decimal("9999.99"), cpt_codes=["59400"]
    )
    claim = claim.model_copy(
        update={
            "extracted_fields": claim.extracted_fields.model_copy(
                update={"icd10_codes": ["K35.80"]}
            )
        }
    )
    kyc = kyc.model_copy(
        update={
            "flags": [KycFlag(code="NAME_MISMATCH", severity="HIGH", evidence="different name")]
        }
    )
    agent = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        weights={**DETECTOR_WEIGHTS, "AMOUNT_OUTLIER": 0},
        reference_prices={"59400": 100000},
        plausibility={"obstetric_cpt_codes": ["59400"], "obstetric_icd10_prefixes": ["O"]},
    )
    result = agent.score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    assert {item.type for item in result.anomalies} == {
        "CODE_MISMATCH",
        "IDENTITY_MISMATCH",
        "NEAR_THRESHOLD",
    }
    assert result.fraud_score == noisy_or_score(result.anomalies)


def test_history_confidence_sufficient_and_cold_start():
    claim, kyc, ocr, received = envelopes(claim_number="CONFIDENCE")
    agent = FraudAgent(FakeHistoryRepo(), settings())
    cold = agent.score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    history = [
        SimpleNamespace(
            claim_id=f"claim-{i}",
            kind=ClaimHistoryKind.PRIOR_CLAIM,
            member_id="MEM-1",
            claim_number=f"prior-{i}",
            provider_npi=f"99999999{i:02d}",
            service_date=date(2025, 1, i + 1),
            cpt_codes=["999"],
            amount=Decimal(100),
        )
        for i in range(3)
    ]
    established = FraudAgent(FakeHistoryRepo(history), settings()).score(
        DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received
    )
    assert cold.confidence == 0.7
    assert established.confidence == 0.9


def test_history_query_failure_returns_confidence_half():
    class BrokenRepo(FakeHistoryRepo):
        def for_member(self, member_id, **kwargs):
            raise RuntimeError("history unavailable")

    claim, kyc, ocr, received = envelopes(claim_number="FAILURE")
    result = FraudAgent(BrokenRepo(), settings()).score(
        DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received
    )
    assert result.confidence == 0.5
    assert result.fraud_score == 0
    assert result.warnings == ["HISTORY_QUERY_FAILED:RuntimeError"]


@pytest.mark.parametrize(
    ("injected_weight", "expected"),
    [
        (0.29994, RiskLevel.LOW),
        (0.29996, RiskLevel.MEDIUM),
        (0.30004, RiskLevel.MEDIUM),
        (0.59994, RiskLevel.MEDIUM),
        (0.59996, RiskLevel.HIGH),
        (0.60004, RiskLevel.HIGH),
    ],
)
def test_rounding_four_places_controls_risk_boundaries(injected_weight, expected):
    claim, kyc, ocr, received = envelopes(
        claim_number="WEIGHT-BOUNDARY", claim_amount=Decimal("9999.99")
    )
    agent = FraudAgent(
        FakeHistoryRepo(),
        settings(),
        weights={**DETECTOR_WEIGHTS, "NEAR_THRESHOLD": injected_weight},
        reference_prices={"99213": 1_000_000},
        plausibility={"obstetric_cpt_codes": [], "obstetric_icd10_prefixes": ["O"]},
    )
    result = agent.score(DocType.CLAIM_FORM, "MEM-1", claim, kyc, ocr, received)
    assert result.fraud_score == round(injected_weight, 4)
    assert result.risk_level == expected


@given(
    st.lists(
        st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False), max_size=8
    ),
    st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
)
def test_adding_an_anomaly_never_lowers_noisy_or_score(weights, additional):
    initial = [
        Anomaly(type="NEAR_THRESHOLD", evidence="existing", weight=value) for value in weights
    ]
    before = noisy_or_score(initial)
    after = noisy_or_score(
        initial + [Anomaly(type="NEAR_THRESHOLD", evidence="additional", weight=additional)]
    )
    assert after >= before
