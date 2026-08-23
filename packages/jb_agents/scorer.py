"""模拟评分 Agent：按本包评分模板逐项预测得分。

- 硬指标（业绩条数、人员职称人数、专利数、绩效档、体系认证数、研发人数…）：从档案结构化字段直接计数，
  按模板档位文本解析出的规则打分——确定性、可解释。
- 软指标（总体评价、服务方案、进度措施…）：对起草文本做多角色 LLM 评审取均值；无 LLM 时给区间不给点值。
- 缺数据不按最高档也不按 0 猜：给 [min,max] 区间 + "缺证据"说明，形成失分热力图。
"""
from __future__ import annotations

import re
from typing import Optional

from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM, PackageTRM, ScoringItem, ScoringTemplate
from pydantic import BaseModel, Field

_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[-~—]\s*(-?\d+(?:\.\d+)?)\s*分")
_SINGLE = re.compile(r"(-?\d+(?:\.\d+)?)\s*分")
_PERF_RULE = re.compile(r"(\d+)\s*项合格业绩[的]?得\s*(\d+)\s*分.*?每多(?:提供)?(?:一|1)项.*?(?:得|加)\s*(\d+)\s*分(?:.*?最高(?:加)?\s*(\d+)\s*分)?", re.S)
_COUNT_TIER = re.compile(r"(?:≥|不少于|不低于|达到)\s*(\d+)\s*人[，,：:]?\s*(?:得|：)?\s*(\d+(?:\.\d+)?)\s*[-~—]?\s*(\d+(?:\.\d+)?)?\s*分")


class ItemScore(BaseModel):
    element: str
    kind: str                       # tech | biz
    score_min: float = 0
    score_max: float = 0
    predicted: Optional[float] = None
    method: str = ""                # hard | llm | range
    basis: str = ""
    missing: list[str] = Field(default_factory=list)   # 缺什么证据能提分


class ScoreReport(BaseModel):
    pkg_no: str = ""
    items: list[ItemScore] = Field(default_factory=list)
    tech_total: Optional[float] = None
    biz_total: Optional[float] = None
    tech_max: float = 0
    biz_max: float = 0
    weighted: Optional[float] = None       # 按权重折算（不含价格分）
    notes: list[str] = Field(default_factory=list)

    def heatmap(self) -> list[dict]:
        """失分热力图：按 (max − predicted) 降序。"""
        rows = []
        for it in self.items:
            pred = it.predicted if it.predicted is not None else it.score_min
            rows.append({"element": it.element, "kind": it.kind, "loss": round(it.score_max - pred, 2),
                         "predicted": pred, "max": it.score_max, "missing": it.missing})
        return sorted(rows, key=lambda r: r["loss"], reverse=True)

    def markdown(self) -> str:
        lines = [f"# 模拟评分 · {self.pkg_no}",
                 f"技术 {self.tech_total if self.tech_total is not None else '?'}/{self.tech_max:g}　商务 {self.biz_total if self.biz_total is not None else '?'}/{self.biz_max:g}　加权（不含价格）{self.weighted if self.weighted is not None else '?'}",
                 "", "| 要素 | 类别 | 预测 | 区间 | 方法 | 依据 | 缺证据 |", "|---|---|---|---|---|---|---|"]
        for it in self.items:
            lines.append(f"| {it.element} | {it.kind} | {it.predicted if it.predicted is not None else '—'} | {it.score_min:g}~{it.score_max:g} | {it.method} | {it.basis} | {'；'.join(it.missing)} |")
        if self.notes:
            lines += ["", "说明：" + "；".join(self.notes)]
        return "\n".join(lines)


_LOOSE = re.compile(r"[（(]\s*(-?\d+(?:\.\d+)?)\s*[-~—]\s*(-?\d+(?:\.\d+)?)")


def _range_of(item: ScoringItem) -> tuple[float, float]:
    """先按要素文本括号内 a-b 解析（容忍截断"（8-13"），再退回解析器给的值。"""
    m = _LOOSE.search(item.element.replace("\n", ""))
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return (min(a, b), max(a, b))
    if item.score_min is not None and item.score_max is not None:
        return float(item.score_min), float(item.score_max)
    nums = [float(x) for x in _SINGLE.findall(item.element + item.content)]
    return (min(nums), max(nums)) if nums else (0.0, 0.0)


def _qualified_perfs(profile: CompanyProfile) -> list:
    return [p for p in profile.performances if {"合同", "发票"} <= set(p.evidence) and p.buyer_is_end_user is not False]


# ---------- 硬指标打分器 ----------

def score_performance(item: ScoringItem, profile: CompanyProfile) -> Optional[ItemScore]:
    lo, hi = _range_of(item)
    m = _PERF_RULE.search(item.content.replace("\n", ""))
    n = len(_qualified_perfs(profile))
    if not m:
        return None
    base_n, base, per, cap = int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)) if m.group(4) else None
    if n < base_n:
        pred = lo
        basis = f"合格业绩 {n} 条，不足 {base_n} 条"
    else:
        extra = (n - base_n) * per
        if cap is not None:
            extra = min(extra, cap)
        pred = min(hi, base + extra)
        basis = f"合格业绩 {n} 条：基础 {base:g} + 加分 {extra:g}"
    missing = []
    if pred < hi:
        need = int((hi - pred) / per + 0.999) if per else 0
        missing.append(f"再补 {need} 条合格业绩可满分" if need else "业绩已满分")
    undated = [p for p in _qualified_perfs(profile) if not p.signed_date]
    if undated:
        missing.append(f"{len(undated)} 条业绩缺签约日期，年限口径未核")
    return ItemScore(element=item.element, kind="tech", score_min=lo, score_max=hi, predicted=pred,
                     method="hard", basis=basis, missing=missing)


def score_team(item: ScoringItem, profile: CompanyProfile) -> Optional[ItemScore]:
    lo, hi = _range_of(item)
    if "团队" not in item.element and "负责人" not in item.content:
        return None
    titled = [p for p in profile.personnel if re.search(r"高级|副高|教授|硕士|博士", p.title)]
    tiers = _COUNT_TIER.findall(item.content.replace("\n", ""))
    if tiers:
        pred = lo
        for need, a, b in sorted(tiers, key=lambda t: int(t[0])):
            if len(titled) >= int(need):
                pred = float(b or a)
        basis = f"档案中副高/硕士及以上 {len(titled)} 人（职称字段未录入者不计）"
    else:
        pred = None
        basis = "团队评审为定性档位，需人工/LLM"
    missing = ["人员职称/学历字段未录入，无法计数" if not titled else "补充高级职称人员证书可提档"]
    return ItemScore(element=item.element, kind="tech", score_min=lo, score_max=hi, predicted=pred,
                     method="hard" if pred is not None else "range", basis=basis, missing=missing)


def score_patent(item: ScoringItem, profile: CompanyProfile) -> Optional[ItemScore]:
    if "专利" not in item.element:
        return None
    lo, hi = _range_of(item)
    n = len([c for c in profile.certificates if "专利" in c.name]) + len([x for x in getattr(profile, "ip_assets", []) or []])
    pred = min(hi, n * 1.0)
    return ItemScore(element=item.element, kind="tech", score_min=lo, score_max=hi, predicted=pred, method="hard",
                     basis=f"采购相关专利 {n} 项", missing=[f"每增 1 项相关专利 +1 分（上限 {hi:g}）"] if pred < hi else [])


def score_performance_eval(item: ScoringItem, profile: CompanyProfile) -> Optional[ItemScore]:
    if "绩效评价" not in item.element:
        return None
    lo, hi = _range_of(item)
    m = re.search(r"未参加绩效评价[：:]?\s*(\d+(?:\.\d+)?)\s*分", item.content)
    default = float(m.group(1)) if m else None
    return ItemScore(element=item.element, kind="tech", score_min=lo, score_max=hi, predicted=default, method="hard",
                     basis="国网供应商绩效评价分未录入，按'未参加'档" if default is not None else "绩效档位需录入",
                     missing=["录入国网绩效评价分（A≥90 得满分）"])


def score_biz_certs(item: ScoringItem, profile: CompanyProfile) -> Optional[ItemScore]:
    """管理体系认证 / 绿电绿证 / 高新 等商务硬指标。"""
    lo, hi = _range_of(item)
    el = item.element
    if "体系" in el or "认证" in el:
        n = len([c for c in profile.certificates if "体系" in c.name])
        m = re.search(r"取得\s*(\d+)\s*项[=＝]?\s*(\d+)\s*分", item.content)
        full_n = int(m.group(1)) if m else 4
        pred = hi if n >= full_n else (lo + (hi - lo) * n / full_n if full_n else lo)
        return ItemScore(element=el, kind="biz", score_min=lo, score_max=hi, predicted=round(pred, 1), method="hard",
                         basis=f"体系认证 {n} 项", missing=[f"补齐至 {full_n} 项体系认证可满分"] if n < full_n else [])
    if "绿电" in el or "绿证" in el:
        has = any("绿" in c.name for c in profile.certificates)
        return ItemScore(element=el, kind="biz", score_min=lo, score_max=hi, predicted=hi if has else lo, method="hard",
                         basis="绿电绿证 " + ("已录入" if has else "未录入"), missing=[] if has else ["取得绿电/绿证"])
    if "高新" in el:
        has = any("高新" in c.name for c in profile.certificates)
        return ItemScore(element=el, kind="biz", score_min=lo, score_max=hi, predicted=hi if has else lo, method="hard",
                         basis="高新技术企业证书 " + ("已录入" if has else "未录入"), missing=[] if has else ["录入高新技术企业证书"])
    if "研发团队" in el:
        n = profile.senior_engineers or 0
        return ItemScore(element=el, kind="biz", score_min=lo, score_max=hi, predicted=None, method="range",
                         basis=f"档案高级工程师 {n} 人（需含高级技师合计）", missing=["录入高级职称+高级技师总数"])
    if "诚信" in el or "不良行为" in el or "信用" in el:
        return ItemScore(element=el, kind="biz", score_min=lo, score_max=hi, predicted=hi, method="hard",
                         basis="档案无不良行为/失信记录（以查询截图为准）", missing=["投标前完成信用查询并留档"])
    return None


HARD_SCORERS = [score_performance, score_team, score_patent, score_performance_eval, score_biz_certs]


# ---------- 软指标：LLM 多角色评审 ----------

def _llm_soft(item: ScoringItem, text: str, lo: float, hi: float) -> Optional[float]:
    try:
        import jb_llm
    except ImportError:
        return None
    if not jb_llm.available() or not text.strip():
        return None
    scores = []
    for role in ("技术专家", "商务专家", "挑剔的评标委员"):
        data = jb_llm.chat_json(
            f"你是国网评标委员会的{role}。按评审标准对下面投标文件章节打分，只输出 JSON {{\"score\": 数字, \"reason\": \"一句话\"}}。\n"
            f"评审要素：{item.element}\n评审标准：{item.content}\n分值范围：{lo:g}~{hi:g}\n\n章节内容：\n{text[:3500]}", purpose="score")
        if isinstance(data, dict) and isinstance(data.get("score"), (int, float)):
            scores.append(max(lo, min(hi, float(data["score"]))))
    return round(sum(scores) / len(scores), 2) if scores else None


def _name_match(name: str, other: str) -> bool:
    """模板名松匹配：前附表引用名（如"FWSW01服务类通用商务详评细则"）与文件名（"FWSW01：…"）首 6 字互含。"""
    return bool(name) and bool(other) and (name[:6] in other or other[:6] in name)


def _template(trm: TRM, pkg: PackageTRM, kind: str,
              library: Optional[list[ScoringTemplate]] = None) -> Optional[ScoringTemplate]:
    """本包应用的评分模板：优先 TRM 内带细则条目的；TRM 里只有名字（docx 封面）或没有时，按名称到模板库兜底。
    模板库只按名称匹配，不按类别乱配——配错模板比没有模板更危险。"""
    name = pkg.scoring_ref.tech_template if kind == "tech" else pkg.scoring_ref.biz_template
    own = [t for t in trm.scoring_templates if t.kind == kind]
    hit = next((t for t in own if not name or _name_match(name, t.name)), None) or (own[0] if own else None)
    if hit is not None and hit.items:
        return hit
    ref = name or (hit.name if hit else "")
    for t in library or []:
        if t.items and t.kind == kind and _name_match(ref, t.name):
            return t
    return hit


def score_package(trm: TRM, pkg: PackageTRM, profile: CompanyProfile, draft_sections: Optional[list] = None,
                  use_llm: bool = True, library: Optional[list[ScoringTemplate]] = None) -> ScoreReport:
    """library：配置中心的评分模板库（按名称兜底 TRM 里缺细则的模板）。"""
    rep = ScoreReport(pkg_no=pkg.pkg_no)
    drafts = {s.title: s.text for s in (draft_sections or [])}
    for kind in ("tech", "biz"):
        tpl = _template(trm, pkg, kind, library)
        if tpl is None or not tpl.items:
            rep.notes.append(f"缺少{ '技术' if kind == 'tech' else '商务'}评分模板细则（{getattr(pkg.scoring_ref, kind + '_template', '') or (tpl.name if tpl else '')}），请到配置中心·评分模板库补录")
            continue
        if tpl not in trm.scoring_templates:
            rep.notes.append(f"{'技术' if kind == 'tech' else '商务'}评分使用模板库《{tpl.name}》")
        for it in tpl.items:
            lo, hi = _range_of(it)
            if hi <= 0 and lo >= 0:
                continue
            scored = None
            for fn in HARD_SCORERS:
                scored = fn(it, profile)
                if scored:
                    scored.kind = kind
                    break
            if scored is None:
                el = re.sub(r"[（(].*", "", it.element).strip(" .．0123456789\n")
                text = next((t for k, t in drafts.items() if el and (el in k or k in el)), "")
                pred = _llm_soft(it, text, lo, hi) if use_llm else None
                if kind == "biz" and not text:
                    basis, missing = "商务文件整体评审（完整性/规范性/报价质量），定性档位", ["按商务评分支撑材料清单补齐证据"]
                else:
                    basis = "LLM 三角色评审均值" if pred is not None else ("无对应起草章节" if not text else "LLM 未配置")
                    missing = [] if text else [f"起草《{el}》章节"]
                scored = ItemScore(element=it.element, kind=kind, score_min=lo, score_max=hi, predicted=pred,
                                   method="llm" if pred is not None else "range", basis=basis, missing=missing)
            rep.items.append(scored)
    for kind in ("tech", "biz"):
        items = [i for i in rep.items if i.kind == kind]
        mx = sum(i.score_max for i in items)
        known = [i for i in items if i.predicted is not None]
        total = round(sum(i.predicted for i in known) + sum(i.score_min for i in items if i.predicted is None), 2) if items else None
        if kind == "tech":
            rep.tech_total, rep.tech_max = total, mx
        else:
            rep.biz_total, rep.biz_max = total, mx
    sr = pkg.scoring_ref
    if rep.tech_total is not None and rep.tech_max and sr.weight_tech is not None:
        w = rep.tech_total / rep.tech_max * sr.weight_tech
        if rep.biz_total is not None and rep.biz_max and sr.weight_biz is not None:
            w += rep.biz_total / rep.biz_max * sr.weight_biz
        rep.weighted = round(w, 2)
    return rep
