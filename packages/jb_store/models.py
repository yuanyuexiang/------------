"""ORM 表定义。字段只增不删（与 TRM 同规则），变更走 Alembic 迁移。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uid() -> str:
    return uuid.uuid4().hex[:12]


class Base(DeclarativeBase):
    pass


class Project(Base):
    """一次投标项目 = 一个招标文件包。"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    filename: Mapped[str] = mapped_column(String(255))
    zip_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|parsing|parsed|failed|confirmed
    batch_name: Mapped[str] = mapped_column(String(255), default="")
    batch_no: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    trm: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)          # 解析结果（机器）
    trm_confirmed: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 人工确认版（确认页写入）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    """异步任务（解析/生成/审查）。Celery 与进程内执行共用同一张表记录进度。"""
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))                        # parse|qualify|...
    status: Mapped[str] = mapped_column(String(16), default="queued")    # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Profile(Base):
    """企业档案（CompanyProfile 整体 JSON；S2 后半拆为知识库多表）。"""
    __tablename__ = "profiles"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    credit_code: Mapped[str] = mapped_column(String(32), default="", index=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
