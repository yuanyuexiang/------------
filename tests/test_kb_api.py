"""知识库 API：主档整体存取 → 条目 CRUD → 附件上传/下载 → 有效期看板。独立临时 SQLite。"""
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    import jb_store
    jb_store.reset_engine()
    from fastapi.testclient import TestClient
    from jb_api.main import app
    with TestClient(app) as c:
        yield c
    jb_store.reset_engine()


def test_kb_flow(client):
    name = "测试企业A"
    r = client.put(f"/api/profiles/{name}", json={"name": name, "credit_code": "91320000TEST",
                                                   "certificates": [{"name": "ISO9001", "valid_until": "2026-09-01"}]})
    assert r.status_code == 200
    lst = client.get("/api/profiles").json()
    assert lst[0]["name"] == name and lst[0]["counts"]["certificates"] == 1

    # 条目 CRUD
    r = client.post(f"/api/profiles/{name}/certificates", json={"name": "高新技术企业证书", "valid_until": "2026-08-30"})
    assert r.status_code == 201 and r.json()["id"]
    cid = r.json()["id"]
    r = client.put(f"/api/profiles/{name}/certificates/{cid}",           # PUT=整体替换
                   json={"name": "高新技术企业证书", "level": "国家级", "valid_until": "2026-08-30"})
    assert r.json()["level"] == "国家级"
    assert len(client.get(f"/api/profiles/{name}/certificates").json()) == 2
    assert client.get(f"/api/profiles/{name}/unknown_kind").status_code == 404
    assert client.get(f"/api/profiles/{name}").json()["certificates"][1]["id"] == cid   # 聚合视图含新条目

    # 有效期看板（按开标日推算）
    rep = client.get(f"/api/profiles/{name}/expiry", params={"on": "2026-08-22"}).json()
    assert rep["summary"]["d30"] == 2 and rep["items"][0]["name"] == "高新技术企业证书"
    assert client.get(f"/api/profiles/{name}/expiry", params={"on": "bad"}).status_code == 400

    # 附件
    r = client.post(f"/api/profiles/{name}/attachments", params={"kind": "certificate"},
                    files={"file": ("证书.pdf", b"%PDF fake", "application/pdf")})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.get(f"/api/profiles/{name}/attachments").json()[0]["filename"] == "证书.pdf"
    d = client.get(f"/api/attachments/{aid}")
    assert d.status_code == 200 and d.content == b"%PDF fake"
    assert client.delete(f"/api/profiles/{name}/attachments/{aid}").status_code == 200
    assert client.get(f"/api/attachments/{aid}").status_code == 404

    assert client.delete(f"/api/profiles/{name}/certificates/{cid}").status_code == 200
    assert client.delete(f"/api/profiles/{name}").status_code == 200
    assert client.get(f"/api/profiles/{name}").status_code == 404
    assert client.post("/api/profiles/不存在/certificates", json={"name": "x"}).status_code == 404
