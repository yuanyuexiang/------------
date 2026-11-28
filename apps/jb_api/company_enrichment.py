"""Thin transport for company enrichment; preview and application are separate operations."""
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile
from jb_kb import attachment_import, company_sources, enrichment
from jb_store import auth
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/api/company-enrichment", tags=["knowledge-base"])


def execute(action, request, **kwargs):
    try:
        return action(request, auth.current_actor(), auth.secret_key(), **kwargs)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(409, "企业资料已变化，请重新识别后再保存") from exc


@router.get("/sources")
def sources():
    return company_sources.OFFICIAL_SOURCES


@router.post("/online")
def retired_online_lookup():
    raise HTTPException(410, "请通过官方入口查询，或上传原件识别企业资料")


def _read_original(file: UploadFile):
    return enrichment.Original(file.filename or "",
                               file.file.read(attachment_import.MAX_ORIGINAL_BYTES + 1))


@router.post("/registry")
def preview_registry(file: UploadFile):
    return execute(enrichment.preview_registry, _read_original(file))


@router.post("/registry/apply", status_code=201)
def create_from_registry(file: UploadFile,
                         token: Annotated[str, Form(min_length=1, max_length=450_000)],
                         selected: Annotated[list[str], Form(max_length=60)]):
    return execute(enrichment.apply, enrichment.ApplyRequest(token=token, selected=selected),
                   original=_read_original(file))


@router.post("/attachment")
def preview_attachment(request: enrichment.AttachmentRequest):
    return execute(enrichment.preview_attachment, request)


@router.post("/apply")
def apply_enrichment(request: enrichment.ApplyRequest):
    return execute(enrichment.apply, request)
