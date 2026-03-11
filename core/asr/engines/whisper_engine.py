#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper语音识别引擎
OpenAI Whisper的实现
"""

import os
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
            **kwargs: 额外参数（enable_diarization: 是否启用说话人分离）
        """
        if not self.initialized:
            raise RuntimeError("Whisper引擎未初始化")

        enable_diarization = kwargs.get("enable_diarization", False)
        start_time = time.time()

        try:
            logger.info(f"🎤 Whisper识别音频: {os.path.basename(audio_path)}")

            # ====== 步骤1: 音频转录 ======
            logger.info("步骤1: 执行语音转录...")

            # 语言处理
            transcribe_language = None
            if self.config.get("chinese_optimized", False) or language == "zh":
                transcribe_language = "zh"
            elif language != "auto":
                transcribe_language = language

            result = self.model.transcribe(
                audio_path,
                language=transcribe_language,
                temperature=0.0,
                beam_size=5,
                best_of=5,
                patience=1,
                initial_prompt="请使用简体中文输出",
            )

            detected_language = result.get("language", "unknown")
            logger.info(
                f"✅ 转录完成: {len(result.get('segments', []))} 个片段, 语言: {detected_language}"
            )

            # ====== 步骤2: 说话人分离（可选）======
            speakers_info = {}
            if enable_diarization:
                logger.info("⚠️  Whisper不支持说话人分离，使用默认Speaker_1")
                speakers_info = {
                    "Speaker_1": {
                        "id": "Speaker_1",
                        "name": "Speaker_1",
                        "segments_count": len(result.get("segments", [])),
                    }
                }
            else:
                logger.info("⏭️  跳过说话人分离（未启用）")

            # ====== 步骤3: 格式化输出 ======
            result_data = {
                "text": result["text"].strip(),
                "language": detected_language,
                "segments": result.get("segments", []),
                "speakers": speakers_info,
                "processing_time": time.time() - start_time,
                "model": f"whisper-{self.config['model_size']}",
                "device": self.config.get("device", "auto"),
            }

            formatted_result = self.format_result(result_data, audio_path)
            logger.info(
                f"✅ Whisper识别完成，耗时: {formatted_result['processing_time']:.2f}s"
            )
            return formatted_result

        except Exception as e:
            logger.error(f"❌ Whisper转录失败: {e}")
            return {
                "text": "",
                "language": language if language != "auto" else "zh",
                "segments": [],
                "speakers": {},
                "processing_time": time.time() - start_time,
                "error": str(e),
            }

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
