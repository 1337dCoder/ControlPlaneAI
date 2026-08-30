"""Unit tests for multi-provider client and provider auto-detection."""

import pytest
from app.providers import LLMProviderClient


def test_provider_detection():
    client = LLMProviderClient()
    
    assert client.detect_provider("gpt-4o") == "openai"
    assert client.detect_provider("gpt-3.5-turbo") == "openai"
    assert client.detect_provider("claude-3-5-sonnet-20241022") == "anthropic"
    assert client.detect_provider("claude-3-haiku") == "anthropic"
    assert client.detect_provider("gemini-1.5-pro") == "gemini"
    assert client.detect_provider("gemini-1.5-flash") == "gemini"


@pytest.mark.asyncio
async def test_mock_generation_structure():
    client = LLMProviderClient(openai_api_key="mock")
    res = await client.generate(
        system_prompt="System instructions",
        user_prompt="Solve 2 + 2",
        model_name="gpt-3.5-turbo"
    )

    assert "content" in res
    assert "tokens_used" in res
    assert "logprobs" in res
    assert "latency_ms" in res
    assert res["tokens_used"] > 0
    assert "[FACTS]" in res["content"]
