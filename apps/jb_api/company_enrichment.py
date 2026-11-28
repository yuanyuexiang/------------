"""Thin transport for company enrichment; preview and application are separate operations."""
from fastapi import APIRouter, HTTPException
from jb_kb import enrichment
from jb_store import auth
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/api/company-enrichment", tags=["knowledge-base"])


def execute(action, request):
    try:
        return action(request, auth.current_actor(), auth.secret_key())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(409, "企业资料已变化，请重新查询后再保存") from exc


@router.post("/online")
def preview_online(request: enrichment.PreviewRequest):
    return execute(enrichment.preview_online, request)


@router.post("/attachment")
def preview_attachment(request: enrichment.AttachmentRequest):
    return execute(enrichment.preview_attachment, request)


@router.post("/apply")
def apply_enrichment(request: enrichment.ApplyRequest):
    return execute(enrichment.apply, request)
