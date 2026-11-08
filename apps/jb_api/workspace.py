"""项目要求、证据关联及文档内容预览接口。"""
import os
from pathlib import Path
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from jb_docgen import traceability
from jb_store import Project, auth, session

from .preparation import load

router = APIRouter(prefix='/api/projects/{project_id}', tags=['workspace'])


def output_dir(project_id):
    return os.path.join(os.environ.get('UPLOAD_DIR', os.path.join(os.getcwd(), 'uploads')), project_id, 'out')


@router.get('/source-archive')
def source_archive(project_id: str):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None or not p.zip_path or not Path(p.zip_path).is_file():
            raise HTTPException(404, '采购原件压缩包不存在')
        return FileResponse(p.zip_path, filename=Path(p.filename).name, media_type='application/zip')


@router.get('/requirements')
def requirements(project_id: str, profile: str, pkg_index: int = 0):
    with session() as s:
        p, cp = load(s, project_id, profile, pkg_index)
        try:
            return traceability.state(s, p, pkg_index, cp, output_dir(project_id))
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc


@router.put('/requirements/{requirement_id}')
def save_link(project_id: str, requirement_id: str, profile: str, payload: dict, pkg_index: int = 0):
    with session() as s:
        p, cp = load(s, project_id, profile, pkg_index, lock=True)
        try:
            traceability.save(s, p, pkg_index, cp, requirement_id, payload,
                              auth.current_actor(), output_dir(project_id))
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc
    return {'ok': True}


@router.get('/source-document')
def source_document(project_id: str, pkg_index: int = 0, source: str = 'main'):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404, '项目不存在')
        try:
            return traceability.source_document(p, pkg_index, source)
        except (ValueError, OSError, KeyError, BadZipFile) as exc:
            raise HTTPException(409, '原件暂时无法读取：' + str(exc)) from exc


@router.get('/document-preview')
def document_preview(project_id: str, profile: str, filename: str, pkg_index: int = 0):
    with session() as s:
        p, _ = load(s, project_id, profile, pkg_index)
        try:
            return traceability.output_document(p, pkg_index, profile, filename, output_dir(project_id))
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc
