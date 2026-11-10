"""SQLAlchemy models and async database setup."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, case, event, func, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import config


class Base(DeclarativeBase):
    pass


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (CheckConstraint("ping_check_every > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))

    is_ping_ok: Mapped[bool | None] = mapped_column(
        Boolean(create_constraint=True), default=None
    )
    ping_check_enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False
    )
    ping_check_every: Mapped[int] = mapped_column(default=30)  # Seconds.
    notificatons_enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False
    )
    last_checked_at: Mapped[datetime | None]

    softwares: Mapped[list["Software"]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    def __str__(self) -> str:
        return f"{self.name} (#{self.id})"


class SoftwareTypes(str, Enum):
    DB = "database"
    APP = "app"


class Software(Base):
    __tablename__ = "softwares"
    __table_args__ = (
        CheckConstraint("health_check_every > 0"),
        CheckConstraint("port > 0 AND port <= 65535"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default=SoftwareTypes.APP.value)
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )

    domain: Mapped[str] = mapped_column(String(2048))
    port: Mapped[int] = mapped_column(default=443)
    health_check_path: Mapped[str] = mapped_column(String(2048), default="/")
    is_healthy: Mapped[bool | None] = mapped_column(
        Boolean(create_constraint=True), default=None
    )
    health_check_enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False
    )
    health_check_every: Mapped[int] = mapped_column(default=60)  # Seconds.
    notificatons_enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_checked_at: Mapped[datetime | None]

    node: Mapped[Node] = relationship(back_populates="softwares", lazy="raise")


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
DATABASE_URL = config.DATABASE_URL or (
    TEST_DATABASE_URL if config.APP_ENV == "test" else "sqlite+aiosqlite:///./data/monitor.db"
)


def create_database_engine(url: str) -> AsyncEngine:
    """Create an engine without connecting or creating database files."""
    database_engine = create_async_engine(url, pool_pre_ping=True)
    if database_engine.dialect.name == "sqlite":

        @event.listens_for(database_engine.sync_engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return database_engine


engine = create_database_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db(database_engine: AsyncEngine = engine) -> None:
    """Create missing tables and repair legacy SQLite text Boolean values."""
    url = database_engine.url
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
