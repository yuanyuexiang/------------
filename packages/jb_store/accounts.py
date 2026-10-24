"""企业账号生命周期。事务内验证、串行保护、审计和限流均在领域层完成。"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from . import auth
from .models import AccountAudit, AuthThrottle, Setting, User


class AccountError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class CreateAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{2,32}$')
    display_name: str = Field(default='', max_length=64)
    role: Literal['admin', 'member'] = 'member'
    can_view_price: StrictBool = False
    confirmation_password: SecretStr = SecretStr('')


class UpdateAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: Optional[str] = Field(default=None, max_length=64)
    role: Optional[Literal['admin', 'member']] = None
    can_view_price: Optional[StrictBool] = None
    active: Optional[StrictBool] = None
    confirmation_password: SecretStr = SecretStr('')


def lock_accounts(s: Session) -> None:
    """Shared database mutex: SQLite write lock / PostgreSQL row lock, until commit.

    Always acquire before reading a user for any lifecycle mutation. The upsert is
    also safe when the lock row has never been created, across API workers.
    """
    if s.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    s.execute(insert(Setting).values(key='account_write_lock', value={})
              .on_conflict_do_nothing(index_elements=['key']))
    s.execute(update(Setting).where(Setting.key == 'account_write_lock').values(value={}))


def audit(s: Session, actor: str, target: Optional[User], action: str, ok: bool,
          detail: Optional[dict] = None, target_name: str = '') -> None:
    s.add(AccountAudit(actor=actor[:64], target_id=target.id if target else '',
                       target_name=target.username if target else target_name[:64],
                       action=action, ok=ok, detail=detail or {}))


def safe_state(user: User) -> dict:
    return {k: getattr(user, k) for k in ('display_name', 'role', 'can_view_price', 'active')}


def throttle_rows(s: Session, keys: list[tuple[str, int]]) -> list[AuthThrottle]:
    now = dt.datetime.utcnow()
    # Bound storage for expired rate-limit entries; audit history is retained.
    s.execute(delete(AuthThrottle).where(AuthThrottle.started_at < now - dt.timedelta(days=1)))
    rows = []
    for key, limit in keys:
        digest = hashlib.sha256(key.encode()).hexdigest()
        row = s.get(AuthThrottle, digest)
        if row is None:
            row = AuthThrottle(key=digest, failures=0, started_at=now)
            s.add(row)
        if row.started_at < now - dt.timedelta(minutes=15):
            row.started_at, row.failures = now, 0
        if row.failures >= limit:
            raise AccountError('尝试次数过多，请在 15 分钟后重试', 429)
        rows.append(row)
    return rows


def confirm_identity(s: Session, actor: User, password: str) -> None:
    if not password:
        raise AccountError('请填写当前管理员密码以确认此操作')
    rows = throttle_rows(s, [('confirm:' + actor.id, 5)])
    if not auth.verify_password(password, actor.password_hash):
        for row in rows:
            row.failures += 1
        raise AccountError('身份验证失败，请检查当前管理员密码', 403)
    for row in rows:
        row.failures = 0


def authenticate(s: Session, username: str, password: str, peer: str) -> dict:
    lock_accounts(s)
    # Account and connection-source buckets are independent; no untrusted forwarding headers.
    try:
        rows = throttle_rows(s, [('login:' + username.lower(), 5), ('peer:' + peer, 100)])
    except AccountError:
        audit(s, '', None, 'login', False, {'reason': '登录失败次数过多'}, username)
        raise
    user = auth.get_user(s, username)
    valid = auth.verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not user.active or not valid:
        for row in rows:
            row.failures += 1
        audit(s, '', user, 'login', False, {'reason': '账号或密码无效'}, username)
        raise AccountError('用户名或密码错误', 401)
    rows[0].failures = 0
    user.last_login_at = dt.datetime.utcnow()
    audit(s, user.username, user, 'login', True)
    return {'token': auth.issue_token(user.username, user=user), 'user': auth.user_out(user),
            'dev_secret': auth.using_dev_secret()}


_DUMMY_HASH = auth.hash_password(secrets.token_urlsafe(24))


def actor_for_write(s: Session, info: dict, admin: bool = True) -> User:
    lock_accounts(s)
    actor = s.get(User, info['id'])
    if (actor is None or not actor.active
            or actor.session_version != info.get('_session_version')):
        raise AccountError('登录已失效，请重新登录', 401)
    if admin and (actor.role != 'admin' or actor.must_change_password):
        raise AccountError('需要已完成改密的管理员账号', 403)
    return actor


def create(s: Session, info: dict, body: CreateAccount) -> dict:
    actor = actor_for_write(s, info)
    if body.role == 'admin' or body.can_view_price:
        confirm_identity(s, actor, body.confirmation_password.get_secret_value())
    if auth.get_user(s, body.username):
        raise AccountError('用户名已存在')
    password = secrets.token_urlsafe(18)
    user = auth.create_user(s, body.username, password, body.display_name.strip(),
                           body.role, body.can_view_price if body.role != 'admin' else False, True)
    audit(s, actor.username, user, 'create', True, {'after': safe_state(user)})
    return {'user': auth.user_out(user), 'temporary_password': password}


def modify(s: Session, info: dict, user_id: str, body: UpdateAccount) -> dict:
    actor = actor_for_write(s, info)
    user = s.get(User, user_id)
    if user is None:
        raise AccountError('用户不存在', 404)
    patch = body.model_dump(exclude_unset=True, exclude={'confirmation_password'})
    if any(value is None for value in patch.values()):
        raise AccountError('用户字段不能为 null')
    before = safe_state(user)
    role, active = patch.get('role', user.role), patch.get('active', user.active)
    if user.id == actor.id and (role != 'admin' or not active):
        raise AccountError('不能降级或停用自己')
    if user.active and user.role == 'admin' and (role != 'admin' or not active):
        if auth.admin_count(s) <= 1:
            raise AccountError('至少保留一个启用的管理员')
    sensitive = (role != user.role or active != user.active
                 or (role != 'admin' and 'can_view_price' in patch
                     and patch['can_view_price'] != user.can_view_price))
    if sensitive:
        confirm_identity(s, actor, body.confirmation_password.get_secret_value())
    for key, value in patch.items():
        setattr(user, key, (value.strip() or user.username) if key == 'display_name' else value)
    # Admin price access is inherited, never store an implicit grant for later demotion.
    if role == 'admin':
        user.can_view_price = False
    if sensitive:
        user.session_version += 1
    after = safe_state(user)
    if before != after:
        action = 'enable' if active and not before['active'] else 'disable' if not active and before['active'] else 'update'
        audit(s, actor.username, user, action, True, {'before': before, 'after': after})
    return auth.user_out(user)


def reset_password(s: Session, info: dict, user_id: str, confirmation: str) -> dict:
    actor = actor_for_write(s, info)
    user = s.get(User, user_id)
    if user is None:
        raise AccountError('用户不存在', 404)
    if user.id == actor.id:
        raise AccountError('请通过右上角“修改密码”修改自己的密码')
    if not user.active:
        raise AccountError('请先恢复账号，再重置密码')
    confirm_identity(s, actor, confirmation)
    password = secrets.token_urlsafe(18)
    auth.set_password(user, password, must_change=True)
    audit(s, actor.username, user, 'reset_password', True)
    return {'user': auth.user_out(user), 'temporary_password': password}


def change_password(s: Session, info: dict, old: str, new: str) -> dict:
    actor = actor_for_write(s, info, admin=False)
    if not 15 <= len(new) <= 128 or not new.strip():
        raise AccountError('新密码须为 15～128 位，可使用长口令')
    confirm_identity(s, actor, old)
    if auth.verify_password(new, actor.password_hash):
        raise AccountError('新密码不能与原密码相同')
    auth.set_password(actor, new, must_change=False)
    audit(s, actor.username, actor, 'change_password', True)
    return {'ok': True, 'token': auth.issue_token(actor.username, user=actor)}


def list_page(s: Session, q: str = '', role: str = '', active: str = '', price: str = '',
              page: int = 1, page_size: int = 10) -> dict:
    filters = []
    if q:
        filters.append(or_(User.username.contains(q, autoescape=True),
                           User.display_name.contains(q, autoescape=True)))
    if role:
        filters.append(User.role == role)
    if active:
        filters.append(User.active == (active == 'enabled'))
    if price:
        granted = or_(User.role == 'admin', User.can_view_price.is_(True))
        filters.append(granted if price == 'allowed' else ~granted)
    total = s.scalar(select(func.count()).select_from(User).where(*filters))
    rows = s.scalars(select(User).where(*filters).order_by(User.created_at, User.id)
                     .offset((page - 1) * page_size).limit(page_size))
    return {'total': total, 'rows': [auth.user_out(u) for u in rows]}


def audit_page(s: Session, target_id: str = '', action: str = '', result: str = '',
               page: int = 1, page_size: int = 10) -> dict:
    filters = []
    if target_id:
        filters.append(AccountAudit.target_id == target_id)
    if action:
        filters.append(AccountAudit.action == action)
    if result:
        filters.append(AccountAudit.ok == (result == 'success'))
    total = s.scalar(select(func.count()).select_from(AccountAudit).where(*filters))
    rows = s.scalars(select(AccountAudit).where(*filters)
                     .order_by(AccountAudit.created_at.desc(), AccountAudit.id)
                     .offset((page - 1) * page_size).limit(page_size))
    return {'total': total, 'rows': [dict(id=r.id, actor=r.actor, target_id=r.target_id,
            target_name=r.target_name, action=r.action, ok=r.ok, detail=r.detail,
            created_at=r.created_at.isoformat()) for r in rows]}
