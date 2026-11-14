"""HTTP adapters for CV and OpenAI-compatible LLM streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class CVClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def predict(self, image: bytes) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/predict",
                files={"image": ("frame.jpg", image, "image/jpeg")},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("cv-service returned a non-object payload")
        return payload


class LLMServiceClient:
    def __init__(self, base_url: str, timeout_s: float, model: str = "mirror-persona-v1") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._model = model

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async with (
            httpx.AsyncClient(timeout=self._timeout_s) as client,
            client.stream(
                "POST",
                f"{self._base_url}/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.3,
                },
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ")
                if data == "[DONE]":
                    return
                payload = json.loads(data)
                choices = payload.get("choices", [])
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content")
                if isinstance(content, str) and content:
                    yield content
