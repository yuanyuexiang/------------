"""数值比较引擎单测（S3 验收：覆盖 ≥90%）。"""
import pytest
from jb_docgen.numeric import compare, parse_quantity, parse_requirement


@pytest.mark.parametrize("req,actual,verdict", [
    ("≥400kVA", "500kVA", "satisfied"),
    ("≥400kVA", "0.5MVA", "satisfied"),          # 单位换算
    ("≥400kVA", "315kVA", "deviation"),
    ("不小于128GB内存", "256GB", "satisfied"),
    ("不小于128GB", "0.1TB", "deviation"),          # 100GB < 128GB
    ("≤0.21", "0.19", "satisfied"),
    ("≤0.21", "13.2", "deviation"),                 # 典型案例库：OPGW 衰减 13.2 vs 0.21
    ("不大于5%", "3%", "satisfied"),
    ("不超过 30ms", "0.02s", "satisfied"),          # 20ms
    ("2.6GHz以上", "2600MHz", "satisfied"),
    ("大于2GHz", "2GHz", "deviation"),               # 严格大于
    ("100~240V", "220V", "satisfied"),
    ("100~240V", "380V", "deviation"),
    ("4*1920GB SSD", "4*2000GB", "satisfied"),
    ("4*1920GB SSD", "2*4000GB", "deviation"),       # 数量不足
    ("配置网络设备授权不小于256个", "512个", "satisfied"),
    ("≥8个GE电口", "8口", "satisfied"),
])
def test_compare(req, actual, verdict):
    assert compare(req, actual).verdict == verdict, compare(req, actual).reason


def test_text_requirement_is_unknown():
    v = compare("支持SDN协议实现大规模网络设备配置自动化", "支持")
    assert v.verdict == "unknown"


def test_unit_mismatch_is_unknown_not_satisfied():
    v = compare("≥400kVA", "400kg")
    assert v.verdict == "unknown" and "单位不可比" in v.reason


def test_unparseable_actual_is_unknown():
    assert compare("≥128GB", "完全响应").verdict == "unknown"   # 禁止以"完全响应"代替具体值


def test_parse_quantity_multiplier():
    q = parse_quantity("2*32Core@2.6GHz CPU")
    assert q.count == 2 and q.unit == "core" and q.value == 32


def test_parse_requirement_kinds():
    assert parse_requirement("★不小于10套").kind == "ge"
    assert parse_requirement("不超过3").kind == "le"
    assert parse_requirement("10~20mm").kind == "range"
    assert parse_requirement("应支持与异厂家设备兼容").kind == "text"
