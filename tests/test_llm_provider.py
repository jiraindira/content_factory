from integrations.claude_adapters import ClaudeJsonLLM
from integrations.openai_adapters import make_llm


def test_default_brand_uses_standard_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm = make_llm({"llm_provider": "claude"})
    assert isinstance(llm, ClaudeJsonLLM)
    assert llm.effort is None and not llm.refusal_fallback


def test_claude_opus_brand_uses_opus_5_5(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm = make_llm({"llm_provider": "claude_opus"})
    assert llm.model == "claude-opus-5-5"
    assert llm.effort == "high"
    assert llm.max_tokens >= 16000
    assert llm.refusal_fallback


class _Resp:
    stop_reason = "end_turn"
    content = []


def test_opus_request_sends_effort_and_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm = make_llm({"llm_provider": "claude_opus"})
    seen = {}

    def fake_beta_create(**kw):
        seen.update(kw)
        return _Resp()

    monkeypatch.setattr(llm.client.beta.messages, "create", fake_beta_create)
    llm._create({"model": llm.model, "max_tokens": 10, "messages": []}, {"format": {"type": "json_schema", "schema": {}}})
    assert seen["output_config"]["effort"] == "high"
    assert "format" in seen["output_config"]
    assert seen["fallbacks"] == "default"
    assert "temperature" not in seen and "thinking" not in seen
