"""导出加固：待补充阻断 → 元数据清理 → （可选）PDF 转换。

- 阻断：任何【待补充】残留即拒绝导出（CLAUDE.md 领域约束）。
- 元数据：docx 核心属性（作者/公司/最后修改者/修订/备注）统一清空——国网串标认定含"文件属性雷同"，
  且暗标禁止出现企业标识（案例 14、否决表形式评审）。
- PDF：优先 gotenberg HTTP（compose profile docgen），其次本机 soffice；都没有则跳过并如实返回。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import docx

from .placeholders import scan_docx

GOTENBERG_URL = os.environ.get("GOTENBERG_URL", "")


@dataclass
class ExportResult:
    ok: bool
    docx_path: str
    pdf_path: Optional[str] = None
    blocked_by: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def clean_metadata(path: str, author: str = "") -> None:
    """清空 core properties 并去掉注释/修订痕迹（python-docx 层面：核心属性）。"""
    d = docx.Document(path)
    cp = d.core_properties
    cp.author = author
    cp.last_modified_by = author
    cp.comments = ""
    cp.keywords = ""
    cp.subject = ""
    cp.title = ""
    cp.category = ""
    cp.revision = 1
    d.save(path)


def to_pdf(path: str, out_dir: Optional[str] = None) -> tuple[Optional[str], str]:
    out_dir = out_dir or os.path.dirname(path)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    if GOTENBERG_URL:
        try:
            import httpx
            with open(path, "rb") as f:
                r = httpx.post(GOTENBERG_URL.rstrip("/") + "/forms/libreoffice/convert",
                               files={"files": (os.path.basename(path), f)}, timeout=120)
            r.raise_for_status()
            with open(pdf, "wb") as g:
                g.write(r.content)
            return pdf, "gotenberg"
        except Exception as exc:  # 转换服务故障：降级
            note = f"gotenberg 失败: {exc}"
        else:
            note = ""
    else:
        note = "未配置 GOTENBERG_URL"
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
                       check=False, capture_output=True, timeout=180)
        if os.path.exists(pdf):
            return pdf, "soffice"
        return None, note + "；soffice 转换失败"
    return None, note + "；本机无 soffice，跳过 PDF"


def export(path: str, want_pdf: bool = True, force: bool = False) -> ExportResult:
    todos = scan_docx(path)
    if force:
        return ExportResult(ok=False, docx_path=path, blocked_by=["不允许强制绕过导出检查"])
    if todos:
        return ExportResult(ok=False, docx_path=path, blocked_by=todos,
                            notes=[f"{len(todos)} 处【待补充】未清零，禁止导出"])
    clean_metadata(path)
    res = ExportResult(ok=True, docx_path=path, notes=["元数据已清理"])
    if want_pdf:
        pdf, note = to_pdf(path)
        res.pdf_path = pdf
        res.notes.append(note)
    return res
