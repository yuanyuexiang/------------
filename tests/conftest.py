"""共享 fixture：独立临时 SQLite 的 API 客户端，默认以自动创建的管理员登录（Bearer）。"""
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    import jb_llm
    import jb_store
    jb_store.reset_engine()
    from fastapi.testclient import TestClient
    from jb_api import main
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path / "uploads"))
    app = main.app
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": "Bearer " + r.json()["token"]})
        yield c
    jb_store.reset_engine()
    jb_llm.set_usage_hook(None)
    jb_llm.configure(base_url=None, model=None, temperature=None, timeout=None)


def login_as(client, username: str, password: str) -> None:
    """切换客户端身份（用户权限测试用）。"""
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.headers.update({"Authorization": "Bearer " + r.json()["token"]})
