from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RuleType = Literal["notice", "time_bar", "payment", "retention", "variation", "eot"]
EventCategory = Literal["change", "delay", "instruction", "disruption"]
PeriodUnitT = Literal["working_days", "calendar_days", "weeks", "months"]


class ExtractedRule(BaseModel):
    rule_type: RuleType = Field(description="notice: contractor must notify; time_bar: claim barred if late; payment; retention; variation: change procedure step; eot: extension-of-time particulars")
    clause_ref: str = Field(description="Clause number exactly as in the contract, e.g. '9.2'")
    title: str
    summary: str = Field(description="One or two sentences in plain English for a QS")
    trigger_event: str | None = Field(description="What starts the clock, e.g. 'Contractor becomes aware of the delay'")
    event_categories: list[EventCategory] = Field(description="Which project event categories this obligation applies to (empty for payment/retention)")
    period_value: int | None = Field(description="Number of units in the period; null if no fixed period")
    period_unit: PeriodUnitT | None
    recipient: str | None = Field(description="Who the notice must go to")
    required_form: str | None = Field(description="Form/content requirements, e.g. 'in writing by email, subject CONTRACT NOTICE + clause'")
    condition_precedent: bool = Field(description="True if failure to comply bars entitlement")
    percentage: float | None = Field(description="For retention/payment rules: percentage if stated")
    day_of_month: int | None = Field(description="For payment application dates: day of month if stated")
    source_quote: str = Field(description="Verbatim sentence(s) from the clause that create the obligation")
    confidence: float = Field(ge=0, le=1)


class ContractExtraction(BaseModel):
    contract_form: str | None = Field(description="e.g. 'PWC-style building works (employer design)', 'NEC4 ECC', 'RIAI'")
    working_day_definition: str | None
    rules: list[ExtractedRule]
