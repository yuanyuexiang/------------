"""价格校验 / 基准价模拟 / 规则引擎（合成数据）。"""
from jb_agents.price import PriceLine, PriceSheet, simulate_interval_avg, validate
from jb_docgen.techparams import ParamResponse, TechParamResult
from jb_kb.models import CompanyProfile, Performance
from jb_parser.trm import TRM, PackageTRM, SpecDoc, SubmissionItem
from jb_rules import Context, review


def _sheet(**kw):
    lines = [PriceLine(row=1, desc="综合网管", qty=2, unit_price_ex_tax=120000, vat_rate=13, spec_id="9999-1"),
             PriceLine(row=2, desc="综合网管", qty=1, unit_price_ex_tax=121000, vat_rate=13, spec_id="9999-1")]
    return PriceSheet(pkg_no="包1", lines=lines, **kw)


def test_price_clean():
    assert [i for i in validate(_sheet()) if i.level == "否决"] == []


def test_price_zero_and_vat():
    s = _sheet()
    s.lines[0].unit_price_ex_tax = 0
    s.lines[1].vat_rate = 17
    rules = {i.rule for i in validate(s)}
    assert {"零单价", "税率错误"} <= rules


def test_price_unbalanced():
    s = _sheet()
    s.lines[1].unit_price_ex_tax = 200000          # 同规范同物资偏离 >12%
    assert any(i.rule == "不平衡报价" for i in validate(s))


def test_price_unit_magnitude_and_limit():
    s = _sheet(max_price_yuan=300000)
    issues = validate(s, peer_avg=3600)             # 万元当元：总价 36 万 vs 均价 3600
    assert any(i.rule == "货币单位" for i in issues)
    assert any(i.rule == "超最高限价" for i in issues)   # 含税 40.7 万 > 30 万


def test_simulation_range():
    sim = simulate_interval_avg(100.0, [95, 98, 102, 105, 110], c_candidates=[0.0, 0.02, 0.05])
    assert sim.score_range[0] <= sim.score_range[1] <= 30
    assert len(sim.detail) == 3
    assert sim.benchmark_range[0] < sim.benchmark_range[1]


def test_rules_engine_blocks_on_forbidden_and_todos():
    tp = TechParamResult(spec_id="9999-1", responses=[
        ParamResponse(1, "x", "≥1", True, "完全响应", "unknown"),
        ParamResponse(2, "y", "≥2", True, "【待补充：y】", "missing"),
        ParamResponse(3, "z", "≤0.21", False, "13.2", "deviation", "不满足：13.2 ≤ 0.21"),
    ])
    ctx = Context(
        trm=TRM(batch_no="W-2026-T-01", submission_table=[SubmissionItem(item="投标函")]),
        pkg=PackageTRM(pkg_no="包1", allow_consortium=False, spec_docs=[SpecDoc(spec_id="D068-1", structured=False)]),
        profile=CompanyProfile(name="测试企业", performances=[Performance(project="P", evidence=["合同"])]),
        tech_params=[tp],
        docx_todos={"技术文件.docx": ["y"]},
        doc_texts={"技术文件.docx": "测试企业 W-2025-OLD-01 正文"},
    )
    rep = review(ctx)
    ids = {f.rule_id for f in rep.findings}
    assert rep.blocked
    assert {"SG-16", "SG-16b", "SG-15", "SG-17", "DOC-01", "DOC-03", "DOC-04", "SG-05", "SG-06b", "Q-01", "SG-21", "SUB-01"} <= ids
    assert "| 否决 |" in rep.markdown()
