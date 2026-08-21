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
