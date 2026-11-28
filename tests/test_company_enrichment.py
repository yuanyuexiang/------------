"""Company intake uses verifiable fields, preserves drafts and feeds real parsed packages."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from docx import Document
from jb_kb import online
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


@pytest.fixture
def licensed(monkeypatch):
    monkeypatch.setenv("JB_QCC_KEY", "synthetic-key")
    monkeypatch.setenv("JB_QCC_SECRET", "synthetic-secret")
    winner = {"Name": COMPANY, "CreditCode": CODE, "WinBidAmt": "29.5万元"}
    notice = {"Title": "历史服务项目", "ProjectNo": "TEST-01",
              "PublishDate": "2025-04-05", "ContentUrl": "https://example.com/notice",
              "WinBidUnitList": [winner], "BidInviUnitList": [{"Name": "某采购单位"}]}
    responses = {
        "ECIV4/GetBasicDetailsByName": {"Name": COMPANY, "CreditCode": CODE,
                                      "OperName": "测试法人", "Address": "测试登记住所",
                                      "StartDate": "2019-03-02", "RegisteredCapital": "2000000",
                                      "RegisteredCapitalUnit": "元", "RegisteredCapitalCCY": "人民币",
                                      "BelongOrg": "某市场监管局"},
        "ECICertification/SearchCertification": [{"Name": "质量管理体系认证", "No": "TEST-QMS",
                                                  "EndDate": "2028-01-01", "InstitutionList": ["测试机构"]}],
        "TenderCheck/GetList": {"Data": [
            notice, {**notice, "Title": "同名企业公告", "WinBidUnitList": [{**winner, "CreditCode": "OTHER"}]},
        ]},
        "ExceptionCheck/GetList": {"VerifyResult": 0, "Data": []},
        "SeriousIllegalCheck/GetList": {"VerifyResult": 1, "Data": [{"AddDate": "2024-01-01"}]},
    }

    def lookup(_client, _key, _secret, path, **params):
        if path == "TenderCheck/GetList":
            assert params["keyword"] == COMPANY and params["msgType"] == "4"
        return responses[path]

    monkeypatch.setattr(online, "_lookup", lookup)
    return responses


def preview(client, *, company=""):
    response = client.post(URL + "/online", json={"credit_code": CODE, "company": company})
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, result, selected=None):
    ids = [item["id"] for item in result["candidates"] if not item["unchanged"]]
    return client.post(URL + "/apply", json={"token": result["token"],
                                            "selected": ids if selected is None else selected})


def upload(client, company, lines):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buffer = BytesIO()
    doc.save(buffer)
    res = client.post(f"/api/profiles/{company}/attachments",
                      files={"file": ("原件.docx", buffer.getvalue(), "application/octet-stream")})
    assert res.status_code == 201
    return res.json()["id"]


def test_signed_preview_adoption_and_originals(client, licensed):
    found = preview(client)
    assert found["checks"][-2]["status"] == "指定来源未检出"
    assert found["checks"][-1]["status"] == "查到记录"
    assert all("同名企业" not in item["title"] for item in found["candidates"])
    assert client.get("/api/profiles").json() == []
    assert apply(client, {**found, "token": found["token"] + "0"}).status_code == 409
    assert apply(client, found).status_code == 200
    profile = client.get(f"/api/profiles/{COMPANY}").json()
    assert profile["registered_capital_wan"] == 200
    assert profile["registry_details"]["登记机关"] == "某市场监管局"
    assert profile["registration"] == {}
    assert profile["field_sources"]["address"]["kind"] == "online"
    award, = profile["performances"]
    assert award["status"] == "draft" and award["evidence"] == []
    assert award["award_date"] == "2025-04-05" and award["award_amount_wan"] == 29.5
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


def test_stale_company_field_and_wrong_entity_are_rejected(client, licensed):
    src = licensed["ECIV4/GetBasicDetailsByName"]
    assert client.put(f"/api/profiles/{COMPANY}/main", json={"credit_code": CODE, "address": "原地址"}).status_code == 200
    found = preview(client, company=COMPANY)
    client.put(f"/api/profiles/{COMPANY}/main", json={"address": "人工更新地址"})
    assert apply(client, found, ["field-address"]).status_code == 409
    assert client.get(f"/api/profiles/{COMPANY}").json()["address"] == "人工更新地址"
    src["CreditCode"] = "WRONG"
    found = preview(client, company=COMPANY)
    assert found["candidates"] == [] and found["checks"][0]["status"] == "无法查询"


def test_unconfigured_provider_promotes_official_entries_without_values(client, monkeypatch):
    monkeypatch.delenv("JB_QCC_KEY", raising=False)
    monkeypatch.delenv("JB_QCC_SECRET", raising=False)
    found = preview(client)
    assert found["candidates"] == [] and not found["token"]
    assert found["checks"][0]["status"] == "未配置" and len(found["sources"]) >= 5


def test_provider_transport_uses_signed_headers(monkeypatch):
    monkeypatch.setattr(online.time, "time", lambda: 1700000000)

    def response(request):
        assert request.url.host == "api.qichacha.com"
        assert request.url.params["keyword"] == CODE
        assert request.headers["Timespan"] == "1700000000"
        assert len(request.headers["Token"]) == 32 and request.headers["Token"].isupper()
        return httpx.Response(200, json={"Status": "200", "Result": {"Name": COMPANY}})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert online._lookup(client, "key", "secret", "verified-schema", keyword=CODE) == {"Name": COMPANY}


def test_old_generated_versions_remain_identifiable():
    profile = CompanyProfile(name=COMPANY, performances=[Performance(project="旧业绩")])
    values = bid_profile_data(profile)
    assert "field_sources" not in values and "registry_details" not in values
    assert "evidence_origin" not in values["performances"][0]
    assert "award_amount_wan" not in values["performances"][0]


def test_checklist_uses_selected_package_and_official_credit_mode(client, licensed):
    assert apply(client, preview(client)).status_code == 200
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
    assert checks_b["信用中国"]["clauses"] and b.json()["evidence"] == []


@pytest.mark.parametrize("sample", [
    pytest.param(FUJIAN, marks=pytest.mark.skipif(not FUJIAN.exists(), reason="缺少本地真实服务样本"), id="service"),
    pytest.param(SHAANXI, marks=pytest.mark.skipif(not SHAANXI.exists(), reason="缺少本地真实物资样本"), id="goods"),
])
def test_real_tender_from_import_to_word(client, licensed, sample):
    assert apply(client, preview(client)).status_code == 200
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
