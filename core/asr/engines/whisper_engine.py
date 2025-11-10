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

            logger.info(f"初始化Whisper - 模型: {self.config}")

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
                self.model = whisper.load_model(self.config["model_size"])
            finally:
                # 恢复原始handler
                urllib.request.HTTPSHandler = original_https_handler

            self.initialized = True
            logger.info(" Whisper初始化成功")
            return True

        except ImportError:
            logger.warning("openai-whisper 未安装")
            return False
        except Exception as e:
            logger.error(f"Whisper初始化失败: {e}")
            # 打印错误的行号
            logger.error(f"Whisper初始化行: {e.__traceback__.tb_lineno}")
            # 尝试离线模式
            try:
                import whisper
                import os

                # 设置环境变量强制离线模式
                os.environ["WHISPER_CACHE"] = os.path.expanduser("~/.cache/whisper")

                # 尝试从本地缓存加载
                self.model = whisper.load_model(
                    self.config["model_size"], download_root=os.environ["WHISPER_CACHE"]
                )
                self.initialized = True
                logger.info("Whisper从本地缓存初始化成功")
                return True
            except Exception as offline_e:
                logger.error(f"Whisper离线初始化也失败: {offline_e}")
                return False

    def recognize_file(
        self, audio_path: str, language: str = "auto", **kwargs
    ) -> Dict[str, Any]:
        """使用Whisper转录

        Args:
            audio_path: 音频文件路径
            language: 语言代码
            **kwargs: 其他参数（为兼容性保留，本引擎暂不使用）
        """
        if not self.initialized:
            raise RuntimeError("Whisper引擎未初始化")

        try:
            start_time = time.time()

            # 语言处理：如果配置了中文优化，使用中文
            transcribe_language = None
            if self.config.get("chinese_optimized", False) or language == "zh":
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
                initial_prompt="请使用简体中文输出",
            )

            processing_time = time.time() - start_time
            model_size = self.config["model_size"]
            detected_language = result.get("language", "unknown")

            # 格式化分段信息，对齐 WhisperX 格式
            formatted_segments = []
            for segment in result.get("segments", []):
                formatted_segment = {
                    "start": round(segment.get("start", 0), 2),
                    "end": round(segment.get("end", 0), 2),
                    "duration": round(
                        segment.get("end", 0) - segment.get("start", 0), 2
                    ),
                    "text": segment.get("text", "").strip(),
                    "speaker": "Speaker_1",  # Whisper 不支持说话人分离
                    "confidence": 0.85,
                    "language": detected_language,
                    "emotion": None,
                }
                formatted_segments.append(formatted_segment)

            # 计算音频时长
            audio_duration = (
                formatted_segments[-1]["end"] if formatted_segments else 0.0
            )

            # 构建默认说话人信息
            speakers_info = {}

            return {
                "text": result["text"].strip(),
                "language": detected_language,
                "segments": formatted_segments,  # 使用格式化后的分段
                "speakers": speakers_info,  # 新增：对齐 WhisperX 格式
                "processing_time": processing_time,
                "model": f"whisper-{model_size}",
                "device": self.config.get("device", "auto"),
                "confidence": 0.85,  # 新增：对齐 WhisperX 格式
                "audio_length": audio_duration,  # 新增：对齐 WhisperX 格式
                "features": {  # 新增：对齐 WhisperX 格式
                    "word_level_timestamps": False,
                    "speaker_diarization": False,
                    "emotion_detection": False,
                },
                "statistics": {  # 新增：对齐 WhisperX 格式
                    "total_segments": len(formatted_segments),
                    "total_speakers": 1,
                    "total_duration": audio_duration,
                },
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
            "model_size": self.config.get("model_size", "small"),
            "device": self.config.get("device", "auto"),
            "initialized": self.initialized,
            "features": ["多语言支持", "高精度识别", "开源模型"],
        }
