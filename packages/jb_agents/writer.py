"""技术方案起草 Agent：评分项 → 检索素材 → LLM 起草（带溯源）→ 事实校验。

约束（CLAUDE.md 领域约束）：
- 事实（数字、案例、证书、人名）只能来自提供的素材；素材没有就写【待补充：xxx】。
- 每处引用素材的句子末尾标 [来源:chunk_id]；起草后做"无来源数字"校验，违规数字改为【待补充】。
- LLM 不可用时返回结构化大纲 + 待补充骨架（不阻塞流程）。
"""
from __future__ import annotations

import re
from typing import Optional

from jb_kb.models import CompanyProfile
from jb_kb.retrieval import Index, build_index
from jb_parser.trm import TRM, PackageTRM, ScoringTemplate
from pydantic import BaseModel, Field

_NUM = re.compile(r"\d+(?:\.\d+)?")
_SRC = re.compile(r"\[来源:([^\]]+)\]")

# 通用服务类章节骨架（无评分模板时兜底；与 JS-FWTY 模板要素对应）
DEFAULT_OUTLINE = [
    ("项目理解与需求分析", "投标文件技术部分总体评价"),
    ("总体服务方案", "服务方案"),
    ("项目团队与人员配置", "项目团队"),
    ("工作进度及保证措施", "工作进度及保证措施"),
    ("质量保证体系", "服务方案"),
    ("信息安全与保密措施", "服务方案"),
    ("售后服务与培训", "服务方案"),
]


class DraftSection(BaseModel):
    title: str
    scoring_element: str = ""       # 对应评分要素
    score_hint: str = ""            # 评审标准摘要（指导写作重点）
    text: str = ""                  # Markdown 正文
    sources: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    by_llm: bool = False
    fact_violations: list[str] = Field(default_factory=list)  # 被改为【待补充】的无来源数字


class Draft(BaseModel):
    pkg_no: str = ""
    sections: list[DraftSection] = Field(default_factory=list)

    def markdown(self) -> str:
        out = []
        for s in self.sections:
            out.append(f"## {s.title}")
            if s.scoring_element:
                out.append(f"> 评分要素：{s.scoring_element}｜{s.score_hint}")
            out.append(s.text or "【待补充：本节内容】")
            out.append("")
        return "\n".join(out)


def _tech_template(trm: TRM, pkg: PackageTRM) -> Optional[ScoringTemplate]:
    name = pkg.scoring_ref.tech_template
    for t in trm.scoring_templates:
        if t.kind == "tech" and (not name or name[:8] in t.name or t.name[:8] in name):
            return t
    return next((t for t in trm.scoring_templates if t.kind == "tech"), None)


def build_outline(trm: TRM, pkg: PackageTRM) -> list[DraftSection]:
    tpl = _tech_template(trm, pkg)
    sections: list[DraftSection] = []
    if tpl:
        for it in tpl.items:
            el = re.sub(r"\s+", "", it.element)
            el = re.sub(r"[（(].*?([）)]|$)", "", el).strip(" .．0123456789")
            if not el or "绩效评价" in el or "专利" in el:
                continue  # 绩效/专利是材料项，不是写作章节
            sections.append(DraftSection(title=el, scoring_element=it.element, score_hint=it.content[:160]))
    if not sections:
        sections = [DraftSection(title=t, scoring_element=e) for t, e in DEFAULT_OUTLINE]
    if pkg.scope:
        sections.insert(0, DraftSection(title="招标范围逐条响应", scoring_element="投标文件技术部分总体评价",
                                        score_hint="对招标范围逐条正面响应，规范、完整、有逻辑"))
    return sections


def _facts_block(profile: CompanyProfile) -> tuple[str, set[str]]:
    """可引用的结构化事实（带 ID），以及其中出现的数字集合（用于校验）。"""
    lines = [f"[来源:fact-company] 企业：{profile.name}；员工 {profile.staff_total or '未知'} 人，其中技术人员 {profile.staff_technical or '未知'} 人；高级工程师 {profile.senior_engineers or '未知'} 人"]
    for i, x in enumerate(profile.performances):
        lines.append(f"[来源:fact-perf-{i}] 业绩：{x.project}（{x.signed_date or '签约日期未录入'}）")
    for i, x in enumerate(profile.personnel):
        lines.append(f"[来源:fact-person-{i}] 人员：{x.name} {x.title}".strip())
    for i, c in enumerate(profile.certificates):
        lines.append(f"[来源:fact-cert-{i}] 证书：{c.name}")
    text = "\n".join(lines)
    return text, set(_NUM.findall(text))


def _prompt(section: DraftSection, pkg: PackageTRM, facts: str, chunks: list[tuple[str, str]]) -> str:
    mat = "\n".join(f"[来源:{cid}] {txt}" for cid, txt in chunks) or "（无可用素材）"
    return f"""你是投标文件技术部分撰写专家。请撰写章节《{section.title}》，目标是在评审要素"{section.scoring_element}"上得高分。
评审标准：{section.score_hint or '规范、完整、针对性强'}
项目：{pkg.project_name or '（见招标范围）'}
招标范围：{pkg.scope or '（未提供）'}

【可引用的企业事实（只能用这些，禁止编造任何数字、案例、证书、人名）】
{facts}

【可复用素材】
{mat}

写作要求：
1. 用 Markdown，三级标题组织，300-600 字，针对招标范围具体展开，不写空话。
2. 凡引用事实或素材的句子，句末标注对应的 [来源:id]。
3. 需要具体数字/案例/人名而上面没有的，写成【待补充：需要什么】，不得编造。
4. 不出现其他项目名、其他甲方名。
只输出章节正文。"""


def _check_numbers(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """正文中的数字若不在事实/素材中出现且所在句无来源标注，替换为【待补充】。"""
    violations: list[str] = []
    out_lines = []
    for line in text.split("\n"):
        if line.startswith("#") or "【待补充" in line:
            out_lines.append(line)
            continue
        has_src = bool(_SRC.search(line))
        nums = [n for n in _NUM.findall(line) if n not in allowed and not re.fullmatch(r"[1-9]|1\d", n)]
        if nums and not has_src:
            for n in nums:
                violations.append(n)
                line = line.replace(n, f"【待补充：数值{n}需核实来源】", 1)
        out_lines.append(line)
    return "\n".join(out_lines), violations


def draft_package(trm: TRM, pkg: PackageTRM, profile: CompanyProfile, use_llm: bool = True,
                  index: Optional[Index] = None) -> Draft:
    index = index or build_index(profile)
    facts, fact_nums = _facts_block(profile)
    draft = Draft(pkg_no=pkg.pkg_no)
    llm = None
    if use_llm:
        try:
            import jb_llm
            llm = jb_llm if jb_llm.available() else None
        except ImportError:
            llm = None
    for sec in build_outline(trm, pkg):
        hits = index.search(f"{sec.title} {sec.scoring_element} {pkg.scope[:80]}", top_k=4)
        chunks = [(h.chunk.id, h.chunk.text) for h in hits]
        allowed = fact_nums | set(_NUM.findall(" ".join(t for _, t in chunks)))
        if llm is None:
            sec.text = f"【待补充：{sec.title}——LLM 未配置，请按评审标准撰写】\n\n可用素材：\n" + \
                       "\n".join(f"- [来源:{cid}] {txt[:80]}" for cid, txt in chunks)
            sec.todos.append(sec.title)
        else:
            try:
                text = llm.chat(_prompt(sec, pkg, facts, chunks), temperature=0.3, timeout=120, purpose="draft")
            except Exception as exc:  # 网络/模型错误：降级为骨架，不中断
                text = f"【待补充：{sec.title}——起草失败：{exc}】"
            text, viol = _check_numbers(text, allowed)
            sec.text, sec.by_llm, sec.fact_violations = text, True, viol
            sec.sources = sorted(set(_SRC.findall(text)))
            sec.todos = re.findall(r"【待补充：([^】]*)】", text)
        draft.sections.append(sec)
    return draft
