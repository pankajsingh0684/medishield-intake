"""Member identity and document-integrity checks."""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from packages.core.config import Settings
from packages.core.db.models import Member
from packages.core.db.repositories import MemberRepo
from packages.core.enums import AgentStatus, DocType
from packages.core.identity import (
    DOB_NAME_LOOKUP_THRESHOLD,
    NAME_MISMATCH_HIGH_PENALTY_THRESHOLD,
    NAME_MISMATCH_MEDIUM_THRESHOLD,
    name_similarity,
    normalize_name,
    parse_identity_date,
)
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMGateway
from packages.core.llm_outputs import LLMOutputBBox, LLMOutputModel
from packages.core.models import BBox, KycFlag, KycResult, OcrField, OcrPayload

KYC_AGENT = "kyc"
KYC_VERSION = "1.0.0"
KYC_PROMPT_VERSION = "v2"
SEEDED_MEMBER_ID_PATTERN = re.compile(r"(?:PT_\d{5}|PT_EX\d{4})\Z")
SEEDED_POLICY_NUMBER_PATTERN = re.compile(r"(?:MED-GLD-\d{7}|MED-SLV-RETRIEVAL)\Z")
KNOWN_POLICY_PREFIXES = ("MED-GLD", "MED-SLV")
MEMBER_MATCH_ONLY_TYPES = {DocType.DISCHARGE_SUMMARY, DocType.PRESCRIPTION}
PROCESSED_TYPES = {
    DocType.ID_DOCUMENT,
    DocType.CLAIM_FORM,
    DocType.POLICY_AMENDMENT,
    *MEMBER_MATCH_ONLY_TYPES,
}
ID_EXPIRING_SOON_DAYS = 30
TAMPER_CORROBORATING_FLAGS = {"NAME_MISMATCH", "DOB_MISMATCH", "ID_EXPIRED"}
KYC_MESSAGE = {
    "role": "user",
    "content": (
        "Inspect the supplied document image for visual tampering. If it is a Medicare card, "
        "also report whether an EXPIRED banner is visible."
    ),
}
FLAG_PENALTIES = {
    "MEMBER_NOT_FOUND": 0.55,
    "DOB_MISMATCH": 0.65,
    "POLICY_MISMATCH": 0.65,
    "ID_EXPIRED": 0.90,
    "ID_EXPIRING_SOON": 0.10,
}


def _within_one_edit(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) == 1
    shorter, longer = sorted((left, right), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def correct_policy_number(policy_number: str) -> str:
    """Fix a plan prefix within edit distance 1 of exactly one known prefix."""
    prefix, separator, tail = policy_number.strip().upper().rpartition("-")
    if not separator or prefix in KNOWN_POLICY_PREFIXES:
        return policy_number.strip()
    matches = [known for known in KNOWN_POLICY_PREFIXES if _within_one_edit(prefix, known)]
    if len(matches) != 1:
        return policy_number.strip()
    return f"{matches[0]}-{tail}"


class TamperAssessment(LLMOutputModel):
    tampering_detected: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None
    affected_page: int | None = Field(default=None, ge=1)
    affected_bbox: LLMOutputBBox | None = None
    expired_banner_visible: bool | None = None
    raw_response_ref: str | None = None


class KycAgent:
    def __init__(
        self,
        member_repo: MemberRepo,
        gateway: LLMGateway,
        settings: Settings,
        *,
        prompt_loader: PromptLoader | None = None,
    ) -> None:
        self.member_repo = member_repo
        self.gateway = gateway
        self.settings = settings
        self.prompt_loader = prompt_loader or PromptLoader(Path(__file__).parent / "prompts")

    def check(
        self,
        doc_type: DocType,
        ocr: OcrPayload,
        received_at: datetime,
        images: Sequence[bytes] | None = None,
    ) -> KycResult:
        started_at = datetime.now(UTC)
        if doc_type not in PROCESSED_TYPES:
            return self._result(
                started_at,
                AgentStatus.SKIPPED,
                True,
                [],
                1.0,
                None,
                self.settings.llm_vision_model,
            )

        model_name = self.settings.llm_vision_model
        try:
            fields = self._field_map(ocr.fields)
            member, lookup_name_ratio = self._find_member(fields, doc_type)
            flags: list[KycFlag] = []
            if member is None:
                flags.append(
                    KycFlag(
                        code="MEMBER_NOT_FOUND",
                        severity="HIGH",
                        evidence=self._field_evidence("member_id", fields, ocr.bounding_boxes)
                        or self._field_evidence("policy_number", fields, ocr.bounding_boxes)
                        or "No matching member was found",
                    )
                )
            else:
                self._check_member_fields(member, fields, ocr, received_at, flags)
                if doc_type not in MEMBER_MATCH_ONLY_TYPES:
                    self._check_policy(member, fields, received_at, flags, doc_type)

            visual: TamperAssessment | None = None
            if doc_type not in MEMBER_MATCH_ONLY_TYPES and images:
                prompt = self.prompt_loader.load("kyc_tamper", KYC_PROMPT_VERSION)
                model_name = prompt.resolve_model(self.settings)
                visual = prompt.invoke(
                    self.gateway,
                    self.settings,
                    [KYC_MESSAGE],
                    images,
                    TamperAssessment,
                )

            if doc_type == DocType.ID_DOCUMENT:
                self._check_expiry(member, fields, ocr, received_at, flags, visual)
                if visual is not None and visual.tampering_detected:
                    corroborated = any(flag.code in TAMPER_CORROBORATING_FLAGS for flag in flags)
                    flags.append(
                        KycFlag(
                            code="TAMPER_SUSPECTED",
                            severity="HIGH" if corroborated else "MEDIUM",
                            evidence=self._tamper_evidence(visual),
                        )
                    )

            evidence_fields = {
                "DOB_MISMATCH": "dob",
                "NAME_MISMATCH": "member_name",
                "POLICY_MISMATCH": "policy_number",
                "ID_EXPIRED": "id_expiry",
            }
            reliable_failures = []
            penalties = []
            for flag in flags:
                field = fields.get(evidence_fields.get(flag.code, ""))
                evidence_confidence = field.confidence if field else None
                if flag.code == "ID_EXPIRED" and field is None and visual is not None:
                    evidence_confidence = visual.confidence
                if (
                    flag.severity == "HIGH"
                    and evidence_confidence is not None
                    and evidence_confidence >= 0.7
                ):
                    reliable_failures.append(evidence_confidence)
                else:
                    penalties.append(self._penalty(flag, lookup_name_ratio))
            confidence = max(0.1, 1.0 - max(penalties, default=0.0))
            if reliable_failures:
                confidence = min(confidence, *reliable_failures)
            if not self._has_identifier(fields):
                confidence = min(confidence, 0.55)
            return self._result(
                started_at,
                AgentStatus.OK,
                not any(flag.severity == "HIGH" for flag in flags),
                flags,
                confidence,
                member.member_id if member else None,
                model_name,
                raw_response_ref=visual.raw_response_ref if visual else None,
            )
        except Exception as error:  # noqa: BLE001
            return self._result(
                started_at,
                AgentStatus.ERROR,
                False,
                [],
                0.0,
                None,
                model_name,
                error=str(error) if self.settings.llm_debug_raw else type(error).__name__,
            )

    def _find_member(
        self, fields: dict[str, OcrField], doc_type: DocType
    ) -> tuple[Member | None, float | None]:
        member_id = self._value(fields, "member_id")
        policy_number = self._printed_policy_number(fields)
        if doc_type == DocType.ID_DOCUMENT:
            if member_id and (
                not SEEDED_MEMBER_ID_PATTERN.fullmatch(member_id)
                or SEEDED_POLICY_NUMBER_PATTERN.fullmatch(member_id)
            ):
                member_id = None
            if policy_number and not SEEDED_POLICY_NUMBER_PATTERN.fullmatch(policy_number):
                policy_number = None
        if member_id:
            member = self.member_repo.get(member_id.strip())
            if member is not None:
                return member, None
        if policy_number:
            member = self.member_repo.get_by_policy_number(policy_number.strip())
            if member is not None:
                return member, None

        dob_value = self._value(fields, "dob")
        name_value = self._value(fields, "member_name")
        dob = parse_identity_date(dob_value) if dob_value else None
        if dob is None or not name_value:
            return None, None
        candidates = self.member_repo.get_by_date_of_birth(dob)
        if not candidates:
            return None, None
        member = max(
            candidates,
            key=lambda candidate: name_similarity(name_value, candidate.full_name or ""),
        )
        ratio = name_similarity(name_value, member.full_name or "")
        if ratio < DOB_NAME_LOOKUP_THRESHOLD:
            return None, ratio
        return member, ratio

    def _check_member_fields(
        self,
        member: Member,
        fields: dict[str, OcrField],
        ocr: OcrPayload,
        received_at: datetime,
        flags: list[KycFlag],
    ) -> None:
        dob_value = self._value(fields, "dob")
        if dob_value and member.date_of_birth:
            dob = parse_identity_date(dob_value)
            if not self._valid_identity_dob(dob_value, received_at) or (
                dob is not None and dob != member.date_of_birth
            ):
                flags.append(
                    KycFlag(
                        code="DOB_MISMATCH",
                        severity="HIGH",
                        evidence=self._field_evidence("dob", fields, ocr.bounding_boxes),
                    )
                )

        name_value = self._value(fields, "member_name")
        if name_value and member.full_name:
            normalized_name = normalize_name(name_value)
            normalized_member = normalize_name(member.full_name)
            if normalized_name != normalized_member:
                similarity = name_similarity(name_value, member.full_name)
                flags.append(
                    KycFlag(
                        code="NAME_MISMATCH",
                        severity=(
                            "MEDIUM" if similarity >= NAME_MISMATCH_MEDIUM_THRESHOLD else "HIGH"
                        ),
                        evidence=(
                            self._field_evidence("member_name", fields, ocr.bounding_boxes)
                            + f"; similarity={similarity:.3f}"
                        ),
                    )
                )

    def _check_expiry(
        self,
        member: Member | None,
        fields: dict[str, OcrField],
        ocr: OcrPayload,
        received_at: datetime,
        flags: list[KycFlag],
        visual: TamperAssessment | None,
    ) -> None:
        raw_expired = re.search(r"\bEXPIRED\b", ocr.raw_text, re.IGNORECASE) is not None
        vision_expired = bool(visual and visual.expired_banner_visible)
        expiry_value = self._value(fields, "id_expiry")
        expiry_date = parse_identity_date(expiry_value) if expiry_value else None
        if expiry_date is None and member is not None:
            expiry_date = member.id_doc_expiry
        evidence = (
            self._field_evidence("id_expiry", fields, ocr.bounding_boxes)
            if expiry_value
            else "Medicare EXPIRED banner"
        )
        if raw_expired or vision_expired:
            flags.append(KycFlag(code="ID_EXPIRED", severity="HIGH", evidence=evidence))
            return
        if expiry_date is None:
            return
        reference_date = received_at.date()
        if expiry_date < reference_date:
            flags.append(
                KycFlag(
                    code="ID_EXPIRED",
                    severity="HIGH",
                    evidence=f"id_expiry={expiry_date.isoformat()}; received_at={reference_date}",
                )
            )
        elif (expiry_date - reference_date).days <= ID_EXPIRING_SOON_DAYS:
            flags.append(
                KycFlag(
                    code="ID_EXPIRING_SOON",
                    severity="LOW",
                    evidence=f"id_expiry={expiry_date.isoformat()}; received_at={reference_date}",
                )
            )

    def _check_policy(
        self,
        member: Member,
        fields: dict[str, OcrField],
        received_at: datetime,
        flags: list[KycFlag],
        doc_type: DocType,
    ) -> None:
        policy_number = self._printed_policy_number(fields)
        if (
            doc_type == DocType.ID_DOCUMENT
            and policy_number
            and re.fullmatch(r"[0-9][A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{4}", policy_number)
        ):
            policy_number = None
        mismatch = bool(policy_number and policy_number.strip() != member.policy_number)
        service_value = self._value(fields, "service_date")
        service_date = parse_identity_date(service_value) if service_value else received_at.date()
        if member.status and member.status.casefold() != "active":
            mismatch = True
        policy = self.member_repo.get_policy(member)
        if policy is not None:
            mismatch = mismatch or bool(
                policy.effective_from and service_date < policy.effective_from
            )
            mismatch = mismatch or bool(policy.effective_to and service_date > policy.effective_to)
        if mismatch:
            flags.append(
                KycFlag(
                    code="POLICY_MISMATCH",
                    severity="HIGH",
                    evidence=(
                        f"policy_number={policy_number or '<absent>'}; "
                        f"active_on={service_date.isoformat()}"
                    ),
                )
            )

    @classmethod
    def _printed_policy_number(cls, fields: dict[str, OcrField]) -> str | None:
        value = cls._value(fields, "policy_number")
        return correct_policy_number(value) if value else None

    @staticmethod
    def _field_map(fields: list[OcrField]) -> dict[str, OcrField]:
        aliases = {"date_of_birth": "dob", "name": "member_name"}
        return {aliases.get(field.key, field.key): field for field in fields}

    @staticmethod
    def _value(fields: dict[str, OcrField], key: str) -> str | None:
        field = fields.get(key)
        return field.value.strip() if field and field.value.strip() else None

    @classmethod
    def _field_evidence(cls, key: str, fields: dict[str, OcrField], boxes: list[BBox]) -> str:
        field = fields.get(key)
        if field is None:
            return f"{key}=<absent>"
        value = field.value
        normalized = re.sub(r"\W", "", value.casefold())
        for box in boxes:
            token = re.sub(r"\W", "", box.text.casefold())
            if box.page == field.page and token and (token in normalized or normalized in token):
                return (
                    f"{key}={value!r}; page={box.page}; "
                    f"bbox=({box.x:.4f},{box.y:.4f},{box.w:.4f},{box.h:.4f})"
                )
        return f"{key}={value!r}; page={field.page}"

    @staticmethod
    def _tamper_evidence(visual: TamperAssessment) -> str:
        evidence = visual.evidence or "Vision model detected visual tampering"
        if visual.affected_bbox is not None:
            box = visual.affected_bbox
            return (
                f"{evidence}; page={box.page}; "
                f"bbox=({box.x:.4f},{box.y:.4f},{box.w:.4f},{box.h:.4f})"
            )
        if visual.affected_page is not None:
            return f"{evidence}; page={visual.affected_page}"
        return evidence

    @staticmethod
    def _has_identifier(fields: dict[str, OcrField]) -> bool:
        return any(KycAgent._value(fields, key) for key in ("member_id", "policy_number", "dob"))

    @staticmethod
    def _penalty(flag: KycFlag, lookup_name_ratio: float | None) -> float:
        if flag.code == "TAMPER_SUSPECTED":
            return 0.70 if flag.severity == "HIGH" else 0.40
        if flag.code == "NAME_MISMATCH":
            similarity = lookup_name_ratio
            if similarity is None:
                match = re.search(r"similarity=([0-9.]+)", flag.evidence)
                similarity = float(match.group(1)) if match else 0.0
            if similarity >= NAME_MISMATCH_MEDIUM_THRESHOLD:
                return 0.30
            if similarity >= NAME_MISMATCH_HIGH_PENALTY_THRESHOLD:
                return 0.50
            return 0.70
        return FLAG_PENALTIES.get(flag.code, 0.0)

    @staticmethod
    def _result(
        started_at: datetime,
        status: AgentStatus,
        kyc_passed: bool,
        flags: list[KycFlag],
        confidence: float,
        member_ref: str | None,
        model_name: str | None,
        *,
        raw_response_ref: str | None = None,
        error: str | None = None,
    ) -> KycResult:
        return KycResult(
            agent=KYC_AGENT,
            agent_version=KYC_VERSION,
            status=status,
            confidence=confidence,
            model=model_name,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_response_ref=raw_response_ref,
            error=error,
            kyc_passed=kyc_passed,
            flags=flags,
            member_ref=member_ref,
        )

    def _valid_identity_dob(self, dob_value: str | None, received_at: datetime) -> bool:
        if not dob_value:
            return True
        dob = parse_identity_date(dob_value)
        if dob is None:
            return False
        reference = received_at.date()
        age = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
        return dob <= reference and 0 <= age <= 120
