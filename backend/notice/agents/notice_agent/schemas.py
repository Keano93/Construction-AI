from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["change", "delay", "instruction", "disruption", "noise"]


class Evidence(BaseModel):
    quote: str = Field(description="Exact words copied from the message that show the event")
    why: str = Field(description="Why this passage matters commercially")


class RuleLink(BaseModel):
    rule_id: str = Field(description="id of an approved contract rule from the list provided")
    clause_ref: str
    reason: str


class Classification(BaseModel):
    category: Category
    secondary_categories: list[Category] = Field(description="Other categories that also apply, most important first")
    confidence: float = Field(ge=0, le=1, description="Probability the category is correct")
    title: str = Field(description="Short register title, e.g. 'Block B pad foundations enlarged (RA-STR-110 rev C)'")
    summary: str = Field(description="2-3 sentences: what happened, who caused it, likely commercial effect")
    trigger_date: str | None = Field(description="YYYY-MM-DD: earliest date the contractor was or should have been aware; null for noise")
    trigger_date_basis: str = Field(description="How the trigger date was chosen")
    evidence: list[Evidence]
    linked_rules: list[RuleLink] = Field(description="Approved rules whose notice obligations this event triggers, most important first")
    related_event_ref: str | None = Field(description="Ref of an existing open event this message is about (e.g. PE-003), else null")


class DraftCitation(BaseModel):
    source: Literal["message", "clause"]
    quote: str = Field(description="Exact words copied from the triggering message or the clause text")


class NoticeDraftOut(BaseModel):
    subject: str
    recipient: str
    body: str
    citations: list[DraftCitation]
    assumptions: list[str] = Field(description="Facts the user must check before sending (e.g. dates, names, quantities)")
