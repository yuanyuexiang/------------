"""人员社保连续性（纪要 2026-09-10 客户流程）：月份推算、资格自检检查项、否决规则 SG-22。"""
from jb_agents.qualify import check_social_insurance, qualify
from jb_kb.models import CompanyProfile, Person
from jb_kb.social_insurance import missing_months, required_months, unit_mismatch
from jb_parser.trm import TRM, KeyTerms, PackageTRM
from jb_rules import Context, RuleSetting, review


def _people():
    return [Person(name="李晓波", social_insurance_unit="测试企业", social_insurance_months=["2026-07", "2026-08", "2026-09"]),
            Person(name="周宇", social_insurance_unit="测试企业", social_insurance_months=["2026-08", "2026-09"]),
            Person(name="黄长江", social_insurance_unit="测试企业")]


def test_required_months_cross_year():
    assert required_months("2026-09-10 09:30", 3) == ["2026-07", "2026-08", "2026-09"]
    assert required_months("2026-01-15", 3) == ["2025-11", "2025-12", "2026-01"]
    assert required_months("", 3) == [] and required_months("2026-09-10", 0) == []


def test_missing_and_unit():
    p = Person(name="a", social_insurance_unit="测试企业（南京）", social_insurance_months=["2026年7月", "2026/08", "2026-09"])
    assert missing_months(p, "2026-09-10", 3) == []
    assert missing_months(Person(name="b", social_insurance_months=["2026-09"]), "2026-09-10", 3) == ["2026-07", "2026-08"]
    assert not unit_mismatch(p, "测试企业(南京)")
    assert unit_mismatch(Person(name="c", social_insurance_unit="别家公司"), "测试企业")
    assert not unit_mismatch(Person(name="d"), "测试企业")        # 未录入不算不一致


def test_qualify_check():
    prof = CompanyProfile(name="测试企业", personnel=_people())
    c = check_social_insurance(prof, "2026-09-10 09:30")
    assert c.status == "不满足" and "周宇 缺 2026-07" in c.reason
    prof.personnel[1].social_insurance_months.append("2026-07")
    c = check_social_insurance(prof, "2026-09-10 09:30")
    assert c.status == "需人工" and "黄长江" in c.reason          # 未录入 → 需人工，不按缺省判满足
    prof.personnel[2].social_insurance_months = ["2026-07", "2026-08", "2026-09"]
    assert check_social_insurance(prof, "2026-09-10 09:30").status == "满足"
    assert check_social_insurance(prof, None).status == "需人工"
    prof.personnel[0].social_insurance_unit = "别家公司"
    assert check_social_insurance(prof, "2026-09-10").status == "不满足"
    assert check_social_insurance(CompanyProfile(name="x"), "2026-09-10") is None
    prof.personnel[0].available = False                             # 不投入的人不参与
    assert "李晓波" not in (check_social_insurance(prof, "2026-09-10").reason or "")


def test_qualify_report_uses_deadline():
    trm = TRM(batch_name="b", key_terms=KeyTerms(bid_deadline="2026-09-10 09:30"), packages=[PackageTRM(pkg_no="包1")])
    rep = qualify(trm, CompanyProfile(name="测试企业", personnel=_people()), use_llm=False)
    items = {c.item: c.status for c in rep.packages[0].checks}
    assert items["人员社保（截止前 3 个月连续）"] == "不满足" and rep.packages[0].verdict == "不可投"


def test_rule_sg22():
    prof = CompanyProfile(name="测试企业", personnel=_people())
    ctx = Context(trm=TRM(), pkg=PackageTRM(pkg_no="包1"), profile=prof, open_date="2026-09-10")
    rep = review(ctx)
    sg = [f for f in rep.findings if f.rule_id.startswith("SG-22")]
    assert {(f.level, f.message.split(" ")[0]) for f in sg} == {("否决", "周宇"), ("需人工", "黄长江")}
    # 参数可配：只要 2 个月 → 周宇齐全
    rep = review(ctx, {"SG-22": RuleSetting(rule_id="SG-22", params={"months": 2})})
    assert not [f for f in rep.findings if f.rule_id == "SG-22"]
    # 无开标日期 → 需人工，不否决
    ctx.open_date = None
    rep = review(ctx)
    assert all(f.level == "需人工" for f in rep.findings if f.rule_id.startswith("SG-22"))
    # 单位不一致 → 否决（与日期无关）
    prof.personnel[0].social_insurance_unit = "别家公司"
    assert any(f.rule_id == "SG-22" and f.level == "否决" and "李晓波" in f.message for f in review(ctx).findings)


def test_missing_unit_requires_manual_review():
    prof = CompanyProfile(name="测试企业", personnel=[Person(
        name="张三", social_insurance_months=["2026-07", "2026-08", "2026-09"])])
    assert check_social_insurance(prof, "2026-09-10").status == "需人工"
    ctx = Context(trm=TRM(), pkg=PackageTRM(), profile=prof, open_date="2026-09-10")
    assert any(f.rule_id == "SG-22b" and "单位未录入" in f.title
               for f in review(ctx).findings)


def test_invalid_deadline_requires_manual_review():
    prof = CompanyProfile(name="测试企业", personnel=[_people()[0]])
    assert check_social_insurance(prof, "待确认").status == "需人工"
    assert check_social_insurance(prof, "2026-09-10", months=0).status == "需人工"
    ctx = Context(trm=TRM(), pkg=PackageTRM(), profile=prof, open_date="待确认")
    assert any(f.rule_id == "SG-22b" for f in review(ctx).findings)
