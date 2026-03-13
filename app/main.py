"""
MVP Auto-Summary Orchestrator — Entry Point.

Replaces the entire n8n container with a single Python process:
  - APScheduler for cron/interval jobs (WF01, WF02, WF03, WF06)
  - python-telegram-bot for bot commands (WF04)
  - Structured logging for monitoring

Usage:
  python -m app.main

Environment:
  All configuration via .env file (see app/config.py).
"""
from __future__ import annotations

import asyncio
import signal
import sys

from app.config import get_settings
from app.core.db import Database
from app.core.dify_api import DifyClient
from app.core.llm import LLMClient
from app.core.logger import get_logger, setup_logging
from app.core.telegram_api import TelegramSender
from app.bot.handler import BotService
from app.scheduler import create_scheduler
from app.webhook_server import WebhookServer

log = get_logger("main")


def main() -> None:
    """Start the orchestrator: scheduler + Telegram bot."""
    setup_logging("INFO")
    log.info("orchestrator_starting", version="1.0.0")

    settings = get_settings()

    # ── Initialize core services ──────────────────────────────
    db = Database(settings.database_dsn)
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    telegram = TelegramSender(settings.telegram_bot_token)
    dify = DifyClient(settings.dify_api_key, settings.dify_base_url)

    log.info(
        "services_initialized",
        db="connected",
        llm_model=settings.llm_model,
        llm_url=settings.llm_base_url,
        recordings_dir=settings.recordings_dir,
    )

    if settings.bitrix_sync_enabled:
        log.info(
            "bitrix_enabled",
            webhook=settings.bitrix_webhook_url[:50] + "..." if len(settings.bitrix_webhook_url) > 50 else settings.bitrix_webhook_url,
            sync_hour=settings.bitrix_sync_hour,
            contract_field=settings.bitrix_contract_field or "NOT_SET",
        )

    # ── Start scheduler (WF01, WF02, WF03, WF06) ─────────────
    scheduler = create_scheduler(settings, db, llm, telegram, dify)
    scheduler.start()
    log.info("scheduler_started", jobs=len(scheduler.get_jobs()))

    # ── Start Bitrix24 webhook server (new calls → instant transcription) ──
    webhook_server: WebhookServer | None = None
    if settings.bitrix_sync_enabled and settings.bitrix_webhook_url:
        webhook_server = WebhookServer(
            db=db,
            transcribe_url=settings.transcribe_url,
            bitrix_webhook_url=settings.bitrix_webhook_url,
            port=settings.webhook_port,
            whisper_url=settings.whisper_url,
        )
        webhook_server.start()

    # ── Start Telegram bot (WF04) — blocking ──────────────────
    bot = BotService(
        token=settings.telegram_bot_token,
        db=db,
        llm=llm,
        dify_chatbot_url=settings.dify_chatbot_url,
        summaries_base_url=settings.summaries_base_url,
    )

    def shutdown(signum, frame):
        log.info("shutdown_signal_received", signal=signum)
        scheduler.shutdown(wait=False)
        if webhook_server:
            webhook_server.stop()
        llm.close()
        telegram.close()
        dify.close()
        db.close()
        log.info("orchestrator_stopped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        # Bot.run_polling() is blocking — scheduler runs in background threads
        bot.start_polling()
    except KeyboardInterrupt:
        shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()
