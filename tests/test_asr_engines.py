import types
from pathlib import Path

import numpy as np
import pytest

from core.asr.engines import remote_api_engine, parakeet_engine, qwen3_asr_engine


class _DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("error")

    def json(self):
        return self._payload


class _DummySession:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    def post(self, url, headers=None, data=None, files=None, timeout=60):
        self.last_request = {
            "url": url,
            "headers": headers,
            "data": data,
            "files": files,
            "timeout": timeout,
        }
        return _DummyResponse(self.payload)


def test_remote_api_engine_formats_response(tmp_path, monkeypatch):
    dummy_payload = {
        "text": "hello world",
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 1.2, "text": "hello", "speaker": "A"},
            {"start": 1.2, "end": 2.5, "text": "world", "speaker": "B"},
        ],
        "speakers": {"A": {"segments_count": 1}, "B": {"segments_count": 1}},
        "model": "cloud-pro",
    }
    dummy_session = _DummySession(dummy_payload)
    monkeypatch.setattr(
        remote_api_engine,
        "requests",
        types.SimpleNamespace(Session=lambda: dummy_session),
    )

    engine = remote_api_engine.RemoteAPIEngine(
        {
            "base_url": "https://api.example.com",
            "endpoint": "/v1/asr",
            "api_key": "token-1",
            "enabled": True,
            "settings_path": str(tmp_path / "settings.json"),
        }
    )
    assert engine.initialize() is True

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"fake audio")

    result = engine.recognize_file(str(audio_file))
    assert result is not None
    assert result["text"] == "hello world"
    assert len(result["segments"]) == 2
    # 确认请求指向正确的URL
    assert dummy_session.last_request["url"].endswith("/v1/asr")


def test_parakeet_segment_builder_groups_words():
    engine = parakeet_engine.ParakeetEngine({"segment_duration": 5, "words_per_segment": 3})
    word_ts = [
        {"start_time": 0.0, "end_time": 0.5, "word": "你好"},
        {"start_time": 0.5, "end_time": 1.0, "word": "世界"},
        {"start_time": 1.0, "end_time": 1.5, "word": "使用"},
        {"start_time": 1.5, "end_time": 2.0, "word": "Parakeet"},
    ]

    segments = engine._build_segments_from_words(word_ts, "fallback")
    assert len(segments) == 2
    assert segments[0]["text"].startswith("你好 世界 使用")
    assert pytest.approx(segments[0]["end"], 0.1) == 1.5


def test_qwen3_engine_uses_python_sdk(tmp_path, monkeypatch):
    dummy_dashscope = types.SimpleNamespace(api_key="")
    monkeypatch.setattr(qwen3_asr_engine, "dashscope", dummy_dashscope)

    calls = []

    class _DummyClient:
        def __init__(self, model: str):
            self.model = model

        def asr(self, wav_path: str, context: str = ""):
            calls.append((Path(wav_path).name, context))
            return "zh", "hello toolkit"

    monkeypatch.setattr(qwen3_asr_engine, "QwenASR", lambda model: _DummyClient(model))
    monkeypatch.setattr(qwen3_asr_engine, "load_audio", lambda _: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(qwen3_asr_engine, "save_audio_file", lambda wav, dest: Path(dest).write_bytes(b"fake"))

    engine = qwen3_asr_engine.Qwen3ASREngine(
        {
            "enabled": True,
            "dashscope_api_key": "test-key",
            "tmp_dir": str(tmp_path),
            "min_duration_for_vad": 999,
        }
    )

    assert engine.initialize() is True
    result = engine.recognize_file(str(tmp_path / "input.wav"))
    assert result is not None
    assert result["text"] == "hello toolkit"
    assert result["segments"][0]["end"] == pytest.approx(1.0, 0.01)
    assert calls and calls[0][1] == ""
