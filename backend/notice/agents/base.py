"""Shared agent contract.

Every agent is a module that declares an `AgentSpec` and uses `run_task` for
each model call. `run_task`:
  * loads the versioned prompt,
  * calls the configured provider with a Pydantic output schema,
  * records an AgentRun (agent version, prompt id@version, provider, model,
    inputs, validated output, token usage, errors).

Agents then *verify* model output in code (citations, rule ids, dates) before
anything reaches the review queue, and compute deadlines with the deadline
engine — never with the model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deadlines import DeadlineRule, Shutdown, WorkingCalendar, compute_deadline
from ..llm import LLMError, get_provider, load_prompt
from ..models import AgentRun, ContractRule, Project, ReviewItem
from ..record import audit, log_project_event
from ..retrieval import search

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    version: str
    title: str
    pillar: str
    description: str
    inputs: list[str]
    outputs: list[str]
    status: str = "live"  # live | planned
    tools: list[str] = field(default_factory=list)


class AgentRunError(RuntimeError):
    pass


def run_task(
    db: Session,
    *,
    spec: AgentSpec,
    project_id: uuid.UUID,
    task: str,
    prompt_agent: str,
    variables: dict[str, Any],
    schema: type[T],
    inputs: dict[str, Any],
    max_tokens: int = 16000,
) -> tuple[T, AgentRun]:
    prompt = load_prompt(prompt_agent, task)
    provider = get_provider()
    run = AgentRun(project_id=project_id, agent=spec.name, agent_version=spec.version, task=task,
                   prompt_id=prompt.ref, provider=provider.name, model=provider.model, inputs=inputs)
    db.add(run)
    db.flush()
    try:
        result = provider.structured(task=f"{prompt_agent}.{task}", prompt=prompt, variables=variables,
                                     schema=schema, max_tokens=max_tokens)
    except LLMError as e:
        run.status, run.error, run.finished_at = "failed", str(e), datetime.now(timezone.utc)
        db.flush()
        raise AgentRunError(str(e)) from e
    run.output = result.output.model_dump(mode="json")
    run.model = result.model
    run.usage = result.usage
    run.status, run.finished_at = "succeeded", datetime.now(timezone.utc)
    db.flush()
    audit(db, action=f"agent.{spec.name}.{task}", actor_type="agent", actor_id=f"{spec.name}@{spec.version}",
          project_id=project_id, entity_type="agent_run", entity_id=run.id,
          details={"provider": provider.name, "model": result.model, "prompt": prompt.ref})
    return schema.model_validate(run.output), run


# --- tools shared by agents ---------------------------------------------

def project_calendar(project: Project) -> WorkingCalendar:
    return WorkingCalendar(
        region=project.holiday_region,
        working_weekdays=frozenset(project.working_weekdays or [0, 1, 2, 3, 4]),
        shutdowns=tuple(Shutdown(s.name, s.start, s.end) for s in project.shutdowns),
    )


def tool_compute_deadline(project: Project, rule: ContractRule, trigger: date) -> dict | None:
    if rule.period_value is None or rule.period_unit is None:
        return None
    res = compute_deadline(trigger, DeadlineRule(rule.period_value, rule.period_unit), project_calendar(project))
    return res.to_trace()


def tool_approved_rules(db: Session, project_id: uuid.UUID, categories: list[str] | None = None) -> list[ContractRule]:
    stmt = select(ContractRule).where(ContractRule.project_id == project_id, ContractRule.status == "approved")
    rules = list(db.execute(stmt).scalars())
    if categories:
        rules = [r for r in rules if set(r.event_categories or []) & set(categories)]
    return sorted(rules, key=lambda r: [int(x) for x in r.clause_ref.split(".") if x.isdigit()])


def tool_retrieve(db: Session, project_id: uuid.UUID, query: str, k: int = 6, kinds: list[str] | None = None):
    return search(db, project_id, query, k=k, kinds=kinds)


def tool_create_review_item(db: Session, *, project_id: uuid.UUID, spec: AgentSpec, run: AgentRun | None, kind: str,
                            title: str, summary: str, confidence: float, citations: list[dict], payload: dict,
                            category: str | None = None, **links) -> ReviewItem:
    low = confidence < get_settings().low_confidence_threshold or not citations
    item = ReviewItem(project_id=project_id, agent=spec.name, agent_run_id=run.id if run else None, kind=kind,
                      category=category, title=title, summary=summary, confidence=round(confidence, 3),
                      low_confidence=low, citations=citations, payload=payload, **links)
    db.add(item)
    db.flush()
    log_project_event(db, project_id, "review_item.created", actor=f"agent:{spec.name}", entity_type="review_item",
                      entity_id=item.id, payload={"kind": kind, "title": title, "low_confidence": low})
    return item
