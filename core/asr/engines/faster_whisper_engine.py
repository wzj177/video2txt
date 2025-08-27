#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FasterWhisper语音识别引擎
faster-whisper的实现，速度更快
"""

import time
import logging
from typing import Dict, Any
from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class FasterWhisperEngine(BaseVoiceEngine):
    """FasterWhisper引擎实现"""

    def initialize(self) -> bool:
        """初始化FasterWhisper"""
        try:
            from faster_whisper import WhisperModel

            logger.info(f"🚀 初始化FasterWhisper - 模型: {self.config.whisper_model}")

            # 如果是中文优化，使用更大的模型
            whisper_model = self.config.whisper_model
            if self.config.chinese_optimized:
                whisper_model = self.config.preferred_chinese_model

            self.model = WhisperModel(
                whisper_model,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )

            self.initialized = True
            logger.info("✅ FasterWhisper初始化成功")
            return True

        except ImportError:
            logger.warning("⚠️ faster-whisper 未安装")
            return False
        except Exception as e:
            logger.error(f"❌ FasterWhisper初始化失败: {e}")
            return False

    def recognize_file(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用FasterWhisper转录"""
        if not self.initialized:
            raise RuntimeError("FasterWhisper引擎未初始化")

        try:
            start_time = time.time()

            # 执行转录
            segments, info = self.model.transcribe(
                audio_path,
                language=language if language != "auto" else None,
                beam_size=5,
                best_of=5,
                temperature=0.0,
            )

            # 处理结果
            result_segments = []
            full_text = ""

            for segment in segments:
                segment_dict = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "words": getattr(segment, "words", []),
                }
                result_segments.append(segment_dict)
                full_text += segment.text + " "

            processing_time = time.time() - start_time

            return {
                "text": full_text.strip(),
                "segments": result_segments,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "processing_time": processing_time,
                "model": f"faster-whisper-{self.config.whisper_model}",
                "device": self.config.device,
            }

        except Exception as e:
            logger.error(f"❌ FasterWhisper转录失败: {e}")
            raise

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "FasterWhisper",
            "version": "unknown",
            "description": "优化版Whisper模型，速度提升5-10倍",
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
            "compute_type": getattr(self.config, "compute_type", "float16"),
            "initialized": self.initialized,
            "features": ["高性能优化", "GPU加速", "内存优化", "批处理支持"],
        }
