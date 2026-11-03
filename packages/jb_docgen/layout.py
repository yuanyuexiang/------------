"""按母版页面可用区域限制表格宽度，保持列比例及合并关系。"""
from __future__ import annotations

import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.section import Section
from docx.shared import Pt
from docx.text.paragraph import Paragraph


def _trim_evidence_spacers(doc) -> int:
    """清理证据已插入或条件章节后的整页占位空行，保留节属性和签章留白。"""
    removed = 0
    run = []
    previous = None

    def flush():
        nonlocal removed
        if len(run) < 8 or previous is None or not any(
                list(p.iter(qn('w:sectPr'))) for p in run):
            return
        proof = bool(list(previous.iter(qn('w:drawing'))) or list(previous.iter(qn('w:pict'))))
        text = Paragraph(previous, doc._body).text if previous.tag == qn('w:p') else ''
        conditional = '如有' in text and re.match(r'^\d+[.．、]', text.strip())
        if not proof and not conditional:
            return
        for index, paragraph in enumerate(run):
            if list(paragraph.iter(qn('w:sectPr'))):
                carrier = Paragraph(paragraph, doc._body)
                carrier.paragraph_format.space_before = Pt(0)
                carrier.paragraph_format.space_after = Pt(0)
                carrier.paragraph_format.line_spacing = Pt(1)
                carrier.paragraph_format.keep_with_next = False
            elif proof or index >= 2:
                paragraph.getparent().remove(paragraph)
                removed += 1

    for element in list(doc.element.body):
        empty = (element.tag == qn('w:p') and not ''.join(element.itertext()).strip()
                 and not element.xpath('.//w:drawing | .//w:pict | .//w:fldChar | .//w:fldSimple | .//w:sdt | .//w:bookmarkStart | .//w:br'))
        if empty:
            run.append(element)
        else:
            flush()
            run = []
            previous = element
    flush()
    return removed


def fit_tables(path: str) -> int:
    doc = Document(path)
    removed_spacers = _trim_evidence_spacers(doc)
    adjusted = 0
    for table in doc.tables:
        section = doc.sections[-1]
        node = table._tbl.getnext()
        while node is not None:
            sections = list(node.iter(qn('w:sectPr')))
            if sections:
                section = Section(sections[0], doc.part)
                break
            node = node.getnext()
        properties = table._tbl.tblPr
        indent = properties.find(qn('w:tblInd'))
        indent_twips = int(indent.get(qn('w:w'), '0')) if indent is not None else 0
        available = int((section.page_width - section.left_margin - section.right_margin) / 635)
        available -= max(indent_twips, 0)
        columns = table._tbl.tblGrid.gridCol_lst
        widths = [int(col.get(qn('w:w'), '0')) for col in columns]
        total = sum(widths)
        if total <= available or available <= 0:
            continue
        scaled = [int(width * available / total) for width in widths]
        scaled[-1] += available - sum(scaled)
        for col, width in zip(columns, scaled):
            col.set(qn('w:w'), str(width))
        for cell_width in table._tbl.xpath('./w:tr/w:tc/w:tcPr/w:tcW'):
            if cell_width.get(qn('w:type')) == 'dxa':
                old = int(cell_width.get(qn('w:w'), '0'))
                cell_width.set(qn('w:w'), str(int(old * available / total)))
        width = properties.find(qn('w:tblW'))
        if width is None:
            width = OxmlElement('w:tblW')
            properties.append(width)
        width.set(qn('w:type'), 'dxa')
        width.set(qn('w:w'), str(available))
        table.autofit = False
        adjusted += 1
    if adjusted or removed_spacers:
        doc.save(path)
    return adjusted
