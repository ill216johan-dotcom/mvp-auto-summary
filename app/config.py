"""
Centralized configuration loaded from environment variables / .env file.

Replaces the scattered credential management across n8n workflows,
gen_wf*.py scripts, and hardcoded values in test scripts.

All settings are typed and validated via pydantic-settings.
Backward-compatible with existing .env variable names (GLM4_*, etc.).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="n8n", alias="POSTGRES_DB")
    postgres_user: str = Field(default="n8n", alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")

    @property
    def database_dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password}"
        )

    # ── LLM (Claude via z.ai — Anthropic Messages API) ───────
    #    Backward-compatible: reads GLM4_* env vars
    llm_api_key: str = Field(alias="GLM4_API_KEY")
    llm_base_url: str = Field(
        default="https://api.z.ai/api/anthropic",
        alias="GLM4_BASE_URL",
    )
    llm_model: str = Field(
        default="claude-3-5-haiku-20241022",
        alias="GLM4_MODEL",
    )

    # ── Telegram ──────────────────────────────────────────────
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # ── Dify (RAG) ────────────────────────────────────────────
    dify_api_key: str = Field(default="", alias="DIFY_API_KEY")
    dify_base_url: str = Field(
        default="https://dify-ff.duckdns.org",
        alias="DIFY_BASE_URL",
    )
    dify_chatbot_url: str = Field(default="", alias="DIFY_CHATBOT_URL")

    # ── Transcribe service ────────────────────────────────────
    transcribe_url: str = Field(
        default="http://transcribe:9001",
        alias="TRANSCRIBE_URL",
    )
    # Direct Whisper URL for multipart /v1/audio/transcriptions call
    whisper_url: str = Field(
        default="http://whisper:8000",
        alias="WHISPER_URL",
    )

    # ── Paths ─────────────────────────────────────────────────
    recordings_dir: str = Field(default="/recordings", alias="RECORDINGS_DIR")
    summaries_dir: str = Field(default="/summaries", alias="SUMMARIES_DIR")
    summaries_base_url: str = Field(
        default="http://84.252.100.93:8181",
        alias="SUMMARIES_BASE_URL",
    )

    # ── Schedule (Moscow time) ────────────────────────────────
    timezone: str = Field(default="Europe/Moscow", alias="TIMEZONE")
    scan_interval_minutes: int = Field(default=5)
    individual_summary_hour: int = Field(default=22)   # WF03
    deadline_extractor_hour: int = Field(default=22)    # WF06
    deadline_extractor_minute: int = Field(default=30)
    daily_digest_hour: int = Field(default=23)          # WF02

    # ── Bitrix24 CRM ──────────────────────────────────────────
    bitrix_webhook_url: str = Field(default="", alias="BITRIX_WEBHOOK_URL")
    bitrix_contract_field: str = Field(default="", alias="BITRIX_CONTRACT_FIELD")
    bitrix_sync_hour: int = Field(default=22, alias="BITRIX_SYNC_HOUR")
    bitrix_sync_enabled: bool = Field(default=True, alias="BITRIX_SYNC_ENABLED")

    # ── Bitrix24 event webhook receiver ───────────────────────
    webhook_port: int = Field(default=8009, alias="WEBHOOK_PORT")

def get_settings() -> Settings:
    """Create and return settings instance (cached at module level)."""
    return Settings()  # type: ignore[call-arg]
