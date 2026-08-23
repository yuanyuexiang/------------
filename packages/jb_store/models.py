"""ORM 表定义。字段只增不删（与 TRM 同规则），变更走 Alembic 迁移。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    # ---- 项目管理（P2）----
    deadline: Mapped[str] = mapped_column(String(16), default="", index=True)   # 投标截止 "YYYY-MM-DD HH:MM"；解析自公告，可人工改
    open_time: Mapped[str] = mapped_column(String(16), default="")
    deadline_manual: Mapped[bool] = mapped_column(Boolean, default=False)     # 人工改过后解析不再覆盖
    stage: Mapped[str] = mapped_column(String(16), default="", index=True)    # 到达的最远阶段，见 jb_store.projects.STAGES
    outcome: Mapped[str] = mapped_column(String(16), default="")              # "" | submitted | won | lost | abandoned
    notes: Mapped[str] = mapped_column(Text, default="")
    results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)      # 各环节最近结果摘要 {qualify|generate|review|score: {...}}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectEvent(Base):
    """项目时间线：解析完成/确认/自检/生成/审查/评分/导出/递交/结果…（谁做的留待用户权限后补 actor 列）。"""
    __tablename__ = "project_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


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
    """企业主档。

    P2 拆表后 `data` 只存主档标量字段（名称/法人/注册资本/联系方式…），
    证照/人员/业绩等列表各自成表（下方 Kb* 表，按 company 关联）。
    旧库 `data` 内仍带列表的行由 jb_kb.repo 在读取时兼容、写入时迁出。
    """
    __tablename__ = "profiles"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    credit_code: Mapped[str] = mapped_column(String(32), default="", index=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------- 企业知识库（总方案 4.2，分期落表；本期：证照/人员/业绩/财务/产品/检测报告/话术/附件） ----------
# 约定：每行 `data` 存该条目的完整 Pydantic JSON（真源），需要检索/排序/预警的列单独冗余。
# 新增 Pydantic 字段不需要迁移；只有新增"需检索"的列才加迁移。

class _KbRow:
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    company: Mapped[str] = mapped_column(ForeignKey("profiles.name", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="approved")   # draft|approved
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbCertificate(_KbRow, Base):
    __tablename__ = "kb_certificates"
    name: Mapped[str] = mapped_column(String(255), default="")
    number: Mapped[str] = mapped_column(String(128), default="")
    cert_type: Mapped[str] = mapped_column(String(64), default="")
    valid_until: Mapped[str] = mapped_column(String(10), default="", index=True)   # YYYY-MM-DD，空=未录入


class KbPerson(_KbRow, Base):
    __tablename__ = "kb_personnel"
    name: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(128), default="")


class KbPerformance(_KbRow, Base):
    __tablename__ = "kb_performances"
    project: Mapped[str] = mapped_column(String(255), default="")
    buyer: Mapped[str] = mapped_column(String(255), default="")
    buyer_is_end_user: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    amount_wan: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    signed_date: Mapped[str] = mapped_column(String(10), default="", index=True)


class KbFinancial(_KbRow, Base):
    __tablename__ = "kb_financials"
    year: Mapped[str] = mapped_column(String(8), default="", index=True)


class KbProduct(_KbRow, Base):
    __tablename__ = "kb_products"
    model: Mapped[str] = mapped_column(String(128), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(128), default="")


class KbTestReport(_KbRow, Base):
    __tablename__ = "kb_test_reports"
    name: Mapped[str] = mapped_column(String(255), default="")
    report_type: Mapped[str] = mapped_column(String(64), default="")
    valid_until: Mapped[str] = mapped_column(String(10), default="", index=True)


class KbBoilerplate(_KbRow, Base):
    __tablename__ = "kb_boilerplates"
    topic: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class KbAttachment(Base):
    """扫描件元数据；文件本体在 UPLOAD_DIR/attachments/<company>/<id>_<filename>（后续可切 MinIO）。"""
    __tablename__ = "kb_attachments"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    company: Mapped[str] = mapped_column(ForeignKey("profiles.name", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="other")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------- 配置中心（P1）：评分模板库 / 否决规则设置 / 通用设置 / LLM 用量 ----------

class ScoringTemplateRow(Base):
    """评分模板库：按名称被各包的评审办法前附表引用。items 存 ScoringItem 列表 JSON。
    origin：parsed（解析招标文件时自动入库）| upload（上传 xlsx）| manual（页面编辑）。"""
    __tablename__ = "scoring_templates"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other", index=True)   # tech | biz | price | other
    source: Mapped[str] = mapped_column(Text, default="")                         # 来源文件/批次
    origin: Mapped[str] = mapped_column(String(16), default="parsed")
    items: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RuleSettingRow(Base):
    """否决规则运行设置：启停 / 级别覆盖 / 参数；规则本体在 jb_rules.RULES（代码），这里只存配置。"""
    __tablename__ = "rule_settings"

    rule_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    level_override: Mapped[str] = mapped_column(String(8), default="")
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Setting(Base):
    """通用键值设置（如 llm：{base_url, model, temperature, timeout}）。密钥永远不放这里。"""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LlmUsage(Base):
    """LLM 调用记账（每次调用一行；用量看板按天/按用途汇总）。"""
    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    model: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="", index=True)   # parse|qualify|draft|score|test
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
