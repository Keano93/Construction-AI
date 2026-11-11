from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChangeType = Literal["scope_increase", "scope_decrease", "specification_change", "quantity_change", "design_development",
                     "new_information", "administrative", "unclear"]
Band = Literal["none", "low", "medium", "high", "unknown"]


class ChangeAssessment(BaseModel):
    change_id: str = Field(description="Id of the change as given (C1, C2, ...)")
    summary: str = Field(description="One sentence a QS can read: what changed, in plain terms")
    change_type: ChangeType
    cost_impact: Band = Field(description="Likely effect on the contractor's cost")
    time_impact: Literal["none", "possible", "likely", "unknown"]
    affected_packages: list[str] = Field(description="Trades/packages affected, e.g. 'M&E', 'groundworks', 'windows'")
    potential_variation: bool = Field(description="True if this may be a Change the contractor should notify")
    rationale: str
    evidence_quote_old: str | None = Field(description="Exact words from the OLD text supporting the assessment, or null")
    evidence_quote_new: str | None = Field(description="Exact words from the NEW text supporting the assessment, or null")
    confidence: float = Field(ge=0, le=1)


class RevisionAssessment(BaseModel):
    overall_summary: str = Field(description="2-3 sentences on what this revision does commercially")
    downplaying_flags: list[str] = Field(description="Where the revision's own description understates the change (e.g. 'coordination only' but the specification is upgraded)")
    assessments: list[ChangeAssessment]
