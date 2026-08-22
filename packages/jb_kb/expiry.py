"""有效期预警：证照 / 检测报告按 valid_until 推算剩余天数，分 30/60/90 天档与已过期。

- 空 valid_until 不猜、不告警，单独列为"未录入"（人工补录的提醒）。
- `on_date` 传开标日即可得到"开标当日是否仍有效"（资格自检同一口径）。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel

from .models import CompanyProfile

LEVELS = (30, 60, 90)


class ExpiryItem(BaseModel):
    kind: str            # certificates | test_reports
    id: str = ""
    name: str = ""
    number: str = ""
    valid_until: str = ""
    days_left: Optional[int] = None   # None=未录入
    level: str = ""                   # expired | d30 | d60 | d90 | ok | unknown


def _parse(d: str) -> Optional[dt.date]:
    d = (d or "").strip().replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y年%m月%d日"):
        try:
            return dt.datetime.strptime(d, fmt).date()
        except ValueError:
            continue
    return None


def classify(days_left: Optional[int]) -> str:
    if days_left is None:
        return "unknown"
    if days_left < 0:
        return "expired"
    for lv in LEVELS:
        if days_left <= lv:
            return f"d{lv}"
    return "ok"


def expiry_report(profile: CompanyProfile, on_date: Optional[dt.date] = None,
                  within_days: int = 90) -> list[ExpiryItem]:
    """返回需要关注的条目：已过期、within_days 内到期、未录入有效期。按剩余天数升序。"""
    today = on_date or dt.date.today()
    out: list[ExpiryItem] = []
    for kind, items in (("certificates", profile.certificates), ("test_reports", profile.test_reports)):
        for it in items:
            until = _parse(it.valid_until)
            days = (until - today).days if until else None
            level = classify(days)
            if level == "ok" and days is not None and days > within_days:
                continue
            out.append(ExpiryItem(kind=kind, id=it.id, name=it.name, number=it.number,
                                  valid_until=it.valid_until, days_left=days, level=level))
    order = {"expired": 0, "d30": 1, "d60": 2, "d90": 3, "ok": 4, "unknown": 5}
    out.sort(key=lambda x: (order[x.level], x.days_left if x.days_left is not None else 10**6))
    return out
