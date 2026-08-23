"""配置中心存取：评分模板库、否决规则设置、通用设置、LLM 用量。只做落盘/汇总，不含业务判断。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from jb_parser.trm import ScoringTemplate
from sqlalchemy import Integer, String, func, select
from sqlalchemy.orm import Session

from .models import LlmUsage, RuleSettingRow, ScoringTemplateRow, Setting

# ---------- 评分模板库 ----------

def template_to_model(row: ScoringTemplateRow) -> ScoringTemplate:
    return ScoringTemplate(name=row.name, kind=row.kind, source=row.source, items=row.items or [])


def list_templates(s: Session) -> list[ScoringTemplateRow]:
    return list(s.execute(select(ScoringTemplateRow).order_by(ScoringTemplateRow.kind, ScoringTemplateRow.name)).scalars())


def library(s: Session) -> list[ScoringTemplate]:
    """供评分器兜底的模板列表（只含有细则条目的）。"""
    return [template_to_model(r) for r in list_templates(s) if r.items]


def get_template_by_name(s: Session, name: str) -> Optional[ScoringTemplateRow]:
    return s.execute(select(ScoringTemplateRow).where(ScoringTemplateRow.name == name)).scalars().first()


def upsert_template(s: Session, tpl: ScoringTemplate, origin: str, overwrite: bool = True,
                    note: str = "") -> ScoringTemplateRow:
    """按名称 upsert。overwrite=False 时已存在则不动（解析自动入库不覆盖人工维护过的模板）。"""
    row = get_template_by_name(s, tpl.name)
    items = [i.model_dump() for i in tpl.items]
    if row is None:
        row = ScoringTemplateRow(name=tpl.name, kind=tpl.kind, source=tpl.source, origin=origin, items=items, note=note)
        s.add(row)
        s.flush()
    elif overwrite or (not row.items and items):
        row.kind, row.source, row.origin, row.items = tpl.kind, tpl.source, origin, items
        if note:
            row.note = note
    return row


def import_parsed_templates(s: Session, templates: list[ScoringTemplate], source_hint: str = "") -> int:
    """解析完成后把带细则的模板入库（不覆盖已有）。返回新增数。"""
    n = 0
    for t in templates:
        if not t.items:
            continue
        if get_template_by_name(s, t.name) is None:
            upsert_template(s, ScoringTemplate(name=t.name, kind=t.kind, source=source_hint or t.source, items=t.items),
                            origin="parsed", overwrite=False)
            n += 1
    return n


# ---------- 否决规则设置 ----------

def rule_settings(s: Session) -> dict[str, dict]:
    """rule_id → {enabled, level_override, params, note}（调用方转成 jb_rules.RuleSetting）。"""
    return {r.rule_id: {"rule_id": r.rule_id, "enabled": r.enabled, "level_override": r.level_override,
                        "params": r.params or {}, "note": r.note, "updated_at": r.updated_at.isoformat()}
            for r in s.execute(select(RuleSettingRow)).scalars()}


def save_rule_setting(s: Session, rule_id: str, enabled: bool = True, level_override: str = "",
                      params: Optional[dict] = None, note: str = "") -> RuleSettingRow:
    row = s.get(RuleSettingRow, rule_id)
    if row is None:
        row = RuleSettingRow(rule_id=rule_id)
        s.add(row)
    row.enabled, row.level_override, row.params, row.note = enabled, level_override, params or None, note
    s.flush()
    return row


# ---------- 通用设置 ----------

def get_setting(s: Session, key: str, default: Optional[dict] = None) -> dict:
    row = s.get(Setting, key)
    return dict(row.value or {}) if row is not None else dict(default or {})


def set_setting(s: Session, key: str, value: dict) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


# ---------- LLM 用量 ----------

def record_usage(s: Session, rec: dict[str, Any]) -> None:
    s.add(LlmUsage(model=rec.get("model") or "", purpose=rec.get("purpose") or "", ok=bool(rec.get("ok")),
                   latency_ms=int(rec.get("latency_ms") or 0), prompt_tokens=rec.get("prompt_tokens"),
                   completion_tokens=rec.get("completion_tokens"), error=rec.get("error") or ""))


def usage_summary(s: Session, days: int = 30) -> dict:
    """近 days 天：总调用/失败/tokens，按用途与按天分组。"""
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    base = select(func.count(), func.sum(func.cast(LlmUsage.ok, Integer)),
                  func.coalesce(func.sum(LlmUsage.prompt_tokens), 0), func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
                  func.coalesce(func.avg(LlmUsage.latency_ms), 0)).where(LlmUsage.created_at >= since)
    total, ok, pt, ct, lat = s.execute(base).one()
    by_purpose = [{"purpose": p or "（未标）", "calls": c, "prompt_tokens": int(a or 0), "completion_tokens": int(b or 0)}
                  for p, c, a, b in s.execute(
                      select(LlmUsage.purpose, func.count(), func.sum(LlmUsage.prompt_tokens), func.sum(LlmUsage.completion_tokens))
                      .where(LlmUsage.created_at >= since).group_by(LlmUsage.purpose).order_by(func.count().desc()))]
    day = func.substr(func.cast(LlmUsage.created_at, String), 1, 10)
    by_day = [{"day": d, "calls": c, "tokens": int((a or 0) + (b or 0))}
              for d, c, a, b in s.execute(
                  select(day, func.count(), func.sum(LlmUsage.prompt_tokens), func.sum(LlmUsage.completion_tokens))
                  .where(LlmUsage.created_at >= since).group_by(day).order_by(day))]
    recent = [{"created_at": r.created_at.isoformat(), "model": r.model, "purpose": r.purpose, "ok": r.ok,
               "latency_ms": r.latency_ms, "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
               "error": r.error[:120]}
              for r in s.execute(select(LlmUsage).order_by(LlmUsage.created_at.desc()).limit(20)).scalars()]
    return {"days": days, "calls": int(total or 0), "failed": int((total or 0) - (ok or 0)),
            "prompt_tokens": int(pt or 0), "completion_tokens": int(ct or 0), "avg_latency_ms": int(lat or 0),
            "by_purpose": by_purpose, "by_day": by_day, "recent": recent}
