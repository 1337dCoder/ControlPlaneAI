"""Multi-provider LLM client abstraction for ControlPlane.

Supports OpenAI, Anthropic Claude, Google Gemini, and OpenAI-compatible local endpoints
(Ollama, vLLM, LiteLLM) behind a unified interface.
Captures generated content, token usage, latency, and token log probabilities.
Provides realistic deterministic mock responses when credentials are not configured.
"""

import os
import time
from typing import Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv
import httpx

load_dotenv()


class LLMProviderClient:
    """Unified client supporting OpenAI, Anthropic, Gemini, and local endpoints."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
    ):
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self.openai_base_url = openai_base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def detect_provider(self, model_name: str) -> str:
        """Detect the appropriate provider based on model naming conventions."""
        model_lower = model_name.lower()
        if "claude" in model_lower:
            return "anthropic"
        elif "gemini" in model_lower:
            return "gemini"
        return "openai"

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Invokes model generation, returning text, token logprobs (if available),
        tokens used, and latency in milliseconds.
        """
        start_time = time.perf_counter()
        provider = self.detect_provider(model_name)

        if provider == "anthropic":
            return await self._generate_anthropic(system_prompt, user_prompt, model_name, temperature, start_time)
        elif provider == "gemini":
            return await self._generate_gemini(system_prompt, user_prompt, model_name, temperature, start_time)
        else:
            return await self._generate_openai(system_prompt, user_prompt, model_name, temperature, start_time)

    async def _generate_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str,
        temperature: float,
        start_time: float
    ) -> Dict[str, Any]:
        """Call OpenAI or OpenAI-compatible endpoint."""
        if not self.openai_api_key or self.openai_api_key.startswith("your_") or self.openai_api_key == "mock":
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return self._mock_generate(user_prompt, model_name, latency_ms)

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "logprobs": True,
            "top_logprobs": 1
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.openai_base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                choice = data["choices"][0]
                content = choice["message"]["content"]
                
                logprobs = []
                if "logprobs" in choice and choice["logprobs"] and "content" in choice["logprobs"]:
                    logprobs = [
                        token_info.get("logprob", 0.0)
                        for token_info in choice["logprobs"]["content"]
                        if token_info.get("logprob") is not None
                    ]

                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens", len(content.split()) * 2)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                return {
                    "content": content,
                    "tokens_used": tokens_used,
                    "logprobs": logprobs,
                    "latency_ms": round(latency_ms, 2),
                    "provider": "openai",
                    "raw_response": data
                }
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            mock_res = self._mock_generate(user_prompt, model_name, latency_ms)
            mock_res["error"] = str(e)
            return mock_res

    async def _generate_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str,
        temperature: float,
        start_time: float
    ) -> Dict[str, Any]:
        """Call Anthropic Messages API."""
        if not self.anthropic_api_key or self.anthropic_api_key.startswith("your_"):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return self._mock_generate(user_prompt, model_name, latency_ms)

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 4096,
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                content = data["content"][0]["text"]
                usage = data.get("usage", {})
                tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                return {
                    "content": content,
                    "tokens_used": tokens_used,
                    "logprobs": [],
                    "latency_ms": round(latency_ms, 2),
                    "provider": "anthropic",
                    "raw_response": data
                }
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            mock_res = self._mock_generate(user_prompt, model_name, latency_ms)
            mock_res["error"] = str(e)
            return mock_res

    async def _generate_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str,
        temperature: float,
        start_time: float
    ) -> Dict[str, Any]:
        """Call Google Gemini generateContent API."""
        if not self.gemini_api_key or self.gemini_api_key.startswith("your_"):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return self._mock_generate(user_prompt, model_name, latency_ms)

        # Use the requested model name directly
        normalized_model = model_name.lower().replace("models/", "")

        target_model = f"models/{normalized_model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={self.gemini_api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": temperature}
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                candidate = data["candidates"][0]["content"]["parts"][0]["text"]
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                tokens_est = len(candidate.split()) * 2

                return {
                    "content": candidate,
                    "tokens_used": tokens_est,
                    "logprobs": [],
                    "latency_ms": round(latency_ms, 2),
                    "provider": "gemini",
                    "raw_response": data
                }
        except Exception as e:
            print(f"GEMINI EXCEPTION: {type(e)} - {str(e)}")
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            mock_res = self._mock_generate(user_prompt, model_name, latency_ms)
            mock_res["error"] = str(e)
            return mock_res

    def _mock_generate(self, user_prompt: str, model_name: str, latency_ms: float) -> Dict[str, Any]:
        """Generate deterministic mock response adhering to TruthPrompt structure."""
        tokens_estimate = len(user_prompt.split()) + 45
        return {
            "content": f"[FACTS]: Verified input request for '{user_prompt[:40]}'.\n[SOLUTION]: Here is the requested structured response.\n[CONFIDENCE: 0.94]",
            "tokens_used": tokens_estimate,
            "logprobs": [-0.05, -0.02, -0.01, -0.04, -0.03],
            "latency_ms": round(latency_ms + 10.0, 2),
            "provider": "mock",
            "raw_response": {"mock": True}
        }
