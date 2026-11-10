"""字体声明与转换器字体清单核对；不替换采购文件字体，也不宣称完成视觉验收。"""
from __future__ import annotations

import hashlib
import json
from zipfile import ZipFile

from lxml import etree

_ALIASES = [('宋体', 'simsun'), ('黑体', 'simhei'), ('仿宋', 'fangsong'),
            ('仿宋_gb2312', 'fangsong_gb2312'), ('楷体', 'kaiti')]


def report(path: str, installed: list[str]) -> dict:
    """声明包括 styles.xml 的备用样式；缺失项是排查线索，不等于正文确实用了该字体。"""
    fonts = set()
    parser = etree.XMLParser(resolve_entities=False)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    theme = False
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith('word/') or not name.endswith('.xml'):
                continue
            root = etree.fromstring(archive.read(name), parser)
            for font in root.xpath('//w:rFonts', namespaces=ns):
                for key in ('ascii', 'eastAsia', 'hAnsi', 'cs'):
                    value = font.get('{' + ns['w'] + '}' + key)
                    if value:
                        fonts.add(value)
                theme = theme or any('Theme' in key for key in font.attrib)
    available = {name.strip().casefold() for name in installed if name.strip()}
    for aliases in _ALIASES:
        if available.intersection(aliases):
            available.update(aliases)
    return {'declared_fonts': sorted(fonts),
            'missing_declared_fonts': sorted(f for f in fonts if f.casefold() not in available),
            'theme_fonts_present': theme,
            'font_inventory_hash': hashlib.sha256(json.dumps(sorted(installed), ensure_ascii=False).encode()).hexdigest(),
            'note': '包含未使用的备用样式声明；主题字体、嵌入字形和 WPS 替代效果仍需实际排版核对。'}
