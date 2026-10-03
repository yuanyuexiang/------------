"""扫描件取图：知识库附件是图片直接用；PDF（社保/劳动合同/毕业证常见形态，纪要 2026-09-10）逐页转 PNG。

转换优先 poppler `pdftoppm`（compose 镜像已装 poppler-utils；本机 brew install poppler），其次 PyMuPDF（可选依赖），
都没有返回空列表由调用方写【待补充】。转出的页图缓存在附件旁 `<文件>.pages/`，同一附件只转一次。
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")
MAX_PAGES = 20
DPI = 110


def _page_no(path: str) -> int:
    m = re.search(r"(\d+)\.png$", path)
    return int(m.group(1)) if m else 0


def pdf_to_images(path: str, max_pages: int = MAX_PAGES) -> list[str]:
    out_dir = path + ".pages"
    cached = sorted(glob.glob(os.path.join(out_dir, "p*.png")), key=_page_no)
    if cached:
        return cached
    os.makedirs(out_dir, exist_ok=True)
    tool = shutil.which("pdftoppm")
    if tool:
        try:
            subprocess.run([tool, "-r", str(DPI), "-png", "-l", str(max_pages), path, os.path.join(out_dir, "p")],
                           check=True, capture_output=True, timeout=120)
        except Exception:
            pass
        pages = sorted(glob.glob(os.path.join(out_dir, "p*.png")), key=_page_no)
        if pages:
            return pages
    try:  # 可选：PyMuPDF
        import fitz
        pdf = fitz.open(path)
        pages = []
        for i, page in enumerate(pdf):
            if i >= max_pages:
                break
            out = os.path.join(out_dir, f"p-{i + 1}.png")
            page.get_pixmap(dpi=DPI).save(out)
            pages.append(out)
        return pages
    except Exception:
        return []


def images_for(path: str) -> tuple[list[str], str]:
    """附件路径 → (可插入的图片列表, 失败原因)。"""
    if not path or not os.path.exists(path):
        return [], "附件文件缺失"
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return [path], ""
    if ext == ".pdf":
        pages = pdf_to_images(path)
        return (pages, "") if pages else ([], f"{os.path.basename(path)} PDF 转图失败（服务器缺 pdftoppm/PyMuPDF）")
    return [], f"{os.path.basename(path)} 非图片/PDF 格式，需转为图片后插入"
