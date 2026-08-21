"""任务层：解析等长任务的执行与进度记录。

双模：
- CELERY_BROKER_URL 已设置（compose：redis）→ 投递到 Celery worker（`celery -A jb_api.tasks worker`）
- 未设置（本地/测试）→ FastAPI BackgroundTasks 进程内执行
两种模式跑的是同一个 `run_parse()`，进度都写 tasks 表，前端轮询 /api/tasks/{id}。
"""
from __future__ import annotations

import os

from jb_parser import parse
from jb_store import Project, Task, session

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
    _update(task_id, status="done", progress=1.0, message=trm.summary(),
            result={"packages": len(trm.packages), "warnings": trm.warnings})


if celery_app is not None:
    run_parse_celery = celery_app.task(name="jinbang.parse")(run_parse)


def submit_parse(background, task_id: str, project_id: str) -> str:
    """按模式投递。background 为 FastAPI BackgroundTasks。返回执行模式。"""
    if celery_app is not None:
        run_parse_celery.delay(task_id, project_id)
        return "celery"
    background.add_task(run_parse, task_id, project_id)
    return "inprocess"
