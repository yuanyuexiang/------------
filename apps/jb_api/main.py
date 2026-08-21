"""jb-api：Jinbang 后端 HTTP 层。

薄 API 原则：业务逻辑全部在 packages/，本层只做路由、参数校验、任务调度。
存储：jb_store（SQLite 本地 / PostgreSQL compose）；长任务：jb_api.tasks（Celery 或进程内）。

启动：uvicorn jb_api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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


@app.get("/api/profiles/{name}")
def get_profile(name: str):
    with session() as s:
        row = s.get(Profile, name)
        if row is None:
            raise HTTPException(404, "企业档案不存在")
        return row.data


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


# ---------- 文件生成 ----------

def _load_trm_profile(project_id: str, profile: str):
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
        return TRM.model_validate(data), CompanyProfile.model_validate(prow.data)


@app.post("/api/projects/{project_id}/generate", status_code=202)
def generate_docs(project_id: str, profile: str, background: BackgroundTasks, pkg_index: int = 0,
                  product_model: Optional[str] = None, with_draft: bool = False):
    """生成商务/技术文件（异步任务；with_draft 时先由写作 Agent 起草）。轮询 /api/tasks/{id}。"""
    _load_trm_profile(project_id, profile)  # 参数校验（404/409）
    with session() as s:
        t = Task(project_id=project_id, kind="generate")
        s.add(t)
        s.flush()
        tid = t.id
    mode = tasks.submit_generate(background, tid, project_id, profile, pkg_index, with_draft, product_model or "")
    return {"task_id": tid, "mode": mode}


@app.post("/api/projects/{project_id}/review")
def review_docs(project_id: str, profile: str, pkg_index: int = 0):
    """合规审查：规则引擎扫描最近一次生成结果 + 档案 + TRM。"""
    import docx as _docx
    from jb_docgen.placeholders import scan_docx
    from jb_docgen.techparams import fill_spec
    from jb_rules import Context, review
    trm, cp = _load_trm_profile(project_id, profile)
    pkg = trm.packages[pkg_index]
    out_dir = os.path.join(UPLOAD_DIR, project_id, "out")
    docx_todos, doc_texts = {}, {}
    if os.path.isdir(out_dir):
        for fn in os.listdir(out_dir):
            if fn.endswith(".docx") and pkg.pkg_no in fn:
                path = os.path.join(out_dir, fn)
                docx_todos[fn] = scan_docx(path)
                d = _docx.Document(path)
                doc_texts[fn] = "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    from jb_docgen import pick_product
    product = pick_product(cp, pkg)
    tech_params = [fill_spec(sd, product) for sd in pkg.spec_docs]
    ctx = Context(trm=trm, pkg=pkg, profile=cp, tech_params=tech_params, docx_todos=docx_todos, doc_texts=doc_texts)
    rep = review(ctx)
    return {"blocked": rep.blocked, "counts": rep.counts(), "findings": [f.model_dump() for f in rep.findings],
            "markdown": rep.markdown()}


@app.post("/api/projects/{project_id}/price/validate")
def price_validate(project_id: str, sheet: dict, peer_avg: Optional[float] = None, over_limit_pct: Optional[float] = None):
    from jb_agents.price import PriceSheet, validate
    issues = validate(PriceSheet.model_validate(sheet), peer_avg=peer_avg, over_limit_pct=over_limit_pct)
    return {"issues": [i.model_dump() for i in issues], "blocked": any(i.level == "否决" for i in issues)}


@app.post("/api/price/simulate")
def price_simulate(my_price: float, peer_prices: list[float], c_candidates: Optional[list[float]] = None,
                   weight: float = 30.0):
    from jb_agents.price import simulate_interval_avg
    sim = simulate_interval_avg(my_price, peer_prices, c_candidates or [0.0, 0.01, 0.02, 0.03, 0.05], weight=weight)
    return {"benchmark_range": sim.benchmark_range, "score_range": sim.score_range, "detail": sim.detail}


@app.get("/api/projects/{project_id}/submission-matrix")
def submission_matrix(project_id: str, profile: str = "", pkg_index: int = 0):
    """递交矩阵：提交方式表 × 本包，标注系统已产出的文件。"""
    with session() as s:
        p = s.get(Project, project_id)
        if not p or not (p.trm_confirmed or p.trm):
            raise HTTPException(404, "项目/TRM 不存在")
        trm = TRM.model_validate(p.trm_confirmed or p.trm)
    out_dir = os.path.join(UPLOAD_DIR, project_id, "out")
    produced = os.listdir(out_dir) if os.path.isdir(out_dir) else []
    rows = []
    for it in trm.submission_table:
        if not it.item:
            continue
        sec = it.section
        gen = None
        if "商务" in sec and any("商务文件" in f for f in produced):
            gen = next(f for f in produced if "商务文件" in f)
        elif "技术" in sec and any("技术文件" in f for f in produced):
            gen = next(f for f in produced if "技术文件" in f)
        rows.append({"section": sec, "seq": it.seq, "item": it.item, "channels": it.channels, "port": it.port,
                     "generated_file": gen, "status": "系统产出(含于文件)" if gen else ("工具内填报" if "价格" in sec else "人工挂载")})
    return {"rows": rows}


@app.get("/api/projects/{project_id}/files/{filename}")
def download_file(project_id: str, filename: str):
    path = os.path.join(UPLOAD_DIR, project_id, "out", os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
