"""技术参数响应表自动填写：规范书每行 → 产品库取具体值 → 数值比较 → 保证值 / 偏差。

铁律（典型案例库 11(2)）：保证值必须是具体数值/实质内容，禁止"响应/完全响应/满足要求/按招标文件执行"。
找不到产品参数 → 【待补充】并进偏差待确认列表，不编造。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from jb_kb.models import Product
from jb_parser.trm import SpecDoc, SpecParamRow

from .numeric import compare, parse_requirement
from .placeholders import todo

FORBIDDEN = ("完全响应", "满足要求", "按招标文件执行", "按招标文件要求执行", "响应", "满足")
_TOKEN = re.compile(r"[A-Za-z]+|[一-龥]{2,}")


@dataclass
class ParamResponse:
    row: int
    name: str
    required: str
    star: bool
    response: str                   # 写入"投标人保证值"列
    verdict: str                    # satisfied | deviation | unknown | missing
    reason: str = ""
    matched_param: str = ""


@dataclass
class TechParamResult:
    spec_id: str
    responses: list[ParamResponse] = field(default_factory=list)

    @property
    def deviations(self) -> list[ParamResponse]:
        return [r for r in self.responses if r.verdict == "deviation"]

    @property
    def todos(self) -> list[ParamResponse]:
        return [r for r in self.responses if r.verdict == "missing"]

    @property
    def unknowns(self) -> list[ParamResponse]:
        return [r for r in self.responses if r.verdict == "unknown"]


_CJK = re.compile(r"[一-龥]+")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_SPLIT = re.compile(r"[，,；;]")


def _keywords(text: str) -> set[str]:
    """拉丁词 + 中文二元组（整段中文当一个词会导致匹配过粗）。"""
    kw = {t.lower() for t in _LATIN.findall(text)}
    for run in _CJK.findall(text):
        kw.update(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) <= 4:
            kw.add(run)
    return kw


def split_compound(required: str) -> list[str]:
    """复合要求行拆分："…1套，2*32Core CPU,不小于128GB内存,4*1920GB SSD,8个GE电口" → 5 项。
    仅当拆出 ≥2 个含数值的子项时才视为复合。"""
    parts = [x.strip() for x in _SPLIT.split(required.replace("★", "").replace("▲", "")) if x.strip()]
    numeric = [x for x in parts if re.search(r"\d", x)]
    return parts if len(numeric) >= 2 else [required]


def match_param_text(text: str, product: Product) -> Optional[tuple[str, str]]:
    """按文本关键词与产品 params 的 key 重叠度匹配，返回 (key, value)。"""
    kw = _keywords(text)
    best, best_score = None, 0
    for key, val in product.params.items():
        score = len(kw & _keywords(key))
        if key.lower() in text.lower():
            score += 2
        if score > best_score:
            best, best_score = (key, val), score
    return best if best_score > 0 else None


def match_param(row: SpecParamRow, product: Product) -> Optional[tuple[str, str]]:
    return match_param_text(row.name + " " + row.required, product)


def _respond_compound(row: SpecParamRow, product: Product) -> Optional[ParamResponse]:
    parts = split_compound(row.required)
    if len(parts) < 2:
        return None
    values, verdicts, reasons, keys = [], [], [], []
    for part in parts:
        if not re.search(r"\d", part) or re.search(r"\d+\s*[套台]", part):
            values.append(part)                   # 无数值/数量陈述子项（"网管主机1套"）原样保留
            continue
        hit = match_param_text(part, product)
        if hit is not None and hit[0] in keys:      # 同一参数不得响应两个不同子项（如电口/光口）
            hit = None
        if hit is None:
            values.append(todo(f"「{part}」对应值"))
            verdicts.append("missing")
            reasons.append(f"{part}: 产品库无对应参数")
            continue
        key, val = hit
        v = compare(part, val)
        values.append(f"{key} {val}")
        verdicts.append(v.verdict)
        reasons.append(f"{part}: {v.reason}")
        keys.append(key)
    if "deviation" in verdicts:
        verdict = "deviation"
    elif "missing" in verdicts:
        verdict = "missing"
    elif "unknown" in verdicts:
        verdict = "unknown"
    else:
        verdict = "satisfied"
    return ParamResponse(row.row, row.name, row.required, row.star, "；".join(values), verdict,
                         "；".join(reasons), ",".join(keys))


def fill_spec(spec: SpecDoc, product: Optional[Product]) -> TechParamResult:
    res = TechParamResult(spec_id=spec.spec_id)
    for row in spec.param_rows:
        if product is None:
            res.responses.append(ParamResponse(row.row, row.name, row.required, row.star,
                                               todo(f"{row.name} 的具体参数值"), "missing", "未选定投标产品"))
            continue
        comp = _respond_compound(row, product)
        if comp is not None:
            res.responses.append(comp)
            continue
        descriptive = parse_requirement(row.required).kind == "text"
        hit = None if descriptive else match_param(row, product)
        if hit is None:
            # 描述性功能要求：在产品 features 中找关键词覆盖
            req_kw = _keywords(row.required)
            feat = max(product.features, key=lambda f: len(_keywords(f) & req_kw), default=None)
            if feat is not None and len(_keywords(feat) & req_kw) < max(4, len(_keywords(feat)) // 2):
                feat = None
            if feat:
                res.responses.append(ParamResponse(row.row, row.name, row.required, row.star, feat, "unknown",
                                                   "功能描述由产品特性匹配，需人工确认逐项满足", "features"))
            else:
                res.responses.append(ParamResponse(row.row, row.name, row.required, row.star,
                                                   todo(f"第{row.row}行「{row.required[:20]}…」的具体响应值"), "missing",
                                                   "产品库无对应参数"))
            continue
        key, val = hit
        if any(val.strip() == w for w in FORBIDDEN):
            res.responses.append(ParamResponse(row.row, row.name, row.required, row.star,
                                               todo(f"{key} 的具体数值（禁止填「{val}」）"), "missing", "产品参数值为禁用措辞"))
            continue
        v = compare(row.required, val)
        res.responses.append(ParamResponse(row.row, row.name, row.required, row.star, val, v.verdict, v.reason, key))
    return res


def deviation_rows(result: TechParamResult) -> list[dict]:
    """技术偏差表行（无偏差时调用方按国网格式填"无偏差"）。"""
    return [{"序号": i + 1, "对应条款": f"参数表第{r.row}行", "招标文件要求": r.required,
             "投标响应": r.response, "偏差说明": r.reason}
            for i, r in enumerate(result.deviations)]
