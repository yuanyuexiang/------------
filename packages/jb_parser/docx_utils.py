"""docx 通用读取：章节切分与表格结构化。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import docx

CHAPTER_PAT = re.compile(r"^第([一二三四五六七八九十]+)章\s*(.*)$")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class Chapter:
    no: int
    title: str
    start: int  # 段落下标（含）
    end: int    # 段落下标（不含）


def load(path: str) -> "docx.document.Document":
    return docx.Document(path)


def split_chapters(doc) -> List[Chapter]:
    """按"第N章"标记切分正文。目录区的章名行（连续出现在文首）会被跳过：
    取每个章号最后一次出现的位置作为正文起点。"""
    hits: Dict[int, List[int]] = {}
    titles: Dict[int, str] = {}
    for i, p in enumerate(doc.paragraphs):
        m = CHAPTER_PAT.match(p.text.strip())
        if not m:
            continue
        no = _CN_NUM.get(m.group(1))
        if not no:
            continue
        hits.setdefault(no, []).append(i)
        titles[no] = m.group(2).strip() or titles.get(no, "")
    starts = sorted((idxs[-1], no) for no, idxs in hits.items())
    chapters: List[Chapter] = []
    for k, (start, no) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(doc.paragraphs)
        chapters.append(Chapter(no=no, title=titles.get(no, ""), start=start, end=end))
    return chapters


def table_rows(table) -> List[List[str]]:
    """表格→二维文本；同一行内被合并单元格产生的重复值去重（保序）。"""
    rows: List[List[str]] = []
    for r in table.rows:
        cells = [c.text.strip() for c in r.cells]
        dedup: List[str] = []
        for c in cells:
            if not dedup or dedup[-1] != c:
                dedup.append(c)
        rows.append(dedup)
    return rows


def find_table(doc, header_keywords: List[str], min_hits: int = 2) -> Optional[List[List[str]]]:
    """按表头关键词定位表格（检查前两行），返回结构化行。"""
    for t in doc.tables:
        if not t.rows:
            continue
        head = " ".join(c.text.strip() for r in t.rows[:2] for c in r.cells)
        hits = sum(1 for k in header_keywords if k in head)
        if hits >= min_hits:
            return table_rows(t)
    return None


def find_tables(doc, header_keywords: List[str], min_hits: int = 2) -> List[List[List[str]]]:
    out = []
    for t in doc.tables:
        if not t.rows:
            continue
        head = " ".join(c.text.strip() for r in t.rows[:2] for c in r.cells)
        if sum(1 for k in header_keywords if k in head) >= min_hits:
            out.append(table_rows(t))
    return out
