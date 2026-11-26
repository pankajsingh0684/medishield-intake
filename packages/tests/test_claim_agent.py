from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from packages.agents.claims.agent import ClaimsAgent, ExtractedValue
from packages.agents.claims.validators import normalize_dea, normalize_npi, validate_claim
from packages.core.config import Settings
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.fixtures import FixtureStore
from packages.core.llm.gateway import Gateway, StubProvider
from packages.core.models import BBox, ClaimFields, OcrField, OcrPayload
from scripts.make_claims_fixtures import generate_fixtures

DATASET_DIR = Path("data/synthetic/dataset")
RECEIVED_AT = datetime(2025, 5, 15, tzinfo=UTC)


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": "postgresql://user:password@localhost/medishield",
        "redis_url": "redis://localhost:6380/0",
        "redis_password": "redis-password",
        "s3_endpoint": "http://localhost:9000",
        "s3_access_key": "access-key",
        "s3_secret_key": "secret-key",
        "s3_bucket": "medishield",
        "qdrant_url": "http://localhost:6333",
        "qdrant_api_key": "qdrant-key",
        "llm_vision_model": "test-vision",
        "llm_text_model": "test-text",
        "llm_fallback_model": "test-fallback",
        "jwt_secret": "jwt-secret",
        "seed_test_user_password": "seed-password",
    }
    values.update(overrides)
    return Settings(**values)


def make_ocr(fields: list[OcrField] | None = None, raw_text: str = "", boxes=None) -> OcrPayload:
    return OcrPayload(
        agent="ocr",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.9,
        model="test-ocr",
        started_at=RECEIVED_AT,
        finished_at=RECEIVED_AT,
        fields=fields or [],
        raw_text=raw_text,
        bounding_boxes=boxes or [],
        pages=1,
        used_text_layer=True,
    )


class EmptyExtractionGateway:
    def complete_json(
        self,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes] | None,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        del model, system, messages, images, kwargs
        return schema.model_validate({"fields": {}})


def test_stub_fallback_extracts_each_claim_document_type(tmp_path: Path):
    generate_fixtures(DATASET_DIR, tmp_path)
    gateway = Gateway(StubProvider(FixtureStore(tmp_path)))
    agent = ClaimsAgent(gateway, make_settings())
    categories = {
        DocType.CLAIM_FORM: "claim_forms/claim_PT_15075.png",
        DocType.DISCHARGE_SUMMARY: "discharge_summaries/discharge_PT_15075.png",
        DocType.PRESCRIPTION: "prescriptions/rx_PT_15075.png",
    }

    for doc_type, relative_path in categories.items():
        result = agent.extract(
            doc_type,
            make_ocr(),
            RECEIVED_AT,
            [(DATASET_DIR / relative_path).read_bytes()],
        )
        assert result.status == AgentStatus.OK
        assert result.schema_valid
        assert result.extracted_fields.field_confidence
        assert any(result.extracted_fields.field_source.values())


def test_ocr_values_keep_confidence_and_matching_bbox_without_llm():
    fields = [
        OcrField(key="claim_amount", value="$250.00", confidence=0.91, page=1),
        OcrField(key="service_date", value="05/01/2025", confidence=0.92, page=1),
        OcrField(key="icd10", value="i25.10", confidence=0.93, page=1),
        OcrField(key="cpt", value="99213", confidence=0.94, page=1),
        OcrField(key="provider_npi", value="NPI-1234567893", confidence=0.95, page=1),
        OcrField(key="signature_present", value="Yes", confidence=0.96, page=1),
    ]
    boxes = [BBox(text="250.00", page=1, x=0.1, y=0.2, w=0.2, h=0.03)]

    result = ClaimsAgent(
        Gateway(StubProvider(FixtureStore(Path("missing")))), make_settings()
    ).extract(DocType.CLAIM_FORM, make_ocr(fields, boxes=boxes), RECEIVED_AT)

    assert result.extracted_fields.icd10_codes == ["I25.10"]
    assert result.extracted_fields.provider_npi == "1234567893"
    assert result.extracted_fields.field_confidence["claim_amount"] == 0.91
    assert result.extracted_fields.field_source["claim_amount"] == boxes[0]


def test_confirmed_blank_required_field_has_normal_confidence():
    result = ClaimsAgent(EmptyExtractionGateway(), make_settings()).extract(
        DocType.CLAIM_FORM,
        make_ocr(raw_text="TOTAL CHARGES:\n"),
        RECEIVED_AT,
        [b"document image"],
    )

    assert not result.schema_valid
    assert result.extracted_fields.field_confidence["claim_amount"] == 0.9
    assert result.confidence >= 0.5


def test_missing_field_on_unreadable_page_escalates_confidence():
    result = ClaimsAgent(EmptyExtractionGateway(), make_settings()).extract(
        DocType.CLAIM_FORM,
        make_ocr(raw_text="TOTAL CHARGES: $0.00").model_copy(update={"confidence": 0.6}),
        RECEIVED_AT,
        [b"document image"],
    )

    assert not result.schema_valid
    assert result.extracted_fields.field_confidence["claim_amount"] == 0.5
    assert result.confidence == 0.5


def test_irrelevant_document_types_are_skipped():
    result = ClaimsAgent(
        Gateway(StubProvider(FixtureStore(Path("missing")))), make_settings()
    ).extract(DocType.ID_DOCUMENT, make_ocr(), RECEIVED_AT)

    assert result.status == AgentStatus.SKIPPED
    assert result.confidence == 1.0


def test_fixture_generator_is_repeatable(tmp_path: Path):
    first = generate_fixtures(DATASET_DIR, tmp_path)
    first_content = {path.name: path.read_bytes() for path in first}
    second = generate_fixtures(DATASET_DIR, tmp_path)

    assert len(first) == 3
    assert first_content == {path.name: path.read_bytes() for path in second}


def _rx_fields(**overrides: str | None) -> list[OcrField]:
    values: dict[str, str | None] = {
        "medication": "Sertraline",
        "sig": "Take 1 tablet daily",
        "provider_npi": "NPI-1234567893",
        "dea": "AB1234563",
        "rx_date": "05/01/2025",
        "refills": "",
    }
    values.update(overrides)
    return [
        OcrField(key=key, value=value, confidence=0.95, page=1)
        for key, value in values.items()
        if value is not None
    ]


def _extract_rx(fields: list[OcrField], confidence: float = 0.9):
    return ClaimsAgent(EmptyExtractionGateway(), make_settings()).extract(
        DocType.PRESCRIPTION,
        make_ocr(fields).model_copy(update={"confidence": confidence}),
        RECEIVED_AT,
    )


def test_prescription_with_blank_refills_passes():
    result = _extract_rx(_rx_fields())

    assert result.schema_valid, result.validation_errors
    assert result.extracted_fields.extra["refills"] == 0
    assert result.extracted_fields.service_date is None


def test_prescription_without_refills_field_passes():
    assert _extract_rx(_rx_fields(refills=None)).schema_valid


def test_prescription_date_maps_to_rx_date_only():
    result = _extract_rx(_rx_fields(rx_date=None, service_date="05/01/2025"))

    assert result.extracted_fields.service_date is None
    assert str(result.extracted_fields.extra["rx_date"]) == "2025-05-01"


def test_multiple_sig_and_drug_lines_become_lists():
    fields = [
        *_rx_fields(),
        OcrField(key="sig", value="Then 2 tablets at night", confidence=0.9, page=1),
        OcrField(key="medication", value="Lisinopril", confidence=0.9, page=1),
    ]

    result = _extract_rx(fields)

    assert result.schema_valid, result.validation_errors
    assert result.extracted_fields.extra["sig"] == [
        "Take 1 tablet daily",
        "Then 2 tablets at night",
    ]
    assert result.extracted_fields.extra["drug_name"] == ["Sertraline", "Lisinopril"]


def test_prescription_missing_dea_fails_schema_at_normal_confidence():
    result = _extract_rx(_rx_fields(dea=None))

    assert not result.schema_valid
    assert any(error.startswith("DEA_NUMBER") for error in result.validation_errors)
    assert result.confidence >= 0.7


def test_low_ocr_confidence_page_keeps_low_confidence():
    result = _extract_rx(_rx_fields(dea=None), confidence=0.6)

    assert not result.schema_valid
    assert result.confidence == 0.5


@pytest.mark.parametrize(
    "placeholder", ["[ILLEGIBLE]", "ILLEGIBLE", "N/A", "?", "---", "unreadable"]
)
def test_placeholder_sig_is_missing_placeholder(placeholder: str) -> None:
    values = ClaimsAgent._build_fields(
        {"sig": ExtractedValue(value=placeholder, confidence=0.95, page=1)}
    )
    assert values.extra.get("sig") is None


def test_npi_and_dea_normalization_reject_invalid_lengths() -> None:
    assert normalize_npi("NPI: 123-456-7890") == "1234567890"
    assert normalize_dea("DEA-AB1234563") == "AB1234563"

    fields = ClaimFields(
        claim_amount=None,
        icd10_codes=[],
        cpt_codes=[],
        provider_npi="123",
        service_date=None,
        extra={"prescriber_npi": "NPI: 123", "dea_number": "SHORT"},
    )
    errors, _warnings = validate_claim(fields, DocType.PRESCRIPTION, RECEIVED_AT)
    assert any("NPI_FORMAT" in error for error in errors)
    assert any("DEA_FORMAT" in error for error in errors)
