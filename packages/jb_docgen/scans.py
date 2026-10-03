"""扫描件取图：知识库附件是图片直接用；PDF（社保/劳动合同/毕业证常见形态，纪要 2026-09-10）逐页转 PNG。

转换优先 poppler `pdftoppm`（compose 镜像已装 poppler-utils；本机 brew install poppler），其次 PyMuPDF（可选依赖），
都没有返回空列表由调用方写【待补充】。转出的页图缓存在附件旁 `<文件>.pages/`，同一附件只转一次。
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")
DPI = 110


def _page_no(path: str) -> int:
    m = re.search(r"(\d+)\.png$", path)
    return int(m.group(1)) if m else 0


def pdf_to_images(path: str, max_pages: Optional[int] = None) -> list[str]:
    """转换完整 PDF；显式页数限制不足时返回失败，完整转换才发布缓存。"""
    out_dir = path + ".pages"
    marker = os.path.join(out_dir, "complete.json")
    stat = os.stat(path)
    signature = [stat.st_size, stat.st_mtime_ns]
    try:
        with open(marker, encoding="utf-8") as f:
            meta = json.load(f)
        cached = sorted(glob.glob(os.path.join(out_dir, "p*.png")), key=_page_no)
        if (meta["source"] == signature and len(cached) == meta["count"]
                and cached and all(os.path.getsize(p) for p in cached)
                and (max_pages is None or len(cached) <= max_pages)):
            return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if max_pages is not None and max_pages <= 0:
        return []
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir) as staging:
        tool = shutil.which("pdftoppm")
        pages = []
        if tool:
            args = [tool, "-r", str(DPI), "-png"]
            if max_pages is not None:
                args.extend(["-l", str(max_pages + 1)])
            try:
                subprocess.run(args + [path, os.path.join(staging, "p")],
                               check=True, capture_output=True, timeout=120)
                pages = sorted(glob.glob(os.path.join(staging, "p*.png")), key=_page_no)
            except (OSError, subprocess.SubprocessError):
                pass
        if not pages:
            # 失败的转换可能留下部分页图，不能作为完整附件使用。
            for partial in glob.glob(os.path.join(staging, "p*.png")):
                os.remove(partial)
            try:
                import fitz
                with fitz.open(path) as pdf:
                    if max_pages is not None and len(pdf) > max_pages:
                        return []
                    for i, page in enumerate(pdf):
                        out = os.path.join(staging, f"p-{i + 1}.png")
                        page.get_pixmap(dpi=DPI).save(out)
                        pages.append(out)
            except Exception:
                return []
        if not pages or (max_pages is not None and len(pages) > max_pages):
            return []
        if not all(os.path.getsize(p) for p in pages):
            return []
        # 旧缓存（包括历史版本截断的缓存）无完整性标记时重新生成。
        if os.path.exists(marker):
            os.remove(marker)
        for old in glob.glob(os.path.join(out_dir, "p*.png")):
            os.remove(old)
        published = []
        for page in pages:
            target = os.path.join(out_dir, os.path.basename(page))
            os.replace(page, target)
            published.append(target)
        temp_marker = os.path.join(staging, "complete.json")
        with open(temp_marker, "w", encoding="utf-8") as f:
            json.dump({"source": signature, "count": len(published)}, f)
        os.replace(temp_marker, marker)
        return published


def images_for(path: str) -> tuple[list[str], str]:
    """附件路径 → (可插入的图片列表, 失败原因)。"""
    if not path or not os.path.exists(path):
        return [], "附件文件缺失"
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return [path], ""
    if ext == ".pdf":
        pages = pdf_to_images(path)
        return (pages, "") if pages else ([], f"{os.path.basename(path)} PDF 转图失败（转换器不可用、文件损坏或转换未完成）")
    return [], f"{os.path.basename(path)} 非图片/PDF 格式，需转为图片后插入"
