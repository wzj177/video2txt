"""OpenAI-compatible AI client (supports stream & json mode)."""

from __future__ import annotations
import os
from typing import Iterator, Dict, Any, Optional

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


class OpenAIClientWrapper:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_BASE")
        self.model = model
        if OpenAI is None:
            raise RuntimeError("openai package not installed. pip install openai")
        self.client = (
            OpenAI(api_key=self.api_key, base_url=self.api_base)
            if self.api_base
            else OpenAI(api_key=self.api_key)
        )

    def chat(self, prompt: str, stream: bool = False, json_mode: bool = False) -> Any:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            return self._stream(kwargs)
        resp = self.client.chat.completions.create(**kwargs)
        return self._extract(resp)

    def _stream(self, kwargs) -> Iterator[str]:
        for chunk in self.client.chat.completions.create(**kwargs):
            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None) or choice
            content = getattr(delta, "content", None) or getattr(delta, "text", None)
            if content:
                yield content

    @staticmethod
    def _extract(resp) -> str:
        try:
            return resp.choices[0].message.content  # type: ignore
        except Exception:
            return str(resp)
