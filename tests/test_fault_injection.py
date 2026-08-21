"""错误注入验收（开发计划 S4）：预埋 20 处典型错误，规则引擎 + 价格校验 + 数值引擎应拦截 ≥95%（≥19 处）。

每处错误对应国网否决情形表/典型案例库中的真实否决原因，见 docs/国网物资与服务投标-场景细化方案 §8.2。
"""
from jb_agents.price import PriceLine, PriceSheet, validate
from jb_docgen.numeric import compare
from jb_docgen.techparams import ParamResponse, TechParamResult, fill_spec
from jb_kb.models import Certificate, CompanyProfile, Performance, Product
from jb_parser.trm import TRM, PackageTRM, SpecDoc, SpecParamRow, SubmissionItem
from jb_rules import Context, review


def _catch(findings, rule_prefix: str, level: str = None) -> bool:
    return any(f.rule_id.startswith(rule_prefix) and (level is None or f.level == level) for f in findings)


def test_twenty_injected_faults_are_caught():
    caught: dict[str, bool] = {}

    # ---- 技术参数类（案例 11）----
    spec = SpecDoc(spec_id="9999-1", structured=True, param_rows=[
        SpecParamRow(row=1, name="衰减", required="★≤0.21", star=True),
        SpecParamRow(row=2, name="内存", required="不小于128GB", star=False),
        SpecParamRow(row=3, name="授权", required="★不小于256个", star=True),
        SpecParamRow(row=4, name="端口", required="★8个GE电口,6个光口", star=True),
    ])
    product = Product(model="X", name="综合网管", category="综合网管",
                      params={"衰减系数": "13.2", "内存": "完全响应", "授权": "200个", "GE电口": "8个"})
    tp = fill_spec(spec, product)
    by = {x.row: x for x in tp.responses}
    caught["F01 响应值不满足要求值(13.2 vs ≤0.21)"] = by[1].verdict == "deviation"
    caught["F02 以'完全响应'代替具体值"] = by[2].verdict == "missing" and "禁止" in by[2].response
    caught["F03 ★授权 200<256"] = by[3].verdict == "deviation"
    caught["F04 光口无参数→不得冒充"] = by[4].verdict == "missing" and "光口" in by[4].response
    caught["F05 单位不可比不判满足"] = compare("≥400kVA", "400kg").verdict == "unknown"
    caught["F06 万元/元量级(0.1TB<128GB)"] = compare("不小于128GB", "0.1TB").verdict == "deviation"

    # ---- 价格类（案例 6/7/8/12、前附表 3.2.5）----
    sheet = PriceSheet(pkg_no="包1", max_price_yuan=500000, lines=[
        PriceLine(row=1, desc="A", qty=1, unit_price_ex_tax=0, vat_rate=13, spec_id="9999-2"),          # 零单价
        PriceLine(row=2, desc="A", qty=1, unit_price_ex_tax=100000, vat_rate=17, spec_id="9999-2"),     # 税率 17 非法定
        PriceLine(row=3, desc="A", qty=1, unit_price_ex_tax=100000.1234567, vat_rate=13, spec_id="9999-2"),  # 小数 7 位
        PriceLine(row=4, desc="B", qty=1, unit_price_ex_tax=100000, vat_rate=13, spec_id="9999-3"),
        PriceLine(row=5, desc="B", qty=1, unit_price_ex_tax=150000, vat_rate=13, spec_id="9999-3"),     # 不平衡 +20%
    ])
    issues = validate(sheet, peer_avg=4500, over_limit_pct=10)   # 总价 45 万 vs 均价 4500 → 百倍
    rules = {i.rule for i in issues}
    caught["F07 零单价"] = "零单价" in rules
    caught["F08 税率非法定"] = "税率错误" in rules
    caught["F09 单价小数位>6"] = "小数位" in rules
    caught["F10 万元当元(百倍异常)"] = "货币单位" in rules
    caught["F11 报价超限"] = "报价超限" in rules
    caught["F12 不平衡报价±12%"] = "不平衡报价" in rules
    caught["F13 超最高限价"] = "超最高限价" in rules

    # ---- 文件/资格类（否决表形式评审、案例 2/5/9/13）----
    profile = CompanyProfile(
        name="测试企业", credit_code="9100X",
        certificates=[Certificate(name="型式试验报告", cert_type="报告", valid_until="2026-01-01")],   # 开标前过期
        performances=[Performance(project="P1", evidence=["合同"]),                                      # 缺发票
                      Performance(project="P2", evidence=["合同", "发票"], buyer_is_end_user=False)],    # 非最终用户
    )
    tp2 = TechParamResult(spec_id="9999-1", responses=[
        ParamResponse(1, "x", "≥1", True, "【待补充：x】", "missing"),
    ])
    ctx = Context(
        trm=TRM(batch_no="W-2026-SNGW-Z03", submission_table=[SubmissionItem(item="投标函")]),
        pkg=PackageTRM(pkg_no="包1", allow_consortium=False,
                       spec_docs=[SpecDoc(spec_id="D068-500009678-00001", structured=False)]),     # 非结构化规范
        profile=profile, tech_params=[tp2],
        docx_todos={"技术文件_包1.docx": ["x"]},
        doc_texts={"技术文件_包1.docx": "本文件由 其他公司 编制 W-2025-SNGW-Z02 …"},             # 无投标人名、旧批次号
        other_pkg_texts={"包2": "本文件由 其他公司 编制 W-2025-SNGW-Z02 …"},                        # 多包雷同
        open_date="2026-05-25",
    )
    f = review(ctx).findings
    caught["F14 待补充残留(阻断导出)"] = _catch(f, "DOC-01", "否决")
    caught["F15 投标人名称缺失"] = _catch(f, "DOC-02", "否决")
    caught["F16 含其他批次编号(复制历史标书)"] = _catch(f, "DOC-04", "否决")
    caught["F17 报告开标前过期"] = _catch(f, "SG-13", "否决")
    caught["F18 业绩缺发票"] = _catch(f, "SG-05")
    caught["F19 非最终用户业绩"] = _catch(f, "SG-06", "否决")
    caught["F20 非结构化规范未附件响应提示"] = _catch(f, "SG-17")
    caught["F21 多包雷同"] = _catch(f, "SIM-01")

    missed = [k for k, v in caught.items() if not v]
    rate = (len(caught) - len(missed)) / len(caught)
    assert len(caught) >= 20
    assert rate >= 0.95, f"拦截率 {rate:.0%}，漏检：{missed}"
