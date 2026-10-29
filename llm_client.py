from __future__ import annotations

import os
from dataclasses import dataclass

import requests


class LLMError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float
    timeout: int

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = os.getenv("LLM_PROVIDER", "local").strip().lower()
        model = os.getenv("LLM_MODEL", "llama3.1").strip()
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.4"))
        timeout = int(os.getenv("LLM_TIMEOUT", "120"))

        if provider == "openrouter":
            base_url = os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ).strip().rstrip("/")
            api_key = os.getenv("LLM_API_KEY", "").strip()
            if not api_key:
                raise LLMError(
                    "LLM_PROVIDER=openrouter requires LLM_API_KEY to be set. "
                    "Get a key at https://openrouter.ai/keys."
                )
        elif provider == "local":
            base_url = os.getenv(
                "LOCAL_BASE_URL", "http://localhost:11434/v1"
            ).strip().rstrip("/")
            api_key = os.getenv("LOCAL_API_KEY", "not-needed").strip() or "not-needed"
        else:
            raise LLMError(
                f"Unknown LLM_PROVIDER '{provider}'. Use 'openrouter' or 'local'."
            )

        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout=timeout,
        )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        if self.config.provider == "openrouter":
            headers["HTTP-Referer"] = os.getenv(
                "OPENROUTER_REFERER", "https://github.com/tuberank-ai"
            )
            headers["X-Title"] = os.getenv("OPENROUTER_TITLE", "TubeRank AI")
        return headers

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise LLMError(
                f"Could not connect to the LLM endpoint at {self.config.base_url}. "
                "If using a local runtime, make sure it is running "
                "(e.g. `ollama serve` and `ollama pull <model>`)."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMError(
                f"The LLM request timed out after {self.config.timeout}s. "
                "Try a smaller model or raise LLM_TIMEOUT."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(
                f"LLM endpoint returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"Unexpected response shape from the LLM endpoint: "
                f"{response.text[:500]}"
            ) from exc

    def describe(self) -> str:
        return f"{self.config.provider} / {self.config.model} @ {self.config.base_url}"
