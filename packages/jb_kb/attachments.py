"""扫描件存储：本期落本地目录（api/worker 共享卷 UPLOAD_DIR/attachments），接口稳定，后续可切 MinIO。

文件名保留原名便于人工核对；路径用 <company>/<id>_<filename>，同一文件重复上传按 sha256 去重（返回已有记录）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from typing import Optional

from jb_store import KbAttachment
from jb_store.models import _uid
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Attachment

_SAFE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def attachments_root() -> str:
    return os.path.join(os.environ.get("UPLOAD_DIR", os.path.join(os.getcwd(), "uploads")), "attachments")


def _to_model(r: KbAttachment) -> Attachment:
    return Attachment(id=r.id, kind=r.kind, filename=r.filename, content_type=r.content_type, size=r.size,
                      sha256=r.sha256, storage_path=r.storage_path, uploaded_at=r.uploaded_at.isoformat())


def store(s: Session, company: str, filename: str, content: bytes, kind: str = "other",
          content_type: str = "") -> Attachment:
    digest = hashlib.sha256(content).hexdigest()
    dup = s.execute(select(KbAttachment).where(KbAttachment.company == company,
                                               KbAttachment.sha256 == digest)).scalars().first()
    if dup is not None:
        return _to_model(dup)
    aid = _uid()
    safe_name = _SAFE.sub("_", os.path.basename(filename)) or "file"
    rel = os.path.join(_SAFE.sub("_", company) or "company", f"{aid}_{safe_name}")
    abs_path = os.path.join(attachments_root(), rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(content)
    row = KbAttachment(id=aid, company=company, kind=kind, filename=safe_name, content_type=content_type,
                       size=len(content), sha256=digest, storage_path=rel,
                       uploaded_at=dt.datetime.utcnow())
    s.add(row)
    s.flush()
    return _to_model(row)


def list_attachments(s: Session, company: str, kind: str = "") -> list[Attachment]:
    q = select(KbAttachment).where(KbAttachment.company == company)
    if kind:
        q = q.where(KbAttachment.kind == kind)
    return [_to_model(r) for r in s.execute(q.order_by(KbAttachment.uploaded_at.desc())).scalars()]


def get_attachment(s: Session, attachment_id: str) -> Optional[Attachment]:
    r = s.get(KbAttachment, attachment_id)
    return _to_model(r) if r is not None else None


def absolute_path(a: Attachment) -> str:
    return os.path.join(attachments_root(), a.storage_path)


def delete_attachment(s: Session, company: str, attachment_id: str) -> bool:
    r = s.get(KbAttachment, attachment_id)
    if r is None or r.company != company:
        return False
    path = os.path.join(attachments_root(), r.storage_path)
    if os.path.exists(path):
        os.remove(path)
    s.delete(r)
    s.flush()
    return True
