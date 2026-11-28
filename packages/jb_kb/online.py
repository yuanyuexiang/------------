"""Licensed company lookups. Match the legal entity before searching associated records."""
from __future__ import annotations

import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from .models import EvidenceOrigin

GSXT = "https://www.gsxt.gov.cn/"
CREDIT_CHINA = "https://www.creditchina.gov.cn/"
ECP = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/"
CNCA = "https://cx.cnca.cn/"
NEA = "https://zzxy.nea.gov.cn/#/gateway/inquiryPublic"
PROCUREMENT = "https://data.ggzy.gov.cn/"
OFFICIAL_SOURCES = [
    {"title": "国家企业信用信息公示系统", "url": GSXT, "kind": "登记与信用"},
    {"title": "信用中国", "url": CREDIT_CHINA, "kind": "信用报告"},
    {"title": "全国认证认可信息公共服务平台", "url": CNCA, "kind": "证书状态"},
    {"title": "国家能源局资质和信用信息系统", "url": NEA, "kind": "电力设施许可证"},
    {"title": "全国公共资源交易平台", "url": PROCUREMENT, "kind": "中标公告"},
    {"title": "国家电网电子商务平台", "url": ECP, "kind": "国网公告与供应商资料"},
]

_QCC_BASE = "https://api.qichacha.com/"
_CODE_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_CODE_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)


class SourceUnavailable(Exception):
    pass


def credit_code(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 18 or any(char not in _CODE_ALPHABET for char in code):
        raise ValueError("请输入有效的18位统一社会信用代码")
    total = sum(_CODE_ALPHABET.index(char) * weight
                for char, weight in zip(code, _CODE_WEIGHTS))
    if code[-1] != _CODE_ALPHABET[(-total) % len(_CODE_ALPHABET)]:
        raise ValueError("统一社会信用代码校验位不正确")
    return code


def clean(value, limit: int = 5000) -> str:
    if isinstance(value, str):
        return value.strip()[:limit]
    return ""


def exact_date(value) -> str:
    match = re.fullmatch(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?(?:[ T]00:00:00)?", clean(value))
    if match:
        try:
            return date(*(int(x) for x in match.groups())).isoformat()
        except ValueError:
            pass
    return ""


def yuan_to_wan(value, unit: str):
    raw = str(value).replace(",", "").replace("，", "").strip()
    if unit not in ("元", "万元", "亿元") or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,8})?", raw):
        return None
    return float(Decimal(raw) * {"元": Decimal("0.0001"), "万元": 1, "亿元": 10000}[unit])


def amount_in_rmb(value):
    match = re.fullmatch(r"(?:人民币\s*)?(-?[\d,，.]+)\s*(亿元|万元|元)(?:人民币)?", clean(value))
    return yuan_to_wan(*match.groups()) if match else None


def number_as_text(value) -> str:
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else clean(value)


def safe_link(value) -> str:
    raw = clean(value, 4096)
    try:
        parsed = urlsplit(raw)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password:
            return raw
    except ValueError:
        pass
    return ""


def _rows(result):
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if isinstance(result, dict) and isinstance(result.get("Data"), list):
        return _rows(result["Data"])
    if isinstance(result, dict) and result.get("VerifyResult") in (0, "0"):
        return []
    raise SourceUnavailable("数据源返回格式无法核验")


def _origin(label, number, excerpt="", url=""):
    return EvidenceOrigin(kind="online", title=f"企查查 · {label}",
                          url=url or f"https://openapi.qcc.com/dataApi/{number}",
                          excerpt=excerpt, fetched_at=datetime.now(timezone.utc).isoformat())


def _status(title, label, detail=""):
    return {"title": title, "status": label, "detail": detail}


def _registry(item, code):
    if not isinstance(item, dict) or clean(item.get("CreditCode")).upper() != code:
        raise SourceUnavailable("返回的主体信用代码与查询条件不一致")
    name = clean(item.get("Name"))
    if not name or len(name) > 128:
        raise SourceUnavailable("无法确认企业全称")
    values = {key: clean(item.get(source)) for key, source in (
        ("legal_person", "OperName"), ("address", "Address"), ("business_scope", "Scope"),
    )}
    values.update(name=name, credit_code=code, founded=exact_date(item.get("StartDate")))
    currency = clean(item.get("RegisteredCapitalCCY"))
    unit = clean(item.get("RegisteredCapitalUnit"))
    amount = number_as_text(item.get("RegisteredCapital"))
    if currency in ("人民币", "CNY", "RMB"):
        capital = yuan_to_wan(amount, unit)
        if capital is not None and capital >= 0:
            values["registered_capital_wan"] = capital
    extra = {label: value for label, value in (
        ("登记类型", clean(item.get("EconKind"))), ("登记机关", clean(item.get("BelongOrg"))),
        ("登记状态", clean(item.get("Status"))), ("注册资本原文", " ".join(x for x in (amount, unit, currency) if x)),
    ) if value}
    return {k: v for k, v in values.items() if v != ""}, extra


def _certificate(row):
    number, name = clean(row.get("No"), 255), clean(row.get("Name"), 255)
    if not number or not name:
        return None
    issuers = row.get("InstitutionList")
    issuer = "、".join(x for value in issuers if (x := clean(value, 160)))[:250] if isinstance(issuers, list) else ""
    status = clean(row.get("Status"), 120)
    return {
        "kind": "certificates", "title": name, "data": {
            "name": name, "number": number, "issuer": issuer,
            "cert_type": clean(row.get("TypeDesc"), 120),
            "valid_from": exact_date(row.get("StartDate")), "valid_until": exact_date(row.get("EndDate")),
        },
        "origin": _origin("资质证书", 255, " · ".join(x for x in (number, status) if x)),
    }


def _award(row, code):
    winners = _rows(row.get("WinBidUnitList") or [])
    winner = next((entry for entry in winners if clean(entry.get("CreditCode")).upper() == code), None)
    title, public_url = clean(row.get("Title"), 255), safe_link(row.get("ContentUrl"))
    title_filter = clean(row.get("Title")) + " " + clean(row.get("BidProgressList"))
    if winner is None or not title or not public_url or re.search(r"候选人|废标|终止", title_filter):
        return None
    buyers = _rows(row.get("BidInviUnitList") or [])
    amount = amount_in_rmb(winner.get("WinBidAmt")) if len(winners) == 1 else None
    return {
        "kind": "performances", "title": title,
        "data": {"project": title, "buyer": clean(buyers[0].get("Name"), 255) if len(buyers) == 1 else "",
                 "award_date": exact_date(row.get("PublishDate")), "award_amount_wan": amount,
                 "award_project_no": clean(row.get("ProjectNo"), 200)},
        "origin": _origin("中标公告", 958, clean(winner.get("WinBidAmt"), 120), public_url),
    }


def _lookup(client, key, secret, path, **params):
    timestamp = str(int(time.time()))
    token = hashlib.md5((key + timestamp + secret).encode(), usedforsecurity=False).hexdigest().upper()
    try:
        with client.stream("GET", _QCC_BASE + path, params={"key": key, **params},
                           headers={"Token": token, "Timespan": timestamp}) as response:
            if response.status_code != 200:
                raise SourceUnavailable("数据源暂不可用")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 2_000_000:
                    raise SourceUnavailable("数据源响应超出处理上限")
        import json
        payload = json.loads(raw)
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceUnavailable("数据源暂不可用") from exc
    if not isinstance(payload, dict) or str(payload.get("Status")) != "200":
        raise SourceUnavailable("数据源未返回有效结果，请核实接口授权和用量")
    return payload.get("Result")


def lookup_company(code: str, known_name: str = "") -> dict:
    code = credit_code(code)
    key, secret = os.getenv("JB_QCC_KEY", "").strip(), os.getenv("JB_QCC_SECRET", "").strip()
    if not key or not secret:
        return {"fields": {}, "extra": {}, "records": [],
                "checks": [_status("企业数据接口", "未配置", "可从官方入口获取原件后导入")]}

    with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
        def get(path, **params):
            return _lookup(client, key, secret, path, **params)

        try:
            fields, extra = _registry(get("ECIV4/GetBasicDetailsByName", keyword=code), code)
        except SourceUnavailable as exc:
            return {"fields": {}, "extra": {}, "records": [],
                    "checks": [_status("工商登记", "无法查询", str(exc))]}
        checks = [_status("工商登记", "已匹配")]
        records = []
        # Certificate lookup is name-based. A renamed local record is resolved by the registry first.
        name = fields["name"]
        requests = [
            ("证照", "ECICertification/SearchCertification", {"searchKey": name, "pageSize": 20}),
            ("中标公告", "TenderCheck/GetList", {"keyword": name, "msgType": "4", "pageSize": 20}),
            ("经营异常", "ExceptionCheck/GetList", {"searchKey": code}),
            ("严重违法", "SeriousIllegalCheck/GetList", {"searchKey": code}),
        ]
        if known_name and known_name != name:
            checks.append(_status("企业名称", "待核对", "登记全称与企业档案不同，请核对更名与主体"))
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [(title, executor.submit(get, path, **params)) for title, path, params in requests]
            for title, future in futures:
                try:
                    data = future.result()
                    rows = _rows(data)
                    if title in ("经营异常", "严重违法"):
                        if rows:
                            checks.append(_status(title, "查到记录", f"返回 {len(rows)} 条，请核对列入及移出状态"))
                        elif isinstance(data, dict) and str(data.get("VerifyResult")) == "0":
                            checks.append(_status(title, "指定来源未检出"))
                        else:
                            checks.append(_status(title, "无法查询", "未收到可核验的查询结论"))
                        continue
                    matched = [_certificate(row) if title == "证照" else _award(row, code) for row in rows[:20]]
                    valid = [value for value in matched if value is not None]
                    # A certificate search can only be tied to the registry name; keep drafts for review.
                    records.extend(valid)
                    scope = "首批最多20条" if title == "证照" else "近两年首批最多20条，按中标方信用代码匹配"
                    checks.append(_status(title, "查询完成", f"{scope}，得到 {len(valid)} 项可核对记录"))
                except SourceUnavailable as exc:
                    checks.append(_status(title, "无法查询", str(exc)))
    return {"fields": fields, "extra": extra, "records": records, "checks": checks}
