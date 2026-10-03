"""jb-docgen：文档引擎（商务文件/技术文件生成、技术参数自动填写、待补充标记）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from jb_kb.models import CompanyProfile, Product
from jb_parser.trm import TRM, PackageTRM

from .builder import GenContext, build_commercial, build_technical
from .placeholders import scan_docx
from .techparams import TechParamResult


@dataclass
class GenResult:
    commercial_path: str
    technical_path: str
    todos: list[str] = field(default_factory=list)          # 生成过程中登记的待补充项
    docx_todos: dict[str, list[str]] = field(default_factory=dict)  # 导出前扫描：文件→标记列表
    tech_params: list[TechParamResult] = field(default_factory=list)
    mode: dict[str, str] = field(default_factory=dict)      # 文件→ master（母版切片）| plain（自建版式）
    notes: list[str] = field(default_factory=list)          # 母版回退原因等说明

    @property
    def export_blocked(self) -> bool:
        return any(self.docx_todos.values())

    def summary(self) -> dict:
        stats = []
        for r in self.tech_params:
            stats.append({"spec_id": r.spec_id, "rows": len(r.responses),
                          "satisfied": sum(1 for x in r.responses if x.verdict == "satisfied"),
                          "deviation": len(r.deviations), "unknown": len(r.unknowns), "missing": len(r.todos)})
        return {"commercial": os.path.basename(self.commercial_path),
                "technical": os.path.basename(self.technical_path),
                "todo_count": sum(len(v) for v in self.docx_todos.values()),
                "export_blocked": self.export_blocked, "tech_params": stats,
                "mode": self.mode, "notes": self.notes}


def pick_product(profile: CompanyProfile, pkg: PackageTRM, model: Optional[str] = None) -> Optional[Product]:
    """按指定型号或分标名称关键词选产品；选不到返回 None（参数表全部【待补充】）。"""
    if model:
        return next((x for x in profile.products if x.model == model), None)
    key = pkg.sub_name
    for x in profile.products:
        if key and (key in x.name or key in x.category):
            return x
    return None


def generate(trm: TRM, pkg: PackageTRM, profile: CompanyProfile, out_dir: str,
             product_model: Optional[str] = None, drafts: Optional[list] = None,
             master_docx: Optional[str] = None, attachment_paths: Optional[dict] = None) -> GenResult:
    """生成商务/技术文件。

    master_docx 给定（招标文件六章主文件）时以其"文件格式"章为母版原位填空，保留国网原版式；
    母版缺段或装配异常则该文件退回自建版式（builder），原因写入 notes，绝不让生成失败。
    attachment_paths：知识库附件 id → 本地路径，用于把扫描件插入对应小节。
    """
    ctx = GenContext(trm=trm, pkg=pkg, profile=profile, product=pick_product(profile, pkg, product_model),
                     drafts=drafts, attachment_paths=attachment_paths or {})
    tag = f"{pkg.sub_no}{pkg.pkg_no}".replace("/", "_") or "pkg"
    com = os.path.join(out_dir, f"商务文件_{tag}.docx")
    tech = os.path.join(out_dir, f"技术文件_{tag}.docx")
    mode = {"commercial": "plain", "technical": "plain"}
    results: list[TechParamResult] = []
    if master_docx:
        from . import master_builder as mb
        try:
            if mb.build_commercial(ctx, master_docx, com):
                mode["commercial"] = "master"
        except Exception as exc:  # 母版异常不阻断生成
            ctx.notes.append(f"商务文件母版装配失败，退回自建版式：{exc!r}")
        try:
            ok, results = mb.build_technical(ctx, master_docx, tech)
            if ok:
                mode["technical"] = "master"
        except Exception as exc:
            ctx.notes.append(f"技术文件母版装配失败，退回自建版式：{exc!r}")
    if mode["commercial"] == "plain":
        build_commercial(ctx, com)
    if mode["technical"] == "plain":
        tech, results = build_technical(ctx, tech)
    res = GenResult(commercial_path=com, technical_path=tech, todos=ctx.todos, tech_params=results,
                    mode=mode, notes=ctx.notes)
    res.docx_todos = {os.path.basename(com): scan_docx(com), os.path.basename(tech): scan_docx(tech)}
    return res
