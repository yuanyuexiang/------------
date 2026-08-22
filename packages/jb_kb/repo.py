"""知识库仓储：CompanyProfile（聚合）⇄ 多表行 的双向转换，以及单条目 CRUD。

- 读：`load_profile()` 把主档 + 各子表拼回 CompanyProfile，下游 Agent 接口不变。
- 写：`save_profile()` 整体覆盖（确认页/建档导入用）；`upsert_item()`/`delete_item()` 单条维护（管理页用）。
- 兼容：旧库 `profiles.data` 内仍带列表（拆表前整体 JSON）的行，读取时若子表为空则回退到 JSON 列表；
  下次整体保存时迁出到子表并从 `data` 中去掉列表。
"""
from __future__ import annotations

from typing import Any, Optional

from jb_store import (
    KbBoilerplate,
    KbCertificate,
    KbFinancial,
    KbPerformance,
    KbPerson,
    KbProduct,
    KbTestReport,
    Profile,
)
from jb_store.models import _uid
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Boilerplate,
    Certificate,
    CompanyProfile,
    FinancialYear,
    Performance,
    Person,
    Product,
    TestReport,
)


class Kind:
    """一类知识库条目：profile 上的列表字段名 ↔ ORM 表 ↔ Pydantic 模型 ↔ 冗余列。"""

    def __init__(self, attr: str, orm: type, model: type[BaseModel], columns: tuple[str, ...]):
        self.attr, self.orm, self.model, self.columns = attr, orm, model, columns

    def to_row_values(self, item: BaseModel) -> dict:
        d = item.model_dump()
        vals = {c: d.get(c) for c in self.columns}
        # 冗余列为 None 时退回列默认（字符串列用空串），避免 NOT NULL 失败
        for c, v in list(vals.items()):
            if v is None and c not in ("buyer_is_end_user", "amount_wan"):
                vals[c] = ""
        if "approved" in d:      # 话术库用 approved 布尔，映射到统一的 status 列
            vals["status"] = "approved" if d["approved"] else "draft"
        else:
            vals["status"] = d.get("status") or "approved"
        vals["data"] = d
        return vals


KINDS: dict[str, Kind] = {
    "certificates": Kind("certificates", KbCertificate, Certificate,
                         ("name", "number", "cert_type", "valid_until")),
    "personnel": Kind("personnel", KbPerson, Person, ("name", "title")),
    "performances": Kind("performances", KbPerformance, Performance,
                         ("project", "buyer", "buyer_is_end_user", "amount_wan", "signed_date")),
    "financials": Kind("financials", KbFinancial, FinancialYear, ("year",)),
    "products": Kind("products", KbProduct, Product, ("model", "name", "category")),
    "test_reports": Kind("test_reports", KbTestReport, TestReport,
                         ("name", "report_type", "valid_until")),
    "boilerplates": Kind("boilerplates", KbBoilerplate, Boilerplate, ("topic", "title", "approved")),
}

LIST_FIELDS = tuple(KINDS)


def _main_data(profile: CompanyProfile) -> dict:
    """主档标量部分（去掉各列表字段）。"""
    d = profile.model_dump()
    for k in LIST_FIELDS:
        d.pop(k, None)
    return d


def _row_to_item(kind: Kind, row) -> BaseModel:
    data = dict(row.data or {})
    data["id"] = row.id
    data["status"] = row.status
    return kind.model.model_validate(data)


# ---------- 聚合读写 ----------

def list_profiles(s: Session) -> list[Profile]:
    return list(s.execute(select(Profile).order_by(Profile.name)).scalars().all())


def load_profile(s: Session, name: str) -> Optional[CompanyProfile]:
    row = s.get(Profile, name)
    if row is None:
        return None
    data = dict(row.data or {})
    legacy = {k: data.pop(k, None) for k in LIST_FIELDS}
    profile = CompanyProfile.model_validate(data)
    for key, kind in KINDS.items():
        rows = s.execute(select(kind.orm).where(kind.orm.company == name)
                         .order_by(kind.orm.created_at, kind.orm.id)).scalars().all()
        if rows:
            setattr(profile, key, [_row_to_item(kind, r) for r in rows])
        elif legacy.get(key):
            setattr(profile, key, [kind.model.model_validate(x) for x in legacy[key]])
    return profile


def save_profile(s: Session, name: str, profile: CompanyProfile) -> None:
    """整体覆盖：主档写 profiles.data（仅标量），各列表全量替换到子表（保留已有 id）。"""
    row = s.get(Profile, name)
    if row is None:
        row = Profile(name=name, credit_code=profile.credit_code, data=_main_data(profile))
        s.add(row)
    else:
        row.credit_code, row.data = profile.credit_code, _main_data(profile)
    s.flush()
    for key, kind in KINDS.items():
        existing = {r.id: r for r in s.execute(select(kind.orm).where(kind.orm.company == name)).scalars()}
        keep: set[str] = set()
        for item in getattr(profile, key):
            rid = item.id or _uid()
            item.id = rid
            vals = kind.to_row_values(item)
            if rid in existing:
                for c, v in vals.items():
                    setattr(existing[rid], c, v)
            else:
                s.add(kind.orm(id=rid, company=name, **vals))
            keep.add(rid)
        for rid, r in existing.items():
            if rid not in keep:
                s.delete(r)


def delete_profile(s: Session, name: str) -> bool:
    row = s.get(Profile, name)
    if row is None:
        return False
    for kind in KINDS.values():
        for r in s.execute(select(kind.orm).where(kind.orm.company == name)).scalars():
            s.delete(r)
    s.delete(row)
    s.flush()
    return True


# ---------- 单条 CRUD（管理页） ----------

def list_items(s: Session, name: str, key: str) -> list[BaseModel]:
    kind = KINDS[key]
    rows = s.execute(select(kind.orm).where(kind.orm.company == name)
                     .order_by(kind.orm.created_at, kind.orm.id)).scalars().all()
    return [_row_to_item(kind, r) for r in rows]


def get_item(s: Session, key: str, item_id: str) -> Optional[BaseModel]:
    kind = KINDS[key]
    r = s.get(kind.orm, item_id)
    return _row_to_item(kind, r) if r is not None else None


def upsert_item(s: Session, name: str, key: str, payload: dict[str, Any]) -> BaseModel:
    """新增（无 id）或更新（有 id）。主档不存在时 404 由调用方判断。"""
    kind = KINDS[key]
    item = kind.model.model_validate(payload)
    r = s.get(kind.orm, item.id) if item.id else None
    if r is not None and r.company != name:
        raise ValueError("条目不属于该企业")
    if r is None:
        item.id = item.id or _uid()
        s.add(kind.orm(id=item.id, company=name, **kind.to_row_values(item)))
    else:
        for c, v in kind.to_row_values(item).items():
            setattr(r, c, v)
    return item


def delete_item(s: Session, name: str, key: str, item_id: str) -> bool:
    kind = KINDS[key]
    r = s.get(kind.orm, item_id)
    if r is None or r.company != name:
        return False
    s.delete(r)
    s.flush()
    return True


def counts(s: Session, name: str) -> dict[str, int]:
    """各类条目数量（列表页概览用）。"""
    return {key: int(s.execute(select(func.count()).select_from(kind.orm).where(kind.orm.company == name)).scalar() or 0)
            for key, kind in KINDS.items()}
