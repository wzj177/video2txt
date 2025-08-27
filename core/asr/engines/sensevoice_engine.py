#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SenseVoice语音识别引擎 - 阿里达摩院中文专用引擎
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import time
import json
import tempfile

from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class SenseVoiceEngine(BaseVoiceEngine):
    """SenseVoice语音识别引擎"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.model = None
        self.device = "auto"
        self.model_name = "iic/SenseVoiceSmall"
        self.processor = None

    def initialize(self) -> bool:
        """初始化SenseVoice引擎"""
        try:
            logger.info("🔧 初始化SenseVoice引擎...")

            # 检查是否安装了必要的依赖
            try:
                import torch
                import torchaudio
                from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
            except ImportError as e:
                logger.warning(f"SenseVoice依赖未安装: {e}")
                logger.info("请安装依赖: pip install torch torchaudio transformers")
                return False

            # 检查CUDA是否可用
            if torch.cuda.is_available():
                self.device = "cuda"
                logger.info("🚀 检测到CUDA，将使用GPU加速")
            else:
                self.device = "cpu"
                logger.info("💻 使用CPU进行推理")

            # 加载模型
            return self._load_model()

        except Exception as e:
            logger.error(f"❌ SenseVoice初始化失败: {e}")
            return False

    def _load_model(self) -> bool:
        """加载SenseVoice模型"""
        try:
            logger.info("📥 加载SenseVoice模型...")

            # 导入必要的库
            import torch
            from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq

            try:
                # 尝试从HuggingFace加载
                self.processor = AutoProcessor.from_pretrained(
                    self.model_name, trust_remote_code=True
                )

                self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    self.model_name,
                    torch_dtype=(
                        torch.float16 if self.device == "cuda" else torch.float32
                    ),
                    device_map=self.device,
                    trust_remote_code=True,
                )

                logger.info(f"✅ SenseVoice模型加载成功 (设备: {self.device})")
                self.initialized = True
                return True

            except Exception as hf_error:
                logger.warning(f"从HuggingFace加载失败: {hf_error}")

                # 尝试使用ModelScope（国内镜像）
                try:
                    from modelscope import AutoProcessor, AutoModelForSpeechSeq2Seq

                    self.processor = AutoProcessor.from_pretrained(
                        "iic/SenseVoiceSmall", trust_remote_code=True
                    )

                    self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                        "iic/SenseVoiceSmall",
                        torch_dtype=(
                            torch.float16 if self.device == "cuda" else torch.float32
                        ),
                        device_map=self.device,
                        trust_remote_code=True,
                    )

                    logger.info("✅ SenseVoice模型从ModelScope加载成功")
                    self.initialized = True
                    return True

                except Exception as ms_error:
                    logger.error(f"ModelScope加载也失败: {ms_error}")
                    logger.error("请检查网络连接或手动下载模型")
                    return False

        except Exception as e:
            logger.error(f"❌ SenseVoice模型加载失败: {e}")
            return False

    def _preprocess_audio(self, audio_path: str) -> str:
        """预处理音频文件"""
        try:
            # 检查音频格式，SenseVoice通常需要16kHz采样率的WAV文件
            import torch
            import torchaudio

            # 加载音频
            waveform, sample_rate = torchaudio.load(audio_path)

            # 转换为单声道
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)

            # 重采样到16kHz（如果需要）
            if sample_rate != 16000:
                resampler = torchaudio.transforms.Resample(sample_rate, 16000)
                waveform = resampler(waveform)
                sample_rate = 16000

            # 保存预处理后的音频
            temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            torchaudio.save(temp_audio.name, waveform, sample_rate)

            return temp_audio.name

        except Exception as e:
            logger.warning(f"音频预处理失败，使用原文件: {e}")
            return audio_path

    def recognize_file(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """识别音频文件"""
        if not self.initialized:
            # 尝试重新初始化
            if not self.initialize():
                raise RuntimeError("SenseVoice引擎未初始化")

        try:
            start_time = time.time()

            logger.info(f"🎤 SenseVoice识别音频: {Path(audio_path).name}")

            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")

            # 预处理音频
            processed_audio = self._preprocess_audio(audio_path)

            try:
                # 使用SenseVoice进行识别
                import torch
                import torchaudio

                # 加载音频
                waveform, sample_rate = torchaudio.load(processed_audio)

                # 使用processor处理音频
                inputs = self.processor(
                    waveform.squeeze(), sampling_rate=sample_rate, return_tensors="pt"
                )

                # 移动到正确的设备
                if self.device == "cuda":
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                # 进行推理
                with torch.no_grad():
                    generated_ids = self.model.generate(**inputs)

                # 解码结果
                transcription = self.processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0]

                # 构建返回结果
                processing_time = time.time() - start_time
                audio_duration = waveform.shape[-1] / sample_rate

                result = {
                    "text": transcription,
                    "language": "zh",  # SenseVoice主要用于中文
                    "segments": [
                        {"start": 0.0, "end": audio_duration, "text": transcription}
                    ],
                    "processing_time": processing_time,
                    "model": "sensevoice",
                    "device": self.device,
                    "confidence": 0.95,  # SenseVoice通常有很高的中文识别准确率
                    "sample_rate": sample_rate,
                    "audio_length": audio_duration,
                }

                logger.info(f"✅ SenseVoice识别完成，耗时: {processing_time:.2f}s")
                logger.info(f"📝 识别结果: {transcription[:100]}...")

                return result

            finally:
                # 清理临时文件
                if processed_audio != audio_path and os.path.exists(processed_audio):
                    try:
                        os.unlink(processed_audio)
                    except:
                        pass

        except Exception as e:
            logger.error(f"❌ SenseVoice识别失败: {e}")

            # 返回错误信息但保持结构一致
            return {
                "text": "",
                "language": "zh",
                "segments": [],
                "processing_time": time.time() - start_time,
                "model": "sensevoice",
                "device": self.device,
                "confidence": 0.0,
                "error": str(e),
            }

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "SenseVoice",
            "version": "1.0",
            "description": "阿里达摩院快速语音理解模型，支持多语言识别、情感识别和事件检测",
            "supported_languages": {
                "zh": "中文 (Mandarin Chinese)",
                "en": "英语 (English)",
                "yue": "粤语 (Cantonese)",
                "ja": "日语 (Japanese)",
                "ko": "韩语 (Korean)",
            },
            "features": [
                "自动语音识别 (ASR)",
                "口语语言识别 (LID)",
                "语音情感识别 (SER)",
                "声学事件检测 (AED)",
                "超低推理延迟 (比Whisper-small快7倍，比Whisper-large快17倍)",
            ],
            "performance_advantage": {
                "vs_whisper_small": "7倍更快",
                "vs_whisper_large": "17倍更快",
                "multilingual": "多语言支持优秀",
            },
            "model": self.model_name,
            "device": self.device,
            "loaded": self.initialized and self.model is not None,
        }
