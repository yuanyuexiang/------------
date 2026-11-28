"""Company intake uses verifiable fields, preserves drafts and feeds real parsed packages."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from docx import Document
from jb_kb import repo
from jb_kb.models import CompanyProfile, Performance, bid_profile_data
from jb_parser.trm import TRM, PackageTRM, QualificationItem
from jb_store import Project, session

COMPANY = "联调测试企业有限公司"
CODE = "91320100MA12345670"
URL = "/api/company-enrichment"
ROOT = Path(__file__).resolve().parents[1]
FUJIAN = ROOT / "服务/2/国网福建电力2026年第三次服务类竞争性谈判采购_采购文件包.zip"
SHAANXI = (ROOT / "物资/1/国网陕西省电力有限公司2026年第三次物资集中招标采购项目_招标文件包"
           / "分标044接入设备/包1_完整招标文件_1813604751495232.zip")


def original(lines):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    return ("原件.docx", buffer.getvalue(), "application/octet-stream")


def registry(*, name=COMPANY, code=CODE):
    return original(["营业执照", f"名称：{name}", f"统一社会信用代码：{code}",
                     "法定代表人：测试法人", "住所：测试登记住所", "成立日期：2019年3月2日",
                     "注册资本：人民币200万元", "类型：有限责任公司"])


def preview(client, file):
    response = client.post(URL + "/registry", files={"file": file})
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, result, selected=None, file=None):
    ids = [item["id"] for item in result["candidates"] if not item["unchanged"]]
    data = {"token": result["token"], "selected": ids if selected is None else selected}
    if file:
        return client.post(URL + "/registry/apply", data=data, files={"file": file})
    return client.post(URL + "/apply", json=data)


def create_company(client):
    file = registry()
    response = apply(client, preview(client, file), file=file)
    assert response.status_code == 201, response.text


def upload(client, company, lines):
    res = client.post(f"/api/profiles/{company}/attachments", files={"file": original(lines)})
    assert res.status_code == 201
    return res.json()["id"]


def test_signed_registry_preview_and_original_saved_on_confirmation(client, tmp_path):
    file = registry()
    found = preview(client, file)
    assert found["company"] == COMPANY
    assert client.get("/api/profiles").json() == []
    assert not list(tmp_path.rglob("原件.docx"))
    assert apply(client, {**found, "token": found["token"] + "0"}, file=file).status_code == 409
    assert apply(client, found, file=registry(name="另一家企业")).status_code == 409
    assert apply(client, found, ["field-address"], file=file).status_code == 409
    assert apply(client, found).status_code == 409
    assert apply(client, found, file=file).status_code == 201
    profile = client.get(f"/api/profiles/{COMPANY}").json()
    assert profile["registered_capital_wan"] == 200 and profile["company_type"] == "有限责任公司"
    assert profile["registration"] == {}
    item, = client.get(f"/api/profiles/{COMPANY}/attachments").json()
    assert item["kind"] == "certificate"
    assert {origin["attachment_id"] for origin in profile["field_sources"].values()} == {item["id"]}
    assert profile["field_sources"]["name"]["kind"] == "attachment"
    license_record, = profile["certificates"]
    assert license_record["number"] == CODE and license_record["attachments"] == [item["id"]]
    assert license_record["status"] == "draft"
    assert client.get(f"/api/attachments/{item['id']}").content == file[1]
    assert apply(client, found, file=file).status_code == 409
    assert client.post(URL + "/registry", files={"file": registry(name="另一家企业")}).status_code == 409


def test_registry_creation_rolls_back_saved_file_on_failed_record(client, tmp_path, monkeypatch):
    file = registry()
    found = preview(client, file)

    def fail(*args, **kwargs):
        raise ValueError("模拟证照保存失败")

    monkeypatch.setattr(repo, "upsert_item", fail)
    assert apply(client, found, file=file).status_code == 409
    assert client.get("/api/profiles").json() == []
    assert not list(tmp_path.rglob("*原件.docx"))


def test_rotated_license_uses_labelled_fields_and_checksum(client, monkeypatch):
    from jb_kb import attachment_import

    monkeypatch.setattr(attachment_import, "read_evidence",
                        lambda *args, **kwargs: {"pages": [], "notes": []})

    def rotated(_):
        yield f"营业执照\n统 一 社 会 信 用 代 码\n{CODE}\n名 称 {COMPANY}\n经营范围 去"

    monkeypatch.setattr(attachment_import, "registry_ocr", rotated)
    result = preview(client, ("扫描执照.png", b"mocked scanner bytes", "image/png"))
    values = {item["field"]: item["value"] for item in result["candidates"] if item["kind"] == "field"}
    assert values == {"name": COMPANY, "credit_code": CODE}


def test_public_credit_report_uses_cover_over_repeated_table_fields(client, monkeypatch):
    from jb_kb import attachment_import

    create_company(client)
    monkeypatch.setattr(attachment_import, "read_evidence", lambda *args, **kwargs: {
        "pages": [{"page": 1, "text": f"法人和非法人组织\n公共信用信息报告\n机构名称：{COMPANY}\n"
                                    f"统一社会信用代码：{CODE}\n报告生成日期    2026年10月20日\n"
                                    "报告出具单位     国家公共信用和地理空间信息中心"},
                  {"page": 2, "text": "报告生成日期   2026年10月20日    报告出具单位    其他列\n"
                                    "企业名称：附录提及的企业"}],
        "notes": [],
    })
    file = ("信用报告.pdf", b"mocked PDF text", "application/pdf")
    uploaded = client.post(f"/api/profiles/{COMPANY}/attachments", files={"file": file}).json()
    res = client.post(URL + "/attachment", json={"company": COMPANY, "attachment_id": uploaded["id"], "kind": "credit"})
    assert res.status_code == 200, res.text
    imported, = res.json()["candidates"]
    assert imported["title"] == "信用中国查询材料" and imported["data"]["valid_from"] == "2026-10-20"
    assert imported["origin"]["page"] == 1 and imported["origin"]["attachment_id"] == uploaded["id"]


def test_existing_online_award_can_be_completed_with_originals(client):
    create_company(client)
    with session() as s:
        repo.upsert_item(s, COMPANY, "performances", {
            "project": "历史服务项目", "buyer": "某采购单位", "status": "draft",
            "award_date": "2025-04-05", "award_amount_wan": 29.5,
            "evidence_origin": {"kind": "online", "title": "历史公告资料",
                                "url": "https://example.com/notice", "fetched_at": "2025-04-06T00:00:00Z"},
        })
    award, = client.get(f"/api/profiles/{COMPANY}/performances").json()
    assert award["status"] == "draft" and award["evidence"] == []
    assert award["signed_date"] == "" and award["amount_wan"] is None
    path = f"/api/profiles/{COMPANY}/performances/{award['id']}"
    assert client.put(path, json={**award, "status": "approved"}).status_code == 409

    other = "另一个企业"
    client.put(f"/api/profiles/{other}/main", json={})
    alien_id = upload(client, other, ["合同", "项目名称：历史服务项目"])
    res = client.post(URL + "/attachment", json={"company": COMPANY, "attachment_id": alien_id, "kind": "contract"})
    assert res.status_code == 409
    aid = upload(client, COMPANY, ["服务合同", f"乙方：{COMPANY}", "甲方：某采购单位",
                                  "项目名称：历史服务项目", "合同签订日期：2025年5月6日", "合同金额：32.0万元"])
    res = client.post(URL + "/attachment", json={"company": COMPANY, "attachment_id": aid, "kind": "contract"})
    assert res.status_code == 200, res.text
    contract, = res.json()["candidates"]
    assert contract["existing_id"] == award["id"]
    applied = apply(client, res.json())
    assert applied.status_code == 200, applied.text
    assert applied.json()["records_updated"] == 1
    award, = client.get(f"/api/profiles/{COMPANY}/performances").json()
    assert award["amount_wan"] == 32 and award["award_amount_wan"] == 29.5
    assert award["signed_date"] == "2025-05-06" and award["status"] == "draft"
    assert award["attachments"] == [aid] and award["evidence_fields"]["signed_date"]["attachment_id"] == aid
    assert client.put(path, json={**award, "status": "approved"}).status_code == 200
    assert client.delete(f"/api/profiles/{COMPANY}/attachments/{aid}").status_code == 200
    assert client.get(f"/api/profiles/{COMPANY}/performances").json()[0]["status"] == "draft"


def test_stale_company_field_and_wrong_entity_are_rejected(client):
    assert client.put(f"/api/profiles/{COMPANY}/main", json={"credit_code": CODE, "address": "原地址"}).status_code == 200
    aid = upload(client, COMPANY, ["营业执照", f"名称：{COMPANY}", f"统一社会信用代码：{CODE}",
                                  "住所：测试登记住所"])
    req = {"company": COMPANY, "attachment_id": aid, "kind": "registry"}
    found = client.post(URL + "/attachment", json=req).json()
    client.put(f"/api/profiles/{COMPANY}/main", json={"address": "人工更新地址"})
    assert apply(client, found, ["field-address"]).status_code == 409
    assert client.get(f"/api/profiles/{COMPANY}").json()["address"] == "人工更新地址"
    wrong = upload(client, COMPANY, ["营业执照", "名称：另一个企业", f"统一社会信用代码：{CODE}"])
    found = client.post(URL + "/attachment", json={**req, "attachment_id": wrong}).json()
    assert found["candidates"] == [] and found["checks"][0]["status"] == "需查看原件"


def test_paid_lookup_is_retired_and_official_sources_do_not_require_a_preview(client, monkeypatch):
    monkeypatch.setenv("JB_QCC_KEY", "synthetic-key")
    monkeypatch.setenv("JB_QCC_SECRET", "synthetic-secret")

    def no_request(*args, **kwargs):
        pytest.fail("企业资料补全不应调用外部收费接口")

    monkeypatch.setattr(httpx.Client, "stream", no_request)
    assert client.post(URL + "/online", json={"credit_code": CODE}).status_code == 410
    sources = client.get(URL + "/sources").json()
    assert {"registry", "credit", "certificate", "award"} <= {
        kind for source in sources for kind in source["materials"]
    }
    create_company(client)


def test_old_generated_versions_remain_identifiable():
    profile = CompanyProfile(name=COMPANY, performances=[Performance(project="旧业绩")])
    values = bid_profile_data(profile)
    assert "field_sources" not in values and "registry_details" not in values
    assert "evidence_origin" not in values["performances"][0]
    assert "award_amount_wan" not in values["performances"][0]


def test_checklist_uses_selected_package_and_official_credit_mode(client):
    create_company(client)
    trm = TRM(packages=[
        PackageTRM(pkg_no="包一", qualification=[QualificationItem(performance_req="请提供合同和发票")]),
        PackageTRM(pkg_no="包二", qualification=[QualificationItem(other_reqs={
            "信用要求": "国网供应商不良行为由采购人查询。须提供信用中国查询截图。",
        })]),
    ])
    with session() as s:
        p = Project(filename="sample.zip", zip_path="", status="confirmed", trm=trm.model_dump())
        s.add(p)
        s.flush()
        pid = p.id
    a = client.get(f"/api/projects/{pid}/requirements", params={"profile": COMPANY, "pkg_index": 0})
    b = client.get(f"/api/projects/{pid}/requirements", params={"profile": COMPANY, "pkg_index": 1})
    checks_a = {x["title"]: x for x in a.json()["material_checks"]}
    checks_b = {x["title"]: x for x in b.json()["material_checks"]}
    assert "信用中国" not in checks_a and "业绩证明" not in checks_b
    assert checks_a["业绩证明"]["status"] == "待核对：合同、发票"
    assert checks_b["国网供应商不良行为"]["status"] == "采购方核查"
    assert checks_b["信用中国"]["clauses"] and checks_b["信用中国"]["import_kind"] == "credit"
    assert b.json()["evidence"] == []


@pytest.mark.parametrize("sample", [
    pytest.param(FUJIAN, marks=pytest.mark.skipif(not FUJIAN.exists(), reason="缺少本地真实服务样本"), id="service"),
    pytest.param(SHAANXI, marks=pytest.mark.skipif(not SHAANXI.exists(), reason="缺少本地真实物资样本"), id="goods"),
])
def test_real_tender_from_import_to_word(client, sample):
    create_company(client)
    with sample.open("rb") as archive:
        job = client.post("/api/projects", files={"file": (sample.name, archive, "application/zip")})
    assert job.status_code == 202, job.text
    pid = job.json()["id"]
    trm = client.get(f"/api/projects/{pid}/trm").json()
    if sample == SHAANXI:
        package = trm["packages"][0]
        assert package["pkg_no"] == "包1" and sample.parent.name == "分标044接入设备"
        # The API receives a single archive, so confirm its original subdivision from the batch folder.
        for key, value in (("sub_no", "分标044"), ("sub_name", "接入设备")):
            assert package[key] in ("", value)
            package[key] = value
    assert trm["packages"] and client.put(f"/api/projects/{pid}/trm", json=trm).status_code == 200
    q = {"profile": COMPANY, "pkg_index": 0}
    checks = client.get(f"/api/projects/{pid}/requirements", params=q)
    assert checks.status_code == 200 and checks.json()["material_checks"]
    g = client.post(f"/api/projects/{pid}/generate", params={**q, "with_draft": False, "allow_incomplete": True})
    assert g.status_code == 202, g.text
    task = client.get(f"/api/tasks/{g.json()['task_id']}").json()
    assert task["status"] == "done", task.get("message")
    commercial = next(file for file in task["result"]["files"] if "商务" in file)
    response = client.get(f"/api/projects/{pid}/files/{commercial}")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as zf:
        assert CODE.encode() in zf.read("word/document.xml")


@pytest.mark.parametrize("kind,lines,expected_id,expected_value", [
    ("registry", ["营业执照", f"名称：{COMPANY}", f"统一社会信用代码：{CODE}",
                  "注册资本：人民币260万元"], "field-registered_capital_wan", 260),
    ("credit", ["信用中国", f"信用主体名称：{COMPANY}", "报告生成日期：2026年5月6日"],
     "record-0", {"cert_type": "信用查询", "validity_kind": "point_in_time", "valid_from": "2026-05-06"}),
    ("certificate", [f"获证组织：{COMPANY}", "证书名称：质量管理体系认证", "证书编号：DOC-QMS"],
     "record-0", {"number": "DOC-QMS"}),
    ("award", ["中标公告", f"中标供应商名称：{COMPANY}", "项目名称：另一个项目", "中标金额：100万元"],
     "record-0", {"award_amount_wan": 100}),
    ("financial", [f"编制单位：{COMPANY}", "报告年度：2025年", "营业收入：100万元"],
     "record-0", {"revenue_wan": 100, "report_kind": "comparative"}),
    ("test_report", [f"受检单位：{COMPANY}", "报告名称：型式试验", "报告编号：TR-26", "规格型号：MODEL-1"],
     "record-0", {"number": "TR-26", "covered_models": ["MODEL-1"]}),
])
def test_attachment_kinds_keep_literal_source_fields(client, kind, lines, expected_id, expected_value):
    assert client.put(f"/api/profiles/{COMPANY}/main", json={"credit_code": CODE}).status_code == 200
    aid = upload(client, COMPANY, lines)
    response = client.post(URL + "/attachment", json={"company": COMPANY, "attachment_id": aid, "kind": kind})
    assert response.status_code == 200, response.text
    candidate = next(x for x in response.json()["candidates"] if x["id"] == expected_id)
    assert candidate["origin"]["attachment_id"] == aid
    if isinstance(expected_value, dict):
        assert expected_value.items() <= candidate["data"].items()
    else:
        assert candidate["value"] == expected_value
