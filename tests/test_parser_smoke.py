"""S1 冒烟回归：对真实样本（tests/fixtures 指向工作区 物资/服务 目录）跑解析。

运行：python3 -m pytest tests/ -q
样本缺失时跳过（CI 环境无样本包）。
"""
import os

import pytest
from jb_parser import parse

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
    # 前附表语义归一
    assert trm.key_terms.validity_days == 90
    assert trm.key_terms.deposit_mode == "none"      # 本批次不要求保证金
    assert trm.key_terms.paperless is True           # 不接收纸质投标文件
    assert trm.key_terms.bid_deadline == "2026-05-25 09:30"   # 招标公告 5.1
    assert trm.key_terms.bid_open_time == "2026-05-25 09:30" and trm.key_terms.bid_open_note == "同投标截止时间"


@pytest.mark.skipif(not os.path.exists(FUJIAN_BATCH), reason="样本缺失")
def test_fujian_negotiation_batch():
    trm = parse(FUJIAN_BATCH)
    assert trm.terminology == "应答"      # 竞谈术语体系
    assert len(trm.packages) == 3         # 包14/15/16
    assert len(trm.rejection_rules) >= 40
    # 评分细则模板（官方 xlsx）结构化
    kinds = {t.kind for t in trm.scoring_templates}
    assert "biz" in kinds and "tech" in kinds and "price" in kinds
    biz = next(t for t in trm.scoring_templates if t.kind == "biz")
    assert len(biz.items) >= 8            # FWSW01 商务细则条目
    # 四列前附表变体 + 竞谈保证金模式
    assert trm.key_terms.validity_days == 90
    assert trm.key_terms.deposit_mode == "诚信担保"
    assert trm.key_terms.bid_deadline == "2026-06-15 08:00"   # "首次应答文件提交的截止时间：…8:00时"


JIANGSU_BATCH = os.path.join(WS, "服务/1/国网江苏省电力有限公司2026年服务第四次公开招标采购_招标文件包.zip")


@pytest.mark.skipif(not os.path.exists(JIANGSU_BATCH), reason="样本缺失")
def test_jiangsu_service_batch():
    trm = parse(JIANGSU_BATCH)
    assert len(trm.packages) == 2         # 包147/148
    # 江苏版双行表头/三渠道提交表变体
    assert len(trm.submission_table) >= 30
    channels = {c for it in trm.submission_table for c in it.channels}
    assert any("e采" in c or "ECP" in c for c in channels)
    assert trm.key_terms.paperless is True
    assert trm.key_terms.bid_deadline == "2026-08-07 14:00"
    assert trm.key_terms.bid_open_time is None                # 公告未写开标时间，不猜
