from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Significance = Literal["cause", "effect", "instruction", "notice", "response", "mitigation", "record"]


class TimelineEntry(BaseModel):
    evidence_id: str = Field(description="Id of the evidence item (E1, E2, ...) this entry is based on")
    description: str = Field(description="One factual sentence: what this record shows")
    significance: Significance
    quote: str = Field(description="Exact words copied from that evidence item")


class TimelineOut(BaseModel):
    entries: list[TimelineEntry] = Field(description="Only evidence relevant to the claim; skip irrelevant items")
    gaps: list[str] = Field(description="Records a claims consultant would expect but which are missing (e.g. daywork sheets, photos, plant hire invoices)")


class QuantumHead(BaseModel):
    head: str = Field(description="Head of claim, e.g. 'Additional excavation and mass concrete', 'Standing plant'")
    basis: str = Field(description="How it would be valued (rates, dayworks, actual cost) - no figures")
    records_needed: list[str]


class NarrativeCitation(BaseModel):
    source: str = Field(description="Evidence id (E3) or clause reference (clause 4.6)")
    quote: str = Field(description="Exact words from that evidence item or clause")


class ClaimNarrative(BaseModel):
    title: str
    executive_summary: str
    entitlement: str = Field(description="Contractual basis: the clauses relied on and why they apply")
    notice_position: str = Field(description="Describe notice compliance exactly as given in the compliance table; do not assess it differently")
    cause: str = Field(description="What happened and why it is the Employer's risk, in date order")
    effect: str = Field(description="Effect on time and cost, by reference to the records")
    quantum_heads: list[QuantumHead]
    risks: list[str] = Field(description="Weaknesses the Employer's Representative is likely to raise")
    citations: list[NarrativeCitation]
    confidence: float = Field(ge=0, le=1)
