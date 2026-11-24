import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from packages.agents.policy.agent import (
    PolicyAgent,
    load_cpt_descriptions,
    load_icd10_descriptions,
)
from packages.core.db.models import Member, Policy, PolicyExclusion
from packages.core.db.repositories import MemberRepo, PolicyExclusionRepo
from packages.core.enums import AgentStatus, DocType
from packages.core.models import ClaimFields, ClaimsResult, KycResult, OcrField, OcrPayload
from packages.rag.retrieve import RetrievedChunk

ROOT = Path(__file__).resolve().parents[2]


class FakeRetriever:
    def __init__(self) -> None:
        self.chunks: dict[str, RetrievedChunk] = {}
        self.results: list[RetrievedChunk] | None = None
        self.policy_id = None
        self.service_date = None
        self.queries: list[str] = []
        self.active_until: date | None = None

    def search(self, query: str, policy_id, effective_date: date) -> list[RetrievedChunk]:
        self.queries.append(query)
        self.policy_id = policy_id
        self.service_date = effective_date
        if self.active_until and effective_date > self.active_until:
            return []
        if self.results is not None:
            return self.results
        return [self.chunks["default"]] if "default" in self.chunks else []


class FakeReranker:
    def __init__(self, score: float = 0.9) -> None:
        self.score = score

    def rerank(self, query: str, chunks: list[RetrievedChunk]):
        return [(chunk, self.score) for chunk in chunks]


class FakeGateway:
    def __init__(self, answer: dict[str, object]) -> None:
        self.answer = answer
        self.calls = 0
        self.messages: list[dict[str, str]] = []

    def complete_json(self, model, system, messages, images, schema, **kwargs):
        self.calls += 1
        self.messages.extend(dict(message) for message in messages)
        return schema.model_validate(self.answer)


def _result_fields(
    cpt_codes: list[str], icd10_codes: list[str], service_date: date | None
) -> ClaimFields:
    return ClaimFields(
        claim_amount=None,
        icd10_codes=icd10_codes,
        cpt_codes=cpt_codes,
        provider_npi=None,
        service_date=service_date,
    )


def _envelopes(member_id: str = "MEMBER-1") -> tuple[KycResult, ClaimsResult, OcrPayload]:
    now = datetime.now(UTC)
    kyc = KycResult(
        agent="kyc",
        agent_version="1",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        kyc_passed=True,
        flags=[],
        member_ref=member_id,
    )
    claims = ClaimsResult(
        agent="claims",
        agent_version="1",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        extracted_fields=_result_fields(["93306"], [], date(2025, 6, 1)),
        schema_valid=True,
        validation_errors=[],
    )
    ocr = OcrPayload(
        agent="ocr",
        agent_version="1",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        fields=[],
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )
    return kyc, claims, ocr


def _policy_fixture(plan_code: str = "GOLD", member_id: str = "MEMBER-1"):
    engine = create_engine("sqlite://")
    Policy.__table__.create(engine)
    Member.__table__.create(engine)
    PolicyExclusion.__table__.create(engine)
    policy_id = uuid4()
    with Session(engine) as session, session.begin():
        policy = Policy(
            policy_id=policy_id,
            plan_code=plan_code,
            name=f"MediShield {plan_code.title()} Plan",
            version="v1",
            effective_from=date(2024, 1, 1),
            effective_to=date(2025, 12, 31),
        )
        member = Member(
            member_id=member_id,
            policy_number=f"MED-{'SLV' if plan_code == 'SILVER' else 'GLD'}-TEST",
            policy_id=policy_id,
            status="ACTIVE",
        )
        session.add_all([policy, member])
    return engine, policy_id


def _chunk(policy_id, text: str = "Echocardiography is covered at 80 percent.") -> RetrievedChunk:
    return RetrievedChunk(
        point_id="clause-1",
        text=text,
        policy_id=policy_id,
        version="v1",
        section_path="3. Inclusions (Covered Services)",
        page=5,
        chunk_type="coverage",
        rrf_score=0.03,
    )


def _agent(engine, policy_id, gateway, retriever, *, reranker=None):
    session = Session(engine)
    return (
        PolicyAgent(
            MemberRepo(session),
            PolicyExclusionRepo(session),
            gateway,
            type("Settings", (), {"llm_text_model": "test-model"})(),
            retriever,
            reranker or FakeReranker(),
        ),
        session,
    )


def _answer(chunk: RetrievedChunk, *, covered=True, percentage=80, certainty=0.9):
    return {
        "covered": covered,
        "coverage_percentage": percentage,
        "clause_id": chunk.point_id,
        "policy_clause": chunk.text,
        "exclusions": [],
        "certainty": certainty,
    }


@pytest.mark.parametrize("plan_code", ["GOLD", "SILVER"])
def test_covered_code_retrieves_for_both_policies(plan_code: str) -> None:
    engine, policy_id = _policy_fixture(plan_code)
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"]))
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime(2025, 6, 2, tzinfo=UTC))

    assert result.status == AgentStatus.OK
    assert result.covered is True
    assert result.coverage_percentage == 80
    assert result.policy_clause.page == 5
    assert result.confidence == pytest.approx(0.9)
    assert retriever.policy_id == policy_id
    assert retriever.service_date == date(2025, 6, 1)
    assert gateway.calls == 1
    _session.close()
    engine.dispose()


def test_rank_one_confidence_uses_llm_certainty() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"], certainty=0.6))
    agent, _session = _agent(engine, policy_id, gateway, retriever, reranker=FakeReranker(0.8))
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.confidence == pytest.approx(0.6)
    _session.close()
    engine.dispose()


def test_claim_coverage_percentage_is_minimum_across_codes() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)

    class MultiAnswerGateway(FakeGateway):
        def complete_json(self, model, system, messages, images, schema, **kwargs):
            self.calls += 1
            percentage = 80 if self.calls == 1 else 60
            return schema.model_validate(
                _answer(retriever.chunks["default"], percentage=percentage)
            )

    gateway = MultiAnswerGateway({})
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["93306", "93000"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is True
    assert result.coverage_percentage == 60
    assert gateway.calls == 2
    _session.close()
    engine.dispose()


def test_combined_percentage_is_null_when_any_code_has_no_percentage() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)

    class MixedPercentageGateway(FakeGateway):
        def complete_json(self, model, system, messages, images, schema, **kwargs):
            self.calls += 1
            percentage = 80 if self.calls == 1 else None
            return schema.model_validate(
                _answer(retriever.chunks["default"], percentage=percentage)
            )

    gateway = MixedPercentageGateway({})
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["93306", "93000"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is True
    assert result.coverage_percentage is None
    _session.close()
    engine.dispose()


@pytest.mark.parametrize("plan_code", ["GOLD", "SILVER"])
def test_exclusion_table_hit_returns_095_without_gateway(plan_code: str) -> None:
    engine, policy_id = _policy_fixture(plan_code)
    with Session(engine) as session, session.begin():
        session.add(
            PolicyExclusion(
                policy_id=policy_id,
                range_start="17000",
                range_end="17999",
                category="Skin lesion destruction",
                basis="Cosmetic exclusion",
                page=7,
            )
        )
    retriever = FakeRetriever()
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["17000"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is False
    assert result.confidence == 0.95
    assert result.exclusions[0].page == 7
    assert gateway.calls == 0
    assert retriever.policy_id is None
    _session.close()
    engine.dispose()


def test_numeric_code_does_not_match_alphanumeric_exclusion_range() -> None:
    engine, policy_id = _policy_fixture()
    with Session(engine) as session, session.begin():
        session.add(
            PolicyExclusion(
                policy_id=policy_id,
                range_start="0001T",
                range_end="0099T",
                category="Category III",
                basis="Experimental",
                page=7,
            )
        )
    retriever = FakeRetriever()
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["00020"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is None
    assert result.confidence == 0.3
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_excluded_and_covered_code_combination_is_not_covered() -> None:
    engine, policy_id = _policy_fixture()
    with Session(engine) as session, session.begin():
        session.add(
            PolicyExclusion(
                policy_id=policy_id,
                range_start="17000",
                range_end="17999",
                category="Skin lesion destruction",
                basis="Cosmetic exclusion",
                page=7,
            )
        )
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"]))
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["17000", "93306"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is False
    assert result.confidence == pytest.approx(0.9)
    assert gateway.calls == 1
    _session.close()
    engine.dispose()


def test_overlapping_exclusion_ranges_are_all_preserved() -> None:
    engine, policy_id = _policy_fixture()
    with Session(engine) as session, session.begin():
        for start, end, basis in (
            ("17000", "17999", "Base exclusion"),
            ("17000", "17010", "Overlapping exclusion"),
        ):
            session.add(
                PolicyExclusion(
                    policy_id=policy_id,
                    range_start=start,
                    range_end=end,
                    category="Skin lesions",
                    basis=basis,
                    page=7,
                )
            )
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, FakeRetriever())
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["17000"], [], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is False
    assert len(result.exclusions) == 2
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_hallucinated_citation_returns_unknown_with_low_confidence() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(
        {
            **_answer(retriever.chunks["default"]),
            "policy_clause": "This fabricated quote is not in the retrieved clause.",
        }
    )
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.status == AgentStatus.OK
    assert result.covered is None
    assert result.confidence == 0.3
    assert result.error is None
    _session.close()
    engine.dispose()


def test_no_relevant_clause_returns_unknown_and_low_confidence() -> None:
    engine, policy_id = _policy_fixture()
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, FakeRetriever())
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is None
    assert result.confidence == 0.3
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_llm_null_answer_returns_unknown_with_confidence_03() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(
        {
            "covered": None,
            "coverage_percentage": None,
            "clause_id": None,
            "policy_clause": None,
            "exclusions": [],
            "certainty": 0.99,
        }
    )
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is None
    assert result.confidence == 0.3
    assert result.status == AgentStatus.OK
    _session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("cited_rank", "certainty", "expected_confidence"),
    [(1, 0.8, 0.8), (4, 0.8, 0.72), (1, 1.0, 0.9)],
)
def test_confidence_uses_certainty_rank_discount_and_cap(
    cited_rank: int, certainty: float, expected_confidence: float
) -> None:
    engine, policy_id = _policy_fixture()
    chunks = [
        RetrievedChunk(
            point_id=f"clause-{rank}",
            text=f"Supporting policy clause {rank} is evidence.",
            policy_id=policy_id,
            version="v1",
            section_path="3. Inclusions (Covered Services)",
            page=rank,
            chunk_type="coverage",
            rrf_score=0.01,
        )
        for rank in range(1, 6)
    ]
    retriever = FakeRetriever()
    retriever.results = chunks
    cited = chunks[cited_rank - 1]
    gateway = FakeGateway(_answer(cited, certainty=certainty))

    class OrderedReranker:
        def rerank(self, query, candidates):
            return [(chunk, 0.95 - rank * 0.05) for rank, chunk in enumerate(candidates)]

    agent, _session = _agent(engine, policy_id, gateway, retriever, reranker=OrderedReranker())
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.policy_clause.page == cited_rank
    assert result.confidence == pytest.approx(expected_confidence)
    _session.close()
    engine.dispose()


def test_cpt_and_icd_queries_use_descriptions_without_code_numbers() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"]))
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["93306"], ["I25.10"], date(2025, 6, 1))}
    )

    agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert retriever.queries == [
        "Complete transthoracic echocardiography covered service",
    ]
    assert all("93306" not in query and "I25.10" not in query for query in retriever.queries)
    _session.close()
    engine.dispose()


def test_low_rerank_score_still_calls_gateway_without_evidence_gate() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"], certainty=0.85))
    agent, _session = _agent(engine, policy_id, gateway, retriever, reranker=FakeReranker(0.01))
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is True
    assert result.confidence == pytest.approx(0.85)
    assert gateway.calls == 1
    _session.close()
    engine.dispose()


def test_wrong_policy_date_gets_no_match() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.active_until = date(2025, 12, 31)
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields(["93306"], [], date(2026, 1, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is None
    assert retriever.service_date == date(2026, 1, 1)
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_fabricated_silver_member_uses_policy_from_number_prefix() -> None:
    engine, gold_policy_id = _policy_fixture("GOLD", "FABRICATED-SILVER")
    silver_policy_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            Policy(
                policy_id=silver_policy_id,
                plan_code="SILVER",
                name="MediShield Silver Plan",
                version="v2",
                effective_from=date(2025, 1, 1),
            )
        )
        member = session.get(Member, "FABRICATED-SILVER")
        member.policy_number = "MED-SLV-FABRICATED"
        member.policy_id = gold_policy_id
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(silver_policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"]))
    agent, _session = _agent(engine, silver_policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes("FABRICATED-SILVER")

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is True
    assert retriever.policy_id == silver_policy_id
    _session.close()
    engine.dispose()


def test_icd_exclusion_table_hit_overrides_covered_answer() -> None:
    engine, policy_id = _policy_fixture()
    with Session(engine) as session, session.begin():
        session.add(
            PolicyExclusion(
                policy_id=policy_id,
                range_start="I10",
                range_end="I20",
                category="Excluded cardiac condition",
                basis="Plan exclusion",
                page=8,
            )
        )
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, FakeRetriever())
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields([], ["I15"], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is False
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_icd_range_match_is_deterministic_without_gateway() -> None:
    engine, policy_id = _policy_fixture()
    with Session(engine) as session, session.begin():
        session.add(
            PolicyExclusion(
                policy_id=policy_id,
                range_start="I10",
                range_end="I20",
                category="Cardiac conditions",
                basis="Plan exclusion",
                page=8,
            )
        )
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, FakeRetriever())
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields([], ["I10"], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is False
    assert result.confidence == 0.95
    assert result.exclusions[0].page == 8
    assert gateway.calls == 0
    _session.close()
    engine.dispose()


def test_retrieval_exception_returns_error_envelope() -> None:
    engine, policy_id = _policy_fixture()

    class FailedRetriever:
        def search(self, *args):
            raise RuntimeError("vector database unavailable")

    agent, _session = _agent(engine, policy_id, FakeGateway({}), FailedRetriever())
    kyc, claims, ocr = _envelopes()

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.status == AgentStatus.ERROR
    assert result.error == "RuntimeError"
    _session.close()
    engine.dispose()


def test_missing_service_date_falls_back_to_received_date_warning() -> None:
    engine, policy_id = _policy_fixture()
    gateway = FakeGateway({})
    agent, _session = _agent(engine, policy_id, gateway, FakeRetriever())
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(update={"extracted_fields": _result_fields(["93306"], [], None)})
    received_at = datetime(2025, 8, 3, 12, tzinfo=UTC)

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, received_at)

    assert "SERVICE_DATE_FALLBACK_RECEIVED_AT" in result.warnings
    assert agent.retriever.service_date == received_at.date()
    _session.close()
    engine.dispose()


def test_unresolved_member_returns_error_envelope() -> None:
    engine, policy_id = _policy_fixture()
    agent, _session = _agent(engine, policy_id, FakeGateway({}), FakeRetriever())
    kyc, claims, ocr = _envelopes("NOT-A-MEMBER")

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.status == AgentStatus.ERROR
    assert result.error == "LookupError"
    _session.close()
    engine.dispose()


def test_amendment_mode_returns_consistency_result() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"], covered=False))
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    ocr = ocr.model_copy(
        update={"fields": [OcrField(key="benefit_limit", value="$25,000", confidence=0.9, page=1)]}
    )

    result = agent.evaluate(
        DocType.POLICY_AMENDMENT, kyc, claims, ocr, datetime(2025, 6, 2, tzinfo=UTC)
    )

    assert result.status == AgentStatus.OK
    assert result.covered is False
    assert result.policy_clause is not None
    assert json.loads(gateway.messages[0]["content"])["mode"] == "amendment"
    _session.close()
    engine.dispose()


def test_cpt_description_lookup_covers_truth_dataset() -> None:
    truth = json.loads((ROOT / "data/synthetic/dataset/truth.json").read_text(encoding="utf-8"))
    dataset_codes = {str(code) for record in truth.values() for code in record.get("cpt_codes", [])}

    assert dataset_codes <= load_cpt_descriptions().keys()


def test_icd10_description_lookup_covers_truth_dataset() -> None:
    truth = json.loads((ROOT / "data/synthetic/dataset/truth.json").read_text(encoding="utf-8"))
    dataset_codes = {
        str(code) for record in truth.values() for code in record.get("icd10_codes", [])
    }

    assert dataset_codes <= load_icd10_descriptions().keys()


def test_null_member_ref_returns_skipped_no_member() -> None:
    engine, policy_id = _policy_fixture()
    agent, _session = _agent(engine, policy_id, FakeGateway({}), FakeRetriever())
    kyc, claims, ocr = _envelopes()
    kyc = kyc.model_copy(update={"member_ref": None})

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.status == AgentStatus.SKIPPED
    assert result.error == "NO_MEMBER"
    _session.close()
    engine.dispose()


def test_icd10_does_not_trigger_policy_llm_without_exclusion_table_hit() -> None:
    engine, policy_id = _policy_fixture()
    retriever = FakeRetriever()
    retriever.chunks["default"] = _chunk(policy_id)
    gateway = FakeGateway(_answer(retriever.chunks["default"]))
    agent, _session = _agent(engine, policy_id, gateway, retriever)
    kyc, claims, ocr = _envelopes()
    claims = claims.model_copy(
        update={"extracted_fields": _result_fields([], ["I10"], date(2025, 6, 1))}
    )

    result = agent.evaluate(DocType.CLAIM_FORM, kyc, claims, ocr, datetime.now(UTC))

    assert result.covered is None
    assert gateway.calls == 0
    assert retriever.queries == []


def test_gap_citation_accepts_normalized_segments_from_same_chunk() -> None:
    policy_id = uuid4()
    chunk = _chunk(
        policy_id,
        "Diagnostic imaging services are covered when medically necessary. "
        "Additional unrelated text appears here for gap testing.",
    )
    citation = (
        "Diagnostic imaging services are covered when medically necessary."
        " ... Additional   unrelated text appears here for gap testing."
    )
    assert PolicyAgent._citation_is_verbatim(citation, chunk.text)


@pytest.mark.parametrize(
    ("citation", "chunk_text"),
    [
        (
            "This entirely invented policy sentence is not in the source.",
            "A sufficiently different retrieved policy chunk with real wording.",
        ),
        ("Short text.", "Short text. This is a sufficiently long retrieved policy chunk."),
        (
            "First exact segment in this retrieved chunk.",
            "Completely unrelated text in one retrieved chunk.",
        ),
    ],
)
def test_citation_rejects_invented_short_or_other_chunk_text(citation, chunk_text) -> None:
    assert not PolicyAgent._citation_is_verbatim(citation, chunk_text)
