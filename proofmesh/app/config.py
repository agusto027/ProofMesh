from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROOFMESH_", env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./proofmesh.db"
    host: str = "0.0.0.0"
    port: int = 8000
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    search_provider: str = "none"
    search_api_key: str | None = None
    document_root: str | None = None
    worker_timeout_seconds: int = Field(default=90, ge=1, le=600)
    max_budget_tokens: int = Field(default=50000, ge=100, le=1000000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
