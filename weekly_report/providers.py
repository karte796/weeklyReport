"""LLM provider adapters. Only the standard library is used (urllib)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

# Built-in presets. Any [providers.<name>] table in the config overrides or extends these.
# type: "openai" = OpenAI-compatible /chat/completions; "anthropic"; "gemini".
PRESETS: dict[str, dict] = {
    "openai":      {"type": "openai", "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
    "deepseek":    {"type": "openai", "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY"},
    "qwen":        {"type": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY"},
    "kimi":        {"type": "openai", "base_url": "https://api.moonshot.cn/v1",
                    "model": "moonshot-v1-32k", "api_key_env": "MOONSHOT_API_KEY"},
    "zhipu":       {"type": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                    "model": "glm-4-flash", "api_key_env": "ZHIPUAI_API_KEY"},
    "siliconflow": {"type": "openai", "base_url": "https://api.siliconflow.cn/v1",
                    "model": "deepseek-ai/DeepSeek-V3", "api_key_env": "SILICONFLOW_API_KEY"},
    "openrouter":  {"type": "openai", "base_url": "https://openrouter.ai/api/v1",
                    "model": "openai/gpt-4o-mini", "api_key_env": "OPENROUTER_API_KEY"},
    "ollama":      {"type": "openai", "base_url": "http://localhost:11434/v1",
                    "model": "qwen2.5", "api_key_env": ""},
    "anthropic":   {"type": "anthropic", "base_url": "https://api.anthropic.com",
                    "model": "claude-sonnet-4-5", "api_key_env": "ANTHROPIC_API_KEY"},
    "gemini":      {"type": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta",
                    "model": "gemini-2.5-flash", "api_key_env": "GEMINI_API_KEY"},
}
PRESETS["claude"] = PRESETS["anthropic"]

RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    pass


@dataclass
class ProviderConfig:
    name: str
    type: str
    base_url: str
    model: str
    api_key: str = ""
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: float = 180
    headers: Optional[dict] = None


def resolve_provider(name: str, cfg: dict, model: Optional[str] = None) -> ProviderConfig:
    user = (cfg.get("providers") or {}).get(name, {})
    if name not in PRESETS and not user:
        known = ", ".join(sorted(set(PRESETS) | set(cfg.get("providers") or {})))
        raise ProviderError(f"unknown provider {name!r}. Available: {known}")
    merged = {**PRESETS.get(name, {}), **user}
    ptype = merged.get("type", "openai")
    if ptype not in ADAPTERS:
        raise ProviderError(f"provider {name!r}: unsupported type {ptype!r} "
                            f"(use one of {', '.join(ADAPTERS)})")
    if not merged.get("base_url") or not (model or merged.get("model")):
        raise ProviderError(f"provider {name!r} needs base_url and model")
    key = merged.get("api_key") or ""
    env_name = merged.get("api_key_env", "")
    if not key and env_name:
        key = os.environ.get(env_name, "")
        if not key:
            raise ProviderError(f"provider {name!r}: environment variable {env_name} is not set")
    return ProviderConfig(
        name=name, type=ptype, base_url=str(merged["base_url"]).rstrip("/"),
        model=model or merged["model"], api_key=key,
        temperature=merged.get("temperature"), max_tokens=merged.get("max_tokens"),
        timeout=float(merged.get("timeout", 180)), headers=merged.get("headers"),
    )


def _post_json(url: str, payload: dict, headers: dict, timeout: float, retries: int = 2) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            if exc.code in RETRY_STATUS and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise ProviderError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise ProviderError(f"request to {url} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"non-JSON response from {url}") from exc
    raise ProviderError("unreachable")  # pragma: no cover


def _openai(p: ProviderConfig, system: str, user: str) -> str:
    payload: dict = {"model": p.model, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}]}
    if p.temperature is not None:
        payload["temperature"] = p.temperature
    if p.max_tokens:
        payload["max_tokens"] = p.max_tokens
    headers = {"Authorization": f"Bearer {p.api_key}"} if p.api_key else {}
    data = _post_json(f"{p.base_url}/chat/completions", payload, {**headers, **(p.headers or {})},
                      p.timeout)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"unexpected response: {json.dumps(data)[:500]}") from exc


def _anthropic(p: ProviderConfig, system: str, user: str) -> str:
    payload: dict = {"model": p.model, "max_tokens": p.max_tokens or 4096, "system": system,
                     "messages": [{"role": "user", "content": user}]}
    if p.temperature is not None:
        payload["temperature"] = p.temperature
    headers = {"x-api-key": p.api_key, "anthropic-version": "2023-06-01", **(p.headers or {})}
    data = _post_json(f"{p.base_url}/v1/messages", payload, headers, p.timeout)
    try:
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"unexpected response: {json.dumps(data)[:500]}") from exc


def _gemini(p: ProviderConfig, system: str, user: str) -> str:
    payload: dict = {"system_instruction": {"parts": [{"text": system}]},
                     "contents": [{"role": "user", "parts": [{"text": user}]}]}
    generation = {}
    if p.temperature is not None:
        generation["temperature"] = p.temperature
    if p.max_tokens:
        generation["maxOutputTokens"] = p.max_tokens
    if generation:
        payload["generationConfig"] = generation
    headers = {"x-goog-api-key": p.api_key, **(p.headers or {})}
    data = _post_json(f"{p.base_url}/models/{p.model}:generateContent", payload, headers, p.timeout)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"unexpected response: {json.dumps(data)[:500]}") from exc


ADAPTERS = {"openai": _openai, "anthropic": _anthropic, "gemini": _gemini}


def complete(provider: ProviderConfig, system: str, user: str) -> str:
    text = ADAPTERS[provider.type](provider, system, user).strip()
    if not text:
        raise ProviderError("the model returned an empty response")
    return strip_fence(text)


def strip_fence(text: str) -> str:
    """Remove a ```markdown ... ``` wrapper some models add around the whole answer."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
