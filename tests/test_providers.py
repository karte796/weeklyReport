import io
import json
import urllib.request

import pytest

from weekly_report import providers
from weekly_report.providers import ProviderError, complete, resolve_provider, strip_fence


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def capture(monkeypatch):
    calls = []

    def install(reply: dict):
        def fake_urlopen(request, timeout=None):
            calls.append({"url": request.full_url, "headers": dict(request.header_items()),
                          "body": json.loads(request.data)})
            return FakeResponse(json.dumps(reply).encode())
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        return calls
    return install


def test_resolve_preset_and_override(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    p = resolve_provider("deepseek", {"providers": {"deepseek": {"model": "deepseek-reasoner"}}})
    assert p.type == "openai" and p.model == "deepseek-reasoner" and p.api_key == "sk-test"
    assert resolve_provider("deepseek", {}, model="x").model == "x"
    assert resolve_provider("ollama", {}).api_key == ""


def test_resolve_errors(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        resolve_provider("openai", {})
    with pytest.raises(ProviderError, match="unknown provider"):
        resolve_provider("nope", {})
    with pytest.raises(ProviderError, match="unsupported type"):
        resolve_provider("x", {"providers": {"x": {"type": "soap", "base_url": "u", "model": "m"}}})


def test_custom_openai_compatible(capture):
    calls = capture({"choices": [{"message": {"content": "```markdown\n# Report\n```"}}]})
    cfg = {"providers": {"gw": {"type": "openai", "base_url": "https://gw.test/v1/", "model": "m",
                                "api_key": "k", "temperature": 0.2}}}
    assert complete(resolve_provider("gw", cfg), "sys", "user") == "# Report"
    call = calls[0]
    assert call["url"] == "https://gw.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert call["body"]["temperature"] == 0.2


def test_anthropic(capture, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    calls = capture({"content": [{"type": "text", "text": "# Hi"}]})
    assert complete(resolve_provider("claude", {}), "sys", "user") == "# Hi"
    assert calls[0]["url"].endswith("/v1/messages")
    assert calls[0]["headers"]["X-api-key"] == "ak"
    assert calls[0]["body"]["system"] == "sys" and calls[0]["body"]["max_tokens"] == 4096


def test_gemini(capture, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    calls = capture({"candidates": [{"content": {"parts": [{"text": "# G"}]}}]})
    assert complete(resolve_provider("gemini", {}), "sys", "user") == "# G"
    assert calls[0]["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert calls[0]["body"]["system_instruction"]["parts"][0]["text"] == "sys"


def test_empty_and_malformed(capture):
    cfg = {"providers": {"gw": {"base_url": "https://gw.test/v1", "model": "m", "api_key": "k"}}}
    capture({"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(ProviderError, match="empty"):
        complete(resolve_provider("gw", cfg), "s", "u")
    capture({"error": "bad"})
    with pytest.raises(ProviderError, match="unexpected"):
        complete(resolve_provider("gw", cfg), "s", "u")


def test_http_error_is_reported(monkeypatch):
    import urllib.error

    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    cfg = {"providers": {"gw": {"base_url": "https://gw.test/v1", "model": "m", "api_key": "k"}}}
    with pytest.raises(ProviderError, match="HTTP 401.*bad key"):
        complete(resolve_provider("gw", cfg), "s", "u")


def test_strip_fence():
    assert strip_fence("# A\n\ntext") == "# A\n\ntext"
    assert strip_fence("```\n# A\n```") == "# A"


def test_every_preset_is_valid():
    for name, preset in providers.PRESETS.items():
        assert preset["type"] in providers.ADAPTERS, name
        assert preset["base_url"].startswith("http"), name
