"""jb-llm：统一 LLM 客户端（OpenAI 兼容接口）。

配置来自环境变量（或仓库根 .env，不覆盖已有环境变量）：
  LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
密钥只放 .env（已 gitignore），严禁写入代码或提交。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

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


def available() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL"))


def chat(prompt: str, system: str = "", temperature: float = 0.0,
         timeout: float = 60.0) -> str:
    """单轮对话，返回文本。未配置或调用失败抛 RuntimeError。"""
    if not available():
        raise RuntimeError("LLM 未配置（缺 LLM_API_KEY/LLM_BASE_URL）")
    messages = ([{"role": "system", "content": system}] if system else []) + \
        [{"role": "user", "content": prompt}]
    resp = httpx.post(
        os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
        json={"model": os.environ.get("LLM_MODEL", "mimo-v2.5-pro"),
              "messages": messages, "temperature": temperature},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_json(prompt: str, system: str = "只输出 JSON，不要任何解释。",
              retries: int = 1) -> Optional[Any]:
    """要求模型输出 JSON 并解析；失败重试 retries 次，仍失败返回 None（调用方留 None，不猜）。"""
    for _ in range(retries + 1):
        try:
            text = chat(prompt, system=system)
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
