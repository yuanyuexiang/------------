"""jb-api：Jinbang 后端 HTTP 层。

薄 API 原则：业务逻辑全部在 packages/，本层只做路由、参数校验、任务调度。
原型阶段解析同步执行；接入 Celery 后改为提交任务 + 轮询。

启动：uvicorn jb_api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from jb_agents import qualify
from jb_kb.models import CompanyProfile
from jb_parser import parse
from jb_parser.trm import TRM

PROFILE_DIR = os.environ.get("PROFILE_DIR", "data/company_profiles")

app = FastAPI(title="Jinbang API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # 逗号分隔的允许来源；默认 jb-web dev server。Nginx 反代（同源）场景无需配置。
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# 原型内存态项目存储；S2 起换 PostgreSQL
_projects: dict[str, dict] = {}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "jb-api"}


@app.post("/api/projects")
async def create_project(file: UploadFile):
    """上传招标文件包 → 解析 → 返回 TRM。"""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "请上传招标文件包 zip")
    project_id = uuid.uuid4().hex[:12]
    workdir = tempfile.mkdtemp(prefix=f"jb_{project_id}_")
    zip_path = os.path.join(workdir, file.filename)
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        trm = parse(zip_path, os.path.join(workdir, "unpacked"))
    except Exception as exc:  # 解析失败也保留项目以便排查
        raise HTTPException(422, f"解析失败: {exc}") from exc
    _projects[project_id] = {"id": project_id, "filename": file.filename,
                             "trm": trm.model_dump()}
    return {"id": project_id, "summary": trm.summary()}


@app.get("/api/projects")
def list_projects():
    return [{"id": p["id"], "filename": p["filename"],
             "batch_name": p["trm"].get("batch_name", "")} for p in _projects.values()]


@app.get("/api/projects/{project_id}/trm")
def get_trm(project_id: str):
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p["trm"]


@app.get("/api/profiles")
def list_profiles():
    """已建档企业（S2 落库前读 data/company_profiles/*.json）。"""
    if not os.path.isdir(PROFILE_DIR):
        return []
    return [f[:-5] for f in sorted(os.listdir(PROFILE_DIR)) if f.endswith(".json")]


@app.post("/api/projects/{project_id}/qualify")
def qualify_project(project_id: str, profile: str, llm: bool = False):
    """资格自检：返回可投性矩阵（JSON + Markdown）。"""
    p = _projects.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    path = os.path.join(PROFILE_DIR, profile + ".json")
    if not os.path.exists(path):
        raise HTTPException(404, "企业档案不存在")
    trm = TRM.model_validate(p["trm"])
    if llm:
        from jb_parser.llm_fallback import enrich
        enrich(trm)
        p["trm"] = trm.model_dump()
    rep = qualify(trm, CompanyProfile.load(path), use_llm=llm)
    return {"report": rep.model_dump(), "markdown": rep.markdown()}
