"""Provider-neutral model adapter (init.md §8.1). AI_PROVIDER=disabled is the default and safe mode:
every AI endpoint then answers deterministically, and no other journey depends on the model."""
import json
import os
from typing import Any, Protocol

import httpx


class ProviderUnavailable(Exception):
    """The model is off, unreachable, slow or returned something unusable; callers fall back."""


class LLMProvider(Protocol):
    model_id: str

    async def health(self) -> dict[str, Any]: ...
    async def generate(self, system: str, prompt: str) -> str: ...
    async def structured_output(self, system: str, prompt: str) -> dict[str, Any]: ...


class DisabledProvider:
    model_id = "none (deterministic fallback)"

    async def health(self) -> dict[str, Any]:
        return {"provider": "disabled", "available": False, "model_id": self.model_id}

    async def generate(self, system: str, prompt: str) -> str:
        raise ProviderUnavailable("AI is disabled")

    async def structured_output(self, system: str, prompt: str) -> dict[str, Any]:
        raise ProviderUnavailable("AI is disabled")


class OllamaProvider:
    """A local model served by Ollama. Nothing is downloaded at boot; pull the model separately."""

    def __init__(self, url: str, model: str, timeout: float = 30) -> None:
        self.url, self.model_id, self.timeout = url.rstrip("/"), model, timeout

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                tags = (await client.get(f"{self.url}/api/tags")).raise_for_status().json()
            present = any(m.get("name", "").split(":")[0] == self.model_id.split(":")[0] for m in tags.get("models", []))
            return {"provider": "ollama", "available": present, "model_id": self.model_id,
                    "note": None if present else "model not pulled"}
        except Exception:
            return {"provider": "ollama", "available": False, "model_id": self.model_id, "note": "unreachable"}

    async def _call(self, system: str, prompt: str, fmt: str | None) -> str:
        body: dict[str, Any] = {"model": self.model_id, "system": system, "prompt": prompt, "stream": False,
                                "options": {"temperature": 0}}
        if fmt:
            body["format"] = fmt
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.url}/api/generate", json=body)
                response.raise_for_status()
                return response.json()["response"]
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

    async def generate(self, system: str, prompt: str) -> str:
        return await self._call(system, prompt, None)

    async def structured_output(self, system: str, prompt: str) -> dict[str, Any]:
        raw = await self._call(system, prompt, "json")
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise ProviderUnavailable("model returned invalid JSON") from exc


class OpenAICompatibleProvider(OllamaProvider):
    """An approved external endpoint. Off unless AI_ALLOW_EXTERNAL=1 is set by policy (no synthetic records
    leave the platform by default)."""

    def __init__(self, url: str, model: str, api_key: str) -> None:
        super().__init__(url, model)
        self.api_key = api_key

    async def health(self) -> dict[str, Any]:
        return {"provider": "openai_compatible", "available": bool(self.api_key), "model_id": self.model_id}

    async def _call(self, system: str, prompt: str, fmt: str | None) -> str:
        body: dict[str, Any] = {"model": self.model_id, "temperature": 0,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if fmt:
            body["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.url}/chat/completions", json=body,
                                             headers={"Authorization": f"Bearer {self.api_key}"})
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc


def from_environment() -> LLMProvider:
    kind = os.getenv("AI_PROVIDER", "disabled")
    if kind == "ollama":
        return OllamaProvider(os.getenv("OLLAMA_URL", "http://ollama:11434"), os.getenv("AI_MODEL", "qwen2.5:0.5b"))
    if kind == "openai_compatible" and os.getenv("AI_ALLOW_EXTERNAL") == "1":
        return OpenAICompatibleProvider(os.environ["AI_BASE_URL"], os.getenv("AI_MODEL", ""), os.getenv("AI_API_KEY", ""))
    return DisabledProvider()
