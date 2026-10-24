"""Provider presets and read-only OpenAI-compatible model discovery."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

import httpx

# Addresses checked against provider documentation on 2026-10-24. No static model catalogue.
PROVIDERS = [
    {'id': 'deepseek', 'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com'},
    {'id': 'qwen', 'name': '阿里云百炼 / 通义千问（北京）', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1'},
    {'id': 'glm', 'name': '智谱 GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4'},
    {'id': 'doubao', 'name': '火山方舟 / 豆包（北京）', 'base_url': 'https://ark.cn-beijing.volces.com/api/v3'},
    {'id': 'minimax', 'name': 'MiniMax（国内）', 'base_url': 'https://api.minimax.cn/v1'},
    {'id': 'mimo', 'name': '小米 MiMo', 'base_url': 'https://api.xiaomimimo.com/v1'},
    {'id': 'siliconflow', 'name': '硅基流动（国内）', 'base_url': 'https://api.siliconflow.cn/v1'},
    {'id': 'custom', 'name': '自定义 / 代理 / 其他区域', 'base_url': ''},
]


def validate_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip('/')
    url = urlsplit(base_url)
    if (url.scheme not in ('http', 'https') or not url.hostname
            or url.username or url.password or url.query or url.fragment):
        raise ValueError('接口地址须为不含账号、查询参数的 HTTP(S) base_url')
    return base_url


def discover(base_url: str, api_key: str) -> dict:
    base_url = validate_url(base_url)
    if not api_key.strip() or any(c in api_key for c in ('\n', '\r')):
        raise ValueError('请先填写 API Key')
    params = {'sub_type': 'chat'} if base_url == 'https://api.siliconflow.cn/v1' else None
    try:
        response = httpx.get(base_url + '/models', headers={'Authorization': 'Bearer ' + api_key},
                             params=params, timeout=20, follow_redirects=False)
        if response.status_code in (401, 403):
            raise ValueError('模型列表访问被拒绝，请检查密钥、区域及账号权限')
        if response.status_code in (404, 405):
            raise ValueError('该接口未提供兼容的模型列表，请手动填写模型或推理接入点 ID')
        if response.status_code != 200:
            raise ValueError(f'模型列表获取失败（HTTP {response.status_code}），可重试或手动填写')
        payload = response.json()
        data = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ValueError('返回的模型列表格式不兼容，请手动填写模型 ID')
        models = sorted({r['id'].strip() for r in data if isinstance(r, dict)
                         and isinstance(r.get('id'), str) and 0 < len(r['id'].strip()) <= 120})
        if not models:
            raise ValueError('服务商返回空模型列表，请检查模型开通情况或手动填写')
        return {'models': models, 'message': '列表来自当前接口；模型是否支持对话及账号能否调用，需测试连接确认。'}
    except (httpx.HTTPError, TypeError, KeyError):
        raise ValueError('获取模型列表失败，请检查网络或手动填写模型 ID') from None
    except ValueError as exc:
        # JSON decode errors may include provider data; never return their raw message.
        if isinstance(exc, json.JSONDecodeError):
            raise ValueError('服务商未返回有效 JSON 模型列表') from None
        raise
