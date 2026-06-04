#!/usr/bin/env python3
"""
Task-016: Shared LLM client for DeepSeek-compatible chat completion APIs.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Expected a top-level JSON object from the LLM response")
    return parsed


@dataclass
class LLMResponse:
    content: str
    raw_response: dict[str, Any]
    model: str


class LLMClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        api_url: str = DEFAULT_API_URL,
        api_timeout: int = 90,
        max_retries: int = 1,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.api_url = api_url
        self.api_timeout = api_timeout
        self.max_retries = max_retries
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required")

    @classmethod
    def from_env(
        cls,
        model: str | None = None,
        api_timeout: int = 90,
        max_retries: int = 1,
    ) -> "LLMClient":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        env_model = os.environ.get("DEEPSEEK_MODEL", "").strip()
        api_url = os.environ.get("DEEPSEEK_API_URL", "").strip() or DEFAULT_API_URL
        return cls(
            api_key=api_key,
            model=model or env_model or "deepseek-v4-pro",
            api_url=api_url,
            api_timeout=api_timeout,
            max_retries=max_retries,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.api_timeout) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                content = raw["choices"][0]["message"]["content"]
                return LLMResponse(content=content, raw_response=raw, model=self.model)
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2 * (attempt + 1))

        raise RuntimeError(f"LLM request failed after retries: {last_error}")
