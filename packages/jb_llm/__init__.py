"""jb-llm：统一 LLM 客户端（OpenAI 兼容接口）。

配置来自环境变量（或仓库根 .env，不覆盖已有环境变量）：
  LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
密钥只放 .env（已 gitignore），严禁写入代码或提交。
配置中心可在运行时覆盖端点/模型/温度/超时（`configure()`，API 层从 settings 表加载）；
每次调用经 `set_usage_hook` 回调记账（用量表），密钥不经过任何落库路径。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Optional

import httpx


def _load_dotenv() -> None:
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.S)

# 运行时覆盖（配置中心写入；密钥只从环境变量读，绝不入库）：base_url / model / temperature / timeout
_overrides: dict[str, Any] = {}
_usage_hook: Optional[Callable[[dict[str, Any]], None]] = None
DEFAULT_MODEL = "mimo-v2.5-pro"


def configure(**kw: Any) -> None:
    """设置运行时覆盖：base_url、model、temperature、timeout；传 None/空串表示清除该项回到环境变量。"""
    for k, v in kw.items():
        if v in (None, ""):
            _overrides.pop(k, None)
        else:
            _overrides[k] = v


def set_usage_hook(fn: Optional[Callable[[dict[str, Any]], None]]) -> None:
    """每次调用后回调 {model, purpose, ok, latency_ms, prompt_tokens, completion_tokens, error}（由 API 层落库）。"""
    global _usage_hook
    _usage_hook = fn


def settings() -> dict[str, Any]:
    """当前生效配置（密钥只给"是否已配置"）。"""
    return {"base_url": _overrides.get("base_url") or os.environ.get("LLM_BASE_URL", ""),
            "model": _overrides.get("model") or os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            "temperature": float(_overrides.get("temperature", 0.0)),
            "timeout": float(_overrides.get("timeout", 60.0)),
            "key_configured": bool(os.environ.get("LLM_API_KEY")),
            "overrides": dict(_overrides)}


def available() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and settings()["base_url"])


def chat(prompt: str, system: str = "", temperature: Optional[float] = None,
         timeout: Optional[float] = None, purpose: str = "") -> str:
    """单轮对话，返回文本。未配置或调用失败抛 RuntimeError。purpose 只用于用量记账。"""
    if not available():
        raise RuntimeError("LLM 未配置（缺 LLM_API_KEY/LLM_BASE_URL）")
    cfg = settings()
    messages = ([{"role": "system", "content": system}] if system else []) + \
        [{"role": "user", "content": prompt}]
    rec: dict[str, Any] = {"model": cfg["model"], "purpose": purpose, "ok": False,
                           "prompt_tokens": None, "completion_tokens": None, "error": ""}
    t0 = time.monotonic()
    try:
        resp = httpx.post(
            cfg["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
            json={"model": cfg["model"], "messages": messages,
                  "temperature": cfg["temperature"] if temperature is None else temperature},
            timeout=cfg["timeout"] if timeout is None else timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        rec.update(ok=True, prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        rec["error"] = str(exc)[:500]
        raise
    finally:
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        if _usage_hook is not None:
            try:
                _usage_hook(rec)
            except Exception:
                pass


def test_connection() -> dict[str, Any]:
    """配置中心"测试连接"：发一条极短请求，返回 ok/latency/model/error（不抛异常）。"""
    t0 = time.monotonic()
    try:
        text = chat("回复“OK”两个字母即可。", timeout=30.0, purpose="test")
        return {"ok": True, "latency_ms": int((time.monotonic() - t0) * 1000), "model": settings()["model"],
                "reply": text.strip()[:50]}
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000), "model": settings()["model"],
                "error": str(exc)[:300]}


def chat_json(prompt: str, system: str = "只输出 JSON，不要任何解释。",
              retries: int = 1, purpose: str = "") -> Optional[Any]:
    """要求模型输出 JSON 并解析；失败重试 retries 次，仍失败返回 None（调用方留 None，不猜）。"""
    for _ in range(retries + 1):
        try:
            text = chat(prompt, system=system, purpose=purpose)
        except (RuntimeError, httpx.HTTPError):
            return None
        m = _JSON_BLOCK.search(text)
        if not m:
            continue
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    return None
