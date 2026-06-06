from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "sales-agent"
    app_version: str = "0.1.0"
    database_url: str = "sqlite+aiosqlite:///./sales_agent.db"
    database_echo: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    openai_api_key: str = ""
    openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openai_model: str = "qwen-max"
    openai_streaming_model: str = "qwen-max"
    jwt_secret_key: str = "dev-secret-change-me-use-env-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
