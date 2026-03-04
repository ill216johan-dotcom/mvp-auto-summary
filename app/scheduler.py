"""
Job Scheduler — APScheduler-based cron and interval jobs.

Replaces n8n schedule triggers:
  WF01: */5 * * * *  (every 5 min)  → scan + check_pending
  WF03: 0 22 * * *   (22:00 daily) → individual summaries
  WF06: */15 * * * *  (every 15 min) → deadline extraction
  WF02: 0 23 * * *   (23:00 daily) → daily digest
"""
from __future__ import annotations

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobEvent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings
from app.core.db import Database
from app.core.dify_api import DifyClient
from app.core.llm import LLMClient
from app.core.logger import get_logger
from app.core.telegram_api import TelegramSender
from app.tasks.daily_digest import DailyDigestTask
from app.tasks.deadline_extractor import DeadlineExtractorTask
from app.tasks.individual_summary import IndividualSummaryTask
from app.tasks.scan_recordings import RecordingScanner

log = get_logger("scheduler")


def _on_job_event(event: JobEvent) -> None:
    """Log job execution results."""
    if event.exception:
        log.error(
            "job_failed",
            job_id=event.job_id,
            error=str(event.exception),
        )
    else:
        log.debug("job_executed", job_id=event.job_id)


def create_scheduler(
    settings: Settings,
    db: Database,
    llm: LLMClient,
    telegram: TelegramSender,
    dify: DifyClient,
) -> BackgroundScheduler:
    """
    Create and configure the background job scheduler.

    Jobs registered:
      - scan_recordings: every N minutes (WF01)
      - check_pending: every N minutes (WF01 companion)
      - individual_summary: daily at HH:00 (WF03)
      - deadline_extractor: every 15 min (WF06)
      - daily_digest: daily at HH:00 (WF02)
    """
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_listener(_on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # ── Task instances ────────────────────────────────────────
    scanner = RecordingScanner(db, settings.transcribe_url, settings.recordings_dir)

    summary_task = IndividualSummaryTask(
        db=db,
        llm=llm,
        dify=dify,
        summaries_dir=settings.summaries_dir,
        summaries_base_url=settings.summaries_base_url,
    )

    deadline_task = DeadlineExtractorTask(
        db=db,
        llm=llm,
        telegram=telegram,
        notify_chat_id=settings.telegram_chat_id,
    )

    digest_task = DailyDigestTask(
        db=db,
        llm=llm,
        telegram=telegram,
        default_chat_id=settings.telegram_chat_id,
        summaries_base_url=settings.summaries_base_url,
    )

    # ── Schedule: WF01 — Scan every N minutes ─────────────────
    scheduler.add_job(
        scanner.scan,
        IntervalTrigger(minutes=settings.scan_interval_minutes),
        id="scan_recordings",
        name="WF01: Scan /recordings for new files",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        scanner.check_pending,
        IntervalTrigger(minutes=settings.scan_interval_minutes),
        id="check_pending",
        name="WF01: Check pending transcriptions",
        max_instances=1,
        coalesce=True,
    )

    # ── Schedule: WF03 — Individual summaries at 22:00 ────────
    scheduler.add_job(
        summary_task.run,
        CronTrigger(hour=settings.individual_summary_hour, minute=0),
        id="individual_summary",
        name="WF03: Per-client summaries",
        max_instances=1,
    )

    # ── Schedule: WF06 — Deadline extraction every 15 min ─────
    scheduler.add_job(
        deadline_task.run,
        IntervalTrigger(minutes=15),
        id="deadline_extractor",
        name="WF06: Extract tasks & deadlines",
        max_instances=1,
        coalesce=True,
    )

    # ── Schedule: WF02 — Daily digest at 23:00 ────────────────
    scheduler.add_job(
        digest_task.run,
        CronTrigger(hour=settings.daily_digest_hour, minute=0),
        id="daily_digest",
        name="WF02: Daily digest → Telegram",
        max_instances=1,
    )

    log.info(
        "scheduler_configured",
        jobs=len(scheduler.get_jobs()),
        timezone=settings.timezone,
        scan_interval=f"{settings.scan_interval_minutes}m",
        summary_at=f"{settings.individual_summary_hour}:00",
        digest_at=f"{settings.daily_digest_hour}:00",
    )

    return scheduler
