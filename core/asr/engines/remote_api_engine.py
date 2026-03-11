#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
远端 API 语音识别引擎

通过 HTTP 将音频转发到自研/第三方 ASR 服务，并将结果适配为统一格式。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class RemoteAPIEngine(BaseVoiceEngine):
    """通过远端 HTTP API 执行语音识别"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config or {})
        self.session = requests.Session()
        self.base_url: str = self.config.get("base_url", "")
        self.endpoint: str = self.config.get("endpoint", "/api/v1/asr/transcribe")
        self.api_key: str = self.config.get("api_key", "")
        self.auth_type: str = self.config.get("auth_type", "header")
        self.auth_header: str = self.config.get("auth_header", "Authorization")
        self.timeout: int = int(self.config.get("timeout", 120))
        self.max_retries: int = int(self.config.get("max_retries", 2))
        self.extra_headers: Dict[str, Any] = self.config.get("extra_headers", {}) or {}
        self.default_params: Dict[str, Any] = self.config.get("default_params", {}) or {}
        self.cloud_provider: str = self.config.get("cloud_provider", "custom")
        self.enabled: bool = bool(self.config.get("enabled", False))
        self.settings_path = Path(self.config.get("settings_path", "config/settings.json"))

    def initialize(self) -> bool:
        """初始化远端API配置"""
        try:
            file_config = self._load_config_from_file()
            if file_config:
                self._merge_config(file_config)

            if not self.enabled:
                logger.warning("远端API未启用，跳过初始化")
                return False

            if not self.base_url:
                logger.error("远端API缺少 base_url 配置")
                return False

            self.initialized = True
            logger.info(
                "远端API引擎初始化完成 -> %s%s",
                self.base_url,
                self.endpoint,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(f"远端API引擎初始化失败: {exc}")
            return False

    def _merge_config(self, file_config: Dict[str, Any]):
        """将配置文件中的字段合并到实例配置"""
        for key in [
            "enabled",
            "base_url",
            "endpoint",
            "api_key",
            "auth_type",
            "auth_header",
            "timeout",
            "max_retries",
            "extra_headers",
            "default_params",
            "cloud_provider",
        ]:
            value = file_config.get(key)
            if value is not None:
                setattr(self, key, value if key not in ["extra_headers", "default_params"] else value or {})

    def _load_config_from_file(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            return {}

        try:
            with open(self.settings_path, "r", encoding="utf-8") as fp:
                settings = json.load(fp)
            return (
                settings.get("asr", {})
                .get("remote_api", {})
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"读取远端API配置失败: {exc}")
            return {}

    def recognize_file(
        self,
        audio_path: str,
        language: str = "auto",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """调用远端API执行识别"""
        if not self.initialized and not self.initialize():
            return None

        if not self.enabled:
            logger.error("远端API引擎未启用")
            return None

        url = urljoin(self.base_url.rstrip("/") + "/", self.endpoint.lstrip("/"))
        enable_diarization = kwargs.get("enable_diarization", False)

        payload = {
            "language": language,
            "enable_diarization": enable_diarization,
            "metadata": {
                "engine": "remote_api",
                "provider": self.cloud_provider,
            },
        }
        payload.update(self.default_params or {})

        headers = dict(self.extra_headers or {})
        if self.api_key:
            if self.auth_type == "header":
                header_name = self.auth_header or "Authorization"
                value = self.api_key
                if header_name.lower() == "authorization" and not value.lower().startswith("bearer "):
                    value = f"Bearer {value}"
                headers[header_name] = value
            elif self.auth_type == "query":
                payload["api_key"] = self.api_key

        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                with open(audio_path, "rb") as audio_file:
                    files = {"file": (Path(audio_path).name, audio_file, "application/octet-stream")}
                    data = {"payload": json.dumps(payload, ensure_ascii=False)}
                    response = self.session.post(
                        url,
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=self.timeout,
                    )
                response.raise_for_status()
                result_payload = response.json()
                normalized = self._normalize_response(result_payload)
                return self.format_result(normalized, audio_path)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(f"远端API调用失败 (attempt {attempt}/{self.max_retries}): {exc}")

        logger.error(f"远端API最终失败: {last_error}")
        return None

    def _normalize_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """将自研API返回结果转化为平台统一格式"""
        result = payload.get("data") if "data" in payload else payload
        if result is None:
            result = {}

        text = result.get("text") or result.get("transcript") or ""
        language = result.get("language", "auto")
        segments = result.get("segments") or []
        speakers = result.get("speakers") or {}

        if not segments and text:
            segments = [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": result.get("audio_length", 0.0) or 0.0,
                    "text": text,
                    "speaker": "Speaker_1",
                    "words": [],
                }
            ]

        normalized = {
            "text": text,
            "language": language,
            "segments": segments,
            "speakers": speakers,
            "model": result.get("model", "remote-api"),
            "device": "cloud",
            "processing_time": result.get("processing_time", 0.0),
            "audio_length": result.get("audio_length", segments[-1]["end"] if segments else 0.0),
        }

        return normalized
