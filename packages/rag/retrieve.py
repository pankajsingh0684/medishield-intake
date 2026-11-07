"""Hybrid policy retrieval and clause reranking interfaces."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from qdrant_client import QdrantClient, models

from packages.rag.embeddings import Embedder
from packages.rag.store import POLICY_COLLECTION, policy_payload_filter

TOP_PER_CHANNEL = 8
RRF_K = 60
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass(frozen=True)
class RetrievedChunk:
    point_id: str
    text: str
    policy_id: UUID
    version: str
    section_path: str
    page: int
    chunk_type: str
    rrf_score: float


class Reranker(Protocol):
    def rerank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[tuple[RetrievedChunk, float]]: ...


class CrossEncoderReranker:
    """Loads the cross-encoder only when scoring the first retrieval batch."""

    def __init__(self, model_name: str = RERANKER_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def rerank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[tuple[RetrievedChunk, float]]:
        if not chunks:
            return []
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        logits = self._model.predict([(query, chunk.text) for chunk in chunks])
        scored = [
            (chunk, 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, float(logit))))))
            for chunk, logit in zip(chunks, logits, strict=True)
        ]
        return sorted(scored, key=lambda item: (-item[1], item[0].point_id))


class DeterministicReranker:
    """Stable lexical reranker for offline stub-provider fixture generation."""

    def rerank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[tuple[RetrievedChunk, float]]:
        terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
        scored = []
        for chunk in chunks:
            chunk_terms = set(re.findall(r"[a-z0-9]+", chunk.text.casefold()))
            score = len(terms & chunk_terms) / max(1, len(terms))
            scored.append((chunk, float(score)))
        return sorted(scored, key=lambda item: (-item[1], item[0].point_id))


class QdrantHybridRetriever:
    def __init__(
        self,
        client: QdrantClient,
        embedder: Embedder,
        *,
        collection_name: str = POLICY_COLLECTION,
        top_per_channel: int = TOP_PER_CHANNEL,
    ) -> None:
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name
        self.top_per_channel = top_per_channel

    def search(self, query: str, policy_id: UUID, effective_date) -> list[RetrievedChunk]:
        embedding = self.embedder.embed([query])[0]
        query_filter = policy_payload_filter(policy_id, effective_date)
        dense_points = self.client.query_points(
            collection_name=self.collection_name,
            query=embedding.dense,
            using="dense",
            query_filter=query_filter,
            limit=self.top_per_channel,
            with_payload=True,
        ).points
        sparse_points = self.client.query_points(
            collection_name=self.collection_name,
            query=models.SparseVector(
                indices=embedding.sparse.indices, values=embedding.sparse.values
            ),
            using="text",
            query_filter=query_filter,
            limit=self.top_per_channel,
            with_payload=True,
        ).points

        rank_scores: dict[str, float] = {}
        point_by_id = {}
        for points in (dense_points, sparse_points):
            for rank, point in enumerate(points, start=1):
                point_id = str(point.id)
                rank_scores[point_id] = rank_scores.get(point_id, 0.0) + 1.0 / (RRF_K + rank)
                point_by_id[point_id] = point

        results = []
        for point_id, score in rank_scores.items():
            payload = point_by_id[point_id].payload or {}
            results.append(
                RetrievedChunk(
                    point_id=point_id,
                    text=str(payload["text"]),
                    policy_id=UUID(str(payload["policy_id"])),
                    version=str(payload["version"]),
                    section_path=str(payload["section_path"]),
                    page=int(payload["page"]),
                    chunk_type=str(payload["chunk_type"]),
                    rrf_score=score,
                )
            )
        return sorted(results, key=lambda item: (-item.rrf_score, item.point_id))
