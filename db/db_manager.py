"""Small async CRUD helper with one session and transaction per operation."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from loguru import logger
from sqlalchemy import and_, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from db.models import Base, async_session

Model = TypeVar("Model", bound=Base)
Filters = dict[str, Any]


class DB_Manager:
    """Missing records return None/False; database failures are logged and re-raised.

    Transaction contexts roll writes back on failure. Returned objects are detached,
    so request relationships explicitly with load_relationships.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker

    @asynccontextmanager
    async def _session(self, operation: str, model: type[Model]) -> AsyncIterator[AsyncSession]:
        try:
            async with self.session_maker.begin() as session:
                yield session
            logger.debug("DB {} succeeded for {}", operation, model.__name__)
        except SQLAlchemyError:
            logger.exception("DB {} failed for {}", operation, model.__name__)
            raise

    @staticmethod
    def _column(model: type[Model], name: str) -> InstrumentedAttribute:
        if name not in inspect(model).column_attrs:
            raise ValueError(f"Unknown column {model.__name__}.{name}")
        return getattr(model, name)

    def _condition(self, model: type[Model], name: str, value: Any):
        column = self._column(model, name)
        if isinstance(value, (list, tuple, set)):
            return column.in_(value)
        return column == value

    async def get_entity(
        self,
        model: type[Model],
        identifier: Any,
        load_relationships: Sequence[InstrumentedAttribute] | None = None,
        field: str = "id",
    ) -> Model | None:
        query = select(model).where(self._column(model, field) == identifier)
        for relationship in load_relationships or ():
            query = query.options(selectinload(relationship))
        async with self._session("get", model) as session:
            return (await session.scalars(query)).one_or_none()

    async def get_entities(
        self,
        model: type[Model],
        where: Filters | None = None,
        load_relationships: Sequence[InstrumentedAttribute] | None = None,
        exclude: Filters | Sequence[Filters] | None = None,
        sort: str | Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[Model]:
        """Equality/IN filters; each exclude group is negated; '-id' sorts descending."""
        query = select(model)
        for name, value in (where or {}).items():
            query = query.where(self._condition(model, name, value))
        groups = [exclude] if isinstance(exclude, dict) else (exclude or ())
        for group in groups:
            if group:
                query = query.where(~and_(*(
                    self._condition(model, name, value) for name, value in group.items()
                )))
        columns = [sort] if isinstance(sort, str) else (sort or ())
        for name in columns:
            column = self._column(model, name.lstrip("-"))
            query = query.order_by(column.desc() if name.startswith("-") else column.asc())
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be zero or greater")
            query = query.limit(limit)
        for relationship in load_relationships or ():
            query = query.options(selectinload(relationship))
        async with self._session("list", model) as session:
            return list((await session.scalars(query)).all())

    async def create_entity(
        self, model: type[Model], entity_id: Any = None, **values: Any
    ) -> Model:
        if entity_id is not None:
            values["id"] = entity_id
        for name in values:
            self._column(model, name)
        async with self._session("create", model) as session:
            entity = model(**values)
            session.add(entity)
            await session.flush()
            await session.refresh(entity)
            return entity

    async def update_entity(
        self, model: type[Model], identifier: Any, field: str = "id", **values: Any
    ) -> bool:
        query = select(model).where(self._column(model, field) == identifier)
        for name in values:
            self._column(model, name)
        async with self._session("update", model) as session:
            entity = (await session.scalars(query)).one_or_none()
            if entity is None:
                return False
            for name, value in values.items():
                setattr(entity, name, value)
            return True

    async def delete_entity(
        self, model: type[Model], identifier: Any, field: str = "id"
    ) -> bool:
        query = select(model).where(self._column(model, field) == identifier)
        async with self._session("delete", model) as session:
            entity = (await session.scalars(query)).one_or_none()
            if entity is None:
                return False
            await session.delete(entity)
            return True


db_manager = DB_Manager(async_session)
