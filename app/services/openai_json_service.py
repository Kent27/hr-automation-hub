from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib import error, request

from app.config import OPENAI_API_KEY, OPENAI_MODEL


class OpenAIJsonService:
    def __init__(
        self,
        api_key: Optional[str] = OPENAI_API_KEY,
        default_model: str = OPENAI_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 90,
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def chat_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        selected_model = model or self.default_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self._chat_json_from_messages(messages=messages, model=selected_model)

    def chat_json_with_images(
        self,
        prompt: str,
        image_data_urls: List[str],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        image_detail: str = "high",
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        if not image_data_urls:
            raise ValueError("At least one image must be provided")

        selected_model = model or self.default_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_url in image_data_urls:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                        "detail": image_detail,
                    },
                }
            )
        messages.append({"role": "user", "content": user_content})

        return self._chat_json_from_messages(messages=messages, model=selected_model)

    def _chat_json_from_messages(
        self,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_response = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"OpenAI returned HTTP {exc.code}: {detail}")
        except error.URLError as exc:
            raise ValueError(f"Failed to reach OpenAI API: {exc.reason}")

        payload_data = self._safe_load_json(raw_response)
        choices = payload_data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("OpenAI response missing choices")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("OpenAI response missing message")
        content = message.get("content")

        if isinstance(content, list):
            text_parts = [
                part.get("text")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            content = "\n".join(text_parts)

        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            content_data = self._safe_load_json(content)
            if content_data:
                return content_data

        raise ValueError("OpenAI response did not contain valid JSON content")

    @staticmethod
    def _safe_load_json(text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
        return {}


openai_json_service = OpenAIJsonService()
