"""配置中心路由：评分模板库 / 否决规则库 / LLM 设置与用量。

薄 API：存取在 jb_store.config，规则目录在 jb_rules.catalog()，LLM 运行时配置在 jb_llm.configure()。
LLM 密钥只从环境变量读，本路由只返回"是否已配置"，不接收、不落库。
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

import jb_llm
from fastapi import APIRouter, HTTPException, Request, UploadFile
from jb_parser import scoring as scoring_parser
from jb_parser.trm import ScoringItem, ScoringTemplate
from jb_rules import LEVELS, RULE_PARAMS, RuleSetting, catalog
from jb_store import ScoringTemplateRow, Setting, session
from jb_store import auth as au
from jb_store import config as cfg

from .auth import require_admin

router = APIRouter(prefix="/api/config", tags=["config"])

LLM_SETTING_KEY = "llm"
LLM_FIELDS = ("base_url", "model", "temperature", "timeout")


# ---------- LLM 运行时配置加载 / 用量记账（main 与 tasks 启动时都调用） ----------

def load_llm_settings() -> dict:
    """从 settings 表读 LLM 覆盖项并应用到 jb_llm；返回当前生效配置。"""
    with session() as s:
        saved = cfg.get_setting(s, LLM_SETTING_KEY)
    jb_llm.configure(**{k: saved.get(k) for k in LLM_FIELDS})
    return jb_llm.settings()


def _record_usage(rec: dict) -> None:
    with session() as s:
        cfg.record_usage(s, rec)


def install_usage_hook() -> None:
    jb_llm.set_usage_hook(_record_usage)


def rule_settings_models() -> dict[str, RuleSetting]:
    """供审查调用：rule_settings 表 → jb_rules.RuleSetting。"""
    with session() as s:
        return {k: RuleSetting(rule_id=k, enabled=v["enabled"], level_override=v["level_override"],
                               params=v["params"], note=v["note"]) for k, v in cfg.rule_settings(s).items()}


# ---------- 评分模板库 ----------

def _tpl_out(r: ScoringTemplateRow, with_items: bool = True) -> dict:
    out = {"id": r.id, "name": r.name, "kind": r.kind, "source": r.source, "origin": r.origin, "note": r.note,
           "item_count": len(r.items or []), "updated_at": r.updated_at.isoformat(), "updated_by": r.updated_by}
    if with_items:
        out["items"] = r.items or []
    return out


@router.get("/scoring-templates")
def list_scoring_templates():
    with session() as s:
        return [_tpl_out(r, with_items=False) for r in cfg.list_templates(s)]


@router.get("/scoring-templates/{template_id}")
def get_scoring_template(template_id: str):
    with session() as s:
        r = s.get(ScoringTemplateRow, template_id)
        if r is None:
            raise HTTPException(404, "模板不存在")
        return _tpl_out(r)


def _validate_items(items: list) -> list[dict]:
    return [ScoringItem.model_validate(i).model_dump() for i in items or []]


@router.post("/scoring-templates", status_code=201)
def create_scoring_template(request: Request, body: dict):
    require_admin(request)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "模板名称必填")
    with session() as s:
        if cfg.get_template_by_name(s, name) is not None:
            raise HTTPException(409, "同名模板已存在")
        tpl = ScoringTemplate(name=name, kind=body.get("kind") or "other", source=body.get("source") or "手工录入",
                              items=[ScoringItem.model_validate(i) for i in body.get("items") or []])
        r = cfg.upsert_template(s, tpl, origin="manual", note=body.get("note") or "")
        r.updated_by = au.current_actor()
        return _tpl_out(r)


@router.put("/scoring-templates/{template_id}")
def update_scoring_template(request: Request, template_id: str, body: dict):
    require_admin(request)
    with session() as s:
        r = s.get(ScoringTemplateRow, template_id)
        if r is None:
            raise HTTPException(404, "模板不存在")
        name = (body.get("name") or r.name).strip()
        other = cfg.get_template_by_name(s, name)
        if other is not None and other.id != r.id:
            raise HTTPException(409, "同名模板已存在")
        r.name, r.kind = name, body.get("kind") or r.kind
        if "items" in body:
            r.items = _validate_items(body["items"])
        if "note" in body:
            r.note = body["note"] or ""
        r.origin, r.updated_by = "manual", au.current_actor()
        s.flush()
        return _tpl_out(r)


@router.delete("/scoring-templates/{template_id}")
def delete_scoring_template(request: Request, template_id: str):
    require_admin(request)
    with session() as s:
        r = s.get(ScoringTemplateRow, template_id)
        if r is None:
            raise HTTPException(404, "模板不存在")
        s.delete(r)
    return {"ok": True}


@router.post("/scoring-templates/upload", status_code=201)
async def upload_scoring_template(request: Request, file: UploadFile, kind: str = "", overwrite: bool = False):
    """上传评分细则 xlsx（国网模板库格式：首行模板名、次行表头），解析后入库。"""
    require_admin(request)
    fn = file.filename or "template.xlsx"
    if not fn.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "请上传评分细则 xlsx")
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        tpl = scoring_parser.parse_xlsx(path, fn)
    finally:
        os.unlink(path)
    if tpl is None or not tpl.items:
        raise HTTPException(400, "未能从文件中解析出评审要素，请检查格式（首行模板名，次行表头：评审要素|评审内容）")
    if kind:
        tpl.kind = kind
    with session() as s:
        exists = cfg.get_template_by_name(s, tpl.name) is not None
        if exists and not overwrite:
            raise HTTPException(409, f"同名模板已存在：{tpl.name}（可勾选覆盖）")
        r = cfg.upsert_template(s, tpl, origin="upload", overwrite=True)
        r.updated_by = au.current_actor()
        return _tpl_out(r)


# ---------- 否决规则库 ----------

@router.get("/rules")
def list_rules():
    """规则目录 + 当前设置合并：每条 {rule_id, level, title, source, doc, default_params, enabled, level_override, params, note}。"""
    with session() as s:
        saved = cfg.rule_settings(s)
    out = []
    for c in catalog():
        st = saved.get(c["rule_id"], {})
        out.append({**c, "default_params": c.pop("params"),
                    "enabled": st.get("enabled", True), "level_override": st.get("level_override", ""),
                    "params": st.get("params", {}), "note": st.get("note", ""), "updated_at": st.get("updated_at"),
                    "updated_by": st.get("updated_by", "")})
    return {"levels": list(LEVELS), "rules": out}


@router.put("/rules/{rule_id}")
def update_rule(request: Request, rule_id: str, body: dict):
    require_admin(request)
    if rule_id not in {c["rule_id"] for c in catalog()}:
        raise HTTPException(404, "规则不存在")
    level = body.get("level_override") or ""
    if level and level not in LEVELS:
        raise HTTPException(400, f"级别须为 {'/'.join(LEVELS)} 或空")
    params = body.get("params") or {}
    allowed = RULE_PARAMS.get(rule_id, {})
    unknown = set(params) - set(allowed)
    if unknown:
        raise HTTPException(400, f"该规则不支持参数：{', '.join(sorted(unknown))}")
    with session() as s:
        row = cfg.save_rule_setting(s, rule_id, enabled=bool(body.get("enabled", True)), level_override=level,
                                    params=params, note=body.get("note") or "")
        row.updated_by = au.current_actor()
    return {"ok": True}


@router.delete("/rules/{rule_id}")
def reset_rule(request: Request, rule_id: str):
    """恢复默认（删除设置行）。"""
    require_admin(request)
    from jb_store import RuleSettingRow
    with session() as s:
        r = s.get(RuleSettingRow, rule_id)
        if r is not None:
            s.delete(r)
    return {"ok": True}


# ---------- LLM 设置 / 用量 ----------

@router.get("/llm")
def get_llm(days: int = 30):
    with session() as s:
        saved = cfg.get_setting(s, LLM_SETTING_KEY)
        usage = cfg.usage_summary(s, days)
    cur = jb_llm.settings()
    return {"effective": {k: cur[k] for k in ("base_url", "model", "temperature", "timeout", "key_configured")},
            "saved": {k: saved.get(k) for k in LLM_FIELDS},
            "env": {"base_url": os.environ.get("LLM_BASE_URL", ""), "model": os.environ.get("LLM_MODEL", "")},
            "available": jb_llm.available(), "usage": usage}


@router.put("/llm")
def put_llm(request: Request, body: dict):
    """保存端点/模型/温度/超时覆盖（空值=清除，回到环境变量）；密钥不接收。"""
    require_admin(request)
    if "api_key" in body or "key" in body:
        raise HTTPException(400, "密钥只能通过环境变量 LLM_API_KEY（.env）配置，不接收、不入库")
    val: dict = {}
    for k in LLM_FIELDS:
        v = body.get(k)
        if v in (None, ""):
            continue
        if k in ("temperature", "timeout"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} 须为数字") from None
            if k == "temperature" and not 0 <= v <= 2:
                raise HTTPException(400, "temperature 取值 0~2")
            if k == "timeout" and not 5 <= v <= 600:
                raise HTTPException(400, "timeout 取值 5~600 秒")
        val[k] = v
    with session() as s:
        cfg.set_setting(s, LLM_SETTING_KEY, val)
        s.get(Setting, LLM_SETTING_KEY).updated_by = au.current_actor()
    jb_llm.configure(**{k: val.get(k) for k in LLM_FIELDS})
    return {"saved": val, "effective": jb_llm.settings()}


@router.post("/llm/test")
def test_llm(request: Request, base_url: Optional[str] = None, model: Optional[str] = None):
    """测试连接：可临时指定端点/模型（不保存）。"""
    require_admin(request)
    if base_url or model:
        backup = dict(jb_llm.settings()["overrides"])
        jb_llm.configure(base_url=base_url, model=model)
        try:
            return jb_llm.test_connection()
        finally:
            jb_llm.configure(base_url=None, model=None)
            jb_llm.configure(**backup)
    return jb_llm.test_connection()
