import pytest
pytest.importorskip("requests")
import llm_client


def test_generate_with_agent_propagates_temperature(monkeypatch):
    captured = {}

    def fake_generate_chapter_text(prompt, provider, model, api_key, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        captured["temperature"] = kwargs.get("temperature")
        captured["max_tokens"] = kwargs.get("max_tokens")
        return "ok"

    monkeypatch.setattr(llm_client, "generate_chapter_text", fake_generate_chapter_text)
    out = llm_client.generate_with_agent({
        "provider": "openai",
        "model": "gpt-5-mini",
        "temperature": 0.33,
        "max_tokens": 777,
        "system_prompt": "sys",
    }, prompt="ciao")

    assert out == "ok"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5-mini"
    assert captured["temperature"] == 0.33
    assert captured["max_tokens"] == 777
