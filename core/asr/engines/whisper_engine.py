#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper语音识别引擎
OpenAI Whisper的实现
"""

import time
import logging
from typing import Dict, Any
from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class WhisperEngine(BaseVoiceEngine):
    """OpenAI Whisper引擎实现"""

    def initialize(self) -> bool:
        """初始化Whisper"""
        try:
            import whisper
            import ssl

            logger.info(f"🎤 初始化Whisper - 模型: {self.config.whisper_model}")

            # 创建不验证SSL证书的上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 临时禁用SSL验证
            import urllib.request

            original_https_handler = urllib.request.HTTPSHandler

            try:
                # 使用不验证SSL的handler
                urllib.request.HTTPSHandler = lambda: urllib.request.HTTPSHandler(
                    context=ssl_context
                )
                self.model = whisper.load_model(self.config.whisper_model)
            finally:
                # 恢复原始handler
                urllib.request.HTTPSHandler = original_https_handler

            self.initialized = True
            logger.info("✅ Whisper初始化成功")
            return True

        except ImportError:
            logger.warning("⚠️ openai-whisper 未安装")
            return False
        except Exception as e:
            logger.error(f"❌ Whisper初始化失败: {e}")
            # 尝试离线模式
            try:
                import whisper
                import os

                # 设置环境变量强制离线模式
                os.environ["WHISPER_CACHE"] = os.path.expanduser("~/.cache/whisper")

                # 尝试从本地缓存加载
                self.model = whisper.load_model(
                    self.config.whisper_model, download_root=os.environ["WHISPER_CACHE"]
                )
                self.initialized = True
                logger.info("✅ Whisper从本地缓存初始化成功")
                return True
            except Exception as offline_e:
                logger.error(f"❌ Whisper离线初始化也失败: {offline_e}")
                return False

    def recognize_file(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用Whisper转录"""
        if not self.initialized:
            raise RuntimeError("Whisper引擎未初始化")

        try:
            start_time = time.time()

            # 语言处理：如果配置了中文优化，使用中文
            transcribe_language = None
            if self.config.chinese_optimized or language == "zh":
                transcribe_language = "zh"
            elif language != "auto":
                transcribe_language = language

            # 执行转录
            result = self.model.transcribe(
                audio_path,
                language=transcribe_language,
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1,
            )

            processing_time = time.time() - start_time

            return {
                "text": result["text"].strip(),
                "segments": result.get("segments", []),
                "language": result.get("language", "unknown"),
                "processing_time": processing_time,
                "model": f"whisper-{self.config.whisper_model}",
                "device": self.config.device,
            }

        except Exception as e:
            logger.error(f"❌ Whisper转录失败: {e}")
            raise

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "Whisper",
            "version": "unknown",
            "description": "OpenAI官方语音识别模型，通用性强",
            "supported_languages": [
                "auto",
                "zh",
                "en",
                "ja",
                "ko",
                "fr",
                "de",
                "es",
                "ru",
            ],
            "model_size": getattr(self.config, "whisper_model", "small"),
            "device": getattr(self.config, "device", "auto"),
            "initialized": self.initialized,
            "features": ["多语言支持", "高精度识别", "开源模型"],
        }
