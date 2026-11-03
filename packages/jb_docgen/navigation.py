"""投标文件导航：真实标题、书签、可点击目录与页码域。"""
from __future__ import annotations

import re

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def _field(paragraph, instruction: str) -> None:
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), instruction)
    field.set(qn("w:dirty"), "true")
    paragraph._p.append(field)


def add_navigation(path: str) -> bool:
    """封面分页后插入目录；保留已有目录，页码由 Word/转换器计算，绝不猜页码。"""
    doc = Document(path)
    if any(p.text.strip() == "目录" for p in doc.paragraphs):
        return False
    if doc.element.xpath('.//w:instrText[contains(., "TOC ")]'):
        return False
    boundary = next((p for p in doc.paragraphs
                     if p._p.xpath('.//w:br[@w:type="page"]')), None)
    if boundary is None:
        return False  # 未识别封面边界时不擅自重排原件。
    body_start = next((p for p in doc.paragraphs
                       if p._p is boundary._p.getnext()), None)
    if body_start is None:
        return False
    headings = []
    started = False
    for paragraph in doc.paragraphs:
        if paragraph._p is boundary._p:
            started = True
            continue
        match = re.fullmatch(r"Heading ([1-3])", paragraph.style.name)
        if started and match and paragraph.text.strip():
            headings.append((paragraph, int(match.group(1))))
    if not headings:
        return False
    ids = [int(x) for x in doc.element.xpath('.//w:bookmarkStart/@w:id') if x.isdigit()]
    next_id = max(ids, default=0) + 1
    existing = set(doc.element.xpath('.//w:bookmarkStart/@w:name'))
    anchor = boundary._p

    def insert(text=""):
        nonlocal anchor
        from .master import insert_paragraph_after
        paragraph = insert_paragraph_after(doc, anchor, text)
        anchor = paragraph._p
        return paragraph

    title = insert("目录")
    title.runs[0].bold = True
    title.runs[0].font.size = Pt(16)
    for paragraph, level in headings:
        while f"jb_section_{next_id}" in existing:
            next_id += 1
        name = f"jb_section_{next_id}"
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(next_id))
        start.set(qn("w:name"), name)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(next_id))
        paragraph._p.insert(1 if paragraph._p.pPr is not None else 0, start)
        paragraph._p.append(end)
        next_id += 1
        entry = insert()
        entry.paragraph_format.left_indent = Cm((level - 1) * 0.5)
        entry.paragraph_format.first_line_indent = 0
        entry.paragraph_format.space_after = Pt(3)
        entry.paragraph_format.space_before = Pt(0)
        entry.paragraph_format.line_spacing = 1.0
        entry.paragraph_format.keep_with_next = False
        section = doc.sections[0]
        entry.paragraph_format.tab_stops.add_tab_stop(
            section.page_width - section.left_margin - section.right_margin,
            WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        link = OxmlElement("w:hyperlink")
        link.set(qn("w:anchor"), name)
        run = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = paragraph.text
        run.append(text)
        link.append(run)
        entry._p.append(link)
        entry.add_run("\t")
        _field(entry, f" PAGEREF {name} \\h ")
    # 将分页放在正文首段，避免分页专用空段落溢出后制造整张空白页。
    body_start.paragraph_format.page_break_before = True
    settings = doc.settings.element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")
    for level in range(1, 5):
        try:
            style = doc.styles[f"Heading {level}"]
        except KeyError:
            continue
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.keep_with_next = True
    # 沿用已有页脚；空页脚才补充页码。
    for section in doc.sections:
        footer = section.footer
        if not any(p.text.strip() or p._p.xpath('.//w:fldSimple | .//w:instrText | .//w:drawing')
                   for p in footer.paragraphs):
            _field(footer.paragraphs[0], " PAGE ")
    doc.save(path)
    return True
