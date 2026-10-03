"""扫描件取图：图片直通、PDF 转页图（本机无 pdftoppm/PyMuPDF 时跳过转换用例）、缓存与失败原因。"""
import os
import shutil

import pytest
from jb_docgen import scans

# 最小合法单页 PDF（无依赖手写）
_MINI_PDF = b"""%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj
trailer<</Root 1 0 R>>
"""


def _has_converter() -> bool:
    if shutil.which("pdftoppm"):
        return True
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def test_images_for_plain_cases(tmp_path):
    img = tmp_path / "a.PNG"
    img.write_bytes(b"x")
    assert scans.images_for(str(img)) == ([str(img)], "")
    assert scans.images_for("") == ([], "附件文件缺失")
    assert scans.images_for(str(tmp_path / "none.pdf")) == ([], "附件文件缺失")
    other = tmp_path / "x.docx"
    other.write_bytes(b"x")
    assert "非图片/PDF" in scans.images_for(str(other))[1]


@pytest.mark.skipif(not _has_converter(), reason="本机无 pdftoppm / PyMuPDF")
def test_pdf_to_images_and_cache(tmp_path):
    pdf = tmp_path / "社保.pdf"
    pdf.write_bytes(_MINI_PDF)
    pages, reason = scans.images_for(str(pdf))
    assert reason == "" and len(pages) == 1 and pages[0].endswith(".png") and os.path.getsize(pages[0]) > 0
    assert os.path.dirname(pages[0]) == str(pdf) + ".pages"
    assert scans.images_for(str(pdf))[0] == pages          # 二次取用走缓存


@pytest.mark.skipif(_has_converter(), reason="有转换器时不测失败分支")
def test_pdf_without_converter(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(_MINI_PDF)
    pages, reason = scans.images_for(str(pdf))
    assert pages == [] and "转图失败" in reason
