from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib import error, request

from app.config import OLLAMA_BASE_URL, OLLAMA_TEXT_MODEL


class OllamaService:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        default_model: str = OLLAMA_TEXT_MODEL,
        timeout_seconds: int = 90,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    def chat_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_model = model or self.default_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": selected_model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
            "think": False,
        }

        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_response = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Ollama returned HTTP {exc.code}: {detail}")
        except error.URLError as exc:
            raise ValueError(f"Failed to reach Ollama at {self.base_url}: {exc.reason}")

        payload_data = self._safe_load_json(raw_response)
        message_content = payload_data.get("message", {}).get("content", "{}")

        if isinstance(message_content, dict):
            return message_content
        if isinstance(message_content, str):
            content_data = self._safe_load_json(message_content)
            if content_data:
                return content_data

        raise ValueError("Ollama response did not contain valid JSON content")

    @staticmethod
    def _safe_load_json(text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
        return {}


ollama_service = OllamaService()
