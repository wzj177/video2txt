#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhisperX语音识别引擎 - 集成转录和说话人分离
基于WhisperX实现，提供精确的词级时间戳和说话人分离功能
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import time
import json

from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class WhisperXEngine(BaseVoiceEngine):
    """WhisperX语音识别引擎 - 一体化转录和说话人分离"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.model = None
        self.compute_type = "int8"
        self.model_size = config.get("model_size", "base") if config else "base"
        self.batch_size = 16

    def initialize(self) -> bool:
        """初始化WhisperX引擎"""
        try:
            logger.info(f"初始化WhisperX引擎 (模型: {self.model_size})...")

            # 检查是否安装了WhisperX
            try:
                import whisperx

                logger.info("WhisperX库检测成功")
            except ImportError as e:
                logger.error(f"WhisperX库未安装: {e}")
                logger.info("请安装WhisperX: pip install whisperx")
                return False

            # 检测设备
            self._detect_device()

            # 获取Hugging Face Token
            self.hf_token = self._get_huggingface_token()

            # 加载模型
            return self._load_models()

        except Exception as e:
            logger.error(f"WhisperX初始化失败: {e}")
            return False

    def _load_models(self) -> bool:
        """加载WhisperX模型"""
        try:
            import whisperx

            logger.info(f"加载WhisperX转录模型 ({self.model_size})...")

            # 加载转录模型
            self.model = whisperx.load_model(
                self.model_size,
                self.device,
                compute_type=self.compute_type,
                language=None,  # 支持自动检测
            )

            logger.info(f" WhisperX转录模型加载成功 (设备: {self.device})")
            self.initialized = True
            return True

        except Exception as e:
            logger.error(f" WhisperX模型加载失败: {e}")
            logger.error("1. 确保已安装 whisperx: pip install whisperx")
            logger.error("2. 检查网络连接，首次使用需要下载模型")
            logger.error("3. 如果GPU内存不足，可以使用更小的模型 (tiny/base/small)")

            return False

    def recognize_file(
        self, audio_path: str, language: str = "auto", **kwargs
    ) -> Dict[str, Any]:
        """
        识别音频文件 - WhisperX转录

        Args:
            audio_path: 音频文件路径
            language: 语言代码 (auto/zh/en等)
            **kwargs: 额外参数（enable_diarization: 是否启用说话人分离）

        Returns:
            包含转录文本、分段、说话人信息的字典
        """
        if not self.initialized:
            if not self.initialize():
                raise RuntimeError("WhisperX引擎未初始化")

        enable_diarization = kwargs.get("enable_diarization", True)
        start_time = time.time()

        try:
            logger.info(f"🎤 WhisperX识别音频: {Path(audio_path).name}")

            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")

            import whisperx

            # ====== 步骤1: 音频转录 ======
            logger.info("步骤1: 执行语音转录...")
            audio = whisperx.load_audio(audio_path)

            result = self.model.transcribe(
                audio,
                batch_size=self.batch_size,
                language=None if language == "auto" else language,
            )

            if not result or not result.get("segments"):
                raise RuntimeError("转录结果为空")

            # 繁体转简体
            result = self.fanti_zh_to_jianti_zh(result)

            detected_language = result.get("language", language)
            logger.info(
                f"转录完成: {len(result['segments'])} 个片段, 语言: {detected_language}"
            )

            # ====== 步骤2: 说话人分离（可选）======
            speakers_info = {}
            if enable_diarization:
                # 对齐词级时间戳
                # result = self.align_timestamps(
                #     detected_language, whisperx, result, audio
                # )
                logger.info("步骤2: 执行说话人分离...")
                speakers_info = self.speak_digitization(whisperx, result, audio_path)
                logger.info(f"说话人分离完成: {len(speakers_info)} 个说话人")
            else:
                logger.info(" 跳过说话人分离（未启用）")

            # ====== 步骤3: 格式化输出 ======
            result["processing_time"] = time.time() - start_time
            result["model"] = f"whisperx-{self.model_size}"
            result["device"] = self.device
            result["speakers"] = speakers_info

            formatted_result = self.format_result(result, audio_path)

            logger.info(
                f"WhisperX识别完成，耗时: {formatted_result['processing_time']:.2f}s"
            )
            return formatted_result

        except Exception as e:
            logger.error(f"WhisperX识别失败: {e}")
            return {
                "text": "",
                "language": language if language != "auto" else "zh",
                "segments": [],
                "speakers": {},
                "processing_time": time.time() - start_time,
                "model": f"whisperx-{self.model_size}",
                "device": self.device,
                "confidence": 0.0,
                "error": str(e),
                "features": {
                    "word_level_timestamps": False,
                    "speaker_diarization": False,
                    "emotion_detection": False,
                },
            }

    def fanti_zh_to_jianti_zh(self, transcribeResult: Any) -> Any:
        """将繁体字转为简体字"""
        import opencc

        converter = opencc.OpenCC("t2s")
        for seg in transcribeResult["segments"]:
            seg["text"] = converter.convert(seg["text"])

        return transcribeResult

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "WhisperX",
            "version": "3.0",
            "framework": "WhisperX + PyAnnote",
            "description": "集成语音识别和说话人分离的一体化解决方案，提供精确的词级时间戳",
            "supported_languages": {
                "auto": "自动检测",
                "zh": "中文",
                "en": "英语",
                "ja": "日语",
                "ko": "韩语",
                "es": "西班牙语",
                "fr": "法语",
                "de": "德语",
                # WhisperX支持Whisper的所有语言
            },
            "features": [
                "高精度语音转录",
                "词级时间戳对齐",
                "说话人分离 (需要HF Token)",
                "多语言支持",
                "批量处理",
            ],
            "capabilities": {
                "word_level_timestamps": True,
                "speaker_diarization": self.hf_token is not None,
                "batch_processing": True,
                "emotion_recognition": False,
                "multilingual": True,
            },
            "performance": {
                "accuracy": "高精度 (基于Whisper)",
                "speed": "中等 (比Whisper稍慢，因为包含对齐和分离)",
                "gpu_recommended": True,
            },
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "loaded": self.initialized and self.model is not None,
            "hf_token_configured": self.hf_token is not None,
        }

    def cleanup(self):
        """清理资源"""
        self.model = None
        self.align_model = None
        self.diarize_model = None
        self.initialized = False
        logger.info("WhisperX资源已清理")
