import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import BaseModel

from packages.agents.kyc.agent import KycAgent
from packages.core.config import Settings
from packages.core.db.models import Member, Policy
from packages.core.enums import AgentStatus, DocType
from packages.core.identity import name_similarity, normalize_name
from packages.core.llm.fixtures import FixtureStore
from packages.core.llm.gateway import Gateway, StubProvider
from packages.core.models import BBox, OcrField, OcrPayload
from scripts.make_kyc_fixtures import generate_fixtures

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "data" / "synthetic" / "dataset"
RECEIVED_AT = datetime(2025, 2, 20, tzinfo=UTC)
MEDICARE_IMAGE = DATASET_DIR / "id_documents" / "id_PT_20745.png"


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


def seeded_members() -> list[Member]:
    clusters = json.loads((DATASET_DIR / "clusters.json").read_text(encoding="utf-8"))
    return [
        Member(
            member_id=cluster["patient_id"],
            full_name=cluster["name"],
            date_of_birth=datetime.strptime(cluster["dob"], "%m/%d/%Y").date(),
            policy_number=cluster["policy"],
            policy_id=uuid5(NAMESPACE_URL, f"medishield:dataset:policy:{cluster['policy']}"),
            status="ACTIVE",
            id_doc_expiry=None,
        )
        for cluster in clusters
    ]


class SeededMemberRepo:
    def __init__(self) -> None:
        self.members = seeded_members()
        self.policies = {
            member.policy_id: Policy(policy_id=member.policy_id) for member in self.members
        }

    def get(self, member_id: str) -> Member | None:
        return next((member for member in self.members if member.member_id == member_id), None)

    def get_by_policy_number(self, policy_number: str) -> Member | None:
        return next(
            (member for member in self.members if member.policy_number == policy_number), None
        )

    def get_by_date_of_birth(self, date_of_birth: date) -> list[Member]:
        return [member for member in self.members if member.date_of_birth == date_of_birth]

    def get_policy(self, member: Member) -> Policy | None:
        return self.policies.get(member.policy_id)


class FixedGateway:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    def complete_json(self, model, system, messages, images, schema, **kwargs) -> BaseModel:
        self.calls += 1
        return schema.model_validate(self.response)


def make_ocr(
    fields: list[OcrField], raw_text: str = "", boxes: list[BBox] | None = None
) -> OcrPayload:
    return OcrPayload(
        agent="ocr",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        model="test-ocr",
        started_at=RECEIVED_AT,
        finished_at=RECEIVED_AT,
        fields=fields,
        raw_text=raw_text,
        bounding_boxes=boxes or [],
        pages=1,
        used_text_layer=True,
    )


def make_agent(response: dict[str, Any] | None = None, repo=None) -> tuple[KycAgent, FixedGateway]:
    gateway = FixedGateway(response or {})
    # Default response is a clean tamper assessment for image-backed cases.
    if response is None:
        gateway.response = {
            "tampering_detected": False,
            "confidence": 0.98,
            "expired_banner": False,
        }
    return KycAgent(repo or SeededMemberRepo(), gateway, make_settings()), gateway


def id_fields(
    member_id: str = "PT_20745",
    *,
    name: str = "John Johnson X.",
    dob: str = "01/02/1965",
    policy: str = "MED-GLD-1954280",
    expiry: str | None = None,
) -> list[OcrField]:
    fields = [
        OcrField(key="member_id", value=member_id, confidence=0.95, page=1),
        OcrField(key="member_name", value=name, confidence=0.95, page=1),
        OcrField(key="dob", value=dob, confidence=0.95, page=1),
        OcrField(key="policy_number", value=policy, confidence=0.95, page=1),
    ]
    if expiry:
        fields.append(OcrField(key="id_expiry", value=expiry, confidence=0.95, page=1))
    return fields


def test_seeded_one_vowel_name_change_is_flagged_even_with_high_similarity():
    agent, _ = make_agent()

    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr(
            id_fields(
                member_id="PT_39451",
                name="Sindra Hall C.",
                dob="09/25/1993",
                policy="MED-GLD-5446912",
            )
        ),
        RECEIVED_AT,
    )

    name_flag = next(flag for flag in result.flags if flag.code == "NAME_MISMATCH")
    assert name_similarity("Sindra Hall C.", "Sandra Hall C.") >= 0.85
    assert name_flag.severity == "MEDIUM"
    assert result.kyc_passed


@pytest.mark.parametrize("name", ["john johnson x", "Johnson John", "John X. Johnson"])
def test_normalized_name_variations_match(name: str):
    agent, _ = make_agent()
    fields = id_fields(name=name)

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT)

    assert "NAME_MISMATCH" not in {flag.code for flag in result.flags}
    assert normalize_name(name) == normalize_name("John Johnson X.")


def test_lookup_uses_policy_number_when_member_id_is_absent():
    agent, _ = make_agent()

    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr([OcrField(key="policy_number", value="MED-GLD-1954280", confidence=0.9, page=1)]),
        RECEIVED_AT,
    )

    assert result.member_ref == "PT_20745"
    assert "MEMBER_NOT_FOUND" not in {flag.code for flag in result.flags}


def test_lookup_uses_dob_and_name_when_document_has_no_identifier():
    agent, _ = make_agent()
    fields = [
        OcrField(key="dob", value="01/02/1965", confidence=0.9, page=1),
        OcrField(key="member_name", value="John Johnson X.", confidence=0.9, page=1),
    ]

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT)

    assert result.member_ref == "PT_20745"


def test_dob_name_fallback_requires_ratio_of_at_least_point_eight():
    agent, _ = make_agent()
    fields = [
        OcrField(key="dob", value="01/02/1965", confidence=0.9, page=1),
        OcrField(key="member_name", value="Completely Different Person", confidence=0.9, page=1),
    ]

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT)

    assert result.member_ref is None
    assert "MEMBER_NOT_FOUND" in {flag.code for flag in result.flags}


@pytest.mark.parametrize(
    ("fields", "raw_text", "expected"),
    [
        ([], "", "MEMBER_NOT_FOUND"),
        (id_fields(dob="01/03/1965"), "", "DOB_MISMATCH"),
        (id_fields(policy="WRONG-POLICY"), "", "POLICY_MISMATCH"),
        (id_fields(expiry="2025-02-19"), "", "ID_EXPIRED"),
        (id_fields(expiry="2025-03-10"), "", "ID_EXPIRING_SOON"),
    ],
)
def test_each_data_flag_alone(fields, raw_text, expected):
    agent, _ = make_agent()

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields, raw_text), RECEIVED_AT)

    assert expected in {flag.code for flag in result.flags}
    assert result.kyc_passed is (expected == "ID_EXPIRING_SOON")


def test_expiring_soon_is_low_and_does_not_fail_kyc():
    agent, _ = make_agent()
    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr(id_fields(expiry="2025-03-22")),
        RECEIVED_AT,
    )

    flag = next(flag for flag in result.flags if flag.code == "ID_EXPIRING_SOON")
    assert flag.severity == "LOW"
    assert result.kyc_passed


def test_combined_high_flags_and_tamper_are_failed():
    agent, _ = make_agent(
        {"tampering_detected": True, "confidence": 0.9, "evidence": "Altered text", "page": 1}
    )
    fields = id_fields(
        member_id="PT_39451", name="Sindra Hall C.", dob="09/24/1993", expiry="2025-02-19"
    )

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT, [b"image"])

    flags = {flag.code: flag for flag in result.flags}
    assert {"NAME_MISMATCH", "DOB_MISMATCH", "ID_EXPIRED", "TAMPER_SUSPECTED"} <= flags.keys()
    assert flags["TAMPER_SUSPECTED"].severity == "HIGH"
    assert not result.kyc_passed


def test_tamper_only_is_medium_and_never_fails_kyc():
    agent, _ = make_agent(
        {"tampering_detected": True, "confidence": 0.9, "evidence": "Font mismatch"}
    )
    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr(id_fields(expiry="2030-01-01")),
        RECEIVED_AT,
        [b"image"],
    )

    flag = next(flag for flag in result.flags if flag.code == "TAMPER_SUSPECTED")
    assert flag.severity == "MEDIUM"
    assert result.kyc_passed
    assert result.confidence == 0.6


def test_absent_fields_are_skipped_after_an_identifier_matches():
    agent, _ = make_agent()
    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr([OcrField(key="member_id", value="PT_20745", confidence=0.9, page=1)]),
        RECEIVED_AT,
    )

    assert not {"DOB_MISMATCH", "NAME_MISMATCH", "POLICY_MISMATCH"} & {
        flag.code for flag in result.flags
    }
    assert result.confidence == 1.0


def test_confidence_uses_largest_flag_penalty_floor_and_no_identifier_cap():
    no_identifier_agent, _ = make_agent()
    absent = no_identifier_agent.check(DocType.ID_DOCUMENT, make_ocr([]), RECEIVED_AT)
    floor_agent, _ = make_agent()
    floor_fields = id_fields(
        member_id="PT_39451",
        name="Sandra Hall C.",
        dob="09/25/1993",
        policy="MED-GLD-5446912",
        expiry="2025-02-19",
    )
    floor = floor_agent.check(DocType.ID_DOCUMENT, make_ocr(floor_fields), RECEIVED_AT)

    assert absent.confidence == pytest.approx(0.45)
    assert floor.confidence == 0.1


def test_medicare_expired_banner_is_detected_from_ocr_before_vision():
    agent, gateway = make_agent(
        {"tampering_detected": False, "confidence": 0.9, "expired_banner": False}
    )
    image = MEDICARE_IMAGE.read_bytes()
    result = agent.check(
        DocType.ID_DOCUMENT,
        make_ocr(id_fields(), "MEDICARE CARD EXPIRED"),
        RECEIVED_AT,
        [image],
    )

    assert "ID_EXPIRED" in {flag.code for flag in result.flags}
    assert gateway.calls == 1


def test_dataset_medicare_card_uses_vision_for_banner_when_ocr_misses_card_label():
    agent, _ = make_agent({"tampering_detected": False, "confidence": 0.9, "expired_banner": True})
    image = MEDICARE_IMAGE.read_bytes()
    fields = [
        OcrField(key="member_name", value="John Johnson X.", confidence=0.9, page=1),
        OcrField(key="dob", value="01/02/1965", confidence=0.9, page=1),
    ]

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT, [image])

    assert "ID_EXPIRED" in {flag.code for flag in result.flags}
    assert result.member_ref == "PT_20745"


def test_generated_stub_tamper_fixture_is_repeatable_and_nonblocking(tmp_path: Path):
    first_paths = generate_fixtures(DATASET_DIR, tmp_path)
    first_payloads = {path.name: path.read_bytes() for path in first_paths}
    second_paths = generate_fixtures(DATASET_DIR, tmp_path)
    assert first_payloads == {path.name: path.read_bytes() for path in second_paths}

    repo = SeededMemberRepo()
    member = repo.get("PT_57795")
    assert member is not None and member.date_of_birth is not None
    fields = [
        OcrField(key="member_id", value=member.member_id, confidence=0.95, page=1),
        OcrField(key="member_name", value=member.full_name or "", confidence=0.95, page=1),
        OcrField(key="dob", value=member.date_of_birth.isoformat(), confidence=0.95, page=1),
        OcrField(key="policy_number", value=member.policy_number, confidence=0.95, page=1),
        OcrField(key="id_expiry", value="2030-01-01", confidence=0.95, page=1),
    ]
    gateway = Gateway(StubProvider(FixtureStore(tmp_path)))
    agent = KycAgent(repo, gateway, make_settings())
    image = (DATASET_DIR / "id_documents" / "id_PT_57795.png").read_bytes()

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT, [image])

    tamper = next(flag for flag in result.flags if flag.code == "TAMPER_SUSPECTED")
    assert tamper.severity == "MEDIUM"
    assert result.kyc_passed
    assert result.raw_response_ref is not None


def test_generated_medicare_stub_fixture_detects_banner_when_ocr_misses_it(tmp_path: Path):
    generate_fixtures(DATASET_DIR, tmp_path)
    gateway = Gateway(StubProvider(FixtureStore(tmp_path)))
    agent = KycAgent(SeededMemberRepo(), gateway, make_settings())
    image = MEDICARE_IMAGE.read_bytes()
    fields = [
        OcrField(key="member_name", value="John Johnson X.", confidence=0.9, page=1),
        OcrField(key="dob", value="01/02/1965", confidence=0.9, page=1),
    ]

    result = agent.check(DocType.ID_DOCUMENT, make_ocr(fields), RECEIVED_AT, [image])

    assert "ID_EXPIRED" in {flag.code for flag in result.flags}
    assert result.member_ref == "PT_20745"


@pytest.mark.parametrize(
    ("effective_from", "effective_to", "service_date"),
    [
        (date(2025, 3, 1), None, "2025-02-01"),
        (None, date(2025, 2, 1), "2025-02-20"),
    ],
)
def test_policy_effective_bounds_are_checked_on_service_date(
    effective_from: date | None,
    effective_to: date | None,
    service_date: str,
):
    repo = SeededMemberRepo()
    member = repo.get("PT_20745")
    assert member is not None
    policy = repo.get_policy(member)
    assert policy is not None
    policy.effective_from = effective_from
    policy.effective_to = effective_to
    agent, _ = make_agent(repo=repo)
    fields = id_fields(expiry="2030-01-01") + [
        OcrField(key="service_date", value=service_date, confidence=0.9, page=1)
    ]

    result = agent.check(DocType.CLAIM_FORM, make_ocr(fields), RECEIVED_AT)

    assert "POLICY_MISMATCH" in {flag.code for flag in result.flags}


@pytest.mark.parametrize("doc_type", [DocType.DISCHARGE_SUMMARY, DocType.PRESCRIPTION])
def test_member_match_only_mode_skips_policy_expiry_and_tamper(doc_type: DocType):
    agent, gateway = make_agent({"tampering_detected": True, "confidence": 0.9})
    result = agent.check(
        doc_type,
        make_ocr(id_fields(dob="01/03/1965", policy="WRONG", expiry="2020-01-01")),
        RECEIVED_AT,
        [b"image"],
    )

    assert {flag.code for flag in result.flags} == {"DOB_MISMATCH"}
    assert gateway.calls == 0


def test_unknown_document_type_is_skipped():
    agent, _ = make_agent()
    result = agent.check(DocType.UNKNOWN, make_ocr([]), RECEIVED_AT)
    assert result.status == AgentStatus.SKIPPED
