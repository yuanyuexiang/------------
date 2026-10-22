"""附件装配和材料分类：同名扫描PDF优先，不把Word原稿误当成缺失扫描件。"""
from __future__ import annotations

import re
from pathlib import Path

from . import master as M
from .placeholders import todo
from .scans import images_for


def _stem(path: str) -> str:
    return re.sub(r"^[0-9a-f]{12}_", "", Path(path).stem)


def scan_ids(ids: list[str], paths: dict) -> list[str]:
    pdf_stems = {_stem(paths[a]) for a in ids if a in paths and Path(paths[a]).suffix.lower() == ".pdf"}
    return [a for a in dict.fromkeys(ids) if not (
        a in paths and Path(paths[a]).suffix.lower() in (".doc", ".docx") and _stem(paths[a]) in pdf_stems)]


def insert_scans(ctx, doc, anchor_el, ids: list[str], what: str):
    last = anchor_el
    ids = scan_ids(ids, ctx.attachment_paths)
    for aid in ids:
        images, reason = images_for(ctx.attachment_paths.get(aid, ""))
        ok = 0
        for img in images:
            para = M.insert_picture_after(doc, last, img)
            if para is not None:
                last, ok = para._p, ok + 1
        if not ok:
            last = M.insert_paragraph_after(doc, last, todo(f"{what}（{reason or '图片插入失败'}）"))._p
    if not ids:
        last = M.insert_paragraph_after(doc, last, todo(f"{what}扫描件插入"))._p
    return last


def certificates_for(profile, kind: str):
    certs = profile.certificates
    if kind == "business":
        return [c for c in certs if "营业执照" in c.name]
    if kind == "tax":
        return [c for c in certs if "税务" in c.name or c.includes_tax_registration]
    if kind == "bank":
        return [c for c in certs if any(w in c.name for w in ("基本存款账户", "开户", "基本账户"))]
    if kind == "credit":
        return [c for c in certs if c.cert_type == "信用查询材料" or any(w in c.name for w in ("信用中国", "信用信息公示", "裁判文书"))]
    if kind == "system":
        return [c for c in certs if c.cert_type == "体系认证"]
    special = {c.id or c.name for group in ("business", "tax", "bank", "credit", "system") for c in certificates_for(profile, group)}
    return [c for c in certs if (c.id or c.name) not in special and c.cert_type != "身份证明"]


def insert_credit(ctx, doc, anchor):
    last = anchor
    for label, keywords in (("信用中国", ("信用中国", "公共信用")),
                            ("国家企业信用信息公示系统", ("企业信用信息公示",)),
                            ("中国裁判文书网", ("裁判文书",))):
        found = [c for c in certificates_for(ctx.profile, "credit") if any(w in c.name for w in keywords)]
        last = M.insert_paragraph_after(doc, last, label + "查询材料")._p
        last = insert_scans(ctx, doc, last, [a for c in found for a in c.attachments], label)
    return last
