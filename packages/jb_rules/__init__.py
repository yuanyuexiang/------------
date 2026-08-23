"""jb-rules：否决规则引擎。

规则来源：真实招标文件"否决情形表"46 行 + 国网典型案例库反推的 SG-01~22（docs/国网物资与服务投标-场景细化方案 §8.2）。
每条规则 = (id, 级别, 名称, 检查函数)。检查函数拿 Context（TRM/包/档案/生成结果/报价单）返回问题列表；
无法自动判断的规则以"需人工"条目输出，保证清单完整、不漏项。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM, PackageTRM
from pydantic import BaseModel, Field


class Finding(BaseModel):
    rule_id: str
    level: str              # 否决 | 扣分 | 建议 | 需人工
    title: str
    message: str
    location: str = ""      # 文件/章节/行
    source: str = ""        # 规则出处（条款号/案例号）


@dataclass
class Context:
    trm: TRM
    pkg: PackageTRM
    profile: CompanyProfile
    tech_params: list = field(default_factory=list)         # TechParamResult
    docx_todos: dict = field(default_factory=dict)           # 文件名 → 待补充列表
    price_issues: list = field(default_factory=list)         # price.Issue
    doc_texts: dict = field(default_factory=dict)            # 文件名 → 全文（雷同/名称检查）
    other_pkg_texts: dict = field(default_factory=dict)      # 同批次其他包技术文件全文（多包雷同）
    open_date: Optional[str] = None                          # YYYY-MM-DD
    params: dict = field(default_factory=dict)               # 当前规则的参数（review() 按 RuleSetting 注入）


Rule = tuple[str, str, str, str, Callable[[Context], list[Finding]]]
_FORBIDDEN = ("完全响应", "满足要求", "按招标文件执行", "按招标文件要求执行", "依据招标文件要求执行")


def _f(rule_id: str, level: str, title: str, msg: str, loc: str = "", src: str = "") -> Finding:
    return Finding(rule_id=rule_id, level=level, title=title, message=msg, location=loc, source=src)


# ---------- 技术参数 ----------

def r_param_forbidden(ctx: Context) -> list[Finding]:
    """技术参数响应以“完全响应/满足要求”等套话代替具体值 → 否决（前附表 1.11.2，案例 11）。"""
    out = []
    phrases = tuple(ctx.params.get("phrases") or _FORBIDDEN)
    for r in ctx.tech_params:
        for x in r.responses:
            if any(w == x.response.strip() or x.response.strip().endswith(w) for w in phrases):
                out.append(_f("SG-16", "否决", "技术参数以套话代替具体值",
                              f"第{x.row}行响应「{x.response}」", f"规范书{r.spec_id}", "前附表1.11.2/案例11(2)"))
    return out


def r_param_missing(ctx: Context) -> list[Finding]:
    """技术参数表有行未填响应值（含★项）→ 否决；数量按规范书汇总。"""
    out = []
    for r in ctx.tech_params:
        miss = [x for x in r.responses if x.verdict == "missing"]
        stars = [x for x in miss if x.star]
        if miss:
            out.append(_f("SG-16b", "否决", "技术参数未填写响应值",
                          f"{len(miss)} 行待补充（其中★项 {len(stars)} 行）", f"规范书{r.spec_id}", "前附表1.11.2"))
    return out


def r_param_deviation(ctx: Context) -> list[Finding]:
    """响应值不满足要求值：★项否决，非★项扣分（前附表 1.11.4，案例 11）。"""
    out = []
    for r in ctx.tech_params:
        for x in r.deviations:
            lvl = "否决" if x.star else "扣分"
            out.append(_f("SG-15", lvl, "技术参数响应值不满足要求值",
                          f"第{x.row}行：{x.reason}", f"规范书{r.spec_id}", "前附表1.11.4/案例11(1)"))
    return out


def r_param_unknown_star(ctx: Context) -> list[Finding]:
    """★功能描述项由产品特性匹配、无法数值比较 → 须人工逐项核对。"""
    out = []
    for r in ctx.tech_params:
        n = sum(1 for x in r.unknowns if x.star)
        if n:
            out.append(_f("SG-15b", "需人工", "★项功能描述需逐项人工确认满足",
                          f"{n} 行★功能项由产品特性匹配，须人工核对", f"规范书{r.spec_id}", "前附表1.11.2"))
    return out


def r_unstructured_spec(ctx: Context) -> list[Finding]:
    """非 9999 结构化规范书须在投标工具以附件逐项响应 → 提醒人工。"""
    us = [s for s in ctx.pkg.spec_docs if not s.structured]
    return [_f("SG-17", "需人工", "非结构化技术规范须以附件形式逐项响应",
               f"{len(us)} 本非 9999 规范（{', '.join(s.spec_id for s in us)}）须在投标工具以附件上传逐项响应",
               "技术文件", "案例11(3)")] if us else []


# ---------- 文件完整性 / 待补充 ----------

def r_todos(ctx: Context) -> list[Finding]:
    """生成文件中仍有【待补充】标记 → 否决并阻断导出（事实字段缺失）。"""
    out = []
    for fn, todos in ctx.docx_todos.items():
        if todos:
            out.append(_f("DOC-01", "否决", "文件存在【待补充】标记（导出阻断）",
                          f"{len(todos)} 处，如：{todos[0]}", fn, "形式评审-格式内容"))
    return out


def r_name_consistency(ctx: Context) -> list[Finding]:
    """项目/批次/企业名称全文一致，防复制历史标书（否决表：名称与证照不一致；案例：批次包号错）。"""
    out = []
    name = ctx.profile.name
    for fn, text in ctx.doc_texts.items():
        if name and name not in text:
            out.append(_f("DOC-02", "否决", "投标人名称未出现在文件中", "封面/投标函应含投标人全称", fn))
        if ctx.trm.batch_no and ctx.trm.batch_no not in text:
            out.append(_f("DOC-03", "扣分", "招标编号未出现在文件中", f"应含 {ctx.trm.batch_no}", fn))
        # 其他批次号痕迹（形如 W-2025-XXXX）
        others = {m for m in re.findall(r"\b[A-Z]-20\d{2}-[A-Z]{2,6}-[A-Z0-9]{2,6}\b", text)} - {ctx.trm.batch_no}
        if others:
            out.append(_f("DOC-04", "否决", "文件含其他批次编号（疑似复制历史标书）", "、".join(sorted(others)), fn, "案例：批次/包号不一致"))
    return out


# ---------- 资格 / 档案 ----------

def r_cert_validity(ctx: Context) -> list[Finding]:
    """档案证书有效期早于开标日 → 否决（案例 9）；未录入有效期提醒补录。"""
    out = []
    for c in ctx.profile.certificates:
        if not c.valid_until:
            out.append(_f("SG-13b", "需人工", "证书有效期未录入", c.name, "企业档案"))
        elif ctx.open_date and c.valid_until < ctx.open_date:
            out.append(_f("SG-13", "否决", "证书/报告在开标日前过期", f"{c.name} 有效期至 {c.valid_until}", "企业档案", "案例9"))
    return out


def r_performance_evidence(ctx: Context) -> list[Finding]:
    """业绩证据不全（合同+发票）或买方非最终用户 → 否决/扣分（案例 2）。"""
    out = []
    for x in ctx.profile.performances:
        if not {"合同", "发票"} <= set(x.evidence):
            out.append(_f("SG-05", "扣分", "业绩证明材料不全（需合同关键页+发票）", x.project, "业绩文件", "案例2(2)"))
        if x.buyer_is_end_user is False:
            out.append(_f("SG-06", "否决", "非最终用户业绩不被认可", x.project, "业绩文件", "案例2(3)"))
        elif x.buyer_is_end_user is None:
            out.append(_f("SG-06b", "需人工", "业绩买方是否最终用户未确认", x.project, "业绩文件"))
    return out


def r_consortium(ctx: Context) -> list[Finding]:
    """招标文件不接受联合体时提示人工确认投标主体（招标公告）。"""
    if ctx.pkg.allow_consortium is False:
        return [_f("Q-01", "需人工", "本包不接受联合体", "确认以独立投标人身份投标，不提交联合体协议", "商务文件", "招标公告")]
    return []


def r_general_credit(ctx: Context) -> list[Finding]:
    """信用中国/失信名单/经营异常等核查须在截止前 20 天内完成 → 提醒人工（否决表）。"""
    return [_f("SG-21", "需人工", "信用/不良行为核查",
               "投标前查询：信用中国、国家企业信用信息公示系统、中国裁判文书网、国网不良行为名单，并截图编入商务文件",
               "商务文件-查询报告及截图", "否决表-资格评审")]


# ---------- 价格 ----------

def r_price(ctx: Context) -> list[Finding]:
    """报价单校验：零单价/超限价/算术错/税率缺失等 → 否决（案例 6/7/8）。"""
    return [_f(f"PRICE-{i.rule}", i.level, i.rule, i.message + (f"（行 {i.rows}）" if i.rows else ""), "价格文件", "案例6/7/8")
            for i in ctx.price_issues]


# ---------- 多包雷同 / 元数据 ----------

def _shingles(text: str, k: int = 8) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + k] for i in range(0, max(0, len(t) - k), 3)}


def r_similarity(ctx: Context) -> list[Finding]:
    """同批次不同包技术文件相似度过高 → 专用部分未差异化（扣分风险）。"""
    out = []
    mine = " ".join(v for k, v in ctx.doc_texts.items() if "技术" in k)
    if not mine:
        return out
    a = _shingles(mine)
    for other, text in ctx.other_pkg_texts.items():
        b = _shingles(text)
        if a and b:
            j = len(a & b) / len(a | b)
            if j > float(ctx.params.get("threshold", 0.9)):
                out.append(_f("SIM-01", "扣分", "与同批次其他包技术文件高度雷同", f"与 {other} 相似度 {j:.0%}，专用部分应差异化", "技术文件"))
    return out


def r_submission_matrix(ctx: Context) -> list[Finding]:
    """提交方式表每项须有产出或人工挂载，按递交矩阵逐项核对（第六章）。"""
    """提交方式表每一项都应有对应产出或人工勾选（递交矩阵）。"""
    req = [s for s in ctx.trm.submission_table if s.item]
    if not req:
        return [_f("SUB-00", "需人工", "未解析到提交方式表", "按第六章人工核对递交清单", "递交")]
    return [_f("SUB-01", "需人工", "递交矩阵逐项核对", f"提交方式表 {len(req)} 项：按通道/端口在投标工具中逐项挂载并勾选", "投标工具", "第六章提交方式表")]


RULES: list[Rule] = [
    ("SG-16", "否决", "技术参数套话", "前附表1.11.2", r_param_forbidden),
    ("SG-16b", "否决", "技术参数缺响应", "前附表1.11.2", r_param_missing),
    ("SG-15", "否决/扣分", "技术参数不满足", "前附表1.11.4", r_param_deviation),
    ("SG-15b", "需人工", "★功能项确认", "前附表1.11.2", r_param_unknown_star),
    ("SG-17", "需人工", "非结构化规范附件响应", "案例11(3)", r_unstructured_spec),
    ("DOC-01", "否决", "待补充标记", "形式评审", r_todos),
    ("DOC-02~04", "否决/扣分", "名称与编号一致性", "形式评审", r_name_consistency),
    ("SG-13", "否决", "证书有效期", "案例9", r_cert_validity),
    ("SG-05/06", "否决/扣分", "业绩认定", "案例2", r_performance_evidence),
    ("Q-01", "需人工", "联合体", "招标公告", r_consortium),
    ("SG-21", "需人工", "信用核查", "否决表", r_general_credit),
    ("PRICE", "否决", "价格校验", "案例6/7/8", r_price),
    ("SIM-01", "扣分", "多包雷同", "串标认定", r_similarity),
    ("SUB-01", "需人工", "递交矩阵", "第六章", r_submission_matrix),
]


# 可配置参数（配置中心展示/编辑）：规则 ID → {参数名: 默认值}
RULE_PARAMS: dict[str, dict] = {
    "SG-16": {"phrases": list(_FORBIDDEN)},
    "SIM-01": {"threshold": 0.9},
}
LEVELS = ("否决", "扣分", "建议", "需人工")


class RuleSetting(BaseModel):
    """一条规则的运行设置（配置中心维护，落 rule_settings 表）。"""
    rule_id: str
    enabled: bool = True
    level_override: str = ""     # 空=用规则自带级别；否则该规则所有发现统一为此级别
    params: dict = Field(default_factory=dict)
    note: str = ""


def catalog() -> list[dict]:
    """规则目录：ID / 默认级别 / 名称 / 依据 / 说明 / 可配参数，供配置中心展示。"""
    return [{"rule_id": rid, "level": lvl, "title": title, "source": src,
             "doc": (fn.__doc__ or "").strip().split("\n")[0], "params": RULE_PARAMS.get(rid, {})}
            for rid, lvl, title, src, fn in RULES]


class ReviewReport(BaseModel):
    pkg_no: str = ""
    findings: list[Finding] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.level == "否决" for f in self.findings)

    def counts(self) -> dict:
        c: dict[str, int] = {}
        for f in self.findings:
            c[f.level] = c.get(f.level, 0) + 1
        return c

    def markdown(self) -> str:
        order = {"否决": 0, "扣分": 1, "建议": 2, "需人工": 3}
        lines = [f"# 合规审查 · {self.pkg_no}", f"结论：{'存在否决项，不可提交' if self.blocked else '无否决项'}　{self.counts()}", "",
                 "| 级别 | 规则 | 问题 | 说明 | 位置 | 依据 |", "|---|---|---|---|---|---|"]
        for f in sorted(self.findings, key=lambda x: order.get(x.level, 9)):
            lines.append(f"| {f.level} | {f.rule_id} | {f.title} | {f.message} | {f.location} | {f.source} |")
        return "\n".join(lines)


def review(ctx: Context, settings: Optional[dict[str, RuleSetting]] = None) -> ReviewReport:
    """跑全部规则；settings（rule_id → RuleSetting）可停用规则、统一覆盖级别、注入参数。"""
    rep = ReviewReport(pkg_no=ctx.pkg.pkg_no)
    settings = settings or {}
    for rid, _lvl, _title, _src, fn in RULES:
        st = settings.get(rid)
        if st is not None and not st.enabled:
            continue
        ctx.params = {**RULE_PARAMS.get(rid, {}), **((st.params if st else None) or {})}
        found = fn(ctx)
        if st is not None and st.level_override in LEVELS:
            for f in found:
                f.level = st.level_override
        rep.findings.extend(found)
    ctx.params = {}
    return rep
