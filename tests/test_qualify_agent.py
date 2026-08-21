"""资格自检 Agent 单元测试：合成 TRM × 合成档案，不依赖样本与 LLM（use_llm=False）。"""
from jb_agents import qualify
from jb_kb.models import CompanyProfile, Performance
from jb_parser.trm import TRM, PackageTRM, QualificationItem


def _profile(n_perf: int, dated: bool = True) -> CompanyProfile:
    return CompanyProfile(
        name="测试企业", credit_code="91000000000000000X",
        performances=[Performance(project=f"项目{i}", evidence=["合同", "发票"],
                                  signed_date="2025-01-01" if dated else "",
                                  buyer_is_end_user=True) for i in range(n_perf)])


def _trm(perf_req: str, report_req: str = "", perf_years=None, report_required=None,
         allow_consortium=False) -> TRM:
    q = QualificationItem(sub_name="分标X", pkg="包1", performance_req=perf_req,
                          test_report_req=report_req, perf_years=perf_years,
                          report_required=report_required)
    return TRM(batch_name="测试批次", packages=[PackageTRM(
        sub_no="分标X", pkg_no="包1", qualification=[q], allow_consortium=allow_consortium)])


def test_enough_performance_is_feasible_with_manual_credit_check():
    rep = qualify(_trm("近三年，具有同类产品合同业绩。"), _profile(3), use_llm=False)
    pkg = rep.packages[0]
    perf = next(c for c in pkg.checks if c.item == "业绩要求")
    assert perf.status == "风险"                      # 未做语义匹配 → 风险而非满足（不按缺省判满足）
    assert pkg.verdict == "有风险"                    # 通用资格恒为"需人工"


def test_count_requirement_fails():
    rep = qualify(_trm("近三年，同类产品累计合同业绩不少于10套"), _profile(4), use_llm=False)
    perf = next(c for c in rep.packages[0].checks if c.item == "业绩要求")
    assert perf.status == "不满足" and "要求不少于 10" in perf.reason
    assert rep.packages[0].verdict == "不可投"


def test_report_required_without_reports_fails():
    rep = qualify(_trm("近三年业绩", report_req="提供型式试验报告", report_required=True),
                  _profile(5), use_llm=False)
    rpt = next(c for c in rep.packages[0].checks if c.item == "检测/试验报告")
    assert rpt.status == "不满足"
    assert rep.packages[0].verdict == "不可投"


def test_undated_performance_flags_risk():
    rep = qualify(_trm("近5年，投标人具有信息系统实施业绩。", perf_years=5),
                  _profile(2, dated=False), use_llm=False)
    perf = next(c for c in rep.packages[0].checks if c.item == "业绩要求")
    assert perf.status == "风险" and "缺签约日期" in perf.reason


def test_no_performance_fails():
    rep = qualify(_trm("近三年业绩"), _profile(0), use_llm=False)
    assert rep.packages[0].verdict == "不可投"


def test_markdown_renders():
    md = qualify(_trm("近三年业绩"), _profile(1), use_llm=False).markdown()
    assert "可投性矩阵" in md and "| 业绩要求 |" in md
