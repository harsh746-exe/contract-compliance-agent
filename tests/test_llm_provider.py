import logging

import pytest

from compliance_agent import config
from compliance_agent.llm import get_provider, reset_provider
from compliance_agent.llm.openai_compat import OpenAICompatProvider
from compliance_agent.llm.provider import LLMRequest


@pytest.fixture(autouse=True)
def _reset_provider_cache():
    reset_provider()
    yield
    reset_provider()


def test_get_provider_uses_openai_when_configured(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(config, "DEEPINFRA_API_KEY", "")

    provider = get_provider()

    assert isinstance(provider, OpenAICompatProvider)
    assert provider.is_available() is True


def test_get_provider_falls_back_when_preferred_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "deepinfra")
    monkeypatch.setattr(config, "DEEPINFRA_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-openai-key")

    provider = get_provider()

    assert isinstance(provider, OpenAICompatProvider)
    assert provider.is_available() is True


@pytest.mark.asyncio
async def test_provider_logs_each_llm_call(monkeypatch, caplog):
    provider = OpenAICompatProvider(
        api_key="test-openai-key",
        model="gpt-4o-mini",
        base_url="https://example.com/v1",
        timeout=1.0,
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "{\"label\": \"compliant\"}"}}],
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    async def fake_post(path, json):
        assert path == "/chat/completions"
        assert json["model"] == "gpt-4o-mini"
        return FakeResponse()

    monkeypatch.setattr(provider.client, "post", fake_post)
    caplog.set_level(logging.INFO)

    response = await provider.complete(
        LLMRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=50,
        )
    )

    assert response.content == "{\"label\": \"compliant\"}"
    assert any("LLM call started" in message for message in caplog.messages)
    assert any("LLM call completed" in message for message in caplog.messages)
