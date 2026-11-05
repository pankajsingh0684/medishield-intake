from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from packages.agents.claims.agent import ClaimsAgent
from packages.core.config import Settings
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.fixtures import FixtureStore
from packages.core.llm.gateway import Gateway, StubProvider
from packages.core.models import BBox, OcrField, OcrPayload
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


def test_missing_field_without_absence_evidence_escalates_confidence():
    result = ClaimsAgent(EmptyExtractionGateway(), make_settings()).extract(
        DocType.CLAIM_FORM,
        make_ocr(raw_text="TOTAL CHARGES: $0.00"),
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
