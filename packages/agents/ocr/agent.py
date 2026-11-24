"""OCR Agent: three-tier document field extraction."""

import logging
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image
from pydantic import ConfigDict, ValidationError, model_validator
from pytesseract import TesseractError, TesseractNotFoundError

from packages.agents.ocr.field_extractors import extract_fields_from_text
from packages.agents.ocr.image_prep import deskew_image, validate_image_quality
from packages.agents.ocr.tesseract_wrapper import (
    OcrWord,
    configure_tesseract,
    render_image_at_dpi,
    run_tesseract_ocr,
)
from packages.agents.ocr.text_layer import extract_text_layer_pages
from packages.agents.ocr.validators import is_valid
from packages.core.config import Settings
from packages.core.documents import RenderedDocument, render_document
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMError, LLMGateway
from packages.core.llm_outputs import LLMOutputBBox, LLMOutputModel, LLMOutputOcrField
from packages.core.models import BBox, OcrField, OcrPayload

logger = logging.getLogger(__name__)

OCR_AGENT = "ocr"
OCR_VERSION = "1.1.0"
OCR_PROMPT_VERSION = "v3"

LOW_CONFIDENCE_THRESHOLD = 0.70
KEY_FIELDS = {
    "member_id",
    "member_name",
    "policy_number",
    "id_number",
    "claim_amount",
    "service_date",
    "provider_npi",
    "icd10",
    "cpt",
    "medication",
}
DOC_TYPE_KEY_FIELDS = {
    DocType.CLAIM_FORM: {
        "claim_amount",
        "service_date",
        "icd10_codes",
        "cpt_codes",
        "provider_npi",
        "signature_present",
    },
    DocType.ID_DOCUMENT: {"member_name", "id_expiry"},
    DocType.DISCHARGE_SUMMARY: {
        "admit_date",
        "discharge_date",
        "icd10_codes",
        "signature_present",
    },
    DocType.PRESCRIPTION: {
        "medication",
        "dosage",
        "refills",
        "provider_npi",
        "dea",
        "rx_date",
    },
}
REQUIRED_FIELD_ALIASES = {"icd10_codes": "icd10", "cpt_codes": "cpt"}

OCR_MESSAGE: Mapping[str, str] = {
    "role": "user",
    "content": "Extract all visible fields from the document image. Return JSON with fields, raw_text, bounding_boxes, pages, used_text_layer=false, and confidence.",
}


class OcrLLMOutput(OcrPayload):
    model_config = ConfigDict(extra="ignore")

    fields: list[LLMOutputOcrField]
    bounding_boxes: list[LLMOutputBBox]

    @model_validator(mode="before")
    @classmethod
    def warn_unknown_fields(cls, values):
        return LLMOutputModel.warn_unknown_fields.__func__(cls, values)


class OCRError(ValueError):
    """OCR processing error."""


class OCRAgent:
    """Three-tier OCR agent for document field extraction."""

    def __init__(
        self,
        gateway: LLMGateway,
        settings: Settings,
        *,
        prompt_loader: PromptLoader | None = None,
    ):
        self.gateway = gateway
        self.settings = settings
        self.prompt_loader = prompt_loader or PromptLoader(Path(__file__).parent / "prompts")
        configure_tesseract(getattr(settings, "tesseract_cmd", None))

    def process(
        self,
        content: bytes,
        mime_type: str,
        doc_type: DocType | None = None,
    ) -> OcrPayload:
        """
        Process a document and extract fields.

        Implements three-tier OCR:
        1. PDF text layer (if ≥50 chars per page)
        2. Tesseract + deskew (for images/PDFs without text layer)
        3. Vision LLM fallback (if mean confidence <0.70 or required fields missing)

        Args:
            content: Document file bytes
            mime_type: MIME type (e.g., "application/pdf", "image/png")

        Returns:
            OcrPayload with extracted fields, raw_text, bounding_boxes

        Raises:
            Invalid documents return an ERROR OcrPayload rather than raising.
        """
        started_at = datetime.now(UTC)
        normalized_mime_type = mime_type.split(";", maxsplit=1)[0].strip().lower()
        if not content:
            return _error_payload("The document is empty", started_at)
        if normalized_mime_type not in {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/tiff",
            "image/tif",
        }:
            return _error_payload(f"Unsupported document type: {mime_type}", started_at)

        self._tesseract_results = None
        try:
            if normalized_mime_type == "application/pdf":
                text_payload = self._try_text_layer(content)
                if text_payload is not None:
                    return text_payload

            tesseract_payload = self._try_tesseract(content, normalized_mime_type, doc_type)
            if tesseract_payload is not None:
                return tesseract_payload

            return self._try_llm_fallback(content, normalized_mime_type, started_at)
        except (
            OCRError,
            LLMError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            logger.warning("OCR processing failed: %s", type(error).__name__)
            return _error_payload(f"OCR processing failed: {error}", started_at)

    def _try_text_layer(self, content: bytes) -> OcrPayload | None:
        """Try to extract text layer from PDF."""
        logger.debug("Attempting PDF text layer extraction")

        result = extract_text_layer_pages(content)
        if not result:
            return None

        page_texts, page_count = result
        text = "\n".join(page_texts)
        ocr_fields = []
        for page_num, page_text in enumerate(page_texts, start=1):
            ocr_fields.extend(
                OcrField(
                    key=field.key, value=field.value, confidence=field.confidence, page=page_num
                )
                for field in extract_fields_from_text(page_text).values()
            )
        confidence = _field_confidence(ocr_fields, page_count)

        return OcrPayload(
            agent=OCR_AGENT,
            agent_version=OCR_VERSION,
            status=AgentStatus.OK,
            confidence=confidence,
            model="text-layer",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            fields=ocr_fields,
            raw_text=text,
            bounding_boxes=[],
            pages=page_count,
            used_text_layer=True,
        )

    def _ocr_pages(
        self, content: bytes, mime_type: str
    ) -> tuple[list[OcrWord], list[tuple[int, str]], int]:
        """Render, deskew and run Tesseract per page; returns words, page texts, page count."""
        rendered = _render_ocr_document(content, mime_type)
        all_words: list[OcrWord] = []
        raw_texts: list[tuple[int, str]] = []

        for page_num, image_bytes in enumerate(rendered.images, start=1):
            image = Image.open(BytesIO(image_bytes))

            is_valid, msg = validate_image_quality(image)
            if not is_valid:
                logger.warning(f"Page {page_num} validation failed: {msg}")
                continue

            image = deskew_image(image)

            if mime_type == "application/pdf":
                image.info["dpi"] = (300, 300)
            image = render_image_at_dpi(image, target_dpi=300)

            ocr_result = run_tesseract_ocr(image, page_num=page_num)
            if ocr_result:
                words, text, _ = ocr_result
                all_words.extend(words)
                raw_texts.append((page_num, text))

        return all_words, raw_texts, len(rendered.images)

    def _try_tesseract(
        self,
        content: bytes,
        mime_type: str,
        doc_type: DocType | None = None,
        *,
        pages: tuple[list[OcrWord], list[tuple[int, str]], int] | None = None,
        dropped: Counter[str] | None = None,
    ) -> OcrPayload | None:
        """Try Tesseract; `pages` supplies precomputed OCR, `dropped` counts invalid values."""
        logger.debug("Attempting Tesseract OCR")

        try:
            all_words, raw_texts, page_count = (
                pages if pages is not None else self._ocr_pages(content, mime_type)
            )

            if not all_words:
                logger.debug("Tesseract extracted no words")
                self._tesseract_results = ({}, 0.0, [])
                return None

            combined_text = "\n".join(text for _, text in raw_texts)
            page_confidences: dict[int, list[float]] = {}
            for word in all_words:
                page_confidences.setdefault(word.page, []).append(word.confidence)
            fields = {}
            for page_num, page_text in raw_texts:
                page_confidence = sum(page_confidences[page_num]) / len(page_confidences[page_num])
                for key, field in extract_fields_from_text(page_text, dropped).items():
                    field.confidence = min(field.confidence, page_confidence)
                    if key not in fields or field.confidence > fields[key].confidence:
                        fields[key] = (field, page_num)

            mean_confidence = sum(word.confidence for word in all_words) / len(all_words)
            required_key_fields = DOC_TYPE_KEY_FIELDS.get(doc_type)
            if required_key_fields is None:
                missing_key_fields = not KEY_FIELDS.intersection(fields)
                missing_fields = set() if not missing_key_fields else KEY_FIELDS
            else:
                missing_fields = {
                    required
                    for required in required_key_fields
                    if REQUIRED_FIELD_ALIASES.get(required, required) not in fields
                }
                missing_key_fields = bool(missing_fields)

            if mean_confidence < LOW_CONFIDENCE_THRESHOLD or missing_key_fields:
                logger.debug(
                    f"Tesseract confidence {mean_confidence:.2f} below threshold or "
                    f"missing required fields {missing_fields}; "
                    "will use LLM fallback"
                )
                self._tesseract_results = (fields, mean_confidence, all_words)
                return None

            ocr_fields = [
                OcrField(
                    key=field.key, value=field.value, confidence=field.confidence, page=page_num
                )
                for field, page_num in fields.values()
            ]

            # Create bounding boxes from words
            bboxes = [
                BBox(text=w.text, page=w.page, x=w.x, y=w.y, w=w.w, h=w.h)
                for w in all_words[:100]  # Limit to first 100 for payload size
            ]

            return OcrPayload(
                agent=OCR_AGENT,
                agent_version=OCR_VERSION,
                status=AgentStatus.OK,
                confidence=_field_confidence(ocr_fields, page_count),
                model="tesseract",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                fields=ocr_fields,
                raw_text=combined_text,
                bounding_boxes=bboxes,
                pages=page_count,
                used_text_layer=False,
            )

        except (
            OCRError,
            OSError,
            TypeError,
            ValueError,
            TesseractError,
            TesseractNotFoundError,
        ) as e:
            logger.debug(f"Tesseract OCR failed: {e}")
            return None

    def _try_llm_fallback(self, content: bytes, mime_type: str, started_at: datetime) -> OcrPayload:
        """Try LLM fallback for structured field extraction."""
        logger.debug("Using LLM fallback for OCR")

        try:
            # Render document to image
            rendered = _render_ocr_document(content, mime_type)

            # Use first image for LLM
            if not rendered.images:
                raise OCRError("No images to process")

            # Load and invoke prompt
            prompt = self.prompt_loader.load("ocr", OCR_PROMPT_VERSION)

            result = prompt.invoke(
                self.gateway,
                self.settings,
                [OCR_MESSAGE],
                rendered.images,
                OcrLLMOutput,
            )

            if not isinstance(result, OcrPayload):
                raise OCRError(f"Unexpected LLM response type: {type(result)}")

            result = OcrPayload.model_validate(result.model_dump(mode="python"))

            # Set timing
            result.started_at = started_at
            result.finished_at = datetime.now(UTC)

            # Merge with Tesseract results if available
            if self._tesseract_results is not None:
                result = self._merge_results(result, self._tesseract_results)

            return result

        except ValidationError as e:
            logger.error(f"LLM response validation failed: {e}")
            raise OCRError(f"Invalid LLM response: {e}")
        except (LLMError, OSError, TypeError, ValueError) as e:
            logger.error(f"LLM fallback failed: {e}")
            raise OCRError(str(e))

    def _merge_results(self, llm_result: OcrPayload, tesseract_results: tuple) -> OcrPayload:
        """
        Merge LLM and Tesseract results, preferring higher confidence per field.

        Args:
            llm_result: OcrPayload from LLM
            tesseract_results: Tuple of (fields_dict, confidence, words)

        Returns:
            Merged OcrPayload
        """
        tesseract_fields, _, tesseract_words = tesseract_results

        # Create merged field list, preferring LLM where confidence higher
        merged_fields_dict = {}

        # Start with LLM fields
        for field in llm_result.fields:
            merged_fields_dict[field.key] = field

        # Add/replace with Tesseract fields if higher confidence
        for key, (tess_field, page_num) in tesseract_fields.items():
            if not is_valid(key, tess_field.value):
                continue
            if (
                key not in merged_fields_dict
                or tess_field.confidence > merged_fields_dict[key].confidence
            ):
                merged_fields_dict[key] = OcrField(
                    key=key,
                    value=tess_field.value,
                    confidence=tess_field.confidence,
                    page=page_num,
                )

        total_pages = max(
            llm_result.pages,
            max((word.page for word in tesseract_words), default=0),
        )
        merged_confidence = _field_confidence(list(merged_fields_dict.values()), total_pages)

        return OcrPayload(
            agent=llm_result.agent,
            agent_version=llm_result.agent_version,
            status=llm_result.status,
            confidence=merged_confidence,
            model=f"{llm_result.model}+tesseract",
            started_at=llm_result.started_at,
            finished_at=datetime.now(UTC),
            fields=list(merged_fields_dict.values()),
            raw_text=llm_result.raw_text,
            bounding_boxes=llm_result.bounding_boxes
            + [
                BBox(text=w.text, page=w.page, x=w.x, y=w.y, w=w.w, h=w.h)
                for w in tesseract_words[:50]
            ],
            pages=llm_result.pages,
            used_text_layer=False,
        )


def _field_confidence(fields: list[OcrField], page_count: int) -> float:
    if not fields or page_count <= 0:
        return 0.0
    mean_field_confidence = sum(field.confidence for field in fields) / len(fields)
    covered_pages = len({field.page for field in fields})
    return mean_field_confidence * covered_pages / page_count


def _error_payload(message: str, started_at: datetime) -> OcrPayload:
    return OcrPayload(
        agent=OCR_AGENT,
        agent_version=OCR_VERSION,
        status=AgentStatus.ERROR,
        confidence=0.0,
        model=None,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        error=message,
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=0,
        used_text_layer=False,
    )


def _render_ocr_document(content: bytes, mime_type: str) -> RenderedDocument:
    normalized_mime_type = mime_type.split(";", maxsplit=1)[0].strip().lower()
    if normalized_mime_type == "application/pdf":
        try:
            document = pymupdf.open(stream=content, filetype="pdf")
            with document:
                page_images = []
                for index in range(document.page_count):
                    pixmap = document.load_page(index).get_pixmap(
                        matrix=pymupdf.Matrix(300 / 72, 300 / 72), alpha=False
                    )
                    image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                    image_bytes = BytesIO()
                    image.save(image_bytes, format="PNG", dpi=(300, 300))
                    page_images.append(image_bytes.getvalue())
                images = tuple(page_images)
                return RenderedDocument(images=images, page_count=document.page_count)
        except Exception as error:
            raise OCRError("The PDF could not be rendered for OCR") from error

    if normalized_mime_type in {"image/tiff", "image/tif"}:
        try:
            with Image.open(BytesIO(content)) as source:
                page_count = getattr(source, "n_frames", 1)
                images = []
                for page_index in range(page_count):
                    source.seek(page_index)
                    source.load()
                    output = BytesIO()
                    source.convert("RGB").save(output, format="PNG", dpi=(300, 300))
                    images.append(output.getvalue())
                return RenderedDocument(images=tuple(images), page_count=page_count)
        except Exception as error:
            raise OCRError("The TIFF could not be rendered for OCR") from error

    return render_document(content, normalized_mime_type)
