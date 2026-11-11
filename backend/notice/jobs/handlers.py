"""Job type -> handler wiring. Imported lazily by the queue."""

import uuid

from sqlalchemy.orm import Session

from ..agents.claims_agent.agent import run_claims_agent
from ..agents.notice_agent.agent import run_notice_agent_for_item
from ..agents.revision_agent.agent import run_revision_compare
from ..contract.service import run_contract_extraction
from .queue import job_handler


@job_handler("contract.extract")
def _contract_extract(db: Session, payload: dict) -> None:
    run_contract_extraction(db, uuid.UUID(payload["contract_id"]))


@job_handler("notice_agent.process_item")
def _notice_item(db: Session, payload: dict) -> None:
    run_notice_agent_for_item(db, uuid.UUID(payload["item_id"]))


@job_handler("revision_agent.compare")
def _revision_compare(db: Session, payload: dict) -> None:
    run_revision_compare(db, uuid.UUID(payload["base_id"]), uuid.UUID(payload["revised_id"]),
                         uuid.UUID(payload["user_id"]) if payload.get("user_id") else None)


@job_handler("claims_agent.draft")
def _claims_draft(db: Session, payload: dict) -> None:
    run_claims_agent(db, uuid.UUID(payload["claim_id"]))
