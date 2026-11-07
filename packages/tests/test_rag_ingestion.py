from collections import Counter
from datetime import date
from pathlib import Path
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from packages.core.db.models import Policy, PolicyExclusion
from packages.rag.chunking import ContentBlock, chunk_blocks, chunk_type_for_heading, count_tokens
from packages.rag.embeddings import Embedding, hashed_sparse_vector
from packages.rag.ingest import ParsedPolicy, _extract_exclusions, ingest_policy_document
from packages.rag.store import QdrantPolicyStore, policy_payload_filter

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"


class FakeEmbedder:
    dimension = 4

    def embed(self, texts: list[str]) -> list[Embedding]:
        return [
            Embedding([float(len(text) % 7), 1.0, 0.0, 0.5], hashed_sparse_vector(text))
            for text in texts
        ]


class FakeStore:
    def __init__(self) -> None:
        self.chunks: dict[str, list[tuple[object, object]]] = {}
        self.dimension: int | None = None

    def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension

    def replace_policy_chunks(
        self, policy_id, version, effective_from, effective_to, chunks, embeddings
    ):
        self.chunks[str(policy_id)] = list(zip(chunks, embeddings, strict=True))


def test_chunker_applies_heading_tags_overlap_and_keeps_small_tables_whole() -> None:
    repeated = "A covered service requires prior authorization. " * 220
    blocks = [
        ContentBlock("Coverage and Benefits", "Coverage and Benefits", 1),
        ContentBlock(repeated, "Coverage and Benefits", 1),
        ContentBlock("Excluded CPT ranges", "Exclusions", 2, is_table=True),
    ]

    chunks = chunk_blocks(blocks)

    assert len(chunks) >= 3
    assert all(chunk.chunk_type == "coverage" for chunk in chunks[:2])
    assert chunks[-1].chunk_type == "exclusion"
    assert chunks[-1].text == "Excluded CPT ranges"
    assert all(count_tokens(chunk.text) <= 1000 for chunk in chunks)
    assert {count_tokens(chunk.text) for chunk in chunks[:2]} <= set(range(1, 801))
    assert count_tokens(chunks[0].text[-300:]) > 0


def test_short_chunks_merge_within_top_level_and_tables_remain_separate() -> None:
    blocks = [
        ContentBlock("Coverage opening", "1. Coverage", 1, is_heading=True),
        ContentBlock("Covered service details. " * 30, "1. Coverage > 1.1 Services", 1),
        ContentBlock(
            "Excluded CPT Range\n15000-15999",
            "1. Coverage > 1.2 Exclusion Schedule",
            2,
            is_table=True,
        ),
        ContentBlock("Short note", "2. Claims", 3),
    ]

    chunks = chunk_blocks(blocks)

    assert not any(chunk.is_heading_only for chunk in chunks)
    assert chunks[0].text.startswith("Coverage opening")
    assert count_tokens(chunks[0].text) >= 60
    assert chunks[1].is_table
    assert count_tokens(chunks[1].text) < 60
    assert chunks[1].chunk_type == "exclusion"
    assert chunks[2].text == "Short note"
    assert count_tokens(chunks[2].text) < 60
    section_counts = Counter(chunk.section_path for chunk in chunks)
    assert all(
        chunk.is_table or section_counts[chunk.section_path] == 1
        for chunk in chunks
        if count_tokens(chunk.text) < 60
    )


def test_fake_embedder_produces_dense_and_sparse_vectors() -> None:
    embedding = FakeEmbedder().embed(["CPT 99213 coverage"])[0]

    assert len(embedding.dense) == 4
    assert embedding.sparse.indices
    assert embedding.sparse.values == [1.0] * len(embedding.sparse.indices)


def test_chunk_type_rules_classify_headings_without_llm() -> None:
    assert chunk_type_for_heading("4. Exclusions") == "exclusion"
    assert chunk_type_for_heading("2. Definitions") == "definition"
    assert chunk_type_for_heading("1. Schedule of Benefits") == "schedule"
    assert chunk_type_for_heading("Covered under this Rider") == "coverage"
    assert chunk_type_for_heading("Claims Procedure") == "other"


def test_both_policy_pdfs_have_18_exclusion_ranges() -> None:
    counts = {
        path.name: len(_extract_exclusions(path.read_bytes())) for path in POLICY_DIR.glob("*.pdf")
    }

    assert counts == {"medishield_gold_plan.pdf": 18, "medishield_silver_plan.pdf": 18}


def test_ingestion_with_fake_embedder_is_idempotent_for_both_policies(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Policy.__table__.create(engine)
    PolicyExclusion.__table__.create(engine)
    store = FakeStore()
    embedder = FakeEmbedder()
    try:
        for filename, plan_code in (
            ("medishield_gold_plan.pdf", "GOLD"),
            ("medishield_silver_plan.pdf", "SILVER"),
        ):
            content = (POLICY_DIR / filename).read_bytes()
            exclusions = _extract_exclusions(content)
            policy_id = uuid4()
            monkeypatch.setattr(
                "packages.rag.ingest.parse_policy",
                lambda _content, _filename, exclusions=exclusions, plan_code=plan_code: (
                    ParsedPolicy(
                        [
                            ContentBlock(
                                f"{plan_code} coverage and benefits " + "covered service " * 120,
                                "Coverage and Benefits",
                                1,
                            ),
                            ContentBlock(
                                "Excluded CPT Code Ranges " + "range row " * 20,
                                "4.1 Excluded CPT Code Ranges",
                                7,
                                is_table=True,
                            ),
                        ],
                        exclusions,
                    )
                ),
            )
            with Session(engine) as session, session.begin():
                session.add(
                    Policy(
                        policy_id=policy_id,
                        plan_code=plan_code,
                        name=f"MediShield {plan_code}",
                        version="test-v1",
                        effective_from=date(2024, 1, 1),
                        object_key=filename,
                        ingest_status="PENDING",
                    )
                )
            for _ in range(2):
                with Session(engine) as session, session.begin():
                    count = ingest_policy_document(session, policy_id, content, store, embedder)
                    assert count > 0
                    policy = session.get(Policy, policy_id)
                    assert policy.ingest_status == "READY"
                    assert policy.chunk_count == count
                    assert (
                        session.scalar(
                            select(func.count())
                            .select_from(PolicyExclusion)
                            .where(PolicyExclusion.policy_id == policy_id)
                        )
                        == 18
                    )
            assert store.dimension == FakeEmbedder.dimension
            assert len(store.chunks[str(policy_id)]) == count
    finally:
        engine.dispose()


def test_corrupt_policy_is_marked_failed_without_writing_chunks(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Policy.__table__.create(engine)
    PolicyExclusion.__table__.create(engine)
    store = FakeStore()
    policy_id = uuid4()
    try:
        with Session(engine) as session:
            session.add(
                Policy(
                    policy_id=policy_id,
                    plan_code="GOLD",
                    version="broken-v1",
                    object_key="corrupt.pdf",
                    ingest_status="PENDING",
                    chunk_count=0,
                )
            )
            session.commit()
            monkeypatch.setattr(
                "packages.rag.ingest.parse_policy",
                lambda *_: (_ for _ in ()).throw(ValueError("Invalid PDF")),
            )

            try:
                ingest_policy_document(session, policy_id, b"not a PDF", store, FakeEmbedder())
            except ValueError as error:
                assert str(error) == "Invalid PDF"
            else:
                raise AssertionError("Corrupt policy ingestion should fail")
            session.commit()
            failed_policy = session.get(Policy, policy_id)
            assert failed_policy.ingest_status == "FAILED"
            assert failed_policy.chunk_count == 0
        assert store.chunks == {}
    finally:
        engine.dispose()


def test_payload_filter_scopes_policy_and_open_effective_end() -> None:
    policy_id = uuid4()

    query_filter = policy_payload_filter(policy_id, date(2025, 6, 1))

    assert isinstance(query_filter, Filter)
    assert any(
        isinstance(condition, FieldCondition)
        and condition.key == "policy_id"
        and condition.match == MatchValue(value=str(policy_id))
        for condition in query_filter.must
    )
    assert any(not isinstance(condition, FieldCondition) for condition in query_filter.must)


def test_qdrant_payload_filter_returns_only_active_matching_policy() -> None:
    client = QdrantClient(":memory:")
    store = QdrantPolicyStore(client)
    store.ensure_collection(4)
    active_policy = uuid4()
    other_policy = uuid4()
    chunks = [
        ContentBlock("Active clause", "Coverage", 1),
        ContentBlock("Wrong policy", "Coverage", 1),
        ContentBlock("Not yet active", "Coverage", 1),
    ]
    from packages.rag.chunking import PolicyChunk

    store.replace_policy_chunks(
        active_policy,
        "v1",
        date(2024, 1, 1),
        None,
        [
            PolicyChunk(block.text, block.section_path, block.page, "coverage")
            for block in (chunks[0],)
        ],
        FakeEmbedder().embed([chunks[0].text]),
    )
    store.replace_policy_chunks(
        other_policy,
        "v1",
        date(2024, 1, 1),
        None,
        [PolicyChunk(chunks[1].text, chunks[1].section_path, chunks[1].page, "coverage")],
        FakeEmbedder().embed([chunks[1].text]),
    )
    future_policy = uuid4()
    store.replace_policy_chunks(
        future_policy,
        "v1",
        date(2026, 1, 1),
        None,
        [PolicyChunk(chunks[2].text, chunks[2].section_path, chunks[2].page, "coverage")],
        FakeEmbedder().embed([chunks[2].text]),
    )

    result = store.query(FakeEmbedder().embed(["clause"])[0].dense, active_policy, date(2025, 1, 1))

    assert [point.payload["text"] for point in result.points] == ["Active clause"]
    client.close()
