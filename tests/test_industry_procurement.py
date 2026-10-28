"""产业单位编码包、无规范ID正文及混入封面的回归。"""
from pathlib import Path

import pytest
from docx import Document
from jb_agents.draft_report import confirmation_items
from jb_agents.preflight import generation_issues
from jb_parser import parse
from jb_parser.extract import extract_batch_info
from jb_parser.trm import TRM, PackageTRM


def test_cover_identity_wins_over_instruction_paragraph():
    doc = Document()
    doc.add_paragraph('采购编号：CY8526JFF17C')
    doc.add_paragraph('国网信通产业集团2026年产业单位第十七次服务类公开谈判采购（三）')
    doc.add_paragraph('（2）响应供应商收到短信后需登陆ECP2.0非招标采购模块查看谈判采购通知路径。')
    assert extract_batch_info(doc, '采购文件.docx') == (
        '国网信通产业集团2026年产业单位第十七次服务类公开谈判采购（三）', 'CY8526JFF17C', '应答')


def test_missing_identity_is_system_issue_and_duplicates_are_grouped():
    assert any(x['blocking'] for x in generation_issues(TRM(), PackageTRM()))
    items = confirmation_items(None, {'商务.docx': ['分标名称', '分标名称'],
                                      '技术.docx': ['分标名称', '被授权人姓名', '数值需核实来源']})
    assert items[0].category == '招标原文待核对'
    assert items[0].occurrences == 3 and len(items[0].locations) == 2
    assert items[1].category == '本次投标事实待确认'
    assert items[2].category == '引用依据待核对'


SAMPLE = Path(__file__).resolve().parents[1] / '国网信通产业集团2026年产业单位第十七次服务类公开谈判采购（三）_采购文件包(1).zip'


@pytest.mark.skipif(not SAMPLE.exists(), reason='本地产业单位采购样本不可用')
def test_industry_package_uses_matching_body_not_foreign_cover(tmp_path):
    trm = parse(str(SAMPLE), str(tmp_path))
    assert trm.batch_no == 'CY8526JFF17C'
    assert len(trm.packages) == 1
    pkg = trm.packages[0]
    assert pkg.pkg_no == 'FF17-229'
    assert pkg.project_name == '能源互联网营销服务系统服务支撑'
    assert '4个月' in pkg.duration_text
    assert pkg.max_price == '132.000000万元'
    assert (pkg.scoring_ref.weight_tech, pkg.scoring_ref.weight_price, pkg.scoring_ref.weight_biz) == (40, 50, 10)
    assert len(pkg.spec_docs) == 1 and not pkg.spec_docs[0].spec_id
    assert '能源互联网' in pkg.spec_docs[0].source
    assert not any(x['blocking'] for x in generation_issues(trm, pkg))
    assert any('湖北思极' in x for x in trm.warnings)


def test_transient_draft_failure_retries_and_successful_sections_are_reused(monkeypatch):
    import jb_llm
    from jb_agents.writer import draft_package
    from jb_kb.models import CompanyProfile
    calls = []

    def chat(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError('temporary')
        return '拟建立交付记录并进行复核。'

    monkeypatch.setattr(jb_llm, 'available', lambda: True)
    monkeypatch.setattr(jb_llm, 'chat', chat)
    draft = draft_package(TRM(), PackageTRM(), CompanyProfile(name='测试'))
    assert all(s.by_llm for s in draft.sections)
    assert len(calls) == len(draft.sections) + 1
    previous = [s.model_dump() for s in draft.sections]
    previous[0]['by_llm'] = False
    calls.clear()
    result = draft_package(TRM(), PackageTRM(), CompanyProfile(name='测试'), previous_sections=previous)
    assert len(calls) == 2
    assert all(s.by_llm for s in result.sections)


def test_service_deliverable_table_uses_plan_without_claiming_product_performance():
    from jb_docgen.spec_response import respond_service_table, service_table_rows
    doc = Document()
    table = doc.add_table(rows=2, cols=4)
    for cell, text in zip(table.rows[0].cells, ['序号', '成果名称', '成果说明', '应答人应答']):
        cell.text = text
    for cell, text in zip(table.rows[1].cells, ['1', '验收报告', '验收报告', '']):
        cell.text = text
    key = service_table_rows(table)[0][1]
    respond_service_table(table, {key: '拟整理验收记录并提交采购方审核。[来源:req-service-0]'})
    assert len(table.columns) == 4
    assert table.rows[1].cells[3].text == '拟整理验收记录并提交采购方审核。'
