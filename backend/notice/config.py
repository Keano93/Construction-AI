from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOTICE_", extra="ignore")

    database_url: str = "postgresql+psycopg://notice:notice@localhost:5432/notice"
    secret_key: str = "dev-only-insecure-secret-change-me-in-production"
    token_ttl_minutes: int = 60 * 12
    storage_dir: Path = REPO_ROOT / "var" / "storage"
    prompts_dir: Path = REPO_ROOT / "prompts"

    # LLM
    llm_provider: str = "auto"  # auto | claude | offline
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    claude_server_fallbacks: bool = True

    # Agents
    low_confidence_threshold: float = 0.7
    jobs_inline: bool = False  # run jobs synchronously (tests, seed)

    embedding_dim: int = 384
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
