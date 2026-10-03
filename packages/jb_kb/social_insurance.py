"""拟投入人员社保连续性：以投标截止/开标时间为基准，往前数 N 个月（默认 3）每月都要有本单位社保记录。

客户流程（纪要 2026-09-10）："以投标截止时间为基准（如 9 月 10 日），自动核查往前推 3 个月（7、8、9 月）的社保证明"。
月份记录在 Person.social_insurance_months（YYYY-MM），证明扫描件走 attachments；缴纳单位须与投标人一致。
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Person

_YM = re.compile(r"(\d{4})\D?(\d{1,2})")


def _norm_month(text: str) -> Optional[str]:
    m = _YM.search(text or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"


def required_months(deadline: str, n: int = 3) -> list[str]:
    """截止月及其前 n-1 个月（升序）。deadline 形如 'YYYY-MM-DD HH:MM'；解析不出返回 []。"""
    base = _norm_month(deadline)
    if not base or n <= 0:
        return []
    y, m = int(base[:4]), int(base[5:])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)


def missing_months(person: Person, deadline: str, n: int = 3) -> list[str]:
    have = {_norm_month(x) for x in person.social_insurance_months}
    return [m for m in required_months(deadline, n) if m not in have]


def unit_mismatch(person: Person, company: str) -> bool:
    """缴纳单位已录入且与投标人不一致（忽略空白与括号差异）。"""
    def _n(s: str) -> str:
        return re.sub(r"[\s（）()]", "", s or "")
    return bool(person.social_insurance_unit) and _n(person.social_insurance_unit) != _n(company)
