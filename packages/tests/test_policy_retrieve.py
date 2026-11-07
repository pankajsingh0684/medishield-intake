from datetime import date
from uuid import uuid4

from qdrant_client import QdrantClient

from packages.rag.chunking import PolicyChunk
from packages.rag.embeddings import Embedding, hashed_sparse_vector
from packages.rag.retrieve import QdrantHybridRetriever
from packages.rag.store import QdrantPolicyStore


class FixedEmbedder:
    dimension = 3

    def embed(self, texts: list[str]) -> list[Embedding]:
        return [Embedding([1.0, 0.0, 0.0], hashed_sparse_vector(text)) for text in texts]


def test_hybrid_retriever_fuses_dense_sparse_and_filters_policy_date() -> None:
    client = QdrantClient(":memory:")
    store = QdrantPolicyStore(client)
    store.ensure_collection(FixedEmbedder.dimension)
    policy_id = uuid4()
    other_policy = uuid4()
    query = "CPT 93306 echocardiography coverage"
    texts = [
        "CPT 93306 echocardiography coverage is included.",
        "Unrelated outpatient service terms.",
        "Wrong policy CPT 93306 echocardiography coverage.",
    ]
    for selected_policy, entries in (
        (policy_id, [(texts[0], 5), (texts[1], 6)]),
        (other_policy, [(texts[2], 7)]),
    ):
        store.replace_policy_chunks(
            selected_policy,
            "v1",
            date(2024, 1, 1),
            date(2025, 12, 31),
            [PolicyChunk(text, "3. Coverage", page, "coverage") for text, page in entries],
            FixedEmbedder().embed([text for text, _ in entries]),
        )

    retriever = QdrantHybridRetriever(client, FixedEmbedder(), top_per_channel=8)
    chunks = retriever.search(query, policy_id, date(2025, 6, 1))

    assert chunks
    assert all(chunk.policy_id == policy_id for chunk in chunks)
    assert all(chunk.page != 7 for chunk in chunks)
    assert all(chunk.rrf_score > 0 for chunk in chunks)
    assert {chunk.text for chunk in chunks} == set(texts[:2])
    assert chunks[0].rrf_score >= chunks[1].rrf_score
    client.close()


def test_hybrid_retriever_filters_out_policy_outside_effective_date() -> None:
    client = QdrantClient(":memory:")
    store = QdrantPolicyStore(client)
    store.ensure_collection(FixedEmbedder.dimension)
    policy_id = uuid4()
    text = "CPT 93306 echocardiography coverage is included."
    store.replace_policy_chunks(
        policy_id,
        "v1",
        date(2024, 1, 1),
        date(2024, 12, 31),
        [PolicyChunk(text, "3. Coverage", 5, "coverage")],
        FixedEmbedder().embed([text]),
    )

    chunks = QdrantHybridRetriever(client, FixedEmbedder()).search(
        "coverage CPT 93306", policy_id, date(2025, 1, 1)
    )

    assert chunks == []
    client.close()
