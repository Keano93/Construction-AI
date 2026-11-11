import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("NOTICE_DATABASE_URL", "postgresql+psycopg://notice:notice@localhost:5432/notice_test")
os.environ["NOTICE_LLM_PROVIDER"] = "offline"
os.environ["NOTICE_JOBS_INLINE"] = "true"
os.environ.setdefault("NOTICE_STORAGE_DIR", str(Path(__file__).resolve().parents[2] / "var" / "test-storage"))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo_data"))


def _db_available() -> bool:
    from sqlalchemy import text

    from notice.db import get_engine

    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def migrated():
    if not _db_available():
        pytest.skip("Postgres test database not available")
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from notice.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def client(migrated):
    from fastapi.testclient import TestClient

    from notice.llm import set_provider
    from notice.main import app

    set_provider(None)
    return TestClient(app)


def register(client, email, org="Test Contractor Ltd"):
    r = client.post("/api/auth/register", json={"organisation": org, "name": "Test QS", "email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
