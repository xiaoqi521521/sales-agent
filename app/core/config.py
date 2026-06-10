from functools import lru_cache
from pathlib import Path
from decimal import Decimal

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
    openai_model: str = "deepseek-v4-flash"
    openai_streaming_model: str = "deepseek-v4-flash"
    jwt_secret_key: str = "dev-secret-change-me-use-env-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    token_input_price_per_1m: Decimal = Decimal("1")
    token_cached_input_price_per_1m: Decimal = Decimal("0.2")
    token_output_price_per_1m: Decimal = Decimal("2")
    token_cost_currency: str = "CNY"
    token_warn_total_threshold: int = 0
    token_warn_cost_threshold: Decimal = Decimal("0")
    agent_summary_model: str = "deepseek-v4-flash"
    agent_summary_trigger_messages: int = 20
    agent_summary_keep_messages: int = 6

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
