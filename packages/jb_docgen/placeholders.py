"""【待补充】标记：事实缺失时的唯一合法输出；导出前必须清零（export 阶段阻断）。"""
from __future__ import annotations

import re

MARK = "【待补充：{}】"
MARK_PAT = re.compile(r"【待补充(?:[：:]([^】]*))?】")


def todo(what: str) -> str:
    return MARK.format(what)


def find_all(text: str) -> list[str]:
    return [value or "未说明的待补充项" for value in MARK_PAT.findall(text)]


def scan_docx(path: str) -> list[str]:
    """扫描正文、嵌套表格、文本框、页眉页脚与注释中的标记（包括跨 run 标记）。"""
    from zipfile import ZipFile

    from lxml import etree

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    found: list[str] = []
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                root = etree.fromstring(archive.read(name), etree.XMLParser(resolve_entities=False))
                for p in root.xpath("//w:p", namespaces=ns):
                    found += find_all("".join(p.xpath(".//w:t/text()", namespaces=ns)))
    return found
