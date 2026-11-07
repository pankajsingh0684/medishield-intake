"""Policy coverage decisions grounded in retrieved clauses and exclusions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.core.db.models import Member, Policy
from packages.core.db.repositories import MemberRepo, PolicyExclusionRepo
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMGateway
from packages.core.models import (
    ClaimsResult,
    KycResult,
    OcrPayload,
    PolicyClause,
    PolicyResult,
)
from packages.rag.retrieve import Reranker, RetrievedChunk

POLICY_AGENT = "policy"
POLICY_VERSION = "1.0.0"
POLICY_PROMPT_VERSION = "v1"
CPT_DESCRIPTIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "cpt_descriptions.json"
ICD10_DESCRIPTIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "icd10_descriptions.json"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    text: str


class PolicyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    covered: bool | None
    coverage_percentage: float | None = Field(default=None, ge=0, le=100)
    clause_id: str | None = None
    policy_clause: str | None = None
    exclusions: list[Citation] = Field(default_factory=list)
    certainty: float = Field(ge=0, le=1)


def build_policy_message(
    *,
    mode: Literal["claim", "amendment"],
    code_type: str,
    code: str,
    description: str,
    chunks: list[RetrievedChunk],
    amendment_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    payload = {
        "mode": mode,
        "code_type": code_type,
        "code": code,
        "description": description,
        "amendment_fields": amendment_fields or {},
        "clauses": [
            {
                "clause_id": chunk.point_id,
                "section_path": chunk.section_path,
                "page": chunk.page,
                "text": chunk.text,
            }
            for chunk in chunks
        ],
    }
    return {
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }


def load_cpt_descriptions(path: Path = CPT_DESCRIPTIONS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(code, str) and isinstance(description, str) for code, description in data.items()
    ):
        raise ValueError("CPT descriptions must be a mapping of code strings to descriptions")
    return data


def load_icd10_descriptions(path: Path = ICD10_DESCRIPTIONS_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(code, str) and isinstance(description, str) for code, description in data.items()
    ):
        raise ValueError("ICD-10 descriptions must be a mapping of code strings to descriptions")
    return data


class PolicyAgent:
    def __init__(
        self,
        member_repo: MemberRepo,
        exclusion_repo: PolicyExclusionRepo,
        gateway: LLMGateway,
        settings,
        retriever,
        reranker: Reranker,
        *,
        prompt_loader: PromptLoader | None = None,
        cpt_descriptions: dict[str, str] | None = None,
        icd10_descriptions: dict[str, str] | None = None,
    ) -> None:
        self.member_repo = member_repo
        self.exclusion_repo = exclusion_repo
        self.gateway = gateway
        self.settings = settings
        self.retriever = retriever
        self.reranker = reranker
        self.prompt_loader = prompt_loader or PromptLoader(Path(__file__).parent / "prompts")
        self.cpt_descriptions = cpt_descriptions or load_cpt_descriptions()
        self.icd10_descriptions = icd10_descriptions or load_icd10_descriptions()

    def evaluate(
        self,
        doc_type: DocType,
        kyc: KycResult,
        claims: ClaimsResult,
        ocr: OcrPayload,
        received_at: datetime,
    ) -> PolicyResult:
        started = datetime.now(UTC)
        model_name = self.settings.llm_text_model
        warnings: list[str] = []
        try:
            if not kyc.member_ref:
                raise LookupError("KYC did not resolve a member")
            member = self.member_repo.get(kyc.member_ref)
            if member is None:
                raise LookupError("Resolved member does not exist")
            service_date = claims.extracted_fields.service_date
            if service_date is None:
                service_date = received_at.date()
                warnings.append("SERVICE_DATE_FALLBACK_RECEIVED_AT")
            policy = self.member_repo.get_policy_for_number(member.policy_number, service_date)
            if policy is None:
                policy = self.member_repo.get_policy(member)
            if policy is None:
                raise LookupError("Member has no policy row for the requested service date")

            if doc_type == DocType.POLICY_AMENDMENT:
                result = self._evaluate_amendment(
                    member, policy, ocr, service_date, started, model_name, warnings
                )
                return result

            outcomes: list[
                tuple[bool | None, float | None, float, PolicyClause | None, list[PolicyClause]]
            ] = []
            exclusions: list[PolicyClause] = []
            fields = claims.extracted_fields
            for code in fields.cpt_codes:
                matching = self.exclusion_repo.lookup(policy.policy_id, code)
                if matching:
                    code_exclusions = []
                    for row in matching:
                        clause = PolicyClause(
                            text=(
                                f"CPT {code} is excluded by range {row.range_start}-{row.range_end}: "
                                f"{row.category or 'Excluded service'}; {row.basis or 'Policy exclusion'}."
                            ),
                            policy_id=policy.policy_id,
                            page=row.page or 1,
                            section="4.1 Excluded CPT Code Ranges",
                            score=0.95,
                        )
                        code_exclusions.append(clause)
                    outcomes.append(
                        (False, None, 0.95, matching_clause(code_exclusions), code_exclusions)
                    )
                    continue
                description = self.cpt_descriptions.get(code, "unlisted procedure")
                outcomes.append(
                    self._evaluate_code(
                        policy,
                        service_date,
                        "CPT",
                        code,
                        description,
                        started,
                        model_name,
                    )
                )

            for code in fields.icd10_codes:
                matching = self.exclusion_repo.lookup(policy.policy_id, code)
                if matching:
                    code_exclusions = [
                        PolicyClause(
                            text=(
                                f"ICD-10 {code} matches excluded range "
                                f"{row.range_start}-{row.range_end}: "
                                f"{row.category or 'Excluded condition'}; "
                                f"{row.basis or 'Policy exclusion'}."
                            ),
                            policy_id=policy.policy_id,
                            page=row.page or 1,
                            section="Policy Exclusions",
                            score=0.95,
                        )
                        for row in matching
                    ]
                    outcomes.append(
                        (False, None, 0.95, matching_clause(code_exclusions), code_exclusions)
                    )
                    continue
                outcomes.append(
                    self._evaluate_code(
                        policy,
                        service_date,
                        "ICD-10",
                        code,
                        self.icd10_descriptions.get(code, "diagnosis"),
                        started,
                        model_name,
                    )
                )

            if not outcomes:
                return self._result(
                    AgentStatus.OK,
                    None,
                    None,
                    None,
                    [],
                    0.3,
                    started,
                    model_name,
                    warnings=warnings,
                )

            for _, _, _, _, code_exclusions in outcomes:
                exclusions.extend(code_exclusions)
            all_covered = all(covered is True for covered, _, _, _, _ in outcomes)
            any_uncovered = any(covered is False for covered, _, _, _, _ in outcomes)
            covered: bool | None = False if any_uncovered else True if all_covered else None
            percentages = [percentage for _, percentage, _, _, _ in outcomes]
            confidence = min(confidence for _, _, confidence, _, _ in outcomes)
            clauses = [clause for _, _, _, clause, _ in outcomes if clause is not None]
            primary_clause = min(clauses, key=lambda clause: clause.score) if clauses else None
            return self._result(
                AgentStatus.OK,
                covered,
                min(percentages)
                if percentages and all(p is not None for p in percentages)
                else None,
                primary_clause,
                exclusions,
                confidence,
                started,
                model_name,
                warnings=warnings,
            )
        except Exception as error:  # noqa: BLE001
            return self._result(
                AgentStatus.ERROR,
                None,
                None,
                None,
                [],
                0.0,
                started,
                model_name,
                error=type(error).__name__,
                warnings=warnings,
            )

    def _evaluate_code(
        self,
        policy: Policy,
        service_date: date,
        code_type: str,
        code: str,
        description: str,
        started: datetime,
        model_name: str,
    ) -> tuple[bool | None, float | None, float, PolicyClause | None, list[PolicyClause]]:
        query = f"{description} covered service"
        candidates = self.retriever.search(query, policy.policy_id, service_date)
        ranked = self.reranker.rerank(query, candidates)
        if not ranked:
            return None, None, 0.3, None, []
        top_five = ranked[:5]
        chunks = [chunk for chunk, _ in top_five]
        answer = self._ask(
            mode="claim",
            code_type=code_type,
            code=code,
            description=description,
            chunks=chunks,
        )
        if answer.covered is None:
            return None, None, 0.3, None, []
        scores = {chunk.point_id: score for chunk, score in top_five}
        ranks = {chunk.point_id: rank for rank, (chunk, _) in enumerate(top_five, start=1)}
        if answer.clause_id not in scores or not answer.policy_clause:
            return None, None, 0.3, None, []
        chunk = next(chunk for chunk in chunks if chunk.point_id == answer.clause_id)
        if answer.policy_clause not in chunk.text:
            return None, None, 0.3, None, []
        clause = self._policy_clause(
            policy.policy_id, chunk, answer.policy_clause, scores[chunk.point_id]
        )
        try:
            exclusions = [
                self._verified_citation(policy.policy_id, item, chunks, scores)
                for item in answer.exclusions
            ]
        except ValueError:
            return None, None, 0.3, None, []
        confidence = self._confidence(answer.certainty, ranks[answer.clause_id])
        if exclusions:
            return False, answer.coverage_percentage, confidence, clause, exclusions
        return answer.covered, answer.coverage_percentage, confidence, clause, []

    def _evaluate_amendment(
        self,
        member: Member,
        policy: Policy,
        ocr: OcrPayload,
        service_date: date,
        started: datetime,
        model_name: str,
        warnings: list[str],
    ) -> PolicyResult:
        amendment_fields = {item.key: item.value for item in ocr.fields if item.value.strip()}
        if not amendment_fields:
            return self._result(
                AgentStatus.OK,
                None,
                None,
                None,
                [],
                0.3,
                started,
                model_name,
                warnings=warnings + ["NO_AMENDMENT_FIELDS"],
            )
        query = f"Current policy clauses relevant to amendment: {json.dumps(amendment_fields, sort_keys=True)}"
        candidates = self.retriever.search(query, policy.policy_id, service_date)
        ranked = self.reranker.rerank(query, candidates)
        if not ranked:
            return self._result(
                AgentStatus.OK,
                None,
                None,
                None,
                [],
                0.3,
                started,
                model_name,
                warnings=warnings,
            )
        top_five = ranked[:5]
        answer = self._ask(
            mode="amendment",
            code_type="AMENDMENT",
            code=member.policy_number,
            description=f"Compare this amendment with the current {policy.name or 'policy'} policy",
            chunks=[chunk for chunk, _ in top_five],
            amendment_fields=amendment_fields,
        )
        if answer.covered is None:
            return self._result(
                AgentStatus.OK,
                None,
                None,
                None,
                [],
                0.3,
                started,
                model_name,
                warnings=warnings,
            )
        scores = {chunk.point_id: score for chunk, score in top_five}
        ranks = {chunk.point_id: rank for rank, (chunk, _) in enumerate(top_five, start=1)}
        if not answer.clause_id or answer.clause_id not in scores or not answer.policy_clause:
            return self._result(
                AgentStatus.OK, None, None, None, [], 0.3, started, model_name, warnings=warnings
            )
        chunk = next(chunk for chunk, _ in top_five if chunk.point_id == answer.clause_id)
        if answer.policy_clause not in chunk.text:
            return self._result(
                AgentStatus.OK, None, None, None, [], 0.3, started, model_name, warnings=warnings
            )
        clause = self._policy_clause(
            policy.policy_id, chunk, answer.policy_clause, scores[chunk.point_id]
        )
        try:
            exclusions = [
                self._verified_citation(
                    policy.policy_id, item, [entry for entry, _ in top_five], scores
                )
                for item in answer.exclusions
            ]
        except ValueError:
            return self._result(
                AgentStatus.OK, None, None, None, [], 0.3, started, model_name, warnings=warnings
            )
        confidence = self._confidence(answer.certainty, ranks[chunk.point_id])
        return self._result(
            AgentStatus.OK,
            False if exclusions else answer.covered,
            answer.coverage_percentage,
            clause,
            exclusions,
            confidence,
            started,
            model_name,
            warnings=warnings,
        )

    @staticmethod
    def _confidence(certainty: float, rank: int) -> float:
        rank_factor = 0.9 if 3 <= rank <= 5 else 1.0
        return min(0.9, certainty * rank_factor)

    def _ask(
        self,
        *,
        mode: Literal["claim", "amendment"],
        code_type: str,
        code: str,
        description: str,
        chunks: list[RetrievedChunk],
        amendment_fields: dict[str, str] | None = None,
    ) -> PolicyAnswer:
        prompt = self.prompt_loader.load("policy_decide", POLICY_PROMPT_VERSION)
        return prompt.invoke(
            self.gateway,
            self.settings,
            [
                build_policy_message(
                    mode=mode,
                    code_type=code_type,
                    code=code,
                    description=description,
                    chunks=chunks,
                    amendment_fields=amendment_fields,
                )
            ],
            [],
            PolicyAnswer,
        )

    @staticmethod
    def _policy_clause(
        policy_id: UUID, chunk: RetrievedChunk, text: str, score: float
    ) -> PolicyClause:
        return PolicyClause(
            text=text,
            policy_id=policy_id,
            page=chunk.page,
            section=chunk.section_path,
            score=score,
        )

    def _verified_citation(
        self,
        policy_id: UUID,
        citation: Citation,
        chunks: list[RetrievedChunk],
        scores: dict[str, float],
    ) -> PolicyClause:
        chunk = next((item for item in chunks if item.point_id == citation.clause_id), None)
        if chunk is None or not citation.text or citation.text not in chunk.text:
            raise ValueError("Policy exclusion citation is not verbatim in retrieved text")
        return self._policy_clause(policy_id, chunk, citation.text, scores[chunk.point_id])

    @staticmethod
    def _result(
        status: AgentStatus,
        covered: bool | None,
        coverage_percentage: float | None,
        policy_clause: PolicyClause | None,
        exclusions: list[PolicyClause],
        confidence: float,
        started: datetime,
        model_name: str | None,
        *,
        error: str | None = None,
        warnings: list[str] | None = None,
    ) -> PolicyResult:
        return PolicyResult(
            agent=POLICY_AGENT,
            agent_version=POLICY_VERSION,
            status=status,
            confidence=max(0.0, min(1.0, confidence)),
            model=model_name,
            started_at=started,
            finished_at=datetime.now(UTC),
            error=error,
            covered=covered,
            coverage_percentage=coverage_percentage,
            policy_clause=policy_clause,
            exclusions=exclusions,
            warnings=warnings or [],
        )


def matching_clause(clauses: list[PolicyClause]) -> PolicyClause:
    return clauses[-1]
