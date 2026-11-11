"""SQLAlchemy models — the schema of record (see docs/PLAN.md §2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

EMBED_DIM = 384


def uid() -> uuid.UUID:
    return uuid.uuid4()


def now() -> datetime:
    return datetime.now(timezone.utc)


def pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)


def fk(target: str, nullable: bool = False, ondelete: str | None = None):
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


def created():
    return mapped_column(DateTime(timezone=True), default=now, nullable=False)


# --- tenancy -------------------------------------------------------------

class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = fk("organisations.id")
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = created()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = fk("organisations.id")
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(200))
    contract_form: Mapped[str | None] = mapped_column(String(60))  # PWC, RIAI, NEC4, FIDIC, bespoke
    our_role: Mapped[str] = mapped_column(String(40), default="main_contractor")
    holiday_region: Mapped[str] = mapped_column(String(10), default="IE")
    working_weekdays: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [0, 1, 2, 3, 4])
    start_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created()

    shutdowns: Mapped[list[ProjectShutdown]] = relationship(cascade="all, delete-orphan", order_by="ProjectShutdown.start")
    parties: Mapped[list[Party]] = relationship(cascade="all, delete-orphan")


class ProjectShutdown(Base):
    __tablename__ = "project_shutdowns"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(120))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)


class Party(Base):
    __tablename__ = "parties"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(60))  # employer, employers_representative, contractor, subcontractor, consultant
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(60))


# --- source material (immutable) ----------------------------------------

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("project_id", "sha256", name="uq_document_project_hash"),)
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    kind: Mapped[str] = mapped_column(String(40))  # contract, email, whatsapp, diary, drawing_register, spec, drawing, quote, compliance, other
    source: Mapped[str] = mapped_column(String(40))  # upload, seed, email_import
    filename: Mapped[str] = mapped_column(String(400))
    mime: Mapped[str] = mapped_column(String(120))
    author: Mapped[str | None] = mapped_column(String(320))
    doc_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(600))
    text: Mapped[str] = mapped_column(Text, default="")
    extraction_method: Mapped[str] = mapped_column(String(40))  # text, ocr, none
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    uploaded_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    created_at: Mapped[datetime] = created()

    items: Mapped[list[Item]] = relationship(back_populates="document", order_by="Item.seq")


class Item(Base):
    """One atomic message inside a document (an email, a WhatsApp message, a diary entry...)."""

    __tablename__ = "items"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    document_id: Mapped[uuid.UUID] = fk("documents.id")
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    author: Mapped[str | None] = mapped_column(String(320))
    recipients: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(600))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()

    document: Mapped[Document] = relationship(back_populates="items")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    document_id: Mapped[uuid.UUID] = fk("documents.id")
    item_id: Mapped[uuid.UUID | None] = fk("items.id", nullable=True)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding = mapped_column(Vector(EMBED_DIM))


Index("ix_chunks_embedding_hnsw", Chunk.embedding, postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})


# --- contract model ------------------------------------------------------

class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    document_id: Mapped[uuid.UUID] = fk("documents.id")
    form: Mapped[str | None] = mapped_column(String(60))
    title: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(30), default="extracting")  # extracting, pending_review, approved, failed
    extraction_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", nullable=True)
    created_at: Mapped[datetime] = created()

    clauses: Mapped[list[ContractClause]] = relationship(order_by="ContractClause.position", cascade="all, delete-orphan")
    rules: Mapped[list[ContractRule]] = relationship(cascade="all, delete-orphan")


class ContractClause(Base):
    __tablename__ = "contract_clauses"
    id: Mapped[uuid.UUID] = pk()
    contract_id: Mapped[uuid.UUID] = fk("contracts.id", ondelete="CASCADE")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    ref: Mapped[str] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)


class ContractRule(Base):
    __tablename__ = "contract_rules"
    id: Mapped[uuid.UUID] = pk()
    contract_id: Mapped[uuid.UUID] = fk("contracts.id", ondelete="CASCADE")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    clause_id: Mapped[uuid.UUID | None] = fk("contract_clauses.id", nullable=True)
    rule_type: Mapped[str] = mapped_column(String(30))  # notice, time_bar, payment, retention, variation, eot
    clause_ref: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    trigger_event: Mapped[str | None] = mapped_column(Text)
    event_categories: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    period_value: Mapped[int | None] = mapped_column(Integer)
    period_unit: Mapped[str | None] = mapped_column(String(20))
    recipient: Mapped[str | None] = mapped_column(String(300))
    required_form: Mapped[str | None] = mapped_column(Text)
    condition_precedent: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. retention %, payment day
    source_quote: Mapped[str] = mapped_column(Text)
    source_char_start: Mapped[int | None] = mapped_column(Integer)
    source_char_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed, approved, rejected
    reviewed_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original: Mapped[dict | None] = mapped_column(JSONB)  # as extracted, kept if the user edits
    created_at: Mapped[datetime] = created()


# --- project record ------------------------------------------------------

class Event(Base):
    """A potential change / delay / instruction / disruption on the project."""

    __tablename__ = "events"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    ref: Mapped[str] = mapped_column(String(20))  # PE-001
    category: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    trigger_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, notified, closed, dismissed
    source_item_id: Mapped[uuid.UUID | None] = fk("items.id", nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", nullable=True)
    related_item_ids: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = created()

    deadlines: Mapped[list[Deadline]] = relationship(back_populates="event")


class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    event_id: Mapped[uuid.UUID] = fk("events.id")
    rule_id: Mapped[uuid.UUID] = fk("contract_rules.id")
    label: Mapped[str] = mapped_column(String(300))
    trigger_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    trace: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, met, cancelled
    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()

    event: Mapped[Event] = relationship(back_populates="deadlines")
    rule: Mapped[ContractRule] = relationship()


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    kind: Mapped[str] = mapped_column(String(40))  # notice
    event_id: Mapped[uuid.UUID | None] = fk("events.id", nullable=True)
    rule_id: Mapped[uuid.UUID | None] = fk("contract_rules.id", nullable=True)
    subject: Mapped[str] = mapped_column(String(400))
    recipient: Mapped[str | None] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, approved, dismissed
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    agent: Mapped[str] = mapped_column(String(60))
    agent_version: Mapped[str] = mapped_column(String(20))
    task: Mapped[str] = mapped_column(String(60))
    prompt_id: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(80))
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, succeeded, failed
    error: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    agent: Mapped[str] = mapped_column(String(60))
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # notice_flag, ...
    category: Mapped[str | None] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(400))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_date: Mapped[date | None] = mapped_column(Date)  # earliest due date for sorting
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, dismissed
    event_id: Mapped[uuid.UUID | None] = fk("events.id", nullable=True)
    draft_id: Mapped[uuid.UUID | None] = fk("drafts.id", nullable=True)
    source_item_id: Mapped[uuid.UUID | None] = fk("items.id", nullable=True)
    decided_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id: Mapped[uuid.UUID] = pk()
    review_item_id: Mapped[uuid.UUID] = fk("review_items.id")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    action: Mapped[str] = mapped_column(String(20))  # edit, approve, dismiss, reopen
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()


class ProjectLog(Base):
    """Append-only domain event log for the project record."""

    __tablename__ = "project_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    actor: Mapped[str] = mapped_column(String(120))  # user:<id> | agent:<name> | system
    created_at: Mapped[datetime] = created()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID | None] = fk("organisations.id", nullable=True)
    project_id: Mapped[uuid.UUID | None] = fk("projects.id", nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20))  # user, agent, system
    actor_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    source_refs: Mapped[list] = mapped_column(JSONB, default=list)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID | None] = fk("projects.id", nullable=True)
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued, running, done, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    run_after: Mapped[datetime] = created()
    created_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
