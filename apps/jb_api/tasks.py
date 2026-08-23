"""任务层：解析等长任务的执行与进度记录。

双模：
- CELERY_BROKER_URL 已设置（compose：redis）→ 投递到 Celery worker（`celery -A jb_api.tasks worker`）
- 未设置（本地/测试）→ FastAPI BackgroundTasks 进程内执行
两种模式跑的是同一个 `run_parse()`，进度都写 tasks 表，前端轮询 /api/tasks/{id}。
"""
from __future__ import annotations

import os

from jb_kb import repo as kb_repo
from jb_parser import parse
from jb_parser.trm import TRM
from jb_store import Project, Task, session
from jb_store import config as cfg
from jb_store import projects as pm

BROKER = os.environ.get("CELERY_BROKER_URL", "")

try:
    from celery import Celery
    celery_app = Celery("jinbang", broker=BROKER or None, backend=None) if BROKER else None
except ImportError:  # celery 为可选依赖
    celery_app = None


def _update(task_id: str, **fields) -> None:
    with session() as s:
        t = s.get(Task, task_id)
        for k, v in fields.items():
            setattr(t, k, v)


def run_parse(task_id: str, project_id: str) -> None:
    _update(task_id, status="running", progress=0.1, message="解压并分类文件")
    with session() as s:
        p = s.get(Project, project_id)
        p.status = "parsing"
        zip_path = p.zip_path
    try:
        trm = parse(zip_path, os.path.join(os.path.dirname(zip_path), "unpacked"))
    except Exception as exc:
        with session() as s:
            p = s.get(Project, project_id)
            p.status, p.error = "failed", str(exc)[:2000]
        _update(task_id, status="failed", message=f"解析失败: {exc}"[:2000])
        return
    with session() as s:
        p = s.get(Project, project_id)
        p.trm = trm.model_dump()
        p.batch_name, p.batch_no, p.status = trm.batch_name, trm.batch_no, "parsed"
        if not p.deadline_manual:            # 人工改过的截止时间不被重新解析覆盖
            p.deadline = trm.key_terms.bid_deadline or p.deadline
            p.open_time = trm.key_terms.bid_open_time or p.open_time
        pm.advance(p, "parsed")
        n_tpl = cfg.import_parsed_templates(s, trm.scoring_templates, source_hint=f"{trm.batch_name or trm.batch_no} 招标文件包")
        pkg_nos = [k.pkg_no for k in trm.packages]
        pm.log_event(s, project_id, "parsed",
                     f"解析完成：{len(pkg_nos)} 个包（{'、'.join(pkg_nos)}）"
                     + (f"，投标截止 {p.deadline}" if p.deadline else "，公告未抽到截止时间，请人工录入")
                     + (f"，{len(trm.warnings)} 条告警" if trm.warnings else "")
                     + (f"，{n_tpl} 个评分模板入库" if n_tpl else ""),
                     {"packages": pkg_nos, "deadline": p.deadline, "summary": trm.summary(), "warnings": trm.warnings})
    _update(task_id, status="done", progress=1.0, message=trm.summary(),
            result={"packages": len(trm.packages), "warnings": trm.warnings})


def run_generate(task_id: str, project_id: str, profile_name: str, pkg_index: int,
                 with_draft: bool, product_model: str = "") -> None:
    """生成商务/技术文件；with_draft=True 时先由写作 Agent 起草技术方案（LLM，分钟级）。"""
    from jb_docgen import generate

    from . import config as config_api
    config_api.install_usage_hook()      # Celery worker 进程内也记账、也读配置中心的 LLM 覆盖
    config_api.load_llm_settings()
    _update(task_id, status="running", progress=0.05, message="加载 TRM 与档案")
    with session() as s:
        p = s.get(Project, project_id)
        cp = kb_repo.load_profile(s, profile_name)
        if not p or cp is None or not (p.trm_confirmed or p.trm):
            _update(task_id, status="failed", message="项目/档案/TRM 不存在")
            return
        trm = TRM.model_validate(p.trm_confirmed or p.trm)
        zip_dir = os.path.dirname(p.zip_path)
    if not (0 <= pkg_index < len(trm.packages)):
        _update(task_id, status="failed", message="pkg_index 越界")
        return
    pkg = trm.packages[pkg_index]
    drafts = None
    draft_md = ""
    if with_draft:
        from jb_agents.writer import draft_package
        _update(task_id, progress=0.15, message="写作 Agent 起草技术方案（按评分项逐节，约 3-5 分钟）")
        d = draft_package(trm, pkg, cp, use_llm=True)
        drafts, draft_md = d.sections, d.markdown()
    _update(task_id, progress=0.8, message="装配商务/技术文件")
    try:
        res = generate(trm, pkg, cp, os.path.join(zip_dir, "out"), product_model or None, drafts=drafts)
    except Exception as exc:
        _update(task_id, status="failed", message=f"生成失败: {exc}"[:2000])
        return
    with session() as s:
        p = s.get(Project, project_id)
        summary = res.summary()
        pm.set_result(p, "generate", {"todo_count": summary.get("todo_count"), "export_blocked": summary.get("export_blocked"),
                                      "files": [os.path.basename(res.commercial_path), os.path.basename(res.technical_path)],
                                      "with_draft": with_draft, "profile": profile_name}, pkg.pkg_no)
        pm.advance(p, "generated")
        pm.log_event(s, project_id, "generated", f"{pkg.pkg_no} 生成商务/技术文件，待补充 {summary.get('todo_count')} 处",
                     {"pkg_no": pkg.pkg_no, "with_draft": with_draft})
    _update(task_id, status="done", progress=1.0, message="生成完成",
            result={"summary": res.summary(), "todos": res.docx_todos,
                    "files": [os.path.basename(res.commercial_path), os.path.basename(res.technical_path)],
                    "draft_markdown": draft_md,
                    "tech_params": [{"spec_id": r.spec_id, "responses": [x.__dict__ for x in r.responses]} for r in res.tech_params]})


if celery_app is not None:
    run_parse_celery = celery_app.task(name="jinbang.parse")(run_parse)
    run_generate_celery = celery_app.task(name="jinbang.generate")(run_generate)


def submit_generate(background, task_id: str, *args) -> str:
    if celery_app is not None:
        run_generate_celery.delay(task_id, *args)
        return "celery"
    background.add_task(run_generate, task_id, *args)
    return "inprocess"


def submit_parse(background, task_id: str, project_id: str) -> str:
    """按模式投递。background 为 FastAPI BackgroundTasks。返回执行模式。"""
    if celery_app is not None:
        run_parse_celery.delay(task_id, project_id)
        return "celery"
    background.add_task(run_parse, task_id, project_id)
    return "inprocess"
