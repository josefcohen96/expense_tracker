"""
Disabled CRON service. All scheduled jobs and recurrence automation have been removed per request.

This module is intentionally left as a no-op placeholder so imports won't break.
"""

import logging

logger = logging.getLogger(__name__)


class CronService:
    """No-op CronService placeholder (scheduling disabled)."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def start(self) -> None:
        logger.info("CronService.start() called, but scheduling is disabled.")

    def stop(self) -> None:
        logger.info("CronService.stop() called, but scheduling is disabled.")
