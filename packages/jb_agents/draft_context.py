"""本包起草上下文；原件仅作为招标要求，不能充当企业能力证明。"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph
from jb_kb.retrieval import Chunk, Index
from jb_parser.trm import TRM, PackageTRM


def requirement_sources(trm: TRM, pkg: PackageTRM,
                        spec_paths: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    sources: dict[str, str] = {}
    warnings: list[str] = []
    sources["req-package"] = (
        f"项目：{pkg.project_name or trm.batch_name}；本包：{pkg.sub_no} {pkg.sub_name} {pkg.pkg_no}；范围：{pkg.scope}；"
        f"服务期原文：{pkg.duration_text}；工期天数：{pkg.duration_days if pkg.duration_days is not None else '未录入'}天；"
        f"最高限价：{pkg.max_price or '未录入'}"
    )
    for i, (key, value) in enumerate(pkg.demand_details.items()):
        sources[f"req-demand-{i}"] = f"{pkg.identity_source}；{key}：{value}"
    for i, template in enumerate(trm.scoring_templates):
        for j, item in enumerate(template.items):
            sources[f"req-score-{i}-{j}"] = f"{template.source}；{item.element}：{item.content}"
    for i, material in enumerate(pkg.materials):
        sources[f"req-material-{i}"] = material.model_dump_json()
    for i, q in enumerate(pkg.qualification):
        sources[f"req-qualification-{i}"] = q.model_dump_json()
    for i, rule in enumerate(trm.rejection_rules):
        sources[f"req-rejection-{i}"] = f"{rule.category} {rule.aspect}：{rule.text}"
    sources["req-terms"] = trm.key_terms.model_dump_json(exclude_none=True)
    for i, spec in enumerate(pkg.spec_docs):
        for row in spec.param_rows:
            sources[f"req-param-{i}-{row.row}"] = (
                f"{spec.title} {'★' if row.star else ''}{row.name}：{row.required} {row.unit}"
            )
        path = ((spec_paths or {}).get(spec.spec_id) or (spec_paths or {}).get(spec.source))
        if not path:
            warnings.append(f"规范书《{spec.title or spec.spec_id}》原文未读取，仅使用已解析要求")
            continue
        try:
            doc = Document(Path(path))
            # XML 顺序保留正文与表格次序；表格单元格文本一并读取。
            paragraphs = []
            for element in doc.element.body:
                lines = [Paragraph(node, doc).text for node in element.iter()
                         if node.tag.endswith('}p')]
                text = ' '.join(lines).strip()
                if text:
                    paragraphs.append(text)
            for j, text in enumerate(paragraphs):
                for start in range(0, len(text), 4000):
                    chunk_id = f"req-spec-{i}-{j}" + (f"-c{start // 4000}" if start else "")
                    sources[chunk_id] = f"《{spec.title or spec.spec_id}》 {text[start:start + 4000]}"
        except Exception:
            warnings.append(f"规范书《{spec.title or spec.spec_id}》原文读取失败，需核对文件")
    return sources, warnings


def section_requirements(sources: dict[str, str], query: str, limit: int = 14000) -> dict[str, str]:
    """每节固定带本包条件，另检索相关规范片段；不混入其他包。"""
    selected = {k: v for k, v in sources.items() if k in ('req-package', 'req-terms') or k.startswith('req-material-')}
    index = Index()
    for key, text in sources.items():
        if key not in selected:
            index.add(Chunk(id=key, kind='requirement', topic='', text=text))
    used = sum(map(len, selected.values()))
    hits = index.search(query, top_k=24)
    # 参数与原文优先，避免通用否决条款挤掉本包实际技术需求。
    hits.sort(key=lambda hit: hit.chunk.id.startswith('req-rejection-'))
    for hit in hits:
        if used + len(hit.chunk.text) > limit:
            continue
        selected[hit.chunk.id] = hit.chunk.text
        used += len(hit.chunk.text)
    return selected


_DATE_RANGE = re.compile(
    r'(20\d{2})年(\d{1,2})月(?:[～~—–\-至到]+(?:(20\d{2})年)?(\d{1,2})月)?'
)


def attribute_schedule_dates(text: str, sources: dict[str, str]) -> str:
    """给漏引的阶段标题/表格日期补唯一原文引用；不处理企业能力或无依据的日期。"""
    def dates(value):
        pairs = set()
        for match in _DATE_RANGE.finditer(re.sub(r'\s+', '', value)):
            year, month, end_year, end_month = match.groups()
            pairs.add((int(year), int(month), int(end_year or year), int(end_month or month)))
        return pairs

    schedules = {}
    for key, value in sources.items():
        plain = re.sub(r'\s+', '', value)
        if key.startswith('req-spec-') and any(word in plain for word in
                                             ('预计时间', '计划时间', '进度安排')):
            schedules[key] = dates(value)
    lines = []
    schedule_table = False
    for line in text.split('\n'):
        if '|' not in line:
            schedule_table = False
        elif any(word in line for word in ('阶段', '计划时间', '预计时间', '进度安排')):
            schedule_table = True
        is_heading = re.match(r'^\s*#{1,6}\s+', line) and any(
            word in line for word in ('阶段', '进度', '安排', '计划'))
        is_table = line.strip().startswith('|') and schedule_table
        pairs = dates(line)
        if (is_heading or is_table) and pairs and '[来源:' not in line:
            candidates = [key for key, values in schedules.items() if pairs <= values]
            if len(candidates) == 1:
                line += f' [来源:{candidates[0]}]'
        lines.append(line)
    return '\n'.join(lines)
