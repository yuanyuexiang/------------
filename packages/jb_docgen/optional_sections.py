"""依据明确的本包适用性保留章节、移除不适用的空白格式正文。"""
from __future__ import annotations

import re

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from . import master as M


def apply_optional_sections(doc, ctx) -> None:
    decisions = dict(ctx.profile.bid_context.get('section_applicability', {}))
    if ctx.pkg.allow_consortium is False:
        decisions['联合体协议书'] = {
            'applicable': False, 'reason': '不适用（本包不接受联合体响应）',
        }
    for topic in ('联合体协议书', '财务信息审核结果凭证单', '公章对投标专用章授权书'):
        decision = decisions.get(topic, {})
        if decision.get('applicable') is not False:
            continue
        heading = next((p for p in doc.paragraphs if topic in p.text
                        and re.match(r'^\d+[.．、]', p.text.strip())), None)
        if heading is None:
            continue
        number = int(re.match(r'^(\d+)', heading.text.strip())[1])
        node = heading._p.getnext()
        while node is not None and node.tag != qn('w:sectPr'):
            if node.tag == qn('w:p'):
                paragraph = Paragraph(node, doc._body)
                text = paragraph.text.strip()
                match = re.match(r'^(\d+)[.．、]', text)
                if (match and int(match[1]) > number or
                        paragraph.style.name in ('Heading 1', 'Heading 2') or
                        re.match(r'^（[一二三四五六七八九十]+）', text)):
                    break
            following = node.getnext()
            node.getparent().remove(node)
            node = following
        M.insert_paragraph_after(doc, heading._p, decision.get('reason') or '无')
