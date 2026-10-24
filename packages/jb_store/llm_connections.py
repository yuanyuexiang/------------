"""Named LLM connections. Secrets are encrypted; only public metadata leaves this module."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field

from . import config, session

KEY = 'llm_connections'
FIELDS = ('base_url', 'model', 'temperature', 'timeout', 'max_tokens')


class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    temperature: float = Field(default=0.3, ge=0, le=2)
    timeout: float = Field(default=300, ge=5, le=600)
    max_tokens: int = Field(default=12000, ge=1, le=131072)
    api_key: str = Field(default='', max_length=4096, repr=False)


def cipher():
    # Shared persistent volume, outside downloadable project directories. Atomic creation under lock.
    import fcntl
    root = Path(os.environ.get('UPLOAD_DIR', 'data/uploads')) / '.secrets'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(root / 'lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / 'llm.key'
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(Fernet.generate_key())
        return Fernet(path.read_bytes())


def legacy(s):
    saved = config.get_setting(s, 'llm')
    return dict(id='legacy', name='现有连接（环境变量密钥）',
                base_url=saved.get('base_url') or os.getenv('LLM_BASE_URL', ''),
                model=saved.get('model') or os.getenv('LLM_MODEL') or 'mimo-v2.6-pro',
                temperature=saved.get('temperature', 0), timeout=saved.get('timeout', 300),
                max_tokens=12000, api_key=os.getenv('LLM_API_KEY', ''))


def public(row):
    return {**{k: v for k, v in row.items() if k not in ('api_key', 'secret')},
            'key_configured': bool(row.get('api_key') or row.get('secret'))}


def listing():
    with session() as s:
        data = config.get_setting(s, KEY)
        return {'default_id': data.get('default_id', 'legacy'),
                'connections': [public(legacy(s)), *[public(r) for r in data.get('rows', [])]]}


def resolve(connection_id=None):
    with session() as s:
        data = config.get_setting(s, KEY)
        cid = connection_id or data.get('default_id', 'legacy')
        if cid == 'legacy':
            return legacy(s)
        row = next((r for r in data.get('rows', []) if r['id'] == cid), None)
        if row is None:
            raise ValueError('模型连接不存在')
        try:
            return {**{k: v for k, v in row.items() if k != 'secret'},
                    'api_key': cipher().decrypt(row['secret'].encode()).decode()}
        except Exception:
            raise ValueError('模型密钥无法解密，请检查密钥文件或重新保存连接') from None


def save(body, connection_id=None):
    value = Connection.model_validate(body)
    value.name, value.model = value.name.strip(), value.model.strip()
    url = urlsplit(value.base_url.strip())
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username
            or url.password or url.query or url.fragment or not value.name or not value.model):
        raise ValueError('请输入有效名称、模型及不含账号、查询参数的 HTTP(S) 接口地址')
    with session() as s:
        # Lock existing registry to prevent concurrent edits losing rows/default changes.
        from .models import Setting
        s.get(Setting, KEY, with_for_update=True)
        data = config.get_setting(s, KEY)
        rows = data.get('rows', [])
        old = next((r for r in rows if r['id'] == connection_id), None)
        if connection_id and not old:
            raise ValueError('连接不存在或为只读环境变量连接')
        if old and not value.api_key.strip() and value.base_url.strip().rstrip('/') != old['base_url'].rstrip('/'):
            raise ValueError('接口地址变更时必须填写对应密钥')
        if not value.api_key.strip() and not old:
            raise ValueError('新连接必须填写 API Key')
        row = value.model_dump(exclude={'api_key'})
        row.update(id=connection_id or uuid.uuid4().hex, base_url=value.base_url.strip().rstrip('/'),
                   secret=cipher().encrypt(value.api_key.strip().encode()).decode()
                   if value.api_key.strip() else old['secret'])
        data['rows'] = [r for r in rows if r['id'] != row['id']] + [row]
        config.set_setting(s, KEY, data)
        return public(row)


def set_default(connection_id):
    row = resolve(connection_id)
    if not row['api_key'] or not row['base_url']:
        raise ValueError('连接未配置完整，不能设为默认')
    with session() as s:
        from .models import Setting
        s.get(Setting, KEY, with_for_update=True)
        data = config.get_setting(s, KEY)
        data['default_id'] = connection_id
        config.set_setting(s, KEY, data)


def discover_models(body: dict) -> dict:
    """Unsaved keys stay in memory; a saved key can only be reused at its original endpoint."""
    from jb_llm.providers import discover, validate_url
    base_url = validate_url(str(body.get('base_url') or ''))
    api_key = str(body.get('api_key') or '').strip()
    if not api_key and body.get('connection_id'):
        saved = resolve(body['connection_id'])
        if base_url != validate_url(saved['base_url']):
            raise ValueError('接口地址已变更，请填写该服务商的 API Key 后获取模型')
        api_key = saved['api_key']
    return discover(base_url, api_key)
