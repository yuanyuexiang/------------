"""LLM 兜底：确定性抽取留 None 的字段，由 LLM 补充并标注来源。

原则（CLAUDE.md）：LLM 只做"从原文抽取结构化"，不做生成；失败保持 None。
"""
from __future__ import annotations

import jb_llm

from .trm import TRM

_QUAL_PROMPT = """从国网招标资格要求中抽取 JSON：
{{"perf_years": 业绩年限数字或null, "perf_scope": "业绩范围简述", "report_required": 是否要求检测/试验报告(true/false/null)}}
业绩要求原文：{perf}
资质要求原文：{report}
只输出 JSON。"""

_KEYTERM_PROMPT = """从投标人须知条款中抽取 JSON（信息不存在则为 null，禁止猜测）：
{{"validity_days": 投标/应答有效期天数, "deposit_mode": "none|诚信担保|年度保证金|按包保证金", "paperless": 是否明确不接收纸质文件}}
条款原文：
{text}
只输出 JSON。"""


def enrich(trm: TRM, max_qual_items: int = 20) -> int:
    """返回 LLM 成功兜底的字段数。未配置 LLM 时直接返回 0。"""
    if not jb_llm.available():
        return 0
    filled = 0
    # 1. 资格条款结构化
    todo = [q for p in trm.packages for q in p.qualification if not q.llm_extracted][:max_qual_items]
    for q in todo:
        data = jb_llm.chat_json(_QUAL_PROMPT.format(perf=q.performance_req or "无",
                                                    report=q.test_report_req or "无"), purpose="parse")
        if not isinstance(data, dict):
            continue
        years = data.get("perf_years")
        q.perf_years = int(years) if isinstance(years, (int, float)) else None
        q.perf_scope = str(data.get("perf_scope") or "")
        rr = data.get("report_required")
        q.report_required = rr if isinstance(rr, bool) else None
        q.llm_extracted = True
        filled += 1
    # 2. KeyTerms 缺项兜底
    kt = trm.key_terms
    missing = [f for f in ("validity_days", "deposit_mode", "paperless") if getattr(kt, f) is None]
    if missing and trm.prenotice:
        text = "\n".join(f"{c.clause_no} {c.name}: {c.content[:200]}"
                         for c in trm.prenotice
                         if any(k in c.name + c.content for k in ("有效期", "保证金", "纸质", "担保")))[:4000]
        data = jb_llm.chat_json(_KEYTERM_PROMPT.format(text=text or "（无相关条款）"), purpose="parse")
        if isinstance(data, dict):
            for f in missing:
                v = data.get(f)
                if v is not None:
                    setattr(kt, f, int(v) if f == "validity_days" else v)
                    kt.llm_filled.append(f)
                    filled += 1
    return filled
