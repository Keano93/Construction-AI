"""Pure (DB-free) parts of the Notice agent, shared by the pipeline and the eval harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ...config import get_settings
from ..citations import locate_quote
from .schemas import Classification


@dataclass
class RuleView:
    id: str
    clause_ref: str
    title: str
    rule_type: str
    event_categories: list[str]
    period_value: int | None
    period_unit: str | None
    summary: str
    condition_precedent: bool = False


@dataclass
class EventView:
    ref: str
    category: str
    title: str
    trigger_date: str
    description: str = ""


@dataclass
class MessageView:
    text: str
    channel: str
    timestamp: datetime | None
    author: str | None
    author_role: str
    subject: str | None = None


@dataclass
class VerifiedClassification:
    raw: Classification
    category: str
    confidence: float
    trigger_date: date | None
    rules: list[RuleView]
    evidence_spans: list[tuple[int, int, str]]  # offsets within message text
    auto_linked: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def low_confidence(self) -> bool:
        return self.confidence < get_settings().low_confidence_threshold

    @property
    def primary_rule(self) -> RuleView | None:
        for r in self.rules:
            if r.rule_type in ("notice", "time_bar") and r.period_value is not None:
                return r
        return self.rules[0] if self.rules else None


NOTICE_RULE_TYPES = {"notice", "time_bar"}


def rules_block(rules: list[RuleView]) -> str:
    if not rules:
        return "(none approved yet)"
    out = []
    for r in rules:
        period = f"{r.period_value} {r.period_unit.replace('_', ' ')}" if r.period_value is not None and r.period_unit else "no fixed period"
        cp = "; condition precedent" if r.condition_precedent else ""
        out.append(f"- id={r.id} | clause {r.clause_ref} {r.title} | applies to: {', '.join(r.event_categories) or '-'} | "
                   f"{period}{cp} | {r.summary}")
    return "\n".join(out)


def events_block(events: list[EventView]) -> str:
    if not events:
        return "(none)"
    return "\n".join(f"- {e.ref} [{e.category}] {e.title} (aware {e.trigger_date})" for e in events)


def classify_variables(project: str, parties: str, rules: list[RuleView], events: list[EventView], msg: MessageView) -> dict:
    return {
        "project": project,
        "parties": parties,
        "rules": rules_block(rules),
        "open_events": events_block(events),
        "channel": msg.channel,
        "timestamp": msg.timestamp.isoformat() if msg.timestamp else "unknown",
        "author": msg.author or "unknown",
        "author_role": msg.author_role,
        "subject": msg.subject or "",
        "text": msg.text,
        # raw objects for the offline provider (ignored by prompt rendering)
        "_rules": rules,
        "_events": events,
        "_message": msg,
    }


def verify_classification(c: Classification, msg: MessageView, rules: list[RuleView]) -> VerifiedClassification:
    """Check model output against the source and the contract model; adjust confidence."""
    issues: list[str] = []
    conf = c.confidence
    spans = []
    for ev in c.evidence:
        span = locate_quote(msg.text, ev.quote)
        if span:
            spans.append((span[0], span[1], ev.why))
        else:
            issues.append(f"evidence quote not found in message: {ev.quote[:60]!r}")
    if c.category != "noise" and not spans:
        conf *= 0.5
        issues.append("no verifiable evidence for a non-noise classification")

    by_id = {r.id: r for r in rules}
    linked: list[RuleView] = []
    for link in c.linked_rules:
        r = by_id.get(link.rule_id)
        if r is None:
            issues.append(f"linked rule {link.rule_id} is not an approved rule; ignored")
            continue
        if r not in linked:
            linked.append(r)
    auto = False
    if c.category != "noise" and not linked:
        # fall back to approved notice rules registered for this category
        linked = [r for r in rules if c.category in r.event_categories and r.rule_type in NOTICE_RULE_TYPES]
        if linked:
            auto = True
            conf *= 0.85
            issues.append("no rule linked by the model; linked by category")
        else:
            issues.append("no approved contract rule covers this category")
            conf *= 0.7

    trig: date | None = None
    if c.category != "noise":
        msg_date = msg.timestamp.date() if msg.timestamp else None
        if c.trigger_date:
            try:
                trig = date.fromisoformat(c.trigger_date)
            except ValueError:
                issues.append(f"unparseable trigger date {c.trigger_date!r}")
        if trig and msg_date and (trig > msg_date or trig < msg_date - timedelta(days=120)):
            issues.append(f"trigger date {trig} implausible for message dated {msg_date}; using message date")
            trig = None
        if trig is None:
            trig = msg_date
    return VerifiedClassification(raw=c, category=c.category, confidence=round(min(max(conf, 0.0), 1.0), 3),
                                  trigger_date=trig, rules=linked, evidence_spans=spans, auto_linked=auto, issues=issues)
