"""jb-api：Jinbang 后端 HTTP 层。

薄 API 原则：业务逻辑全部在 packages/，本层只做路由、参数校验、任务调度。
存储：jb_store（SQLite 本地 / PostgreSQL compose）；长任务：jb_api.tasks（Celery 或进程内）。

启动：uvicorn jb_api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from jb_agents import qualify
from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM
from jb_store import Profile, Project, Task, init_db, session
from sqlalchemy import select

from . import tasks

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.getcwd(), "uploads"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 开发便利；生产以 alembic upgrade head 为准
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    yield


app = FastAPI(title="Jinbang API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _project_out(p: Project) -> dict:
    return {"id": p.id, "filename": p.filename, "status": p.status, "batch_name": p.batch_name,
            "batch_no": p.batch_no, "error": p.error, "created_at": p.created_at.isoformat(),
            "confirmed": p.trm_confirmed is not None}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "jb-api", "task_mode": "celery" if tasks.celery_app else "inprocess"}


# ---------- 项目 / 解析 ----------

@app.post("/api/projects", status_code=202)
async def create_project(file: UploadFile, background: BackgroundTasks):
    """上传招标文件包 → 建项目 → 异步解析。返回 project_id + task_id 供轮询。"""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "请上传招标文件包 zip")
    with session() as s:
        p = Project(filename=file.filename, zip_path="")
        s.add(p)
        s.flush()
        pdir = os.path.join(UPLOAD_DIR, p.id)
        os.makedirs(pdir, exist_ok=True)
        p.zip_path = os.path.join(pdir, file.filename)
        with open(p.zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        t = Task(project_id=p.id, kind="parse")
        s.add(t)
        s.flush()
        pid, tid = p.id, t.id
    mode = tasks.submit_parse(background, tid, pid)
    return {"id": pid, "task_id": tid, "mode": mode}


@app.get("/api/projects")
def list_projects():
    with session() as s:
        rows = s.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
        return [_project_out(p) for p in rows]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    with session() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        return _project_out(p)


@app.get("/api/projects/{project_id}/trm")
def get_trm(project_id: str, confirmed: bool = False):
    with session() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        data = p.trm_confirmed if confirmed and p.trm_confirmed else p.trm
        if data is None:
            raise HTTPException(409, f"TRM 尚未就绪（状态 {p.status}）")
        return data


@app.put("/api/projects/{project_id}/trm")
def confirm_trm(project_id: str, trm: dict):
    """确认页提交：保存人工确认版 TRM（整体覆盖；Schema 校验）。"""
    validated = TRM.model_validate(trm)
    with session() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        p.trm_confirmed = validated.model_dump()
        p.status = "confirmed"
    return {"ok": True}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    with session() as s:
        t = s.get(Task, task_id)
        if not t:
            raise HTTPException(404, "任务不存在")
        return {"id": t.id, "project_id": t.project_id, "kind": t.kind, "status": t.status,
                "progress": t.progress, "message": t.message, "result": t.result}


# ---------- 企业档案 / 资格自检 ----------

@app.get("/api/profiles")
def list_profiles():
    with session() as s:
        rows = s.execute(select(Profile).order_by(Profile.name)).scalars().all()
        return [{"name": r.name, "credit_code": r.credit_code, "updated_at": r.updated_at.isoformat()}
                for r in rows]


@app.put("/api/profiles/{name}")
def upsert_profile(name: str, profile: dict):
    cp = CompanyProfile.model_validate(profile)
    with session() as s:
        row = s.get(Profile, name)
        if row is None:
            s.add(Profile(name=name, credit_code=cp.credit_code, data=cp.model_dump()))
        else:
            row.credit_code, row.data = cp.credit_code, cp.model_dump()
    return {"ok": True}


@app.post("/api/projects/{project_id}/qualify")
def qualify_project(project_id: str, profile: str, llm: bool = False):
    """资格自检：优先用人工确认版 TRM。"""
    with session() as s:
        p = s.get(Project, project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        data = p.trm_confirmed or p.trm
        if data is None:
            raise HTTPException(409, "TRM 尚未就绪")
        prow = s.get(Profile, profile)
        if prow is None:
            raise HTTPException(404, "企业档案不存在")
        trm = TRM.model_validate(data)
        cp = CompanyProfile.model_validate(prow.data)
    if llm:
        from jb_parser.llm_fallback import enrich
        enrich(trm)
    rep = qualify(trm, cp, use_llm=llm)
    return {"report": rep.model_dump(), "markdown": rep.markdown()}
