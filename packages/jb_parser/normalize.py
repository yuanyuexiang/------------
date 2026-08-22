"""前附表语义归一：从投标人须知前附表条款中抽取结构化关键条件（KeyTerms）。

原则：正则可确定的直接抽；抽不到的留 None 并保留原文引用，后续 LLM 兜底或
人工在确认页补。绝不猜测。
"""
from __future__ import annotations

import re
from typing import Optional

from .trm import KeyTerms, PrenoticeClause

_VALIDITY_PAT = re.compile(r"自\S*截止\S*起\s*(\d+)\s*(?:日|天)")
_DATE_PAT = re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日[\d:：时分\s]*)")
# 招标公告 5.1：投标文件提交的截止时间（投标截止时间，下同）为2026年8月7日14:00时（北京时间）
#   变体（四样本实测）："…截止时间…为…" / "…截止时间…：…"；"上午8:00" / "09:30时" / "8:00时"；竞谈为"首次应答截止时间"
_DEADLINE_PAT = re.compile(
    r"(?:投标|应答)文件提交的截止时间[^\n。]{0,40}?(\d{4})年(\d{1,2})月(\d{1,2})日\s*(上午|下午)?\s*(\d{1,2})[:：](\d{2})")
_OPEN_SAME_PAT = re.compile(r"开标时间[:：]?\s*同(?:投标|应答)截止时间")
_OPEN_PAT = re.compile(r"开标时间[:：]?\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*(上午|下午)?\s*(\d{1,2})[:：](\d{2})")


def _iso(y: str, mo: str, d: str, ampm: Optional[str], h: str, mi: str) -> str:
    hour = int(h)
    if ampm == "下午" and hour < 12:
        hour += 12
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d} {hour:02d}:{int(mi):02d}"


def extract_announcement_terms(text: str, kt: KeyTerms) -> None:
    """从招标公告正文抽投标截止/开标时间，写入 kt（已存在的值不覆盖；抽不到留 None）。"""
    if kt.bid_deadline is None:
        m = _DEADLINE_PAT.search(text)
        if m:
            kt.bid_deadline = _iso(*m.groups())
            kt.bid_deadline_text = m.group(0).strip()[:160]
    if kt.bid_open_time is None:
        if _OPEN_SAME_PAT.search(text):
            kt.bid_open_time, kt.bid_open_note = kt.bid_deadline, "同投标截止时间"
        else:
            m = _OPEN_PAT.search(text)
            if m:
                kt.bid_open_time = _iso(*m.groups())
                kt.bid_open_note = m.group(0).strip()[:160]


def _find(clauses: list[PrenoticeClause], *keywords: str) -> Optional[PrenoticeClause]:
    for c in clauses:
        text = c.name + c.content
        if all(k in text for k in keywords):
            return c
    return None


def extract_key_terms(clauses: list[PrenoticeClause]) -> KeyTerms:
    kt = KeyTerms()

    c = _find(clauses, "投标有效期") or _find(clauses, "应答有效期")
    if c:
        kt.validity_clause = c.clause_no
        m = _VALIDITY_PAT.search(c.content)
        if m:
            kt.validity_days = int(m.group(1))

    c = _find(clauses, "保证金")
    if c:
        kt.deposit_clause = c.clause_no
        content = c.content
        if "不要求" in content or "不收取" in content:
            kt.deposit_mode = "none"
        elif "诚信担保" in content or "信用承诺" in content:
            kt.deposit_mode = "诚信担保"
        elif "年度" in content:
            kt.deposit_mode = "年度保证金"
        elif content:
            kt.deposit_mode = "按包保证金"

    c = _find(clauses, "盖章要求") or _find(clauses, "签字或盖章")
    if c:
        kt.sign_clause = c.clause_no
        kt.sign_whole_doc = "整体电子签章" in c.content

    for c in clauses:
        if "不接收纸质" in c.content or "不接受纸质" in c.content:
            kt.paperless = True
            break

    c = _find(clauses, "是否采用电子招标投标")
    if c:
        kt.electronic = c.content.strip().startswith("是")

    c = _find(clauses, "澄清", "招标文件") or _find(clauses, "要求澄清")
    if c:
        m = _DATE_PAT.search(c.content)
        if m:
            kt.clarify_deadline = m.group(1).strip()

    c = _find(clauses, "最高限价")
    if c:
        kt.max_price_clause = c.clause_no
        kt.max_price_note = c.content[:120]

    c = _find(clauses, "增值税")
    if c:
        kt.vat_note = c.content[:120]
    return kt
