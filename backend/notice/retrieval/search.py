from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chunk, Document
from .embeddings import get_embedder

CHUNK_SIZE = 1200
OVERLAP = 150


def chunk_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split [start, end) into overlapping windows, preferring paragraph/sentence breaks."""
    spans = []
    pos = start
    while pos < end:
        hi = min(pos + CHUNK_SIZE, end)
        if hi < end:
            window = text[pos:hi]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut > CHUNK_SIZE // 2:
                hi = pos + cut + 1
        spans.append((pos, hi))
        if hi >= end:
            break
        pos = max(hi - OVERLAP, pos + 1)
    return spans


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    item_id: uuid.UUID | None
    filename: str
    kind: str
    text: str
    char_start: int
    char_end: int
    score: float


def search(db: Session, project_id: uuid.UUID, query: str, *, k: int = 8, kinds: list[str] | None = None) -> list[Hit]:
    vec = get_embedder().embed(query)
    dist = Chunk.embedding.cosine_distance(vec)
    stmt = (
        select(Chunk, Document.filename, Document.kind, dist.label("d"))
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.project_id == project_id)
        .order_by(dist)
        .limit(k)
    )
    if kinds:
        stmt = stmt.where(Document.kind.in_(kinds))
    return [
        Hit(c.id, c.document_id, c.item_id, fn, kind, c.text, c.char_start, c.char_end, 1 - float(d))
        for c, fn, kind, d in db.execute(stmt)
    ]
