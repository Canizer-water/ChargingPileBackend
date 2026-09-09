"""async SQLAlchemy engine / session / Base + create_all 轻量补列。"""

from __future__ import annotations

import logging

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import types as sa_types
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def create_engine_from_url(url: str) -> AsyncEngine:
    return create_async_engine(url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None) -> AsyncEngine:
    """应用启动/测试 fixture 调用；重复调用幂等（重建）。"""
    global _engine, _session_factory
    _engine = create_engine_from_url(url or get_settings().database_url)
    _session_factory = create_session_factory(_engine)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


def _ddl_type(col) -> str:
    """把模型列映射成 SQLite ALTER 用 DDL（create_all 不会给旧表补列）。"""
    t = col.type
    if isinstance(t, sa_types.Boolean):
        return "INTEGER NOT NULL DEFAULT 0"
    if isinstance(t, sa_types.Integer):
        return "INTEGER NOT NULL DEFAULT 0"
    if isinstance(t, (sa_types.Float, sa_types.Numeric)):
        return "REAL NOT NULL DEFAULT 0.0"
    if isinstance(t, sa_types.String):
        return "VARCHAR NOT NULL DEFAULT ''"
    if isinstance(t, (sa_types.DateTime, sa_types.Date)):
        return "DATETIME"  # 时间列允许空，避免给已有行编造时间
    return "TEXT"


def sync_missing_columns(conn) -> None:
    """create_all 之后的轻量迁移：给已存在的表补缺失列（SQLite；幂等）。

    模型新增了列而旧库未建时，仅靠 create_all 不会自动加列，会导致查询报
    “no such column”。本函数遍历模型元数据，对缺列执行幂等 ALTER。
    """
    if conn.dialect.name != "sqlite":
        return
    insp = sa_inspect(conn)
    tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing or col.primary_key:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {_ddl_type(col)}'
            conn.exec_driver_sql(ddl)
            logger.info("db: added missing column %s.%s", table.name, col.name)
