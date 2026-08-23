"""用户与权限：密码哈希、签名令牌、操作人上下文。纯标准库（pbkdf2 + HMAC），不引入新依赖。

- 角色只有 admin / member，价格可见性是按人的开关（can_view_price）；admin 天然可见。
- 令牌：HMAC-SHA256 签名的 JSON（username/exp），密钥 JB_SECRET_KEY（未设置时用开发默认值并告警）。
- 操作人：请求中间件 / worker 任务开头调 set_actor()，log_event 等落盘时自动带上。
"""
from __future__ import annotations

import base64
import contextvars
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User

ROLES = ("admin", "member")
ROLE_CN = {"admin": "管理员", "member": "成员"}
DEFAULT_ADMIN = ("admin", "admin")           # 首次启动自动建，must_change_password=True
_DEV_SECRET = "jinbang-dev-secret-change-me"
_PBKDF2_ROUNDS = 200_000

_actor: contextvars.ContextVar[str] = contextvars.ContextVar("jb_actor", default="")


def set_actor(username: str) -> None:
    _actor.set(username or "")


def current_actor() -> str:
    return _actor.get()


# ---------- 密码 ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_b64, digest_b64 = stored.split("$")
        salt, digest = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
    return hmac.compare_digest(calc, digest)


# ---------- 令牌 ----------

def secret_key() -> str:
    return os.environ.get("JB_SECRET_KEY") or _DEV_SECRET


def using_dev_secret() -> bool:
    return not os.environ.get("JB_SECRET_KEY")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(username: str, hours: float = 12.0) -> str:
    payload = {"u": username, "exp": int((dt.datetime.utcnow() + dt.timedelta(hours=hours)).timestamp())}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret_key().encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[str]:
    """返回用户名；签名错/过期返回 None。"""
    try:
        body, sig = token.split(".")
        expect = _b64(hmac.new(secret_key().encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(dt.datetime.utcnow().timestamp()):
            return None
        return payload.get("u") or None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


# ---------- 用户 ----------

def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "role_cn": ROLE_CN.get(u.role, u.role), "can_view_price": u.can_view_price or u.role == "admin",
            "active": u.active, "must_change_password": u.must_change_password,
            "created_at": u.created_at.isoformat(), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


def get_user(s: Session, username: str) -> Optional[User]:
    return s.execute(select(User).where(User.username == username)).scalars().first()


def list_users(s: Session) -> list[User]:
    return list(s.execute(select(User).order_by(User.created_at)).scalars())


def create_user(s: Session, username: str, password: str, display_name: str = "", role: str = "member",
                can_view_price: bool = False, must_change_password: bool = True) -> User:
    if role not in ROLES:
        raise ValueError("角色只能是 admin 或 member")
    if get_user(s, username) is not None:
        raise ValueError("用户名已存在")
    u = User(username=username, display_name=display_name or username, password_hash=hash_password(password),
             role=role, can_view_price=can_view_price, must_change_password=must_change_password)
    s.add(u)
    s.flush()
    return u


def authenticate(s: Session, username: str, password: str) -> Optional[User]:
    u = get_user(s, username)
    if u is None or not u.active or not verify_password(password, u.password_hash):
        return None
    u.last_login_at = dt.datetime.utcnow()
    return u


def set_password(u: User, password: str, must_change: bool = False) -> None:
    u.password_hash = hash_password(password)
    u.must_change_password = must_change


def ensure_admin(s: Session) -> bool:
    """没有任何用户时建默认管理员（admin/admin，强制改密）。返回是否新建。"""
    if s.execute(select(User.id).limit(1)).first() is not None:
        return False
    pw = os.environ.get("JB_ADMIN_PASSWORD") or DEFAULT_ADMIN[1]
    create_user(s, DEFAULT_ADMIN[0], pw, display_name="管理员", role="admin", can_view_price=True,
                must_change_password=not os.environ.get("JB_ADMIN_PASSWORD"))
    return True


def admin_count(s: Session) -> int:
    return len([u for u in list_users(s) if u.role == "admin" and u.active])
