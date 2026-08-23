"""登录 / 当前用户 / 改密 / 用户管理（admin），以及鉴权中间件。

- 除 /api/health、/api/auth/login 外，所有 /api/* 都要 Bearer 令牌；校验通过后 request.state.user 可用，
  并把用户名写入操作人上下文（jb_store.auth.set_actor），事件/配置改动自动记 actor。
- 价格接口用 require_price()；管理接口用 require_admin()。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from jb_store import User, session
from jb_store import auth as au

router = APIRouter(prefix="/api", tags=["auth"])

PUBLIC_PATHS = {"/api/health", "/api/auth/login"}


# ---------- 中间件 ----------

async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    token = ""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    elif "token" in request.query_params:           # 文件下载链接（<a href>）无法带 header
        token = request.query_params["token"]
    username = au.verify_token(token) if token else None
    if not username:
        return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
    with session() as s:
        u = au.get_user(s, username)
        if u is None or not u.active:
            return JSONResponse({"detail": "账号不存在或已停用"}, status_code=401)
        info = au.user_out(u)
    request.state.user = info
    au.set_actor(username)
    try:
        return await call_next(request)
    finally:
        au.set_actor("")


def current_user(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "未登录")
    return u


def require_admin(request: Request) -> dict:
    u = current_user(request)
    if u["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return u


def require_price(request: Request) -> dict:
    u = current_user(request)
    if not u["can_view_price"]:
        raise HTTPException(403, "无价格数据查看权限（请管理员在「用户与权限」开启）")
    return u


# ---------- 登录 / 自己 ----------

@router.post("/auth/login")
def login(body: dict):
    username, password = (body.get("username") or "").strip(), body.get("password") or ""
    with session() as s:
        u = au.authenticate(s, username, password)
        if u is None:
            raise HTTPException(401, "用户名或密码错误")
        return {"token": au.issue_token(u.username), "user": au.user_out(u), "dev_secret": au.using_dev_secret()}


@router.get("/auth/me")
def me(request: Request):
    return {"user": current_user(request), "dev_secret": au.using_dev_secret()}


@router.put("/auth/password")
def change_password(request: Request, body: dict):
    u = current_user(request)
    old, new = body.get("old_password") or "", body.get("new_password") or ""
    if len(new) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    with session() as s:
        row = au.get_user(s, u["username"])
        if row is None or not au.verify_password(old, row.password_hash):
            raise HTTPException(400, "原密码错误")
        au.set_password(row, new, must_change=False)
    return {"ok": True}


# ---------- 用户管理（admin） ----------

@router.get("/users")
def list_users(request: Request):
    require_admin(request)
    with session() as s:
        return [au.user_out(u) for u in au.list_users(s)]


@router.post("/users", status_code=201)
def create_user(request: Request, body: dict):
    require_admin(request)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or len(password) < 6:
        raise HTTPException(400, "用户名必填，初始密码至少 6 位")
    with session() as s:
        try:
            u = au.create_user(s, username, password, display_name=body.get("display_name") or "",
                               role=body.get("role") or "member", can_view_price=bool(body.get("can_view_price")),
                               must_change_password=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return au.user_out(u)


@router.put("/users/{user_id}")
def update_user(request: Request, user_id: str, body: dict):
    """改显示名/角色/价格权限/启停；reset_password 给新初始密码（登录后强制改）。"""
    me_ = require_admin(request)
    with session() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "用户不存在")
        role = body.get("role", u.role)
        if role not in au.ROLES:
            raise HTTPException(400, "角色只能是 admin 或 member")
        active = bool(body.get("active", u.active))
        # 不能把最后一个管理员降级/停用（包括自己）
        if u.role == "admin" and (role != "admin" or not active) and au.admin_count(s) <= 1:
            raise HTTPException(400, "至少保留一个启用的管理员")
        if u.username == me_["username"] and (role != "admin" or not active):
            raise HTTPException(400, "不能降级或停用自己")
        u.display_name = body.get("display_name", u.display_name) or u.username
        u.role, u.active = role, active
        u.can_view_price = bool(body.get("can_view_price", u.can_view_price))
        if body.get("reset_password"):
            if len(body["reset_password"]) < 6:
                raise HTTPException(400, "初始密码至少 6 位")
            au.set_password(u, body["reset_password"], must_change=True)
        s.flush()
        return au.user_out(u)


@router.delete("/users/{user_id}")
def delete_user(request: Request, user_id: str):
    """删除用户（历史事件里的 actor 仍保留用户名）。"""
    me_ = require_admin(request)
    with session() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "用户不存在")
        if u.username == me_["username"]:
            raise HTTPException(400, "不能删除自己")
        if u.role == "admin" and au.admin_count(s) <= 1:
            raise HTTPException(400, "至少保留一个启用的管理员")
        s.delete(u)
    return {"ok": True}


def bootstrap() -> bool:
    """启动时建默认管理员（仅空库）。"""
    with session() as s:
        return au.ensure_admin(s)
