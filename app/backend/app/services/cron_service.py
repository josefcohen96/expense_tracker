"""
APScheduler-based CronService for materializing recurring transactions.

Runs `apply_recurring` once at startup and then daily at 03:15.
The recurrence algorithm is idempotent (unique (recurrence_id, period_key)),
so multiple invocations won't duplicate data.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import recurrence

logger = logging.getLogger(__name__)


class CronService:
    """Background scheduler for recurring jobs."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None
        self._daily_job_id = "apply_recurring_daily"
        self._startup_job_id = "apply_recurring_startup"

    def start(self) -> None:
        if self._scheduler is not None:
            logger.info("CronService already started; ignoring duplicate start.")
            return

        scheduler = BackgroundScheduler()

        # Immediate run on startup
        scheduler.add_job(
            self._run_apply_recurring,
            id=self._startup_job_id,
            next_run_time=datetime.now(),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

        # Daily schedule at 03:15 (server local time)
        daily_trigger = CronTrigger(hour=3, minute=15)
        scheduler.add_job(
            self._run_apply_recurring,
            id=self._daily_job_id,
            trigger=daily_trigger,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

        scheduler.start()
        self._scheduler = scheduler
        logger.info("CronService started: startup and daily recurrence jobs scheduled.")

    def stop(self) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.shutdown(wait=False)
            logger.info("CronService stopped.")
        finally:
            self._scheduler = None

    @staticmethod
    def _run_apply_recurring() -> None:
        try:
            inserted = recurrence.apply_recurring()
            logger.info("apply_recurring executed: inserted=%s", inserted)
        except Exception:
            logger.exception("apply_recurring failed")
