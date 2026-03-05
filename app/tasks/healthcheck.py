"""
Healthcheck task - triggers missed jobs.

Runs every 30 minutes and checks:
  - If time > 22:30 and individual_summary not run today → trigger WF03
  - If time > 23:30 and daily_digest not sent today → trigger WF02
"""
from __future__ import annotations

from datetime import date, datetime

from app.core.db import Database
from app.core.logger import get_logger
from app.tasks.daily_digest import DailyDigestTask
from app.tasks.individual_summary import IndividualSummaryTask

log = get_logger("healthcheck")


def run_healthcheck(
    db: Database,
    summary_task: IndividualSummaryTask,
    digest_task: DailyDigestTask,
) -> None:
    """
    Check for missed scheduled jobs and trigger them if needed.
    
    This ensures that even if the orchestrator was down during scheduled time,
    critical jobs still run.
    """
    now = datetime.now()
    today = date.today()
    
    log.info("healthcheck_running", time=now.isoformat())
    
    # Check WF03: Individual summaries
    if now.hour >= 22 and now.minute >= 30:
        try:
            unprocessed = db.get_unprocessed_calls(today)
            if unprocessed:
                log.warning(
                    "healthcheck_triggering_summary",
                    count=len(unprocessed),
                    reason="unprocessed calls found after 22:30",
                )
                summary_task.run(target_date=today)
        except Exception as e:
            log.error("healthcheck_summary_failed", error=str(e), exc_info=True)
    
    # Check WF02: Daily digest
    if now.hour >= 23 and now.minute >= 30:
        try:
            todays_summaries = db.get_todays_summaries(today)
            digest_sent = db.is_digest_sent(today)
            
            if todays_summaries and not digest_sent:
                log.warning(
                    "healthcheck_triggering_digest",
                    count=len(todays_summaries),
                    reason="summaries exist but digest not sent after 23:30",
                )
                digest_task.run()
        except Exception as e:
            log.error("healthcheck_digest_failed", error=str(e), exc_info=True)
    
    log.info("healthcheck_completed")
