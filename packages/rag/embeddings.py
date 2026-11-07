"""Dense local embeddings and deterministic hashed sparse vectors."""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SparseEmbedding:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class Embedding:
    dense: list[float]
    sparse: SparseEmbedding


class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[Embedding]: ...


def hashed_sparse_vector(text: str) -> SparseEmbedding:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    counts: Counter[int] = Counter()
    for token in tokens:
        index = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")
        counts[index] += 1
    indices = sorted(counts)
    return SparseEmbedding(indices, [float(counts[index]) for index in indices])


class LocalSentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dimension = int(self._model.get_embedding_dimension())

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[Embedding]:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [
            Embedding([float(value) for value in vector], hashed_sparse_vector(text))
            for text, vector in zip(texts, vectors, strict=True)
        ]
