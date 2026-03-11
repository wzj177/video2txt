#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Qwen3-ASR API wrapper extracted from the toolkit."""

from __future__ import annotations

import os
import random
import time
from typing import Tuple

try:  # dashscope may be optional during import; actual engine checks later
    import dashscope  # type: ignore
except Exception:  # pragma: no cover
    dashscope = None

from pydub import AudioSegment

MAX_API_RETRY = 10
API_RETRY_SLEEP = (1, 2)

LANGUAGE_CODE_MAPPING = {
    "ar": "Arabic",
    "zh": "Chinese",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "es": "Spanish",
}


class QwenASR:
    """Tiny helper around DashScope's Qwen3 ASR API."""

    def __init__(self, model: str = "qwen3-asr-flash") -> None:
        if dashscope is None:  # pragma: no cover - runtime failure is handled outside
            raise ImportError("dashscope package not available")
        self.model = model

    def asr(self, wav_url: str, context: str = "") -> Tuple[str, str]:
        if not wav_url.startswith("http"):
            if not os.path.exists(wav_url):
                raise FileNotFoundError(f"{wav_url} not found")
            wav_url = self._ensure_supported_scheme(wav_url)

        last_error = None
        for _ in range(MAX_API_RETRY):
            try:
                payload = [
                    {
                        "role": "system",
                        "content": [{"text": context}],
                    },
                    {
                        "role": "user",
                        "content": [{"audio": wav_url}],
                    },
                ]
                response = dashscope.MultiModalConversation.call(  # type: ignore[attr-defined]
                    model=self.model,
                    messages=payload,
                    result_format="message",
                    asr_options={"enable_lid": True, "enable_itn": False},
                )
                if response.status_code != 200:
                    raise RuntimeError(f"status_code={response.status_code}: {response}")
                content = response["output"]["choices"][0]["message"]
                recog_text = ""
                if content.get("content"):
                    recog_text = content["content"][0].get("text", "")
                lang_code = None
                if "annotations" in content:
                    lang_code = content["annotations"][0].get("language")
                language = LANGUAGE_CODE_MAPPING.get(lang_code, lang_code or "Unknown")
                return language, self._post_process(recog_text)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(random.uniform(*API_RETRY_SLEEP))

        raise RuntimeError(f"Qwen3-ASR request failed: {last_error}")

    @staticmethod
    def _ensure_supported_scheme(file_path: str) -> str:
        file_size = os.path.getsize(file_path)
        source = file_path
        if file_size > 10 * 1024 * 1024:
            mp3_path = os.path.splitext(file_path)[0] + ".mp3"
            AudioSegment.from_file(file_path).export(mp3_path, format="mp3")
            source = mp3_path
        return f"file://{source}"

    @staticmethod
    def _post_process(text: str, threshold: int = 20) -> str:
        return _fix_pattern_repeats(_fix_char_repeats(text, threshold), threshold)


def _fix_char_repeats(text: str, threshold: int) -> str:
    result = []
    i = 0
    while i < len(text):
        count = 1
        while i + count < len(text) and text[i + count] == text[i]:
            count += 1
        if count > threshold:
            result.append(text[i])
        else:
            result.append(text[i : i + count])
        i += count
    return "".join(result)


def _fix_pattern_repeats(text: str, threshold: int, max_len: int = 20) -> str:
    n = len(text)
    min_repeat_chars = threshold * 2
    if n < min_repeat_chars:
        return text

    i = 0
    result = []
    while i <= n - min_repeat_chars:
        for k in range(1, max_len + 1):
            if i + k * threshold > n:
                break
            pattern = text[i : i + k]
            valid = all(text[i + rep * k : i + (rep + 1) * k] == pattern for rep in range(1, threshold))
            if not valid:
                continue
            end_index = i + threshold * k
            while end_index + k <= n and text[end_index : end_index + k] == pattern:
                end_index += k
            result.append(pattern)
            result.append(_fix_pattern_repeats(text[end_index:], threshold, max_len))
            return "".join(result)
        result.append(text[i])
        i += 1
    result.append(text[i:])
    return "".join(result)
