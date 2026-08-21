"""企业建档回归：从南京百恩特真实投标文件建档（样本缺失自动跳过）。"""
import os

import pytest
from jb_kb import build_profile

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = [
    os.path.join(WS, "服务/2/132673-9012008-2037-南京百恩特自动化科技有限公司-云平台电子商务文件-包14.包15.包16.docx"),
    os.path.join(WS, "服务/2/132673-9012008-2037-南京百恩特自动化科技有限公司-云平台电子技术文件-包16.docx"),
]


@pytest.mark.skipif(not all(os.path.exists(d) for d in DOCS), reason="样本缺失")
def test_build_baiente_profile():
    p = build_profile(DOCS)
    assert p.name == "南京百恩特自动化科技有限公司"
    assert p.credit_code == "913201115804606862"
    assert p.registered_capital_wan == 3000.0
    assert p.staff_total == 88 and p.staff_technical == 80
    assert len(p.performances) == 4                       # 业绩：合同+发票齐全
    assert all(set(x.evidence) == {"合同", "发票"} for x in p.performances)
    assert len(p.personnel) >= 4                          # 人员证件七件套
    assert any("社保证明" in x.credentials for x in p.personnel)
    assert len(p.financials) == 3                         # 近三年财务
    assert all(f.revenue_wan for f in p.financials)
