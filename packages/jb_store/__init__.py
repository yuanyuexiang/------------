"""jb-store：持久层（SQLAlchemy 2.0）。

- DATABASE_URL 未设置时用仓库根 `jinbang.db`（SQLite），compose 下为 PostgreSQL（pgvector 镜像）。
- 表结构演进用 Alembic（`alembic upgrade head`）；开发/测试可用 `init_db()` 直接建表。
- 领域对象（TRM / CompanyProfile / FeasibilityReport）以 JSON 列整体存取：Pydantic 是真源，
  数据库只做落盘与检索；需要按字段查询的列（batch_name、status 等）单独冗余。
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Profile, Project, Task  # noqa: F401

DEFAULT_SQLITE = "sqlite:///" + os.path.join(os.getcwd(), "jinbang.db")


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_SQLITE)


def make_engine(url: str = ""):
    url = url or database_url()
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, **kwargs)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = make_engine()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    """测试用：切换 DATABASE_URL 后重建引擎。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session() -> Iterator[Session]:
    get_engine()
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
