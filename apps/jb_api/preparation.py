"""投标准备任务接口；校验、归并、来源核对均由领域层完成。"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from jb_docgen import preparation as domain
from jb_kb import repo
from jb_parser.trm import TRM
from jb_store import Profile, Project, Task, session
from jb_store import auth as au
from sqlalchemy import select

router = APIRouter(prefix='/api/projects/{project_id}/preparation', tags=['preparation'])


def load(s, project_id, company, index, lock=False):
    query = select(Project).where(Project.id == project_id)
    p = s.scalar(query.with_for_update() if lock else query)
    if lock:
        s.scalar(select(Profile).where(Profile.name == company).with_for_update())
    cp = repo.load_profile(s, company)
    if p is None or cp is None:
        raise HTTPException(404, '项目或企业不存在')
    trm = TRM.model_validate(p.trm_confirmed or p.trm or {})
    if not 0 <= index < len(trm.packages):
        raise HTTPException(400, '标包不存在')
    return p, cp


@router.get('')
def get_preparation(project_id: str, profile: str, pkg_index: int = 0):
    with session() as s:
        p, cp = load(s, project_id, profile, pkg_index)
        return domain.state(s, p, pkg_index, cp)


@router.put('/{kind}')
def save_preparation(project_id: str, kind: str, profile: str, payload: dict, pkg_index: int = 0):
    with session() as s:
        p, cp = load(s, project_id, profile, pkg_index, lock=True)
        try:
            domain.save(s, p, pkg_index, cp, kind, payload, au.current_actor())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return {'ok': True, 'regenerate_required': True}


@router.post('/suggest/{kind}', status_code=202)
def suggest(project_id: str, kind: str, profile: str, background: BackgroundTasks,
            pkg_index: int = 0, item_id: str = ''):
    from .tasks import submit_suggestion
    if kind not in ('statistics', 'registration', 'performance'):
        raise HTTPException(400, '该任务需要企业确认本次安排，不能由AI代为决定')
    with session() as s:
        p, cp = load(s, project_id, profile, pkg_index, lock=True)
        if kind == 'performance' and not any(x.id == item_id for x in cp.performances):
            raise HTTPException(404, '请选择具体历史业绩')
        active = s.scalar(select(Task.id).where(Task.project_id == project_id,
                          Task.kind == 'suggest', Task.status.in_(['queued', 'running'])))
        if active:
            raise HTTPException(409, '本项目已有资料检索任务，请等待完成')
        t = Task(project_id=p.id, kind='suggest', actor=au.current_actor())
        s.add(t)
        s.flush()
        tid = t.id
    mode = submit_suggestion(background, tid, project_id, profile, pkg_index, kind, item_id)
    return {'task_id': tid, 'mode': mode}
