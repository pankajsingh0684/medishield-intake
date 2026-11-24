"""Tests for OCR agent."""

import io
import json
import math
import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
import pytesseract
import pytest
from PIL import Image

from packages.agents.ocr import agent as ocr_agent_module
from packages.agents.ocr import tesseract_wrapper
from packages.agents.ocr.agent import OCR_MESSAGE, OCRAgent
from packages.agents.ocr.cache import OcrCache
from packages.agents.ocr.field_extractors import (
    ExtractedField,
    extract_claim_amount,
    extract_cpt_codes,
    extract_dob,
    extract_fields_from_text,
    extract_icd10_codes,
    extract_member_id,
    extract_policy_number,
)
from packages.agents.ocr.image_prep import deskew_image, validate_image_quality
from packages.agents.ocr.tesseract_wrapper import (
    OcrWord,
    configure_tesseract,
    render_image_at_dpi,
    run_tesseract_ocr,
)
from packages.agents.ocr.text_layer import extract_text_layer
from packages.agents.ocr.validators import is_valid, is_valid_icd10
from packages.core.config import Settings
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.fixtures import FixtureStore, fixture_key
from packages.core.llm.gateway import Gateway, StubProvider
from packages.core.models import OcrField, OcrPayload

# Helper functions


def make_raster_bytes(width: int = 200, height: int = 100, format: str = "PNG") -> bytes:
    """Create a simple test image as bytes."""
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def make_pdf_with_text(text: str) -> bytes:
    """Create a simple PDF with text layer."""
    try:
        import pymupdf
    except ImportError:
        pytest.skip("pymupdf not available")

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_textbox((10, 10, 190, 90), text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_empty_pdf() -> bytes:
    """Create a PDF with no text layer."""
    try:
        import pymupdf
    except ImportError:
        pytest.skip("pymupdf not available")

    doc = pymupdf.open()
    doc.new_page(width=200, height=100)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_multi_page_pdf(texts: list[str]) -> bytes:
    """Create a PDF with one text block per supplied page."""
    import pymupdf

    doc = pymupdf.open()
    for text in texts:
        page = doc.new_page(width=400, height=300)
        page.insert_textbox((20, 20, 380, 280), text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_settings() -> Settings:
    """Create a test Settings object."""
    return Settings(
        DATABASE_URL="postgresql://user:pass@localhost/test",
        REDIS_URL="redis://localhost",
        REDIS_PASSWORD="redis-test",
        S3_ENDPOINT="http://localhost:9000",
        S3_ACCESS_KEY="minioadmin",
        S3_SECRET_KEY="minioadmin",
        S3_BUCKET="medishield-documents",
        QDRANT_URL="http://localhost:6333",
        QDRANT_API_KEY="test-key",
        LLM_PROVIDER="stub",
        LLM_VISION_MODEL="test-vision",
        LLM_TEXT_MODEL="test-text",
        LLM_FALLBACK_MODEL="test-fallback",
        JWT_SECRET="test-jwt-secret",
        SEED_TEST_USER_PASSWORD="test-user-password",
    )


def make_agent(gateway: Gateway | None = None, settings: Settings | None = None) -> OCRAgent:
    """Create an OCR agent with stub gateway."""
    settings = settings or make_settings()
    fixture_dir = Path(__file__).parent.parent.parent / "fixtures" / "llm"
    provider = StubProvider(FixtureStore(fixture_dir))
    return OCRAgent(gateway or Gateway(provider), settings)


def make_ocr_payload(
    *, fields: list[OcrField] | None = None, raw_text: str = "", pages: int = 1
) -> OcrPayload:
    return OcrPayload(
        agent="ocr",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.92,
        model="stub-vision",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        fields=fields or [],
        raw_text=raw_text,
        bounding_boxes=[],
        pages=pages,
        used_text_layer=False,
    )


def write_ocr_fixture(root: Path, images: tuple[bytes, ...], payload: OcrPayload) -> Gateway:
    store = FixtureStore(root)
    key = fixture_key("ocr", [dict(OCR_MESSAGE)], list(images))
    store.write(key, payload.model_dump(mode="json"))
    return Gateway(StubProvider(store))


def dominant_skew_degrees(image: Image.Image) -> float:
    grayscale = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(grayscale, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 100)
    assert lines is not None
    angles = []
    for line in lines:
        _, theta = line[0]
        angle = math.degrees(theta) - 90
        if abs(angle) > 45:
            angle -= math.copysign(180, angle)
        angles.append(angle)
    return float(np.median(angles))


# Field extraction tests


class TestFieldExtraction:
    """Test regex-based field extraction."""

    def test_extract_member_id(self):
        """Test member ID extraction."""
        text = "Member ID: M123456 Active"
        assert extract_member_id(text) == "M123456"

    def test_extract_member_id_missing(self):
        """Test missing member ID."""
        text = "No ID here"
        assert extract_member_id(text) is None

    def test_extract_dob(self):
        """Test date of birth extraction."""
        text = "DOB: 05/15/1980"
        assert extract_dob(text) == "05/15/1980"

    def test_extract_dob_hyphen_format(self):
        """Test DOB with hyphenated format."""
        text = "1980-05-15"
        assert extract_dob(text) == "1980-05-15"

    def test_extract_policy_number(self):
        """Test policy number extraction."""
        assert extract_policy_number("Policy: MED-GLD-1234567") == "MED-GLD-1234567"

    def test_policy_brand_is_not_misclassified_as_policy_number(self):
        assert extract_policy_number("MediShield Gold Plan Policy Document") is None

    def test_claim_amount_requires_a_billing_label(self):
        assert extract_claim_amount("Policy Year 2025") is None
        assert extract_claim_amount("28. TOTAL CHARGE: $9,875.00") == "9,875.00"
        assert extract_claim_amount("Total Charges $12,340.00") == "12,340.00"

    def test_member_and_provider_names_use_their_own_labels(self):
        from packages.agents.ocr.field_extractors import extract_fields_from_text

        fields = extract_fields_from_text("Member Name: Jane Doe Provider Name: Alex Smith")
        assert fields["member_name"].value == "JANE DOE"
        assert fields["provider_name"].value == "ALEX SMITH"

    def test_extract_icd10_codes(self):
        """Test ICD-10 code extraction."""
        text = "Diagnosis: E11.9, I10, M79.1"
        codes = extract_icd10_codes(text)
        assert "E11.9" in codes or "E11" in codes

    def test_extract_cpt_codes(self):
        """CPT codes need a label and the spec shape; HCPCS-style D0100 is not a CPT."""
        text = "CPT: 99213, 99214, D0100"
        codes = extract_cpt_codes(text)
        assert codes == ["99213", "99214"]


class TestImagePreprocessing:
    """Test image preprocessing."""

    def test_validate_image_quality_valid(self):
        """Test validation of a valid image."""
        img = Image.new("RGB", (200, 100))
        is_valid, msg = validate_image_quality(img)
        assert is_valid
        assert msg == "OK"

    def test_validate_image_quality_too_small(self):
        """Test validation of an image that's too small."""
        img = Image.new("RGB", (50, 50))
        is_valid, msg = validate_image_quality(img)
        assert not is_valid
        assert "too small" in msg.lower()

    def test_deskew_image_straight(self):
        """Test that deskewing a straight image doesn't break it."""
        img = Image.new("RGB", (200, 100), color="white")
        deskewed = deskew_image(img)
        assert isinstance(deskewed, Image.Image)
        assert deskewed.size[0] > 0 and deskewed.size[1] > 0

    def test_deskew_corrects_a_genuinely_skewed_sample(self):
        pixels = np.full((500, 800), 255, dtype=np.uint8)
        for y in range(60, 440, 70):
            cv2.line(pixels, (100, y), (700, y), 0, 3)
        sample = Image.fromarray(cv2.cvtColor(pixels, cv2.COLOR_GRAY2RGB))
        skewed = sample.rotate(8, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")

        before_angle = dominant_skew_degrees(skewed)
        corrected = deskew_image(skewed)
        after_angle = dominant_skew_degrees(corrected)

        assert abs(before_angle) >= 5
        assert abs(after_angle) < 2
        assert abs(after_angle) < abs(before_angle)

    def test_render_image_at_dpi(self):
        """Test DPI rendering."""
        img = Image.new("RGB", (100, 100))
        rendered = render_image_at_dpi(img, target_dpi=300)
        assert isinstance(rendered, Image.Image)
        # Size may change based on DPI adjustment
        assert rendered.size[0] > 0

    def test_tesseract_uses_psm_six(self, monkeypatch):
        captured = {}

        def fake_image_to_data(image, *, output_type, config):
            captured["config"] = config
            return {
                "text": ["Member", ""],
                "conf": ["90", "-1"],
                "left": [10, 0],
                "top": [10, 0],
                "width": [40, 0],
                "height": [12, 0],
            }

        monkeypatch.setattr(tesseract_wrapper.pytesseract, "image_to_data", fake_image_to_data)
        result = run_tesseract_ocr(Image.new("RGB", (200, 100)))

        assert result is not None
        assert captured["config"] == "--psm 6"


class TestTextLayerExtraction:
    """Test PDF text layer extraction."""

    def test_extract_text_layer_with_content(self):
        """Test extracting text layer from PDF with content."""
        pdf_bytes = make_pdf_with_text(
            "Member ID M123456. This PDF page has enough extractable text to meet the "
            "required fifty-character minimum for text-layer extraction."
        )
        result = extract_text_layer(pdf_bytes)

        assert result is not None
        text, page_count = result
        assert "M123456" in text
        assert page_count == 1

    def test_every_pdf_page_must_meet_character_threshold(self):
        pdf_bytes = make_multi_page_pdf(
            [
                (
                    "Member ID M123456. This first page has enough text to meet the required "
                    "fifty-character minimum for PDF text extraction."
                ),
                "Short page",
            ]
        )
        assert extract_text_layer(pdf_bytes) is None

    def test_scanned_pdf_renders_every_page_at_300_dpi(self):
        pdf_bytes = make_multi_page_pdf(["Short page", "Another short page"])
        rendered = ocr_agent_module._render_ocr_document(pdf_bytes, "application/pdf")

        assert rendered.page_count == 2
        assert len(rendered.images) == 2
        for image_bytes in rendered.images:
            with Image.open(io.BytesIO(image_bytes)) as image:
                assert image.info["dpi"] == pytest.approx((300, 300), abs=1)

    def test_extract_text_layer_empty(self):
        """Test extracting from PDF without text layer."""
        pdf_bytes = make_empty_pdf()
        result = extract_text_layer(pdf_bytes)
        assert result is None  # Below minimum threshold

    def test_extract_text_layer_invalid(self):
        """Test extracting from invalid PDF bytes."""
        result = extract_text_layer(b"not a pdf")
        assert result is None


class TestOCRAgent:
    """Test the OCR agent."""

    def test_agent_initialization(self):
        """Test agent can be initialized."""
        agent = make_agent()
        assert agent is not None
        assert agent.settings is not None

    def test_ocr_fallback_prompt_version_and_complete_payload_contract(self) -> None:
        from packages.agents.ocr.agent import OCR_PROMPT_VERSION
        from packages.core.llm.prompts import PromptLoader

        prompt = PromptLoader(Path("packages/agents/ocr/prompts")).load("ocr", OCR_PROMPT_VERSION)

        assert OCR_PROMPT_VERSION == "v3"
        assert prompt.max_tokens == 3000
        for required_property in (
            "agent_version",
            "started_at",
            "finished_at",
            "bounding_boxes",
            "used_text_layer",
        ):
            assert f'"{required_property}"' in prompt.system

    def test_classifier_prompt_matches_prediction_schema(self) -> None:
        from packages.agents.classifier.agent import CLASSIFIER_PROMPT_VERSION
        from packages.core.llm.prompts import PromptLoader

        prompt = PromptLoader(Path("packages/agents/prompts")).load(
            "classifier", CLASSIFIER_PROMPT_VERSION
        )

        assert prompt.schema == "ClassificationPrediction"
        assert "doc_type" in prompt.system
        assert "confidence" in prompt.system
        assert "routing_tags" in prompt.system

    def test_process_empty_image_returns_error_payload(self):
        agent = make_agent()

        result = agent.process(b"", "image/png")

        assert result.status == AgentStatus.ERROR
        assert result.error
        assert result.fields == []
        assert result.confidence == 0.0

    def test_process_invalid_mime_type_returns_error_payload(self):
        agent = make_agent()
        img_bytes = make_raster_bytes()

        result = agent.process(img_bytes, "invalid/type")

        assert result.status == AgentStatus.ERROR
        assert result.error
        assert result.fields == []
        assert result.confidence == 0.0

    def test_process_low_confidence_uses_stub_fallback(self, tmp_path, monkeypatch):
        image_bytes = make_raster_bytes(400, 200)
        from packages.core.documents import render_document

        rendered = render_document(image_bytes, "image/png")
        payload = make_ocr_payload(
            fields=[OcrField(key="member_id", value="M123456", confidence=0.96, page=1)],
            raw_text="Member ID: M123456",
        )
        agent = make_agent(write_ocr_fixture(tmp_path, rendered.images, payload))

        def low_confidence_ocr(image, page_num=1):
            word = OcrWord("unclear", 0.35, 10, 10, 40, 12, page_num)
            return [word], "unclear", 0.35

        monkeypatch.setattr(ocr_agent_module, "run_tesseract_ocr", low_confidence_ocr)
        result = agent.process(image_bytes, "image/png")

        assert isinstance(result, OcrPayload)
        assert result.model == "stub-vision+tesseract"
        assert result.fields[0].value == "M123456"
        assert result.confidence == pytest.approx(0.96)

    def test_missing_document_key_alone_triggers_stub_fallback(self, tmp_path, monkeypatch):
        image_bytes = make_raster_bytes(400, 200)
        from packages.core.documents import render_document

        rendered = render_document(image_bytes, "image/png")
        payload = make_ocr_payload(
            fields=[OcrField(key="claim_amount", value="4095.00", confidence=0.98, page=1)],
            raw_text="TOTAL CHARGE: $4095.00",
        )
        agent = make_agent(write_ocr_fixture(tmp_path, rendered.images, payload))

        def high_confidence_but_missing_keys(image, page_num=1):
            word = OcrWord("4095.00", 0.95, 10, 10, 55, 14, page_num)
            return [word], "TOTAL CHARGE: $4095.00", 0.95

        monkeypatch.setattr(ocr_agent_module, "run_tesseract_ocr", high_confidence_but_missing_keys)
        result = agent.process(image_bytes, "image/png", doc_type=DocType.CLAIM_FORM)

        assert result.model == "stub-vision+tesseract"
        assert result.fields[0].value == "4095.00"


class TestOCRIntegration:
    """Integration tests for OCR pipeline."""

    def test_pdf_text_layer_skips_ocr(self, monkeypatch):
        """Test that PDFs with text layer use text layer extraction."""
        agent = make_agent()
        pdf_bytes = make_pdf_with_text(
            "Member ID: M123456. This page contains sufficient extractable text to exceed "
            "the minimum text-layer character count of fifty."
        )

        monkeypatch.setattr(
            ocr_agent_module,
            "run_tesseract_ocr",
            lambda *args, **kwargs: pytest.fail("Tesseract must be skipped for eligible PDF text"),
        )
        result = agent.process(pdf_bytes, "application/pdf")

        assert result.used_text_layer is True
        assert result.pages == 1
        assert any(field.key == "member_id" and field.value == "M123456" for field in result.fields)

    def test_empty_page_handled(self, tmp_path, monkeypatch):
        """Test that empty pages are handled gracefully."""
        pdf_bytes = make_empty_pdf()

        rendered = ocr_agent_module._render_ocr_document(pdf_bytes, "application/pdf")
        payload = make_ocr_payload(raw_text="", pages=1)
        agent = make_agent(write_ocr_fixture(tmp_path, rendered.images, payload))
        monkeypatch.setattr(ocr_agent_module, "run_tesseract_ocr", lambda *args, **kwargs: None)

        result = agent.process(pdf_bytes, "application/pdf")
        assert isinstance(result, OcrPayload)
        assert result.fields == []
        assert result.raw_text == ""
        assert result.pages == 1

    def test_output_validates_as_ocr_payload(self):
        """Test that output validates as OcrPayload schema."""
        # Create a minimal valid payload
        payload = OcrPayload(
            agent="ocr",
            agent_version="1.0.0",
            status=AgentStatus.OK,
            confidence=0.85,
            model="test",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            fields=[OcrField(key="member_id", value="M123456", confidence=0.95, page=1)],
            raw_text="Member ID: M123456",
            bounding_boxes=[],
            pages=1,
            used_text_layer=False,
        )

        assert isinstance(payload, OcrPayload)
        assert payload.agent == "ocr"
        assert payload.confidence == 0.85
        assert len(payload.fields) == 1

    def test_real_tesseract_extracts_clean_dataset_claim_amount(self):
        """Exercise native Tesseract on a frozen clean claim image; never skip if absent."""
        settings = Settings()
        configure_tesseract(settings.tesseract_cmd)
        try:
            version = pytesseract.get_tesseract_version()
        except (OSError, pytesseract.TesseractNotFoundError) as error:
            pytest.fail(
                "Real Tesseract integration requires the Tesseract executable. Install it "
                "with `choco install tesseract`, or set TESSERACT_CMD in .env to the full "
                f"path to tesseract.exe. Detection error: {error}",
                pytrace=False,
            )

        repository_root = Path(__file__).resolve().parents[2]
        dataset_dir = repository_root / "data" / "synthetic" / "dataset"
        truth_by_id = json.loads((dataset_dir / "truth.json").read_text(encoding="utf-8"))
        image_path = dataset_dir / "claim_forms" / "claim_PT_19116.png"
        expected_amount = truth_by_id["claim_PT_19116"]["claim_amount"]

        with Image.open(image_path) as source:
            image = render_image_at_dpi(source.convert("RGB"), target_dpi=300)
            result = run_tesseract_ocr(image)

        assert result is not None, f"Tesseract {version} returned no text for {image_path.name}"
        _, raw_text, _ = result
        total_match = re.search(r"PAGE TOTALS\s+\$([\d,]+\.\d{2})", raw_text, re.IGNORECASE)
        assert total_match is not None, f"Could not read the labeled claim total: {raw_text}"
        assert Decimal(total_match.group(1).replace(",", "")) == Decimal(expected_amount)


class TestOCREdgeCases:
    """Test edge cases and error handling."""

    def test_corrupt_image_returns_error_payload(self):
        agent = make_agent()

        result = agent.process(b"\x00\x01\x02\x03", "image/png")

        assert result.status == AgentStatus.ERROR
        assert result.error
        assert result.fields == []
        assert result.confidence == 0.0

    def test_unsupported_image_returns_error_payload(self):
        result = make_agent().process(make_raster_bytes(), "image/bmp")

        assert result.status == AgentStatus.ERROR
        assert "Unsupported document type" in result.error
        assert result.fields == []
        assert result.confidence == 0.0

    def test_malformed_pdf_returns_error(self):
        """Test that malformed PDF is handled gracefully."""
        agent = make_agent()

        result = agent.process(b"%PDF-1.4\ninvalid pdf content", "application/pdf")
        assert result.status == AgentStatus.ERROR
        assert result.fields == []


class TestExtractorPrecision:
    """A wrong extracted value must never beat a fallback value."""

    @pytest.mark.parametrize("code", ["K35.80", "G43.909", "I25.10", "M54.5"])
    def test_icd10_validator_accepts_spec_codes(self, code):
        assert is_valid_icd10(code)

    @pytest.mark.parametrize("code", ["K35.8x", "12345"])
    def test_icd10_validator_rejects_malformed_codes(self, code):
        assert not is_valid_icd10(code)

    def test_icd10_extraction_keeps_decimals(self):
        assert extract_icd10_codes("Dx K35.80, G43.909 I25.10 M54.5") == [
            "K35.80",
            "G43.909",
            "I25.10",
            "M54.5",
        ]

    def test_malformed_icd10_is_dropped_and_counted(self):
        dropped = Counter()
        assert extract_icd10_codes("Dx K35.8x U07.1", dropped) == []
        assert dropped["icd10"] == 2

    def test_invalid_values_are_dropped_and_counted(self):
        dropped = Counter()
        fields = extract_fields_from_text("DOS: 05/13/2096 TOTAL CHARGE: $0.00", dropped)
        assert "service_date" not in fields
        assert "claim_amount" not in fields
        assert dropped["service_date"] == 1
        assert dropped["claim_amount"] == 1

    def test_cpt_requires_a_label(self):
        assert extract_cpt_codes("Total 99213 billed") == []

    def test_cpt_excludes_id_claim_and_zip_numbers(self):
        dropped = Counter()
        text = (
            "Ref 12345 Member ID: 17665 Claim No: 55512 Chicago, IL 60611 "
            "CPT 90837 17665 60611 55512"
        )
        assert extract_cpt_codes(text, dropped) == ["90837"]
        assert dropped["cpt"] == 3

    def test_discharge_before_admit_drops_both_dates(self):
        dropped = Counter()
        text = "Admission Date: 02/19/2025 Discharge Date: 02/14/2025"
        fields = extract_fields_from_text(text, dropped)
        assert "admit_date" not in fields
        assert "discharge_date" not in fields
        assert dropped["date_order"] == 1

    def test_ordered_admit_and_discharge_dates_are_kept(self):
        text = "Admission Date: 02/14/2025 Discharge Date: 02/19/2025"
        fields = extract_fields_from_text(text)
        assert fields["admit_date"].value == "02/14/2025"
        assert fields["discharge_date"].value == "02/19/2025"

    def test_invalid_tesseract_value_cannot_win_the_merge(self):
        agent = make_agent()
        llm = make_ocr_payload(
            fields=[OcrField(key="service_date", value="2025-05-13", confidence=0.5, page=1)]
        )
        invalid = ExtractedField("service_date", "2096-05-13", 0.9)
        assert not is_valid("service_date", invalid.value)

        merged = agent._merge_results(llm, ({"service_date": (invalid, 1)}, 0.9, []))
        assert [field.value for field in merged.fields] == ["2025-05-13"]

        valid = ExtractedField("service_date", "2025-05-14", 0.9)
        merged = agent._merge_results(llm, ({"service_date": (valid, 1)}, 0.9, []))
        assert [field.value for field in merged.fields] == ["2025-05-14"]

    def test_cache_version_change_invalidates_cache(self, tmp_path):
        content = b"image bytes"
        pages = ([OcrWord("Total", 0.9, 1, 2, 3, 4, 1)], [(1, "Total")], 1)
        OcrCache(tmp_path, "1.0.0").put(content, pages)

        assert OcrCache(tmp_path, "1.0.0").get(content) == pages
        assert OcrCache(tmp_path, "1.1.0").get(content) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
