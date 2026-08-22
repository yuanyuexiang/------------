"""知识库多表：聚合存取往返、旧 JSON 行兼容、单条 CRUD、有效期预警、附件。纯包层（不依赖 apps/）。"""
import datetime as dt
import os

import pytest
from jb_kb import attachments as att
from jb_kb import models as kbm
from jb_kb import repo
from jb_kb.expiry import expiry_report
from jb_kb.models import Boilerplate, Certificate, CompanyProfile, Performance
from jb_store import Profile, session


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/kb.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    import jb_store
    jb_store.reset_engine()
    jb_store.init_db()
    yield
    jb_store.reset_engine()


def _profile() -> CompanyProfile:
    return CompanyProfile(
        name="测试企业A", credit_code="91320000TEST", registered_capital_wan=3000,
        certificates=[Certificate(name="质量管理体系认证证书", number="Q-1", valid_until="2027-01-31"),
                      Certificate(name="安全生产许可证", number="A-2")],
        performances=[Performance(project="某综合能源项目", buyer="国网某公司", buyer_is_end_user=True,
                                  amount_wan=120.5, signed_date="2025-03-01", evidence=["合同", "发票"])],
        boilerplates=[Boilerplate(topic="售后服务", title="响应时限", text="2 小时响应", approved=True),
                      Boilerplate(topic="培训", title="待审", text="草稿", approved=False)],
        test_reports=[kbm.TestReport(name="型式试验报告", agency="电科院", valid_until="2026-09-15")],
    )


def test_save_load_roundtrip_and_counts(db):
    with session() as s:
        repo.save_profile(s, "测试企业A", _profile())
    with session() as s:
        cp = repo.load_profile(s, "测试企业A")
        assert cp is not None and cp.registered_capital_wan == 3000
        assert [c.number for c in cp.certificates] == ["Q-1", "A-2"]
        assert all(c.id for c in cp.certificates)                     # 入库后分配 id
        assert cp.performances[0].buyer_is_end_user is True and cp.performances[0].amount_wan == 120.5
        assert repo.counts(s, "测试企业A") == {"certificates": 2, "personnel": 0, "performances": 1,
                                             "financials": 0, "products": 0, "test_reports": 1, "boilerplates": 2}
        # 主档 JSON 不再含列表（列表只在子表）
        assert "certificates" not in s.get(Profile, "测试企业A").data


def test_resave_keeps_ids_and_removes_dropped(db):
    with session() as s:
        repo.save_profile(s, "测试企业A", _profile())
    with session() as s:
        cp = repo.load_profile(s, "测试企业A")
        keep_id = cp.certificates[0].id
        cp.certificates = cp.certificates[:1]
        cp.certificates[0].valid_until = "2028-01-01"
        repo.save_profile(s, "测试企业A", cp)
    with session() as s:
        cp = repo.load_profile(s, "测试企业A")
        assert [c.id for c in cp.certificates] == [keep_id] and cp.certificates[0].valid_until == "2028-01-01"


def test_legacy_json_profile_is_split_on_first_read(db):
    """拆表前整体 JSON 行：首次读取就地迁入子表（幂等），之后聚合/单条/计数口径一致。"""
    legacy = _profile().model_dump()
    for x in legacy["certificates"]:
        x.pop("id")                                   # 旧数据没有 id
    with session() as s:
        s.add(Profile(name="旧企业", credit_code="x", data=legacy))
    with session() as s:
        items = repo.list_items(s, "旧企业", "certificates")
        assert len(items) == 2 and all(i.id for i in items)
        assert "certificates" not in s.get(Profile, "旧企业").data
        assert repo.counts(s, "旧企业")["certificates"] == 2
        assert len(repo.load_profile(s, "旧企业").boilerplates) == 2
    with session() as s:                              # 再读不重复迁入
        assert repo.counts(s, "旧企业")["certificates"] == 2


def test_item_crud(db):
    with session() as s:
        repo.save_profile(s, "测试企业A", _profile())
        c = repo.upsert_item(s, "测试企业A", "certificates", {"name": "高新技术企业证书", "valid_until": "2026-12-31"})
        assert c.id
        cid = c.id
    with session() as s:
        c2 = repo.upsert_item(s, "测试企业A", "certificates", {"id": cid, "name": "高新技术企业证书", "level": "国家级"})
        assert c2.level == "国家级"
        assert repo.get_item(s, "certificates", cid).level == "国家级"
        with pytest.raises(ValueError):
            repo.upsert_item(s, "别家", "certificates", {"id": cid, "name": "窜改"})
        assert repo.delete_item(s, "测试企业A", "certificates", cid)
        assert repo.get_item(s, "certificates", cid) is None
        assert not repo.delete_item(s, "测试企业A", "certificates", cid)
        # 话术库 approved 布尔映射到 status 列
        items = repo.list_items(s, "测试企业A", "boilerplates")
        assert {i.title: i.approved for i in items} == {"响应时限": True, "待审": False}


def test_expiry_report_levels():
    cp = _profile()
    today = dt.date(2026, 8, 22)
    rep = expiry_report(cp, on_date=today, within_days=90)
    by_name = {r.name: r for r in rep}
    assert by_name["型式试验报告"].level == "d30" and by_name["型式试验报告"].days_left == 24
    assert by_name["安全生产许可证"].level == "unknown"            # 未录入不猜
    assert "质量管理体系认证证书" not in by_name                    # 90 天外不列
    assert expiry_report(cp, on_date=dt.date(2027, 3, 1))[0].level == "expired"
    assert [r.level for r in rep] == ["d30", "unknown"]            # 排序：紧急在前


def test_attachments_store_dedup_delete(db):
    with session() as s:
        repo.save_profile(s, "测试企业A", _profile())
        a = att.store(s, "测试企业A", "营业执照.pdf", b"%PDF-1.4 fake", kind="certificate", content_type="application/pdf")
        assert a.id and a.size == 13 and os.path.exists(att.absolute_path(a))
        dup = att.store(s, "测试企业A", "营业执照-副本.pdf", b"%PDF-1.4 fake", kind="certificate")
        assert dup.id == a.id                                       # 同内容去重
        assert [x.id for x in att.list_attachments(s, "测试企业A", "certificate")] == [a.id]
        assert att.delete_attachment(s, "测试企业A", a.id) and not os.path.exists(att.absolute_path(a))
        assert att.get_attachment(s, a.id) is None
