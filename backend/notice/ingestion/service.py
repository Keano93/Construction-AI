"""Ingestion: file -> immutable Document + Items + Chunks, then queue agent work."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..jobs import enqueue
from ..models import Chunk, Contract, Document, Item, Project
from ..record import audit, log_project_event
from ..retrieval import chunk_spans, get_embedder
from .extractors import MESSAGE_KINDS, extract

REVISION_KINDS = {"drawing_register", "spec", "drawing"}


@dataclass
class IngestResult:
    document: Document
    created: bool


def _store(project_id: uuid.UUID, sha: str, filename: str, data: bytes) -> str:
    root = get_settings().storage_dir / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{sha}{Path(filename).suffix.lower()}"
    if not path.exists():
        path.write_bytes(data)
    return str(path)


def ingest_file(
    db: Session,
    project: Project,
    filename: str,
    data: bytes,
    *,
    kind: str | None = None,
    source: str = "upload",
    uploaded_by: uuid.UUID | None = None,
    author: str | None = None,
    doc_timestamp: datetime | None = None,
    run_agents: bool = True,
) -> IngestResult:
    sha = hashlib.sha256(data).hexdigest()
    existing = db.execute(select(Document).where(Document.project_id == project.id, Document.sha256 == sha)).scalar_one_or_none()
    if existing:
        return IngestResult(existing, False)

    ex = extract(filename, data, kind)
    doc = Document(
        project_id=project.id,
        kind=ex.kind,
        source=source,
        filename=filename,
        mime=ex.mime,
        author=author or ex.author,
        doc_timestamp=doc_timestamp or ex.timestamp,
        sha256=sha,
        size_bytes=len(data),
        storage_path=_store(project.id, sha, filename, data),
        text=ex.text,
        extraction_method=ex.method,
        meta=ex.meta,
        uploaded_by=uploaded_by,
    )
    db.add(doc)
    db.flush()

    embedder = get_embedder()
    items: list[Item] = []
    for seq, spec in enumerate(ex.items):
        item_text = ex.text[spec.char_start:spec.char_end]
        item = Item(
            project_id=project.id,
            document_id=doc.id,
            seq=seq,
            kind=spec.kind or ex.kind,
            author=spec.author,
            recipients=spec.recipients,
            subject=spec.subject,
            timestamp=spec.timestamp or doc.doc_timestamp,
            text=item_text,
            char_start=spec.char_start,
            char_end=spec.char_end,
            sha256=hashlib.sha256(item_text.encode()).hexdigest(),
        )
        db.add(item)
        items.append(item)
    db.flush()

    for item in items:
        for s, e in chunk_spans(ex.text, item.char_start, item.char_end):
            if ex.text[s:e].strip():
                db.add(Chunk(project_id=project.id, document_id=doc.id, item_id=item.id, text=ex.text[s:e],
                             char_start=s, char_end=e, embedding=embedder.embed(ex.text[s:e])))

    actor = f"user:{uploaded_by}" if uploaded_by else "system"
    log_project_event(db, project.id, "document.ingested", actor=actor, entity_type="document", entity_id=doc.id,
                      payload={"filename": filename, "kind": ex.kind, "items": len(items), "sha256": sha, "method": ex.method})
    audit(db, action="document.ingest", actor_type="user" if uploaded_by else "system", actor_id=str(uploaded_by or "system"),
          org_id=project.org_id, project_id=project.id, entity_type="document", entity_id=doc.id,
          source_refs=[{"document_id": str(doc.id), "sha256": sha}], details={"filename": filename, "kind": ex.kind})

    if run_agents:
        if ex.kind == "contract":
            contract = Contract(project_id=project.id, document_id=doc.id, form=project.contract_form, title=filename)
            db.add(contract)
            db.flush()
            enqueue(db, "contract.extract", {"contract_id": contract.id}, project.id)
        elif ex.kind in REVISION_KINDS:
            from ..agents.revision_agent.agent import find_base_document

            base = find_base_document(db, doc)
            if base is not None:
                enqueue(db, "revision_agent.compare", {"base_id": base.id, "revised_id": doc.id}, project.id)
        elif ex.kind in MESSAGE_KINDS:
            for item in items:
                enqueue(db, "notice_agent.process_item", {"item_id": item.id}, project.id)
    return IngestResult(doc, True)
