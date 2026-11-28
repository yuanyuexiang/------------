"""按母版页面可用区域限制表格宽度，保持列比例及合并关系。"""
from __future__ import annotations

import re

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.section import Section
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from lxml import etree

_WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def ensure_table_grid(table) -> bool:
    """Use explicit cell widths when they describe an unambiguous column grid."""
    grid = table.find(qn('w:tblGrid'))
    if grid is not None and grid.gridCol_lst:
        return True
    candidates = set()
    spans = []
    for row in table.tr_lst:
        start = row.grid_before
        widths = []
        for cell in row.tc_lst:
            span = cell.grid_span
            width = cell.width
            twips = width.twips if width is not None and width > 0 else None
            spans.append((start, span, twips))
            widths.append(twips)
            start += span
        if len(widths) == start and not row.grid_before and not row.grid_after and all(widths) and widths:
            candidates.add(tuple(widths))
    if len(candidates) != 1:
        return False
    widths = candidates.pop()
    if any(start + span > len(widths) or (
            width is not None and sum(widths[start:start + span]) != width)
           for start, span, width in spans):
        return False
    if grid is None:
        grid = OxmlElement('w:tblGrid')
        properties = table.find(qn('w:tblPr'))
        table.insert(0 if properties is None else table.index(properties) + 1, grid)
    for width in widths:
        column = OxmlElement('w:gridCol')
        column.set(qn('w:w'), str(width))
        grid.append(column)
    return True


def structural_issues(path: str) -> list[str]:
    """Check references and vertical merges in the completed Word package."""
    try:
        doc = Document(path)
    except (OSError, KeyError, ValueError, PackageNotFoundError, etree.XMLSyntaxError) as exc:
        return [f'Word 文档结构无法读取（{type(exc).__name__}）']
    issues = []
    parts = [(doc.part, '正文'), *((rel.target_part, '页眉页脚')
             for rel in doc.part.rels.values() if not rel.is_external and
             rel.reltype.rsplit('/', 1)[-1] in ('header', 'footer'))]
    for part, label in parts:
        root = part.element
        missing = {value for el in root.iter() for attr, value in el.attrib.items()
                   if attr.startswith(f'{{{_REL_NS}}}') and value not in part.rels}
        if missing:
            issues.append(f'{label}有 {len(missing)} 处图片、链接或其他附件引用缺失')
        for index, table in enumerate(root.iter(qn('w:tbl')), 1):
            previous = set()
            for row in table.tr_lst:
                spans = set()
                column = row.grid_before
                for cell in row.tc_lst:
                    span = (column, cell.grid_span)
                    if cell.vMerge == 'continue' and span not in previous:
                        name = ''.join(table.tr_lst[0].xpath('.//w:t/text()')).strip()
                        issues.append(f'{label}第 {index} 个表格（{name[:38] or "无表头"}）的纵向合并不连续')
                        break
                    if cell.vMerge is not None:
                        spans.add(span)
                    column += cell.grid_span
                else:
                    previous = spans
                    continue
                break
    return list(dict.fromkeys(issues))


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


def _trim_empty_terminal_section(doc) -> int:
    """仅合并没有任何正文、页形相同的最后空分节；保留签章段落及其留白。"""
    body = list(doc.element.body)
    if not body or body[-1].tag != qn('w:sectPr'):
        return 0
    carrier = next((i for i in range(len(body) - 2, -1, -1)
                    if body[i].tag == qn('w:p') and body[i].xpath('./w:pPr/w:sectPr')), None)
    if carrier is None:
        return 0
    for element in body[carrier + 1:-1]:
        if (element.tag != qn('w:p') or ''.join(element.itertext()).strip()
                or element.xpath('.//w:drawing | .//w:pict | .//w:fldChar | .//w:fldSimple | .//w:sdt | .//w:br')):
            return 0
    previous = body[carrier].xpath('./w:pPr/w:sectPr')[0]
    final = body[-1]
    for tag in ('pgSz', 'pgMar', 'cols'):
        left, right = previous.find(qn('w:' + tag)), final.find(qn('w:' + tag))
        if (dict(left.attrib) if left is not None else {}) != (dict(right.attrib) if right is not None else {}):
            return 0
    kind = final.find(qn('w:type'))
    if kind is not None and kind.get(qn('w:val')) in ('continuous', 'oddPage', 'evenPage'):
        return 0
    if kind is None:
        kind = OxmlElement('w:type')
        final.append(kind)
    kind.set(qn('w:val'), 'continuous')
    for element in body[carrier + 1:-1]:
        element.getparent().remove(element)
    paragraph = Paragraph(body[carrier], doc._body)
    if not paragraph.text.strip() and not body[carrier].xpath('.//w:drawing | .//w:pict'):
        paragraph.paragraph_format.line_spacing = Pt(1)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.keep_with_next = False
    return 1


def fit_tables(path: str, *, preserve_source: bool = False) -> int:
    doc = Document(path)
    removed_spacers = _trim_evidence_spacers(doc)
    removed_sections = _trim_empty_terminal_section(doc)
    adjusted = 0
    repaired = 0
    for table in doc.tables:
        grid = table._tbl.find(qn('w:tblGrid'))
        if grid is None or not grid.gridCol_lst:
            if not ensure_table_grid(table._tbl):
                continue
            repaired += 1
        if preserve_source:
            continue
        section = doc.sections[-1]
        node = table._tbl.getnext()
        while node is not None:
            sections = list(node.iter(qn('w:sectPr')))
            if sections:
                section = Section(sections[0], doc.part)
                break
            node = node.getnext()
        properties = table._tbl.find(qn('w:tblPr'))
        if properties is None or None in (section.page_width, section.left_margin, section.right_margin):
            continue
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
    if adjusted or repaired or removed_spacers or removed_sections:
        doc.save(path)
    return adjusted
