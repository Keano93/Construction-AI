"""Local embeddings — no document text leaves the deployment.

The default embedder is a deterministic feature-hashing model over word
unigrams and bigrams (signed hashing trick, L2-normalised, 384 dims). It is
cheap, reproducible and good enough for lexical retrieval over contracts and
correspondence. To use a neural model, implement `Embedder` (e.g. a locally
hosted sentence-transformer) and set it with `set_embedder`; dimension must
match the pgvector column (384).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

DIM = 384
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
_STOP = frozenset(
    "the a an and or of to in on for at by with from is are was were be been it this that as we you our your i "
    "will shall would should can could not no if any all have has had do does did".split()
)


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    dim = DIM

    def _features(self, text: str) -> list[str]:
        toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for f in self._features(text):
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            idx, sign = h % self.dim, 1.0 if (h >> 63) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


_embedder: Embedder = HashingEmbedder()


def get_embedder() -> Embedder:
    return _embedder


def set_embedder(e: Embedder) -> None:
    global _embedder
    if e.dim != DIM:
        raise ValueError(f"Embedder dim {e.dim} != column dim {DIM}")
    _embedder = e
