"""投标项目管理：阶段推进、事件时间线、截止日计算。只做落盘与派生，不含业务判断。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, ProjectEvent

# 到达的最远阶段（单向前进；回退只会发生在重新解析）
STAGES = ["parsed", "confirmed", "qualified", "generated", "reviewed", "submitted"]
STAGE_CN = {"": "待解析", "parsed": "已解析", "confirmed": "已确认", "qualified": "已自检",
            "generated": "已生成", "reviewed": "已审查", "submitted": "已递交"}
OUTCOMES = ("", "submitted", "won", "lost", "abandoned")
OUTCOME_CN = {"": "在投", "submitted": "已递交", "won": "中标", "lost": "未中标", "abandoned": "放弃"}


def advance(p: Project, stage: str) -> bool:
    """把项目推进到 stage（仅当比当前更远）。返回是否发生推进。"""
    cur = STAGES.index(p.stage) if p.stage in STAGES else -1
    new = STAGES.index(stage)
    if new > cur:
        p.stage = stage
        return True
    return False


def log_event(s: Session, project_id: str, kind: str, message: str = "",
              data: Optional[dict[str, Any]] = None) -> ProjectEvent:
    ev = ProjectEvent(project_id=project_id, kind=kind, message=message, data=data)
    s.add(ev)
    return ev


def events(s: Session, project_id: str) -> list[ProjectEvent]:
    return list(s.execute(select(ProjectEvent).where(ProjectEvent.project_id == project_id)
                          .order_by(ProjectEvent.created_at.desc(), ProjectEvent.id.desc())).scalars())


def set_result(p: Project, key: str, value: Any, pkg_no: str = "") -> None:
    """results[key] 或 results[key][pkg_no] = value（按包的结果以包号分桶）。"""
    res = dict(p.results or {})
    if pkg_no:
        bucket = dict(res.get(key) or {})
        bucket[pkg_no] = value
        res[key] = bucket
    else:
        res[key] = value
    p.results = res


def parse_deadline(text: str) -> Optional[dt.datetime]:
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def days_left(deadline: str, now: Optional[dt.datetime] = None) -> Optional[float]:
    """距截止的天数（可为负=已过）；未录入返回 None。"""
    d = parse_deadline(deadline)
    if d is None:
        return None
    delta = d - (now or dt.datetime.now())
    return round(delta.total_seconds() / 86400, 1)


def is_active(p: Project) -> bool:
    return p.outcome in ("", "submitted")


def sort_key(p: Project, now: Optional[dt.datetime] = None):
    """列表排序：在投未过期按截止日升序 → 在投已过期（近的在前）→ 在投无截止日 → 已结束（更新时间倒序）。"""
    now = now or dt.datetime.now()
    active = is_active(p)
    d = parse_deadline(p.deadline) if active else None
    if not active:
        group, key = 3, 0.0
    elif d is None:
        group, key = 2, 0.0
    elif d >= now:
        group, key = 0, d.timestamp()
    else:
        group, key = 1, -d.timestamp()
    return (group, key, -(p.updated_at.timestamp() if p.updated_at else 0))
