"""Reconcile per-record APScheduler jobs with database preferences."""

import asyncio
from datetime import UTC, datetime

import httpx
from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config import Settings
from db.db_manager import DB_Manager
from db.models import Node, Software
from utils.health import healthcheck
from utils.ping import ping


class MonitorService:
    def __init__(self, db: DB_Manager, client: httpx.AsyncClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings
        self.slots = asyncio.Semaphore(settings.CHECK_CONCURRENCY)
        self._tasks: set[asyncio.Task] = set()
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
        )
        self.scheduler.add_listener(self._log_job_error, EVENT_JOB_ERROR)

    @staticmethod
    def _log_job_error(event: JobExecutionEvent) -> None:
        logger.opt(exception=event.exception).error("Scheduled job {} failed", event.job_id)

    async def start(self) -> None:
        self.scheduler.start(paused=True)
        await self.sync_jobs()
        self.scheduler.add_job(
            self.sync_jobs,
            "interval",
            seconds=self.settings.SCHEDULE_SYNC_SECONDS,
            id="schedule-sync",
        )
        self.scheduler.resume()
        logger.info("Monitoring scheduler started")

    async def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            # AsyncIOScheduler queues shutdown on its event loop. Let it cancel
            # running checks before the shared HTTP client and engine are closed.
            await asyncio.sleep(0)
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
            logger.info("Monitoring scheduler stopped")

    async def sync_jobs(self) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            wanted: set[str] = set()
            nodes = await self.db.get_entities(
                Node, where={"ping_check_enabled": True}
            )
            software = await self.db.get_entities(
                Software, where={"health_check_enabled": True}
            )
            for node in nodes:
                self._ensure_job(
                    wanted, f"ping:{node.id}", node.ping_check_every, self.check_node, node.id
                )
            for item in software:
                self._ensure_job(
                    wanted, f"health:{item.id}", item.health_check_every, self.check_software, item.id
                )
            for job in self.scheduler.get_jobs():
                if job.id != "schedule-sync" and job.id not in wanted:
                    self.scheduler.remove_job(job.id)
        finally:
            self._tasks.discard(task)

    def _ensure_job(
        self, wanted: set[str], job_id: str, seconds: int, callback, record_id: int
    ) -> None:
        if not isinstance(seconds, int) or seconds <= 0:
            logger.warning("Skipping {}: interval must be a positive number of seconds", job_id)
            return
        wanted.add(job_id)
        existing = self.scheduler.get_job(job_id)
        if existing and existing.trigger.interval.total_seconds() == seconds:
            return
        self.scheduler.add_job(
            callback,
            "interval",
            seconds=seconds,
            args=[record_id],
            id=job_id,
            replace_existing=True,
            next_run_time=datetime.now(UTC),
        )
        logger.info("Scheduled {} every {} seconds", job_id, seconds)

    async def check_node(self, node_id: int) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async with self.slots:
                node = await self.db.get_entity(Node, node_id)
                if node is None or not node.ping_check_enabled:
                    return
                healthy = await ping(node, timeout=self.settings.CHECK_TIMEOUT_SECONDS)
                await self.db.update_entity(
                    Node,
                    node.id,
                    is_ping_ok=healthy,
                    last_checked_at=datetime.now(UTC).replace(tzinfo=None),
                )
                logger.debug("Node #{} ping: {}", node.id, healthy)
        finally:
            self._tasks.discard(task)

    async def check_software(self, software_id: int) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async with self.slots:
                software = await self.db.get_entity(Software, software_id)
                if software is None or not software.health_check_enabled:
                    return
                healthy = await healthcheck(
                    software, self.client, timeout=self.settings.CHECK_TIMEOUT_SECONDS
                )
                await self.db.update_entity(
                    Software,
                    software.id,
                    is_healthy=healthy,
                    last_checked_at=datetime.now(UTC).replace(tzinfo=None),
                )
                logger.debug("Software #{} healthy: {}", software.id, healthy)
        finally:
            self._tasks.discard(task)
