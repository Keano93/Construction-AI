"""Load the synthetic Riverside Apartments demo project.

    python -m seed.load_demo [--reset]

--reset drops and recreates the database schema first (destroys all data).
Login afterwards: demo@brennock.example / riverside-demo
"""

from __future__ import annotations

import argparse
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
from notice.models import Contract, ContractRule, Item, Organisation, Party, Project, ProjectShutdown, ReviewItem, User
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
        for folder, kind in (("drawings", None), ("tender", "quote"), ("compliance", "compliance")):
            n += len(_ingest_tree(db, project, user, folder, kind=kind))
        print(f"Drawings, quotes, compliance: {n} documents")

    processed = drain()
    with session_scope() as db:
        pending = db.execute(select(ReviewItem).where(ReviewItem.status == "pending")).scalars().all()
        low = sum(1 for r in pending if r.low_confidence)
        contract = db.execute(select(Contract)).scalars().first()
        print(f"Jobs run: {processed}. Review queue: {len(pending)} pending ({low} low confidence). Contract status: {contract.status}")
    print(f"\nLogin: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
