"""Qdrant collection management and policy chunk operations."""

from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import Distance, Modifier, SparseVectorParams, VectorParams

from packages.rag.chunking import PolicyChunk
from packages.rag.embeddings import Embedding

POLICY_COLLECTION = "policy_chunks"


def _date_ordinal(value: date) -> int:
    return value.toordinal()


def policy_payload_filter(policy_id: UUID, effective_date: date | None = None) -> models.Filter:
    conditions = [
        models.FieldCondition(key="policy_id", match=models.MatchValue(value=str(policy_id)))
    ]
    if effective_date is not None:
        conditions.extend(
            [
                models.FieldCondition(
                    key="effective_from_ordinal",
                    range=models.Range(lte=_date_ordinal(effective_date)),
                ),
                models.Filter(
                    should=[
                        models.FieldCondition(
                            key="effective_to_ordinal",
                            range=models.Range(gte=_date_ordinal(effective_date)),
                        ),
                        models.IsNullCondition(
                            is_null=models.PayloadField(key="effective_to_ordinal")
                        ),
                    ]
                ),
            ]
        )
    return models.Filter(must=conditions)


class QdrantPolicyStore:
    def __init__(self, client: QdrantClient, collection_name: str = POLICY_COLLECTION) -> None:
        self.client = client
        self.collection_name = collection_name

    def ensure_collection(self, dimension: int) -> None:
        recreate = False
        if self.client.collection_exists(self.collection_name):
            params = self.client.get_collection(self.collection_name).config.params
            dense = params.vectors
            sparse = params.sparse_vectors or {}
            valid_dense = (
                isinstance(dense, dict)
                and dense.get("dense") is not None
                and dense["dense"].size == dimension
                and dense["dense"].distance == Distance.COSINE
            )
            valid_sparse = "text" in sparse and sparse["text"].modifier == Modifier.IDF
            recreate = not (valid_dense and valid_sparse)
        if recreate:
            self.client.delete_collection(self.collection_name)
        if recreate or not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={"dense": VectorParams(size=dimension, distance=Distance.COSINE)},
                sparse_vectors_config={"text": SparseVectorParams(modifier=Modifier.IDF)},
            )

    def replace_policy_chunks(
        self,
        policy_id: UUID,
        version: str,
        effective_from: date,
        effective_to: date | None,
        chunks: list[PolicyChunk],
        embeddings: list[Embedding],
    ) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=policy_payload_filter(policy_id)),
            wait=True,
        )
        points = []
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            point_id = uuid5(NAMESPACE_URL, f"{policy_id}:{index}:{chunk.text}")
            points.append(
                models.PointStruct(
                    id=str(point_id),
                    vector={
                        "dense": embedding.dense,
                        "text": models.SparseVector(
                            indices=embedding.sparse.indices, values=embedding.sparse.values
                        ),
                    },
                    payload={
                        "policy_id": str(policy_id),
                        "version": version,
                        "section_path": chunk.section_path,
                        "page": chunk.page,
                        "effective_from": effective_from.isoformat(),
                        "effective_to": effective_to.isoformat() if effective_to else None,
                        "effective_from_ordinal": _date_ordinal(effective_from),
                        "effective_to_ordinal": (
                            _date_ordinal(effective_to) if effective_to else None
                        ),
                        "chunk_type": chunk.chunk_type,
                        "text": chunk.text,
                    },
                )
            )
        if points:
            self.client.upsert(self.collection_name, points=points, wait=True)

    def query(
        self,
        dense: list[float],
        policy_id: UUID,
        effective_date: date,
        limit: int = 8,
    ):
        return self.client.query_points(
            collection_name=self.collection_name,
            query=dense,
            using="dense",
            query_filter=policy_payload_filter(policy_id, effective_date),
            limit=limit,
            with_payload=True,
        )
