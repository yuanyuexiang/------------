"""登录 / 当前用户 / 改密 / 用户管理（admin），以及鉴权中间件。

- 除 /api/health、/api/auth/login 外，所有 /api/* 都要 Bearer 令牌；校验通过后 request.state.user 可用，
  并把用户名写入操作人上下文（jb_store.auth.set_actor），事件/配置改动自动记 actor。
- 价格接口用 require_price()；管理接口用 require_admin()。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from jb_store import User, accounts, session
from jb_store import auth as au
from pydantic import ValidationError

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
    claims = au.token_claims(token) if token else None
    if not claims:
        return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
    with session() as s:
        u = s.get(User, claims['id'])
        if (u is None or not u.active or u.username != claims.get('u')
                or u.session_version != claims['v']):
            return JSONResponse({"detail": "账号不存在或已停用"}, status_code=401)
        info = au.user_out(u)
        info['_session_version'] = u.session_version
    if info['must_change_password'] and (path, request.method) not in {
        ('/api/auth/me', 'GET'), ('/api/auth/password', 'PUT')
    }:
        return JSONResponse({'detail': '请先修改初始密码', 'code': 'PASSWORD_CHANGE_REQUIRED'}, status_code=403)
    request.state.user = info
    au.set_actor(info['username'])
    try:
        response = await call_next(request)
        if path.startswith(('/api/auth/', '/api/users')):
            response.headers['Cache-Control'] = 'no-store'
        return response
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


# ---------- Thin transport adapters; account rules live in jb_store.accounts ----------

def execute(action, actor: str = '', target_id: str = '', kind: str = ''):
    error = None
    with session() as s:
        try:
            result = action(s)
        except accounts.AccountError as exc:
            # Commit failed-attempt counters and safe audit records, never submitted secrets.
            if kind:
                accounts.audit(s, actor, s.get(User, target_id) if target_id else None,
                               kind, False, {'reason': str(exc)})
            error = exc
    if error:
        raise HTTPException(error.status, str(error))
    return result


def validated(schema, body: dict):
    try:
        return schema.model_validate(body)
    except ValidationError:
        raise HTTPException(400, '账号资料格式不正确，请检查账号、姓名和权限字段') from None


@router.post('/auth/login')
def login(request: Request, body: dict):
    username, password = body.get('username', ''), body.get('password', '')
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 64 or len(password) > 128:
        raise HTTPException(400, '账号或密码格式不正确')
    return JSONResponse(execute(lambda s: accounts.authenticate(
        s, username.strip(), password, request.client.host if request.client else 'unknown')),
        headers={'Cache-Control': 'no-store'})


@router.get('/auth/me')
def me(request: Request):
    user = {k: v for k, v in current_user(request).items() if not k.startswith('_')}
    return {'user': user, 'dev_secret': au.using_dev_secret()}


@router.put('/auth/password')
def change_password(request: Request, body: dict):
    user = current_user(request)
    old, new = body.get('old_password', ''), body.get('new_password', '')
    if not isinstance(old, str) or not isinstance(new, str) or len(old) > 128:
        raise HTTPException(400, '密码格式不正确')
    return execute(lambda s: accounts.change_password(s, user, old, new),
                   user['username'], user['id'], 'change_password')


@router.get('/users')
def list_users(request: Request, q: str = Query('', max_length=64),
               role: Literal['', 'admin', 'member'] = '',
               active: Literal['', 'enabled', 'disabled'] = '',
               price: Literal['', 'allowed', 'denied'] = '',
               page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    require_admin(request)
    with session() as s:
        return accounts.list_page(s, q.strip(), role, active, price, page, page_size)


@router.get('/users/audit')
def account_audit(request: Request, target_id: str = Query('', max_length=12),
                  action: str = Query('', max_length=32), result: Literal['', 'success', 'failed'] = '',
                  page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    require_admin(request)
    with session() as s:
        return accounts.audit_page(s, target_id, action, result, page, page_size)


@router.post('/users', status_code=201)
def create_user(request: Request, body: dict):
    user = require_admin(request)
    value = validated(accounts.CreateAccount, body)
    return execute(lambda s: accounts.create(s, user, value), user['username'], kind='create')


@router.put('/users/{user_id}')
def update_user(request: Request, user_id: str, body: dict):
    user = require_admin(request)
    value = validated(accounts.UpdateAccount, body)
    return execute(lambda s: accounts.modify(s, user, user_id, value),
                   user['username'], user_id, 'update')


@router.post('/users/{user_id}/reset-password')
def reset_password(request: Request, user_id: str, body: dict):
    user = require_admin(request)
    password = body.get('confirmation_password', '')
    if not isinstance(password, str) or len(password) > 128:
        raise HTTPException(400, '确认密码格式不正确')
    return execute(lambda s: accounts.reset_password(s, user, user_id, password),
                   user['username'], user_id, 'reset_password')


@router.delete('/users/{user_id}')
def delete_user(request: Request, user_id: str):
    require_admin(request)
    raise HTTPException(409, '为保留历史身份，请停用账号；不再提供永久删除')


def bootstrap() -> bool:
    """启动时建默认管理员（仅空库）。"""
    with session() as s:
        return au.ensure_admin(s)
