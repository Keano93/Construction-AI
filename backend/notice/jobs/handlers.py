"""Job type -> handler wiring. Imported lazily by the queue."""

import uuid

from sqlalchemy.orm import Session

from ..agents.notice_agent.agent import run_notice_agent_for_item
from ..contract.service import run_contract_extraction
from .queue import job_handler


@job_handler("contract.extract")
def _contract_extract(db: Session, payload: dict) -> None:
    run_contract_extraction(db, uuid.UUID(payload["contract_id"]))


@job_handler("notice_agent.process_item")
def _notice_item(db: Session, payload: dict) -> None:
    run_notice_agent_for_item(db, uuid.UUID(payload["item_id"]))
