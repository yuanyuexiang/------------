"""项目级生成版本及可读文件名。版本在持有项目行锁时预留，失败后不复用。"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from jb_parser.trm import TRM
from jb_store import Project, Task
from jb_store import projects as pm
from sqlalchemy import select
from sqlalchemy.orm import Session

CST = timezone(timedelta(hours=8))


def reserve(s: Session, project: Project, pkg_index: int,
            now: Optional[datetime] = None) -> dict:
    """调用方必须持有项目行锁；同项目所有包和企业共享递增序号，避免文件重名。"""
    tasks = list(s.scalars(select(Task).where(Task.project_id == project.id, Task.kind == 'generate')))
    results = project.results or {}
    previous = max([results.get('generation_counter', 0), len(tasks),
                    *[(t.result or {}).get('version', 0) for t in tasks]])
    version = previous + 1
    pm.set_result(project, 'generation_counter', version)
    trm = TRM.model_validate(project.trm_confirmed or project.trm)
    pkg = trm.packages[pkg_index]
    at = (now or datetime.now(CST)).astimezone(CST)
    title = safe_part(pkg.project_name or trm.batch_name or trm.batch_no or project.filename, 24)
    package = safe_part('_'.join(filter(None, [pkg.sub_no, pkg.pkg_no])), 24)
    return {'version': version, 'generated_at': at.isoformat(),
            'filename_prefix': f'{title}_{package}_V{version:03d}_{at:%Y%m%d-%H%M%S}'}


def safe_part(value: str, limit: int) -> str:
    text = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|\s]+', '-', str(value)).strip(' .-_')
    return text[:limit].rstrip(' .-_') or '项目'


def document_name(metadata: dict, kind: str) -> str:
    if kind not in ('商务文件', '技术文件'):
        raise ValueError('未知投标文件类型')
    return f"{metadata['filename_prefix']}_{kind}.docx"
