"""用户与权限：登录/令牌、默认管理员改密、用户管理、角色与价格门禁、actor 审计。"""
from conftest import login_as


def test_login_and_me(client):
    r = client.get("/api/auth/me").json()
    assert r["user"]["username"] == "admin" and r["user"]["role"] == "admin" and r["user"]["must_change_password"]
    assert r["dev_secret"] is True                      # 未设 JB_SECRET_KEY 时提示
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    anon = client.get("/api/projects", headers={"Authorization": ""})
    assert anon.status_code == 401
    assert client.get("/api/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/api/projects", headers={"Authorization": "Bearer x.y"}).status_code == 401


def test_change_password(client):
    assert client.put("/api/auth/password", json={"old_password": "nope", "new_password": "abcdef"}).status_code == 400
    assert client.put("/api/auth/password", json={"old_password": "admin", "new_password": "123"}).status_code == 400
    assert client.put("/api/auth/password", json={"old_password": "admin", "new_password": "abcdef"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 401
    login_as(client, "admin", "abcdef")
    assert client.get("/api/auth/me").json()["user"]["must_change_password"] is False


def test_users_roles_price_gate_and_actor(client):
    # 建成员（默认不可见价格）
    r = client.post("/api/users", json={"username": "zhang", "password": "zhang123", "display_name": "张三"})
    assert r.status_code == 201 and r.json()["role"] == "member" and r.json()["can_view_price"] is False
    uid = r.json()["id"]
    assert client.post("/api/users", json={"username": "zhang", "password": "zhang123"}).status_code == 400   # 重名
    assert client.post("/api/users", json={"username": "li", "password": "123"}).status_code == 400           # 密码太短
    # 最后一个管理员不能降级/停用/删除
    me = client.get("/api/auth/me").json()["user"]
    assert client.put(f"/api/users/{me['id']}", json={"role": "member"}).status_code == 400
    assert client.put(f"/api/users/{me['id']}", json={"active": False}).status_code == 400
    assert client.delete(f"/api/users/{me['id']}").status_code == 400
    # 管理员建一份档案；成员登录后：不能管用户/配置，能用知识库，不能看价格
    assert client.put("/api/profiles/测试企业", json={"name": "测试企业"}).status_code == 200
    login_as(client, "zhang", "zhang123")
    assert client.get("/api/users").status_code == 403
    assert client.put("/api/config/rules/SG-16", json={"enabled": False}).status_code == 403
    assert client.put("/api/config/llm", json={"model": "x"}).status_code == 403
    assert client.get("/api/config/rules").status_code == 200              # 只读可以
    assert client.post("/api/profiles/测试企业/certificates", json={"name": "ISO9001"}).status_code == 201
    sheet = {"pkg_no": "包1", "lines": []}
    assert client.post("/api/projects/x/price/validate", json=sheet).status_code == 403
    # 管理员开价格权限后可用；重置密码后强制改密
    login_as(client, "admin", "admin")
    assert client.put(f"/api/users/{uid}", json={"can_view_price": True, "reset_password": "newpass1"}).json()["can_view_price"] is True
    assert client.post("/api/auth/login", json={"username": "zhang", "password": "zhang123"}).status_code == 401
    login_as(client, "zhang", "newpass1")
    assert client.get("/api/auth/me").json()["user"]["must_change_password"] is True
    assert client.post("/api/projects/x/price/validate", json=sheet).status_code == 200
    # 停用后令牌失效
    login_as(client, "admin", "admin")
    client.put(f"/api/users/{uid}", json={"active": False})
    login_as_fail = client.post("/api/auth/login", json={"username": "zhang", "password": "newpass1"})
    assert login_as_fail.status_code == 401
    assert client.delete(f"/api/users/{uid}").status_code == 200
