"""Load the synthetic Riverside Apartments demo project.

    python -m seed.load_demo [--reset]

--reset drops and recreates the database schema first (destroys all data).
Login afterwards: demo@brennock.example / riverside-demo
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select, text

from notice.config import REPO_ROOT, get_settings
from notice.contract.service import review_rule
from notice.db import get_engine, session_scope
from notice.ingestion.extractors import MESSAGE_KINDS
from notice.jobs import drain, enqueue
from notice.ingestion.service import ingest_file
from notice.agents.claims_agent.agent import create_claim
from notice.models import Contract, ContractRule, Event, Item, Organisation, Party, Project, ProjectShutdown, ReviewItem, User
from notice.record import audit
from notice.security import hash_password

sys.path.insert(0, str(REPO_ROOT / "demo_data"))
from riverside_messages import P, ROLES  # noqa: E402

DEMO_DIR = REPO_ROOT / "demo_data" / "riverside"
EMAIL, PASSWORD = "demo@brennock.example", "riverside-demo"
AUTO_APPROVE = {"notice", "time_bar", "eot", "variation"}  # payment/retention left for the user to review in the UI


def reset_schema() -> None:
    from alembic import command
    from alembic.config import Config

    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")


def _ingest_tree(db, project, user, folder: str, kind: str | None = None, run_agents: bool = False) -> list:
    docs = []
    for path in sorted((DEMO_DIR / folder).rglob("*")):
        if path.is_file():
            res = ingest_file(db, project, path.name, path.read_bytes(), kind=kind, source="seed", uploaded_by=user.id,
                              run_agents=run_agents)
            docs.append(res.document)
    return docs


ESTIMATES = [  # demo QS estimates, EUR excl. VAT (illustrative figures)
    (r"RA-STR-110|foundations", 18500, "Larger pads P7-P14: concrete and rebar uplift"),
    (r"soft ground|B4 to B6", 42000, "Dig-out to 2.5m, mass concrete, standing plant"),
    (r"sprinkler tank", 48000, "Brightwater indicative EUR 40-50k plus builder's work"),
    (r"accessible units", 9800, "Partition moves and wider doors, B L1"),
    (r"lift pit", 14200, "Break out and recast pit base"),
    (r"outfall", 36500, "85m extra drainage run and road crossing"),
    (r"brick", 22000, "Cumbrian brick premium, all elevations"),
    (r"lighting columns", 6400, "4 no. columns, ducting and bases"),
]


def seed_commercial() -> None:
    """Illustrative QS estimates, and one notice approved and issued on 9 Nov 2026, so the commercial pack has content."""
    from notice.review import service as review

    with session_scope() as db:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        project = db.execute(select(Project).where(Project.org_id == user.org_id)).scalar_one()
        events = list(db.execute(select(Event).where(Event.project_id == project.id).order_by(Event.trigger_date)).scalars())
        for pattern, value, note in ESTIMATES:
            free = [e for e in events if e.estimated_value is None]
            ev = next((e for e in free if re.search(pattern, e.title, re.I)), None) or \
                next((e for e in free if re.search(pattern, e.description, re.I)), None)
            if ev:
                ev.estimated_value, ev.value_note = value, note
        steel = next((e for e in events if re.search(r"extension of time", e.title, re.I)), None)
        if steel:
            ri = db.execute(select(ReviewItem).where(ReviewItem.event_id == steel.id)).scalar_one_or_none()
            if ri and ri.draft_id:
                review.approve(db, ri, user.id, comment="Demo: approved")
                review.mark_issued(db, ri, user.id, date(2026, 11, 9), comment="Demo: sent by email")
        audit(db, action="seed.commercial", actor_type="system", actor_id="seed", org_id=project.org_id, project_id=project.id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate the schema first")
    args = ap.parse_args()
    if not DEMO_DIR.exists():
        sys.exit("demo_data/riverside not found - run: python demo_data/generate.py")
    if args.reset:
        reset_schema()

    with session_scope() as db:
        if db.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none():
            sys.exit("Demo already loaded. Use --reset to reload.")
        org = Organisation(name="Brennock Construction Ltd")
        db.add(org)
        db.flush()
        user = User(org_id=org.id, email=EMAIL, name="Aoife Daly (demo)", password_hash=hash_password(PASSWORD), role="admin")
        db.add(user)
        db.flush()
        project = Project(org_id=org.id, name="Riverside Apartments", code="RA-2026", location="Ballincollig Road, Co. Cork",
                          contract_form="PWC-style (employer designed building works)", holiday_region="IE",
                          start_date=date(2026, 7, 6))
        db.add(project)
        db.flush()
        # Contract definition of Working Day excludes 21 December - 3 January
        db.add(ProjectShutdown(project_id=project.id, name="Christmas (contract Working Day definition)",
                               start=date(2026, 12, 21), end=date(2027, 1, 3)))
        for key, (name, email) in P.items():
            role, organisation = ROLES[key]
            db.add(Party(project_id=project.id, name=name, email=email, role=role, organisation=organisation))
        audit(db, action="seed.demo_project", actor_type="system", actor_id="seed", org_id=org.id, project_id=project.id)
        db.flush()
        db.refresh(project)

        # 1. contract -> rule extraction
        _ingest_tree(db, project, user, "contract", kind="contract", run_agents=True)
    print(f"Contract ingested; extracting rules ({get_settings().llm_provider} provider)...")
    drain()

    with session_scope() as db:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        project = db.execute(select(Project).where(Project.org_id == user.org_id)).scalar_one()
        rules = list(db.execute(select(ContractRule).where(ContractRule.project_id == project.id)).scalars())
        approved = 0
        for r in rules:
            if r.rule_type in AUTO_APPROVE and r.details.get("quote_verified", False):
                review_rule(db, r, user_id=user.id, decision="approve")
                approved += 1
        print(f"Contract rules: {len(rules)} extracted, {approved} approved by the demo user, {len(rules) - approved} left for review")

        # 2. correspondence + diaries, processed in chronological order
        docs = []
        for folder in ("correspondence", "site_diary"):
            docs += _ingest_tree(db, project, user, folder, run_agents=False)
        items = list(db.execute(select(Item).where(Item.project_id == project.id, Item.kind.in_(MESSAGE_KINDS))).scalars())
        for it in sorted(items, key=lambda i: i.timestamp):
            enqueue(db, "notice_agent.process_item", {"item_id": it.id}, project.id)
        print(f"Correspondence: {len(docs)} documents, {len(items)} messages queued for the Notice agent")

        # 3. other project documents (used by later-phase agents)
        n = 0
        n += len(_ingest_tree(db, project, user, "drawings", run_agents=True))  # revision pairs auto-compare
        for folder, kind in (("tender", "quote"), ("compliance", "compliance")):
            n += len(_ingest_tree(db, project, user, folder, kind=kind))
        print(f"Drawings, quotes, compliance: {n} documents (drawing/spec revisions queued for the Revision agent)")

    processed = drain()

    # Demo claim: the unforeseen ground conditions at B4-B6 (first change event that mentions them)
    with session_scope() as db:
        user = db.execute(select(User).where(User.email == EMAIL)).scalar_one()
        project = db.execute(select(Project).where(Project.org_id == user.org_id)).scalar_one()
        ground = [e for e in db.execute(select(Event).where(Event.project_id == project.id).order_by(Event.trigger_date)).scalars()
                  if re.search(r"soft|ground|B4", f"{e.title} {e.description}", re.I)][:2]
        if ground:
            claim = create_claim(db, project, [e.id for e in ground], user.id, "Unforeseen ground conditions at B4-B6")
            enqueue(db, "claims_agent.draft", {"claim_id": claim.id}, project.id)
    processed += drain()
    seed_commercial()
    with session_scope() as db:
        pending = db.execute(select(ReviewItem).where(ReviewItem.status == "pending")).scalars().all()
        low = sum(1 for r in pending if r.low_confidence)
        contract = db.execute(select(Contract)).scalars().first()
        kinds = {}
        for r in pending:
            kinds[r.kind] = kinds.get(r.kind, 0) + 1
        print(f"Jobs run: {processed}. Review queue: {len(pending)} pending ({low} low confidence) {kinds}. Contract status: {contract.status}")
    print(f"\nLogin: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
