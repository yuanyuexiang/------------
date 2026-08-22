"""API 端到端：上传→异步解析（进程内）→TRM→确认→档案→资格自检。独立临时 SQLite，不污染开发库。"""
import os

import pytest

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(WS, "服务/1/国网江苏省电力有限公司2026年服务第四次公开招标采购_招标文件包.zip")


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


def test_health_reports_task_mode(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["task_mode"] == "inprocess"


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="样本缺失")
def test_full_flow(client):
    with open(SAMPLE, "rb") as f:
        r = client.post("/api/projects", files={"file": ("pkg.zip", f, "application/zip")})
    assert r.status_code == 202
    pid, tid = r.json()["id"], r.json()["task_id"]
    # TestClient 在响应后同步执行 BackgroundTasks → 此时任务已完成
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "done" and t["result"]["packages"] == 2
    assert client.get(f"/api/projects/{pid}").json()["status"] == "parsed"
    trm = client.get(f"/api/projects/{pid}/trm").json()
    assert trm["packages"][0]["pkg_no"] == "包147"
    # 人工确认：改一个字段后提交，后续以确认版为准
    trm["key_terms"]["validity_days"] = 120
    assert client.put(f"/api/projects/{pid}/trm", json=trm).status_code == 200
    assert client.get(f"/api/projects/{pid}/trm", params={"confirmed": True}).json()["key_terms"]["validity_days"] == 120
    assert client.get(f"/api/projects/{pid}").json()["status"] == "confirmed"
    # 项目管理：截止时间来自公告、阶段随环节推进、事件时间线
    pj = client.get(f"/api/projects/{pid}").json()
    assert pj["deadline"] == "2026-08-07 14:00" and pj["stage"] == "confirmed" and pj["pkg_nos"] == ["包147", "包148"]
    # 档案 upsert + 资格自检（不启用 LLM）
    profile = {"name": "测试企业", "credit_code": "9100X",
               "performances": [{"project": "某信息系统实施", "evidence": ["合同", "发票"]}]}
    assert client.put("/api/profiles/测试企业", json=profile).status_code == 200
    assert client.get("/api/profiles").json()[0]["name"] == "测试企业"
    q = client.post(f"/api/projects/{pid}/qualify", params={"profile": "测试企业"}).json()
    assert {p["pkg_no"] for p in q["report"]["packages"]} == {"包147", "包148"}
    assert "可投性矩阵" in q["markdown"]
    # 文件生成 + 下载
    g = client.post(f"/api/projects/{pid}/generate", params={"profile": "测试企业", "pkg_index": 0})
    assert g.status_code == 202
    gt = client.get(f"/api/tasks/{g.json()['task_id']}").json()
    assert gt["status"] == "done" and gt["result"]["summary"]["export_blocked"] is True
    assert client.get(f"/api/projects/{pid}/files/{gt['result']['files'][0]}").status_code == 200
    # 合规审查 + 递交矩阵 + 价格
    rv = client.post(f"/api/projects/{pid}/review", params={"profile": "测试企业"}).json()
    assert rv["blocked"] and any(f["rule_id"] == "DOC-01" for f in rv["findings"])
    sm = client.get(f"/api/projects/{pid}/submission-matrix").json()
    assert len(sm["rows"]) >= 30
    sim = client.post("/api/price/simulate", params={"my_price": 100}, json=[95, 98, 102, 105]).status_code
    assert sim in (200, 422)  # 参数形态以 OpenAPI 为准；此处仅验证路由存在
    # 项目详情：阶段到 reviewed，结果摘要按包分桶，时间线完整
    d = client.get(f"/api/projects/{pid}/detail").json()
    assert d["stage"] == "reviewed"
    assert d["results"]["qualify"]["verdicts"]["包147"] and d["results"]["generate"]["包147"]["export_blocked"] is True
    assert d["results"]["review"]["包147"]["blocked"] is True
    assert [e["kind"] for e in d["events"]][::-1] == ["parsed", "confirmed", "qualified", "generated", "reviewed"]
    assert len(d["files"]) >= 2 and len(d["package_list"]) == 2
    # 人工改截止时间（之后重新解析不覆盖）、标记结果、列表排序/过滤、删除
    assert client.patch(f"/api/projects/{pid}", json={"deadline": "bad"}).status_code == 400
    pj = client.patch(f"/api/projects/{pid}", json={"deadline": "2026-09-01 09:30", "notes": "影子投标"}).json()
    assert pj["deadline_manual"] and pj["days_left"] is not None
    pj = client.patch(f"/api/projects/{pid}", json={"outcome": "submitted"}).json()
    assert pj["stage"] == "submitted" and pj["active"] and pj["outcome_cn"] == "已递交"
    assert client.patch(f"/api/projects/{pid}", json={"outcome": "won"}).json()["active"] is False
    assert client.get("/api/projects", params={"active": True}).json() == []
    assert client.get("/api/projects", params={"active": False}).json()[0]["id"] == pid
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404 and client.get("/api/projects").json() == []


def test_reject_non_zip(client):
    r = client.post("/api/projects", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 400
