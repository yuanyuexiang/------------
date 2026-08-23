"""资格自检 Agent：TRM 资格要求 × 企业档案 → 每包可投性矩阵。

规则优先、LLM 仅做"业绩是否属于要求类型"的分类判断（不生成事实）。
状态：满足 / 风险 / 不满足 / 需人工；任一"不满足"→ 不可投，任一"风险/需人工"→ 有风险。
每条结论带证据与依据，抽不到的数据如实标"需人工"，绝不按缺省值判满足。
"""
from __future__ import annotations

import re
from typing import Optional

from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM, PackageTRM, QualificationItem
from pydantic import BaseModel, Field

SATISFIED, RISK, FAILED, MANUAL = "满足", "风险", "不满足", "需人工"
_COUNT_PAT = re.compile(r"不少于\s*(\d+)\s*(?:套|项|个|台|份)")
_YEARS_PAT = re.compile(r"近\s*(\d+)\s*年")


class Check(BaseModel):
    item: str                       # 检查项
    status: str                     # 满足/风险/不满足/需人工
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    requirement: str = ""           # 原文
    by_llm: bool = False


class PackageFeasibility(BaseModel):
    sub_no: str = ""
    sub_name: str = ""
    pkg_no: str = ""
    project_name: str = ""
    verdict: str = ""               # 可投/有风险/不可投
    checks: list[Check] = Field(default_factory=list)


class FeasibilityReport(BaseModel):
    batch_name: str = ""
    company: str = ""
    packages: list[PackageFeasibility] = Field(default_factory=list)

    def markdown(self) -> str:
        lines = [f"# 可投性矩阵 · {self.company}", f"批次：{self.batch_name}", ""]
        for p in self.packages:
            lines.append(f"## {p.sub_no} {p.sub_name} {p.pkg_no} — **{p.verdict}**")
            if p.project_name:
                lines.append(f"项目：{p.project_name}")
            lines.append("")
            lines.append("| 检查项 | 结论 | 说明 | 证据 |")
            lines.append("|---|---|---|---|")
            for c in p.checks:
                ev = "；".join(c.evidence)[:120]
                lines.append(f"| {c.item} | {c.status} | {c.reason} | {ev} |")
            lines.append("")
        return "\n".join(lines)


# ---------- 业绩匹配 ----------

def _llm_match_performances(scope: str, titles: list[str]) -> Optional[list[bool]]:
    """用 LLM 判断每条业绩是否属于要求类型；不可用/失败返回 None。"""
    try:
        import jb_llm
    except ImportError:
        return None
    if not jb_llm.available() or not titles:
        return None
    prompt = (
        "判断下列业绩项目是否属于招标要求的业绩类型。只输出 JSON 数组，元素为 true/false，顺序与输入一致。\n"
        f"要求的业绩类型：{scope}\n业绩项目：\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    )
    data = jb_llm.chat_json(prompt, purpose="qualify")
    if isinstance(data, list) and len(data) == len(titles) and all(isinstance(x, bool) for x in data):
        return data
    return None


def check_performance(q: QualificationItem, profile: CompanyProfile, use_llm: bool) -> Optional[Check]:
    req = q.performance_req.strip()
    if not req:
        return None
    scope = q.perf_scope or req
    years = q.perf_years
    if years is None:
        m = _YEARS_PAT.search(req)
        years = int(m.group(1)) if m else None
    m = _COUNT_PAT.search(scope) or _COUNT_PAT.search(req)
    need = int(m.group(1)) if m else 1

    perfs = profile.performances
    if not perfs:
        return Check(item="业绩要求", status=FAILED, reason="企业档案无业绩记录", requirement=req)

    titles = [p.project for p in perfs]
    flags = _llm_match_performances(scope, titles) if use_llm else None
    by_llm = flags is not None
    matched = [p for p, f in zip(perfs, flags)] if flags else perfs
    if flags:
        matched = [p for p, f in zip(perfs, flags) if f]

    notes = []
    if not by_llm:
        notes.append("业绩类型未做语义匹配（按全部业绩计）")
    undated = [p for p in matched if not p.signed_date]
    if years and undated:
        notes.append(f"{len(undated)} 条业绩缺签约日期，近{years}年口径需人工核对")
    end_user_unknown = [p for p in matched if p.buyer_is_end_user is None]
    if end_user_unknown:
        notes.append("买方是否最终用户未录入（国网不认可非最终用户业绩）")
    weak = [p for p in matched if not {"合同", "发票"} <= set(p.evidence)]
    if weak:
        notes.append(f"{len(weak)} 条业绩合同/发票不全")

    evidence = [f"{p.project}（{'/'.join(p.evidence)}）" for p in matched]
    if len(matched) < need:
        return Check(item="业绩要求", status=FAILED,
                     reason=f"匹配业绩 {len(matched)} 条，要求不少于 {need} 条", evidence=evidence,
                     requirement=req, by_llm=by_llm)
    status = RISK if notes else SATISFIED
    reason = f"匹配业绩 {len(matched)} 条（要求≥{need}）" + ("；" + "；".join(notes) if notes else "")
    return Check(item="业绩要求", status=status, reason=reason, evidence=evidence,
                 requirement=req, by_llm=by_llm)


def check_report(q: QualificationItem, profile: CompanyProfile) -> Optional[Check]:
    req = q.test_report_req.strip()
    if q.report_required is False or (q.report_required is None and not req):
        return None
    reports = [c for c in profile.certificates if any(k in c.name for k in ("试验", "检测", "鉴定", "报告"))]
    if reports:
        return Check(item="检测/试验报告", status=RISK,
                     reason="档案有报告类记录，覆盖型号/参数/有效期需人工核对",
                     evidence=[c.name for c in reports], requirement=req)
    return Check(item="检测/试验报告", status=FAILED, reason="要求提供检测/试验报告，企业档案中无记录",
                 requirement=req)


def check_other(q: QualificationItem, profile: CompanyProfile) -> list[Check]:
    out = []
    cert_req = q.other_reqs.get("企业资质条件", "")
    if cert_req:
        names = [c.name for c in profile.certificates]
        out.append(Check(item="企业资质条件", status=MANUAL,
                         reason="资质条件需人工比对档案证书", evidence=names, requirement=cert_req))
    staff_req = q.other_reqs.get("主要人员要求", "")
    if staff_req:
        out.append(Check(item="主要人员要求", status=MANUAL if profile.personnel else FAILED,
                         reason=f"档案在册人员 {len(profile.personnel)} 人，证书匹配需人工确认",
                         evidence=[p.name for p in profile.personnel], requirement=staff_req))
    return out


def check_general(pkg: PackageTRM, profile: CompanyProfile) -> list[Check]:
    out = [Check(item="通用资格（信用/不良行为/失信）", status=MANUAL,
                 reason="需查询信用中国/国家企业信用信息公示系统/国网不良行为名单并截图",
                 evidence=[f"统一社会信用代码 {profile.credit_code}"] if profile.credit_code else [])]
    if pkg.allow_consortium is False:
        out.append(Check(item="联合体", status=SATISFIED, reason="本包不接受联合体；按独立投标准备"))
    return out


def qualify_package(pkg: PackageTRM, profile: CompanyProfile, use_llm: bool = True) -> PackageFeasibility:
    pf = PackageFeasibility(sub_no=pkg.sub_no, sub_name=pkg.sub_name, pkg_no=pkg.pkg_no,
                            project_name=pkg.project_name)
    if not pkg.qualification:
        pf.checks.append(Check(item="资格要求", status=MANUAL, reason="未解析到本包资格要求，需人工对照公告"))
    for q in pkg.qualification:
        for c in (check_performance(q, profile, use_llm), check_report(q, profile)):
            if c:
                pf.checks.append(c)
        pf.checks.extend(check_other(q, profile))
    pf.checks.extend(check_general(pkg, profile))
    statuses = {c.status for c in pf.checks}
    pf.verdict = "不可投" if FAILED in statuses else ("有风险" if statuses & {RISK, MANUAL} else "可投")
    return pf


def qualify(trm: TRM, profile: CompanyProfile, use_llm: bool = True) -> FeasibilityReport:
    rep = FeasibilityReport(batch_name=trm.batch_name, company=profile.name)
    for pkg in trm.packages:
        rep.packages.append(qualify_package(pkg, profile, use_llm))
    return rep
