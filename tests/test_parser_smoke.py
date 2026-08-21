"""S1 冒烟回归：对真实样本（tests/fixtures 指向工作区 物资/服务 目录）跑解析。

运行：python3 -m pytest tests/ -q
样本缺失时跳过（CI 环境无样本包）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from packages.jb_parser import parse  # noqa: E402

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根，样本在 物资/、服务/
SHAANXI_PKG = os.path.join(
    WS, "物资/1/国网陕西省电力有限公司2026年第三次物资集中招标采购项目_招标文件包/"
        "分标051综合网管/包1_完整招标文件_1813604751495232.zip")
SHAANXI_PKG_ALT = os.path.join(
    WS, "物资/1/国网陕西省电力有限公司2026年第三次物资集中招标采购项目_招标文件包/"
        "分标051综合网管/包1_完整招标文件_1813606452501308.zip")
FUJIAN_BATCH = os.path.join(WS, "服务/2/国网福建电力2026年第三次服务类竞争性谈判采购_采购文件包.zip")


def _first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


@pytest.mark.skipif(_first_existing(SHAANXI_PKG, SHAANXI_PKG_ALT) is None, reason="样本缺失")
def test_shaanxi_package():
    trm = parse(_first_existing(SHAANXI_PKG, SHAANXI_PKG_ALT))
    assert trm.batch_no == "W-2026-SNGW-Z03"
    assert trm.terminology == "投标"
    assert len(trm.prenotice) >= 70
    assert len(trm.rejection_rules) >= 40
    assert len(trm.submission_table) >= 40
    assert len(trm.packages) == 1
    pkg = trm.packages[0]
    assert pkg.sub_no == "分标051" and pkg.pkg_no == "包1"
    assert len(pkg.materials) >= 2
    assert len(pkg.spec_docs) >= 3
    stars = [r for s in pkg.spec_docs for r in s.param_rows if r.star]
    assert len(stars) >= 10  # 综合网管规范书含大量★项


@pytest.mark.skipif(not os.path.exists(FUJIAN_BATCH), reason="样本缺失")
def test_fujian_negotiation_batch():
    trm = parse(FUJIAN_BATCH)
    assert trm.terminology == "应答"      # 竞谈术语体系
    assert len(trm.packages) == 3         # 包14/15/16
    assert len(trm.rejection_rules) >= 40
