"""企业知识库路由：主档整体存取 + 各类条目 CRUD + 扫描件附件 + 有效期预警。

薄 API：转换/校验/存取都在 jb_kb.repo / jb_kb.attachments / jb_kb.expiry。
路径约定：/api/profiles/{name}/{kind}，kind ∈ jb_kb.repo.KINDS（certificates/personnel/performances/
financials/products/test_reports/boilerplates）；attachments 与 expiry 为显式路由（先于通配注册）。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from jb_kb import attachments as att
from jb_kb import repo
from jb_kb.expiry import expiry_report
from jb_kb.models import CompanyProfile
from jb_store import Profile, session

router = APIRouter(prefix="/api", tags=["knowledge-base"])


def _kind(kind: str) -> str:
    if kind not in repo.KINDS:
        raise HTTPException(404, f"未知知识库类别：{kind}")
    return kind


def _require_company(s, name: str) -> None:
    if s.get(Profile, name) is None:
        raise HTTPException(404, "企业档案不存在")


# ---------- 主档（聚合） ----------

@router.get("/profiles")
def list_profiles():
    with session() as s:
        return [{"name": r.name, "credit_code": r.credit_code, "updated_at": r.updated_at.isoformat(),
                 "counts": repo.counts(s, r.name)} for r in repo.list_profiles(s)]


@router.get("/profiles/{name}")
def get_profile(name: str):
    with session() as s:
        cp = repo.load_profile(s, name)
        if cp is None:
            raise HTTPException(404, "企业档案不存在")
        return cp.model_dump()


@router.put("/profiles/{name}")
def upsert_profile(name: str, profile: dict):
    cp = CompanyProfile.model_validate(profile)
    with session() as s:
        repo.save_profile(s, name, cp)
    return {"ok": True}


@router.put("/profiles/{name}/main")
def update_main(name: str, fields: dict):
    """只更新主档标量字段（名称/法人/注册资本/联系方式…），子表不受影响；主档不存在则新建。"""
    with session() as s:
        return repo.save_main(s, name, fields).model_dump()


@router.delete("/profiles/{name}")
def delete_profile(name: str):
    with session() as s:
        if not repo.delete_profile(s, name):
            raise HTTPException(404, "企业档案不存在")
    return {"ok": True}


@router.get("/profiles/{name}/expiry")
def profile_expiry(name: str, days: int = 90, on: Optional[str] = None):
    """有效期看板：已过期 / days 内到期 / 未录入。on=YYYY-MM-DD 可按开标日推算。"""
    try:
        on_date = dt.date.fromisoformat(on) if on else None
    except ValueError:
        raise HTTPException(400, "on 须为 YYYY-MM-DD") from None
    with session() as s:
        cp = repo.load_profile(s, name)
        if cp is None:
            raise HTTPException(404, "企业档案不存在")
    items = expiry_report(cp, on_date=on_date, within_days=days)
    summary = {lv: sum(1 for i in items if i.level == lv) for lv in ("expired", "d30", "d60", "d90", "unknown")}
    return {"items": [i.model_dump() for i in items], "summary": summary}


# ---------- 附件 ----------

@router.post("/profiles/{name}/attachments", status_code=201)
async def upload_attachment(name: str, file: UploadFile, kind: str = "other"):
    content = await file.read()
    if not content:
        raise HTTPException(400, "空文件")
    with session() as s:
        _require_company(s, name)
        a = att.store(s, name, file.filename or "file", content, kind=kind, content_type=file.content_type or "")
        return a.model_dump()


@router.get("/profiles/{name}/attachments")
def list_attachments(name: str, kind: str = ""):
    with session() as s:
        _require_company(s, name)
        return [a.model_dump() for a in att.list_attachments(s, name, kind)]


@router.delete("/profiles/{name}/attachments/{attachment_id}")
def delete_attachment(name: str, attachment_id: str):
    with session() as s:
        if not att.delete_attachment(s, name, attachment_id):
            raise HTTPException(404, "附件不存在")
    return {"ok": True}


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: str):
    with session() as s:
        a = att.get_attachment(s, attachment_id)
    if a is None:
        raise HTTPException(404, "附件不存在")
    return FileResponse(att.absolute_path(a), filename=a.filename,
                        media_type=a.content_type or "application/octet-stream")


# ---------- 条目 CRUD ----------

@router.get("/profiles/{name}/{kind}")
def list_items(name: str, kind: str):
    kind = _kind(kind)
    with session() as s:
        _require_company(s, name)
        return [i.model_dump() for i in repo.list_items(s, name, kind)]


@router.post("/profiles/{name}/{kind}", status_code=201)
def create_item(name: str, kind: str, item: dict):
    kind = _kind(kind)
    item.pop("id", None)
    with session() as s:
        _require_company(s, name)
        return repo.upsert_item(s, name, kind, item).model_dump()


@router.put("/profiles/{name}/{kind}/{item_id}")
def update_item(name: str, kind: str, item_id: str, item: dict):
    kind = _kind(kind)
    item["id"] = item_id
    with session() as s:
        _require_company(s, name)
        if repo.get_item(s, kind, item_id) is None:
            raise HTTPException(404, "条目不存在")
        try:
            return repo.upsert_item(s, name, kind, item).model_dump()
        except ValueError as e:
            raise HTTPException(409, str(e)) from None


@router.delete("/profiles/{name}/{kind}/{item_id}")
def delete_item(name: str, kind: str, item_id: str):
    kind = _kind(kind)
    with session() as s:
        if not repo.delete_item(s, name, kind, item_id):
            raise HTTPException(404, "条目不存在")
    return {"ok": True}
