"""Application entry point: uvicorn app:app --host 0.0.0.0 --port 3001."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import config
from db.db_manager import DB_Manager
from db.models import DATABASE_URL, create_database_engine, init_db
from routes.admin import mount_admin
from routes.map import router
from utils.monitoring import MonitorService

ROOT = Path(__file__).resolve().parent


def create_app(
    database_url: str = DATABASE_URL, *, monitoring_enabled: bool | None = None
) -> FastAPI:
    """The factory lets tests use an isolated database and disable real checks."""
    engine = create_database_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    db = DB_Manager(sessions)
    enabled = config.MONITORING_ENABLED if monitoring_enabled is None else monitoring_enabled

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logger.remove()
        logger.add(sys.stderr, level=config.LOG_LEVEL, backtrace=False, diagnose=False)
        try:
            await init_db(engine)
            async with httpx.AsyncClient(
                trust_env=False,
                limits=httpx.Limits(
                    max_connections=config.CHECK_CONCURRENCY,
                    max_keepalive_connections=config.CHECK_CONCURRENCY,
                ),
            ) as client:
                monitor = MonitorService(db, client, config)
                application.state.monitor = monitor
                try:
                    if enabled:
                        await monitor.start()
                    logger.info("Light Server Map started")
                    yield
                finally:
                    await monitor.stop()
        finally:
            await engine.dispose()

    application = FastAPI(title="Light Server Map", version="0.1.0", lifespan=lifespan)
    application.state.db = db
    application.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    application.include_router(router)
    mount_admin(application, sessions, config)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3001)
