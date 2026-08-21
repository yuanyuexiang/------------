"""数值比较引擎：判断产品参数值是否满足技术规范要求值。

要求值形态（国网标准技术参数表实测）：
  "≥400kVA" / "不小于128GB" / "≤0.21" / "不大于 5%" / "≥2.6GHz" / "100~240V" / "4*1920GB" / "=13%"
纯描述性要求（"支持SDN协议…"）无法数值比较，返回 kind="text" 交由人工/LLM 判断。

原则：比不出来就说比不出来（verdict="unknown"），绝不默认满足。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_GE_WORDS = ("不小于", "不低于", "不少于", "至少", "大于等于", "≥", ">=", "以上")
_LE_WORDS = ("不大于", "不高于", "不超过", "不多于", "小于等于", "≤", "<=", "以内", "以下")
_GT_WORDS = ("大于", ">")
_LT_WORDS = ("小于", "<")

# 单位归一：同一物理量换算到基准单位
_UNIT_SCALE = {
    # 容量/存储
    "kb": ("b", 1e3), "mb": ("b", 1e6), "gb": ("b", 1e9), "tb": ("b", 1e12), "pb": ("b", 1e15),
    # 功率/视在功率
    "w": ("w", 1), "kw": ("w", 1e3), "mw": ("w", 1e6), "va": ("va", 1), "kva": ("va", 1e3), "mva": ("va", 1e6),
    # 频率
    "hz": ("hz", 1), "khz": ("hz", 1e3), "mhz": ("hz", 1e6), "ghz": ("hz", 1e9),
    # 电压/电流
    "v": ("v", 1), "kv": ("v", 1e3), "mv": ("v", 1e-3), "a": ("a", 1), "ka": ("a", 1e3), "ma": ("a", 1e-3),
    # 长度
    "mm": ("m", 1e-3), "cm": ("m", 1e-2), "m": ("m", 1), "km": ("m", 1e3),
    # 时间
    "ms": ("s", 1e-3), "s": ("s", 1), "min": ("s", 60), "h": ("s", 3600),
    # 速率
    "kbps": ("bps", 1e3), "mbps": ("bps", 1e6), "gbps": ("bps", 1e9),
    # 其他常见
    "%": ("%", 1), "℃": ("℃", 1), "db": ("db", 1), "dbm": ("dbm", 1), "kg": ("kg", 1), "g": ("kg", 1e-3),
    "core": ("core", 1), "核": ("core", 1),
    # 计数单位互通（个/套/台/路/口），视为无量纲
    "个": ("", 1), "套": ("", 1), "台": ("", 1), "路": ("", 1), "口": ("", 1), "项": ("", 1), "份": ("", 1),
}

_NUM = r"(-?\d+(?:\.\d+)?)"
_UNIT = r"([a-zA-Z%℃]{1,5}|[个套台路口核项份]|)"
_RANGE_PAT = re.compile(_NUM + r"\s*[~～\-—至]\s*" + _NUM + r"\s*" + _UNIT)
_MULT_PAT = re.compile(r"(\d+)\s*[\*×x]\s*" + _NUM + r"\s*" + _UNIT)
_NUM_UNIT_PAT = re.compile(_NUM + r"\s*" + _UNIT)


@dataclass
class Quantity:
    value: float
    unit: str           # 归一后基准单位（空串=无量纲）
    raw_unit: str = ""
    count: int = 1      # "4*1920GB" 的 4


@dataclass
class Requirement:
    kind: str                       # ge | le | gt | lt | eq | range | text
    low: Optional[Quantity] = None
    high: Optional[Quantity] = None
    raw: str = ""
    assumed_min: bool = False       # 裸数值按"不低于"假设，需人工确认方向


@dataclass
class Verdict:
    verdict: str                    # satisfied | deviation | unknown
    reason: str = ""
    requirement: Optional[Requirement] = None
    actual: Optional[Quantity] = None


def _norm_unit(u: str) -> tuple[str, float]:
    key = u.strip().lower()
    if key in _UNIT_SCALE:
        return _UNIT_SCALE[key]
    if u.strip() in _UNIT_SCALE:
        return _UNIT_SCALE[u.strip()]
    return (key, 1.0)


def parse_quantity(text: str) -> Optional[Quantity]:
    """从文本取第一个数值+单位；支持 "4*1920GB"（count=4）。"""
    text = text.replace("，", ",").strip()
    m = _MULT_PAT.search(text)
    if m:
        base, scale = _norm_unit(m.group(3))
        return Quantity(value=float(m.group(2)) * scale, unit=base, raw_unit=m.group(3), count=int(m.group(1)))
    m = _NUM_UNIT_PAT.search(text)
    if not m:
        return None
    base, scale = _norm_unit(m.group(2))
    return Quantity(value=float(m.group(1)) * scale, unit=base, raw_unit=m.group(2))


def parse_requirement(text: str) -> Requirement:
    t = text.replace("★", "").replace("▲", "").strip()
    m = _RANGE_PAT.search(t)
    if m and not any(w in t for w in _GE_WORDS + _LE_WORDS):
        base, scale = _norm_unit(m.group(3))
        return Requirement(kind="range", raw=text,
                           low=Quantity(float(m.group(1)) * scale, base, m.group(3)),
                           high=Quantity(float(m.group(2)) * scale, base, m.group(3)))
    q = parse_quantity(t)
    if q is None:
        return Requirement(kind="text", raw=text)
    if any(w in t for w in _GE_WORDS):
        return Requirement(kind="ge", low=q, raw=text)
    if any(w in t for w in _LE_WORDS):
        return Requirement(kind="le", high=q, raw=text)
    if any(w in t for w in _GT_WORDS):
        return Requirement(kind="gt", low=q, raw=text)
    if any(w in t for w in _LT_WORDS):
        return Requirement(kind="lt", high=q, raw=text)
    # 裸数值（配置行如 "4*1920GB SSD"）：国网口径为最低配置，按"不低于"处理，并在 assumed_min 标注
    return Requirement(kind="ge", low=q, raw=text, assumed_min=True)


def compare(requirement: str, actual: str) -> Verdict:
    """产品实际值 actual 是否满足要求 requirement。"""
    req = parse_requirement(requirement)
    if req.kind == "text":
        return Verdict("unknown", "描述性要求，需人工/LLM 判断", req)
    act = parse_quantity(actual)
    if act is None:
        return Verdict("unknown", "产品值无法解析为数值", req)
    ref = req.low or req.high
    if ref and ref.unit and act.unit and ref.unit != act.unit:
        return Verdict("unknown", f"单位不可比（要求 {ref.raw_unit or ref.unit}，实际 {act.raw_unit or act.unit}）", req, act)
    if ref and ref.count != act.count and req.kind != "range":
        if act.count < ref.count:
            return Verdict("deviation", f"数量 {act.count} < 要求 {ref.count}", req, act)
    v = act.value
    ok, why = True, ""
    if req.kind == "ge":
        ok, why = v >= req.low.value, f"{v:g} ≥ {req.low.value:g}"
    elif req.kind == "gt":
        ok, why = v > req.low.value, f"{v:g} > {req.low.value:g}"
    elif req.kind == "le":
        ok, why = v <= req.high.value, f"{v:g} ≤ {req.high.value:g}"
    elif req.kind == "lt":
        ok, why = v < req.high.value, f"{v:g} < {req.high.value:g}"
    elif req.kind == "range":
        ok, why = req.low.value <= v <= req.high.value, f"{req.low.value:g} ≤ {v:g} ≤ {req.high.value:g}"
    elif req.kind == "eq":
        ok, why = abs(v - req.low.value) < 1e-9, f"{v:g} = {req.low.value:g}"
    note = "（裸数值按不低于处理，方向请确认）" if req.assumed_min else ""
    return Verdict("satisfied" if ok else "deviation", ("满足：" if ok else "不满足：") + why + note, req, act)
