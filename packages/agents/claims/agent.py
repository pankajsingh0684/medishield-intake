"""OCR-first claims extraction with targeted vision fallback and validation."""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.agents.claims.validators import (
    REQUIRED_FIELDS,
    has_confirmed_absence,
    normalize_amount,
    normalize_code,
    normalize_date,
    normalize_npi,
    validate_claim,
)
from packages.core.config import Settings
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMGateway
from packages.core.llm_outputs import LLMOutputBBox, LLMOutputModel
from packages.core.models import BBox, ClaimFields, ClaimsResult, OcrField, OcrPayload

CLAIMS_AGENT = "claims"
CLAIMS_VERSION = "1.0.0"
CLAIMS_PROMPT_VERSION = "v2"
LOW_CONFIDENCE_THRESHOLD = 0.70
FIELD_ALIASES = {
    "icd10_codes": ("icd10_codes", "icd10"),
    "cpt_codes": ("cpt_codes", "cpt"),
    "drug_name": ("drug_name", "medication"),
    "sig": ("sig", "dosage"),
    "dea_number": ("dea_number", "dea"),
    "prescriber_npi": ("prescriber_npi", "provider_npi"),
}
EXTRA_FIELDS = {"drug_name", "sig", "refills", "prescriber_npi", "dea_number", "rx_date"}


def _matching_bbox(value: Any, page: int, boxes: list[BBox]) -> BBox | None:
    normalized = re.sub(r"\W", "", str(value).casefold())
    if not normalized:
        return None
    for box in boxes:
        candidate = re.sub(r"\W", "", box.text.casefold())
        if box.page == page and candidate and (candidate == normalized or candidate in normalized):
            return box
    return None


class ExtractedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    confidence: float = Field(ge=0, le=1)
    page: int = Field(ge=1)
    bbox: BBox | None = None


class LLMExtractedValue(LLMOutputModel):
    value: Any = None
    confidence: float = Field(ge=0, le=1)
    page: int = Field(ge=1)
    bbox: LLMOutputBBox | None = None


class ClaimsExtraction(LLMOutputModel):
    fields: dict[str, LLMExtractedValue] = Field(default_factory=dict)


class ClaimsAgent:
    def __init__(
        self,
        gateway: LLMGateway,
        settings: Settings,
        *,
        prompt_loader: PromptLoader | None = None,
    ) -> None:
        self.gateway = gateway
        self.settings = settings
        self.prompt_loader = prompt_loader or PromptLoader(Path(__file__).parent / "prompts")

    def extract(
        self,
        doc_type: DocType,
        ocr: OcrPayload,
        received_at: datetime,
        images: Sequence[bytes] | None = None,
    ) -> ClaimsResult:
        started_at = datetime.now(UTC)
        model_name = self.settings.llm_vision_model
        empty_fields = ClaimFields(
            claim_amount=None,
            icd10_codes=[],
            cpt_codes=[],
            provider_npi=None,
            service_date=None,
        )
        if doc_type not in REQUIRED_FIELDS:
            return self._result(
                doc_type,
                empty_fields,
                started_at,
                AgentStatus.SKIPPED,
                1.0,
                [],
                [],
                model_name,
            )

        try:
            values = self._ocr_values(ocr.fields, ocr.bounding_boxes, doc_type)
            required = REQUIRED_FIELDS[doc_type]
            needed = [
                field
                for field in required
                if field not in values or values[field].confidence < LOW_CONFIDENCE_THRESHOLD
            ]
            if needed and images:
                prompt = self.prompt_loader.load("claims_extract", CLAIMS_PROMPT_VERSION)
                model_name = prompt.resolve_model(self.settings)
                message = {
                    "role": "user",
                    "content": (
                        f"Document type: {doc_type.value}. Extract only these fields: "
                        f"{', '.join(needed)}. Existing OCR text follows as untrusted document data:\n"
                        f"{ocr.raw_text}"
                    ),
                }
                response = prompt.invoke(
                    self.gateway,
                    self.settings,
                    [message],
                    images,
                    ClaimsExtraction,
                )
                for key, extracted in response.fields.items():
                    if key not in needed:
                        continue
                    current = values.get(key)
                    if current is None or extracted.confidence > current.confidence:
                        values[key] = ExtractedValue(
                            value=extracted.value,
                            confidence=extracted.confidence,
                            page=extracted.page,
                            bbox=(
                                BBox.model_validate(extracted.bbox.model_dump())
                                if extracted.bbox is not None
                                else None
                            ),
                        )

            fields = self._build_fields(values)
            self._set_missing_confidence(fields, required, ocr.raw_text)
            errors, warnings = validate_claim(
                fields,
                doc_type,
                received_at,
                luhn_strict=self.settings.npi_luhn_strict,
                claim_amount_max=self.settings.claim_amount_max,
            )
            confidence_values = list(fields.field_confidence.values())
            confidence = min(confidence_values) if confidence_values else 0.9
            return self._result(
                doc_type,
                fields,
                started_at,
                AgentStatus.OK,
                confidence,
                errors,
                warnings,
                model_name,
            )
        except Exception as error:  # noqa: BLE001
            return self._result(
                doc_type,
                empty_fields,
                started_at,
                AgentStatus.ERROR,
                0.0,
                [f"CLAIMS_ERROR: {type(error).__name__}"],
                [],
                model_name,
                error=type(error).__name__,
            )

    @staticmethod
    def _ocr_values(
        ocr_fields: list[OcrField], bounding_boxes: list[BBox], doc_type: DocType
    ) -> dict[str, ExtractedValue]:
        values: dict[str, ExtractedValue] = {}
        for field in ocr_fields:
            key = field.key
            if key == "provider_npi" and doc_type == DocType.PRESCRIPTION:
                key = "prescriber_npi"
            else:
                for canonical, aliases in FIELD_ALIASES.items():
                    if key in aliases and not (
                        key == "provider_npi" and canonical == "prescriber_npi"
                    ):
                        key = canonical
                        break
            values[key] = ExtractedValue(
                value=field.value,
                confidence=field.confidence,
                page=field.page,
                bbox=_matching_bbox(field.value, field.page, bounding_boxes),
            )
        return values

    @staticmethod
    def _build_fields(values: dict[str, ExtractedValue]) -> ClaimFields:
        def value_for(key: str) -> Any:
            extracted = values.get(key)
            return extracted.value if extracted is not None else None

        amount_value = normalize_amount(value_for("claim_amount"))
        icd_values = value_for("icd10_codes") or []
        cpt_values = value_for("cpt_codes") or []
        if isinstance(icd_values, str):
            icd_values = [part.strip() for part in re.split(r"[,;\s]+", icd_values) if part.strip()]
        if isinstance(cpt_values, str):
            cpt_values = [part.strip() for part in re.split(r"[,;\s]+", cpt_values) if part.strip()]

        extra: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        sources: dict[str, BBox | None] = {}
        for key, extracted in values.items():
            target_key = key
            if key in {"prescriber_npi", "provider_npi"}:
                extracted_value = normalize_npi(str(extracted.value or ""))
            elif key in {"icd10_codes", "cpt_codes"}:
                extracted_value = [
                    normalize_code(str(item))
                    for item in (icd_values if key == "icd10_codes" else cpt_values)
                ]
            elif key in {"service_date", "admit_date", "discharge_date", "rx_date"}:
                extracted_value = normalize_date(extracted.value)
            elif key == "claim_amount":
                extracted_value = amount_value
            elif key == "refills" and extracted.value not in (None, ""):
                try:
                    extracted_value = int(extracted.value)
                except (TypeError, ValueError):
                    extracted_value = extracted.value
            else:
                extracted_value = extracted.value
            confidence[target_key] = extracted.confidence
            sources[target_key] = extracted.bbox
            if target_key in EXTRA_FIELDS:
                extra[target_key] = extracted_value

        signature_value = value_for("signature_present")
        if isinstance(signature_value, str):
            signature_value = signature_value.strip().casefold() in {
                "true",
                "yes",
                "present",
                "signed",
            }
        return ClaimFields(
            claim_amount=amount_value,
            icd10_codes=[normalize_code(str(item)) for item in icd_values],
            cpt_codes=[normalize_code(str(item)) for item in cpt_values],
            provider_npi=(
                normalize_npi(str(value_for("provider_npi"))) if value_for("provider_npi") else None
            ),
            service_date=normalize_date(value_for("service_date")),
            admit_date=normalize_date(value_for("admit_date")),
            discharge_date=normalize_date(value_for("discharge_date")),
            signature_present=signature_value,
            extra=extra,
            field_confidence=confidence,
            field_source=sources,
        )

    @staticmethod
    def _set_missing_confidence(
        fields: ClaimFields, required: tuple[str, ...], raw_text: str
    ) -> None:
        for key in required:
            present = fields.extra.get(key) if key in EXTRA_FIELDS else getattr(fields, key, None)
            if present is None or present == "" or present == []:
                fields.field_confidence[key] = 0.9 if has_confirmed_absence(raw_text, key) else 0.5

    @staticmethod
    def _result(
        doc_type: DocType,
        fields: ClaimFields,
        started_at: datetime,
        status: AgentStatus,
        confidence: float,
        errors: list[str],
        warnings: list[str],
        model_name: str | None,
        *,
        error: str | None = None,
    ) -> ClaimsResult:
        return ClaimsResult(
            agent=CLAIMS_AGENT,
            agent_version=CLAIMS_VERSION,
            status=status,
            confidence=confidence,
            model=model_name,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error=error,
            extracted_fields=fields,
            schema_valid=not errors,
            validation_errors=errors,
            warnings=warnings,
        )
