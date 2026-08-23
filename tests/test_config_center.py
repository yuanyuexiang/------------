"""配置中心：规则启停/调级/参数、评分模板库兜底、LLM 运行时覆盖与用量记账、API 端到端。"""
import os

import httpx
import jb_llm
import pytest
from jb_agents.scorer import score_package
from jb_docgen.techparams import ParamResponse, TechParamResult
from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM, PackageTRM, ScoringItem, ScoringRef, ScoringTemplate
from jb_rules import Context, RuleSetting, catalog, review

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUJIAN_XLSX_DIR = os.path.join(WS, "服务/2")


def _ctx_with_forbidden():
    tp = TechParamResult(spec_id="9999-1", responses=[
        ParamResponse(row=1, name="内存", required="不小于128GB", star=False, response="完全响应", verdict="unknown", reason="")])
    return Context(trm=TRM(), pkg=PackageTRM(pkg_no="包1"), profile=CompanyProfile(name="T"), tech_params=[tp])


def test_rule_catalog_and_settings():
    ids = {c["rule_id"] for c in catalog()}
    assert {"SG-16", "SIM-01", "DOC-01"} <= ids
    assert any(c["params"].get("phrases") for c in catalog() if c["rule_id"] == "SG-16")
    base = review(_ctx_with_forbidden())
    assert any(f.rule_id == "SG-16" and f.level == "否决" for f in base.findings)
    # 停用
    off = review(_ctx_with_forbidden(), {"SG-16": RuleSetting(rule_id="SG-16", enabled=False)})
    assert not any(f.rule_id == "SG-16" for f in off.findings)
    # 调级
    lvl = review(_ctx_with_forbidden(), {"SG-16": RuleSetting(rule_id="SG-16", level_override="扣分")})
    assert all(f.level == "扣分" for f in lvl.findings if f.rule_id == "SG-16")
    # 参数：换禁用词后"完全响应"不再命中
    prm = review(_ctx_with_forbidden(), {"SG-16": RuleSetting(rule_id="SG-16", params={"phrases": ["另一套话"]})})
    assert not any(f.rule_id == "SG-16" for f in prm.findings)


def test_scoring_library_fallback():
    lib_tpl = ScoringTemplate(name="FWSW01：服务类通用商务详评细则", kind="biz", items=[
        ScoringItem(element="管理体系认证（3-5 分）", content="取得4项=5分；1-3项=4分")])
    pkg = PackageTRM(pkg_no="包1", scoring_ref=ScoringRef(biz_template="FWSW01服务类通用商务详评细则", weight_biz=10))
    # TRM 里只有名字（docx 封面）没有细则 → 用模板库
    trm = TRM(scoring_templates=[ScoringTemplate(name="FWSW01：服务类通用商务详评细则", kind="biz")], packages=[pkg])
    rep = score_package(trm, pkg, CompanyProfile(name="T"), use_llm=False, library=[lib_tpl])
    assert rep.biz_max == 5 and any("模板库" in n for n in rep.notes)
    # 无库时明确提示缺细则，不乱配
    rep2 = score_package(trm, pkg, CompanyProfile(name="T"), use_llm=False)
    assert rep2.biz_max == 0 and any("缺少商务评分模板细则" in n for n in rep2.notes)
    # 名称不匹配的库模板不会被用
    rep3 = score_package(trm, pkg, CompanyProfile(name="T"), use_llm=False,
                         library=[ScoringTemplate(name="WZSW02：物资商务", kind="biz", items=lib_tpl.items)])
    assert rep3.biz_max == 0


def test_llm_configure_and_hook(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "http://env.example/v1")
    jb_llm.configure(base_url="http://override.example/v1", model="m-x", temperature=0.5)
    try:
        st = jb_llm.settings()
        assert st["base_url"] == "http://override.example/v1" and st["model"] == "m-x" and st["temperature"] == 0.5
        assert st["key_configured"] and jb_llm.available()
        recs = []
        jb_llm.set_usage_hook(recs.append)
        with pytest.raises(httpx.HTTPError):
            jb_llm.chat("hi", timeout=1.0, purpose="test")     # 端点不可达 → 抛错但仍记账
        assert recs and recs[0]["purpose"] == "test" and recs[0]["ok"] is False and recs[0]["error"]
        jb_llm.configure(base_url=None, model=None, temperature=None)
        assert jb_llm.settings()["base_url"] == "http://env.example/v1"
    finally:
        jb_llm.set_usage_hook(None)
        jb_llm.configure(base_url=None, model=None, temperature=None, timeout=None)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    import jb_store
    jb_store.reset_engine()
    from fastapi.testclient import TestClient
    from jb_api.main import app
    with TestClient(app) as c:
        yield c
    jb_store.reset_engine()
    jb_llm.set_usage_hook(None)
    jb_llm.configure(base_url=None, model=None, temperature=None, timeout=None)


def test_config_api(client):
    # 规则
    rules = client.get("/api/config/rules").json()
    assert rules["levels"][0] == "否决" and any(r["rule_id"] == "SG-16" and r["enabled"] for r in rules["rules"])
    assert client.put("/api/config/rules/SG-16", json={"enabled": False, "level_override": "扣分", "params": {"phrases": ["x"]}}).status_code == 200
    r = next(x for x in client.get("/api/config/rules").json()["rules"] if x["rule_id"] == "SG-16")
    assert r["enabled"] is False and r["level_override"] == "扣分" and r["params"] == {"phrases": ["x"]}
    assert client.put("/api/config/rules/SG-16", json={"params": {"bogus": 1}}).status_code == 400
    assert client.put("/api/config/rules/SG-16", json={"level_override": "严重"}).status_code == 400
    assert client.put("/api/config/rules/NOPE", json={}).status_code == 404
    assert client.delete("/api/config/rules/SG-16").status_code == 200
    assert next(x for x in client.get("/api/config/rules").json()["rules"] if x["rule_id"] == "SG-16")["enabled"] is True
    # 评分模板库
    body = {"name": "JS-TEST 技术详评", "kind": "tech", "items": [{"element": "总体（6-10 分）", "content": "优 9-10", "score_min": 6, "score_max": 10}]}
    t = client.post("/api/config/scoring-templates", json=body).json()
    assert t["item_count"] == 1 and t["origin"] == "manual"
    assert client.post("/api/config/scoring-templates", json=body).status_code == 409
    assert client.put(f"/api/config/scoring-templates/{t['id']}", json={"note": "n", "items": body["items"] * 2}).json()["item_count"] == 2
    assert client.get("/api/config/scoring-templates").json()[0]["name"] == "JS-TEST 技术详评"
    assert client.get(f"/api/config/scoring-templates/{t['id']}").json()["items"][0]["score_max"] == 10
    assert client.delete(f"/api/config/scoring-templates/{t['id']}").status_code == 200
    assert client.get("/api/config/scoring-templates").json() == []
    # LLM 设置：密钥拒收；覆盖项保存并生效；测试连接在未配置时返回 ok=False 而非 500
    assert client.put("/api/config/llm", json={"api_key": "secret"}).status_code == 400
    assert client.put("/api/config/llm", json={"temperature": 3}).status_code == 400
    out = client.put("/api/config/llm", json={"base_url": "http://x.example/v1", "model": "m1", "temperature": "0.2"}).json()
    assert out["effective"]["model"] == "m1" and out["effective"]["temperature"] == 0.2
    g = client.get("/api/config/llm").json()
    assert g["effective"]["base_url"] == "http://x.example/v1" and g["effective"]["key_configured"] is False
    assert g["available"] is False and g["usage"]["calls"] == 0
    t = client.post("/api/config/llm/test").json()
    assert t["ok"] is False and "未配置" in t["error"]
    # 清除覆盖
    assert client.put("/api/config/llm", json={}).json()["saved"] == {}


@pytest.mark.skipif(not os.path.isdir(FUJIAN_XLSX_DIR), reason="样本缺失")
def test_upload_scoring_template_xlsx(client, tmp_path):
    """用真实福建样本里的评分细则 xlsx 上传入库。"""
    import glob

    from jb_parser.unpack import unpack
    z = os.path.join(FUJIAN_XLSX_DIR, "国网福建电力2026年第三次服务类竞争性谈判采购_采购文件包.zip")
    if not os.path.exists(z):
        pytest.skip("样本缺失")
    res = unpack(z, str(tmp_path / "unpacked"))        # 递归解压（zip 套 zip）
    xlsx = sorted(p for p in glob.glob(os.path.join(res.root, "**", "*.xlsx"), recursive=True) if "商务评分模板" in p)
    assert xlsx, "样本里应有商务评分模板 xlsx"
    with open(xlsx[0], "rb") as f:
        data = f.read()
    name = os.path.basename(xlsx[0])
    r = client.post("/api/config/scoring-templates/upload", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "biz" and r.json()["item_count"] >= 5
    assert client.post("/api/config/scoring-templates/upload", files={"file": (name, data, "application/octet-stream")}).status_code == 409
    assert client.post("/api/config/scoring-templates/upload?overwrite=true", files={"file": (name, data, "application/octet-stream")}).status_code == 201
