"""Application configuration loaded from environment variables."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Central settings object. Values come from env vars / .env."""

    def __init__(self) -> None:
        self.database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://report_agent:report_agent_password@localhost:5434/daily_reports",
        )
        self.openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model: str = os.getenv(
            "OPENROUTER_MODEL", "openrouter/free"
        )
        self.openrouter_base_url: str = "https://openrouter.ai/api/v1"
        self.gradio_server_name: str = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
        self.gradio_server_port: int = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def validate_for_llm(self) -> None:
        """Raise a clear error if the OpenRouter key is missing when LLM is needed."""
        if not self.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. "
                "Copy .env.example to .env and add your key from https://openrouter.ai"
            )

    def validate_for_db(self) -> None:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Expected format: postgresql+psycopg://user:pass@host:port/dbname"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def setup_logging(level: str | None = None) -> None:
    """Configure root logger once at startup."""
    lvl = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
