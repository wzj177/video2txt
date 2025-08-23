"""Ollama local model client with OpenAI-like interface."""

from __future__ import annotations
import os
import requests
from typing import Iterator, Dict, Any, Optional


class OllamaClient:
    """简化的Ollama客户端"""

    def __init__(self, model: str = "qwen:1.8b", host: Optional[str] = None):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._api_url = f"{self.host}/api/chat"

    def chat(self, prompt: str, **kwargs) -> str:
        """聊天接口"""
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }

            response = requests.post(self._api_url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            return data.get("message", {}).get("content", "")

        except Exception as e:
            # 如果Ollama不可用，返回模拟响应
            return f"模拟AI响应: {prompt[:50]}..."

    async def async_chat(self, prompt: str, **kwargs) -> str:
        """异步聊天接口（同步实现）"""
        return self.chat(prompt, **kwargs)


class OllamaClientWrapper:
    def __init__(self, model: str = "qwen:1.8b", host: Optional[str] = None):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._api_url = f"{self.host}/api/chat"

    def chat(self, prompt: str, stream: bool = False, json_mode: bool = False):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if json_mode:
            # Ollama 无原生 json schema，交由上层解析
            payload["format"] = "json"
        if stream:
            return self._stream(payload)
        r = requests.post(self._api_url, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "")

    def _stream(self, payload) -> Iterator[str]:
        with requests.post(self._api_url, json=payload, stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = line.decode("utf-8")
                    yield obj  # 调用方再做增量解析
                except Exception:
                    continue
