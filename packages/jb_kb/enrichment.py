"""Review and apply sourced company facts and draft evidence in one transaction."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Union

from jb_store import Profile, session
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from . import attachment_import, attachments, repo
from .models import EvidenceOrigin

LABELS = {
    "name": "企业名称", "credit_code": "统一社会信用代码", "legal_person": "法定代表人",
    "address": "登记住所", "business_scope": "经营范围", "founded": "成立日期",
    "registered_capital_wan": "注册资本（人民币万元）", "company_type": "企业类型",
}
TITLES = {"certificates": "证照", "performances": "业绩", "financials": "财务", "test_reports": "检测报告"}
_EXPIRY = 1800


class Candidate(BaseModel):
    id: str
    kind: str
    title: str
    origin: EvidenceOrigin
    field: str = ""
    value: Optional[Union[str, float]] = None
    current: Optional[Union[str, float]] = None
    data: dict = Field(default_factory=dict)
    field_origins: dict[str, EvidenceOrigin] = Field(default_factory=dict)
    unchanged: bool = False
    existing_id: str = ""


class Review(BaseModel):
    company: str
    actor: str
    expires: int
    existing: bool
    expected_code: str
    candidates: list[Candidate]
    original_sha256: str = ""
    original_name: str = ""


@dataclass(frozen=True)
class Original:
    filename: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class AttachmentRequest(BaseModel):
    company: str = Field(min_length=1, max_length=128)
    attachment_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(max_length=32)


class ApplyRequest(BaseModel):
    token: str = Field(min_length=1, max_length=450_000)
    selected: list[str] = Field(max_length=60)


def _record_key(kind, item):
    if kind == "certificates":
        return item.number.casefold() if item.number else item.name
    if kind == "performances":
        return item.project, item.buyer
    if kind == "financials":
        return item.year.rstrip("年")
    return item.number.casefold() if item.number else item.name


def _matching_records(cp, kind, raw):
    if cp is None:
        return []
    candidate = repo.KINDS[kind].model.model_validate(raw)
    return [item for item in getattr(cp, kind)
            if _record_key(kind, item) == _record_key(kind, candidate)]


def _signature(payload: str, secret: str):
    return hmac.new(secret.encode(), b"company-enrichment-v2:" + payload.encode(),
                    hashlib.sha256).hexdigest()


def _snapshot(result, cp, name, expected_code, actor, secret, *,
              original: Optional[Original] = None):
    candidates = []
    for key, (value, origin) in result["fields"].items():
        if key == "name" and cp:
            continue
        current = getattr(cp, key) if cp else None
        candidates.append(Candidate(id=f"field-{key}", kind="field", title=LABELS[key], field=key,
                                    value=value, current=current, origin=origin,
                                    unchanged=value == current and cp is not None and key in cp.field_sources))
    for i, record in enumerate(result["records"]):
        kind = record["kind"]
        origin = record["origin"]
        matches = _matching_records(cp, kind, record["data"])
        attach_id = origin.attachment_id
        match = matches[0] if len(matches) == 1 and attach_id else None
        amend = bool(match and match.status == "draft" and attach_id not in match.attachments)
        candidates.append(Candidate(
            id=f"record-{i}", kind=kind, title=record["title"], data=record["data"],
            origin=origin, field_origins=record.get("field_origins", {}),
            unchanged=bool(matches) and not amend, existing_id=match.id if amend else "",
        ))

    snapshot = Review(company=name, actor=actor, expires=int(time.time()) + _EXPIRY,
                      existing=cp is not None, expected_code=expected_code, candidates=candidates,
                      original_sha256=original.sha256 if original else "",
                      original_name=original.filename if original else "")
    b64 = base64.urlsafe_b64encode(snapshot.model_dump_json().encode()).decode()
    return {"company": name, "candidates": candidates, "checks": result["checks"],
            "token": b64 + "." + _signature(b64, secret) if candidates else ""}


def _check_company_code(s, name: str, code: str) -> None:
    if code and s.scalar(select(Profile.name).where(
        func.upper(func.trim(Profile.credit_code)) == code, Profile.name != name
    )):
        raise ValueError("统一社会信用代码已关联其他企业档案，请在已有档案中补全资料")


def preview_registry(original: Original, actor: str, secret: str):
    if not original.content or len(original.content) > attachment_import.MAX_ORIGINAL_BYTES:
        raise ValueError("请选择大小在 30 MB 以内的非空原件")
    path = Path(original.filename.replace("\\", "/"))
    suffix = path.suffix.lower()
    if suffix not in attachment_import.ORIGINAL_TYPES:
        raise ValueError("请选择 PDF、图片或 Word 原件")
    filename = path.stem.encode()[:180].decode(errors="ignore") + suffix
    original = Original(filename, original.content)
    with TemporaryDirectory(prefix="jb-registry-") as folder:
        local = Path(folder) / ("original" + suffix)
        local.write_bytes(original.content)
        result = attachment_import.extract_original(str(local), filename, "registry", None)
    name = result["fields"].get("name", ("", None))[0]
    code = result["fields"].get("credit_code", ("", None))[0]
    if not name or not code:
        return _snapshot(result, None, "", "", actor, secret)
    with session() as s:
        if s.get(Profile, name):
            raise ValueError("企业档案已存在，请在该企业中补全资料")
        _check_company_code(s, name, code)
    return _snapshot(result, None, name, code, actor, secret, original=original)


def preview_attachment(request: AttachmentRequest, actor: str, secret: str):
    if request.kind not in attachment_import.KINDS:
        raise ValueError("请选择支持的附件用途")
    with session() as s:
        cp = repo.load_profile(s, request.company)
        attachment = next((item for item in attachments.list_attachments(s, request.company)
                           if item.id == request.attachment_id), None)
    if cp is None or attachment is None:
        raise ValueError("原件不存在或不属于该企业")
    result = attachment_import.extract(cp, attachment, request.kind)
    code = result["fields"].get("credit_code", (cp.credit_code, None))[0]
    return _snapshot(result, cp, cp.name, code, actor, secret)


def _review(token, actor, secret):
    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(_signature(payload, secret), signature):
        raise ValueError("候选记录校验失败，请重新查询")
    try:
        review = Review.model_validate_json(base64.urlsafe_b64decode(payload))
    except (ValueError, ValidationError) as exc:
        raise ValueError("候选记录无法读取，请重新查询") from exc
    if review.actor != actor or review.expires < time.time():
        raise ValueError("候选记录已过期，请重新查询")
    return review


def _source_text(origin: EvidenceOrigin):
    parts = [origin.title, f"第{origin.page}页" if origin.page else "",
             origin.url, origin.fetched_at[:10]]
    return " · ".join(part for part in parts if part)


def _attach_to_draft(cp, entry):
    matches = _matching_records(cp, entry.kind, entry.data)
    if len(matches) != 1 or matches[0].id != entry.existing_id or matches[0].status != "draft":
        raise ValueError("对应的待审核资料已变化，请重新识别原件")
    raw = matches[0].model_dump()
    aid = entry.origin.attachment_id
    if aid in raw["attachments"]:
        return None
    raw["attachments"].append(aid)
    sources = {}
    for field, value in entry.data.items():
        if field == "evidence":
            raw[field] = list(dict.fromkeys([*raw[field], *value]))
        elif raw.get(field) in (None, "", []):
            raw[field] = value
            if field in entry.field_origins:
                sources[field] = entry.field_origins[field]
    return raw, sources


def _apply(s, review, chosen, original, rollback):
    if not review.existing and s.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(review.expected_code.encode()).digest()[:8],
                             "big", signed=True)
        s.execute(select(func.pg_advisory_xact_lock(key)))
    row = s.scalar(select(Profile).where(Profile.name == review.company).with_for_update())
    cp = repo.load_profile(s, review.company) if row is not None else None
    if review.existing != (cp is not None):
        raise ValueError("企业档案已变化，请重新查询")
    if not review.company:
        raise ValueError("未核对到企业名称")
    if cp and (cp.credit_code and cp.credit_code.strip().upper() != review.expected_code):
        raise ValueError("当前企业信用代码已更新，请重新查询")
    _check_company_code(s, review.company, review.expected_code)
    attachment_ids = {item.id for item in attachments.list_attachments(s, review.company)} if cp else set()
    if original:
        repo.save_main(s, review.company, {"credit_code": review.expected_code})
        s.flush()
        filename = review.original_name
        attachment = attachments.store(
            s, review.company, filename, original.content, kind="certificate",
            content_type=attachment_import.ORIGINAL_TYPES[Path(filename).suffix],
        )
        rollback.callback(Path(attachments.absolute_path(attachment)).unlink, missing_ok=True)
        attachment_ids.add(attachment.id)
        chosen = [entry.model_copy(update={
            "origin": entry.origin.model_copy(update={"attachment_id": attachment.id}),
            "field_origins": {key: origin.model_copy(update={"attachment_id": attachment.id})
                              for key, origin in entry.field_origins.items()},
        }) for entry in chosen]
    fields, origins, records, updates = {}, {}, [], []
    existing_keys = {kind: {_record_key(kind, item) for item in getattr(cp, kind)}
                     if cp else set() for kind in TITLES}
    for entry in chosen:
        if entry.origin.attachment_id and entry.origin.attachment_id not in attachment_ids:
            raise ValueError("关联的原件已被删除，请重新选择资料")
        if entry.kind == "field":
            if entry.field == "name":
                if cp is None:
                    origins["name"] = entry.origin
                continue
            current = getattr(cp, entry.field) if cp else None
            if current != entry.current:
                raise ValueError("字段已被修改，请重新查询并核对差异")
            fields[entry.field] = entry.value
            origins[entry.field] = entry.origin
        elif entry.existing_id:
            patched = _attach_to_draft(cp, entry)
            if patched:
                updates.append((entry.kind, *patched))
        else:
            key = _record_key(entry.kind, repo.KINDS[entry.kind].model.model_validate(entry.data))
            if key in existing_keys[entry.kind]:
                continue
            existing_keys[entry.kind].add(key)
            records.append((entry.kind, {
                **entry.data, "status": "draft", "source": _source_text(entry.origin),
                "evidence_origin": entry.origin.model_dump(),
                "evidence_fields": {key: origin.model_dump() for key, origin in entry.field_origins.items()},
                "attachments": [entry.origin.attachment_id] if entry.origin.attachment_id else [],
            }))
    if fields:
        repo.save_main(s, review.company, fields, field_sources=origins)
    for kind, data in records:
        repo.upsert_item(s, review.company, kind, data)
    for kind, data, sources in updates:
        repo.upsert_item(s, review.company, kind, data, evidence_fields=sources)
    return {"company": review.company, "fields_updated": len(fields), "records_added": len(records),
            "records_updated": len(updates),
            "record_kinds": list(dict.fromkeys(entry[0] for entry in [*records, *updates]))}


def apply(request: ApplyRequest, actor: str, secret: str, *, original: Optional[Original] = None):
    review = _review(request.token, actor, secret)
    by_id = {entry.id: entry for entry in review.candidates if not entry.unchanged}
    chosen = list(dict.fromkeys(request.selected))
    if not chosen or any(key not in by_id for key in chosen):
        raise ValueError("请选择可采用的字段或资料")
    if not review.existing:
        if not {"field-name", "field-credit_code"}.issubset(chosen):
            raise ValueError("新建企业需要确认企业名称和统一社会信用代码")
        if (not original or len(original.content) > attachment_import.MAX_ORIGINAL_BYTES
                or original.sha256 != review.original_sha256):
            raise ValueError("原件与预览文件不一致，请重新识别")
    elif original:
        raise ValueError("请在对应企业档案中导入原件")
    with ExitStack() as rollback:
        with session() as s:
            result = _apply(s, review, [by_id[key] for key in chosen], original, rollback)
        rollback.pop_all()
    return result
