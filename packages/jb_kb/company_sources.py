"""Official public lookup links and normalization of facts printed on originals."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

GSXT = "https://www.gsxt.gov.cn/"
CREDIT_CHINA = "https://www.creditchina.gov.cn/"
ECP = "https://ecp.sgcc.com.cn/ecp2.0/portal/#/"
CNCA = "https://cx.cnca.cn/"
NEA = "https://zzxy.nea.gov.cn/#/gateway/inquiryPublic"
PROCUREMENT = "https://data.ggzy.gov.cn/"
OFFICIAL_SOURCES = [
    {"title": "国家企业信用信息公示系统", "url": GSXT, "materials": ("registry", "credit")},
    {"title": "信用中国", "url": CREDIT_CHINA, "materials": ("credit",)},
    {"title": "全国认证认可信息公共服务平台", "url": CNCA, "materials": ("certificate",)},
    {"title": "国家能源局资质和信用信息系统", "url": NEA, "materials": ("certificate",)},
    {"title": "全国公共资源交易平台", "url": PROCUREMENT, "materials": ("award",)},
    {"title": "国家电网电子商务平台", "url": ECP, "materials": ("award", "credit")},
]

_CODE_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_CODE_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)


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
