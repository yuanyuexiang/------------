"""只读成品对标：结构、图片原件与视图、待补充及所在节的图幅边界。

差异是复核线索，不据此判定人员、业绩或法律事实正确，也不以页数接近作为合格条件。
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from docx import Document
from docx.oxml.ns import qn
from docx.section import Section

from .placeholders import scan_docx


def _title(text: str) -> str:
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'^(?:[（(][一二三四五六七八九十]+[）)]|\d+(?:\.\d+)*[.．、]?)', '', text)
    text = re.split(r'[（(](?:可在|上传|如有|格式|若资格)', text)[0]
    return text.rstrip('：:')


def inspect(path: str) -> dict:
    doc = Document(path)
    # 节属性位于该节末尾，从后向前关联，不能全篇沿用最后一节的页边距。
    section = doc.sections[-1]
    sections = {}
    for element in reversed(list(doc.element.body)):
        properties = list(element.iter(qn('w:sectPr')))
        if properties:
            section = Section(properties[0], doc.part)
        sections[element] = section
    views = Counter()
    overflow = []
    occurrence = 0
    for element in doc.element.body:
        section = sections[element]
        width = section.page_width - section.left_margin - section.right_margin
        height = section.page_height - section.top_margin - section.bottom_margin
        for inline in element.iter(qn('wp:inline')):
            occurrence += 1
            extent = inline.find(qn('wp:extent'))
            effects = inline.find(qn('wp:effectExtent'))
            extra = {key: max(0, int(effects.get(key, '0'))) if effects is not None else 0
                     for key in ('l', 'r', 't', 'b')}
            if extent is not None and (
                int(extent.get('cx')) + extra['l'] + extra['r'] > width + 635
                or int(extent.get('cy')) + extra['t'] + extra['b'] > height + 635
            ):
                overflow.append(occurrence)
        for blip in element.iter(qn('a:blip')):
            rid = blip.get(qn('r:embed'))
            if not rid:
                continue
            digest = hashlib.sha256(doc.part.related_parts[rid].blob).hexdigest()
            picture = blip.getparent().getparent()
            crop = picture.find('.//' + qn('a:srcRect'))
            transform = picture.find('.//' + qn('a:xfrm'))
            settings = tuple((key, crop.get(key, '0') if crop is not None else '0')
                             for key in ('l', 't', 'r', 'b'))
            settings += tuple((key, transform.get(key, '0') if transform is not None else '0')
                              for key in ('rot', 'flipH', 'flipV'))
            views[(digest, settings)] += 1
    headings = [p.text.strip() for p in doc.paragraphs
                if re.fullmatch(r'Heading [1-4]', p.style.name) and p.text.strip()]
    image_tables = sum(bool(t._tbl.xpath('.//w:drawing | .//w:pict'))
                       and not any(c.text.strip() for row in t.rows for c in row.cells)
                       for t in doc.tables)
    return {
        'headings': headings, 'tables': len(doc.tables),
        'business_tables': len(doc.tables) - image_tables,
        'image_occurrences': sum(views.values()), 'overwide_or_overheight_images': overflow,
        'pending': scan_docx(path), '_views': views,
    }


def compare(reference: str, candidate: str) -> dict:
    standard, output = inspect(reference), inspect(candidate)
    wanted, actual = standard.pop('_views'), output.pop('_views')
    titles = {_title(t) for t in output['headings']}
    return {
        'reference': standard, 'candidate': output,
        'missing_reference_headings': [t for t in standard['headings'] if _title(t) not in titles],
        'missing_image_views': sum((wanted - actual).values()),
        'additional_image_views': sum((actual - wanted).values()),
        'limits': '结构与图片差异仅供复核；不判断事实正确性，不替代渲染及逐页检查。',
    }
