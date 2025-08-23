#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音识别核心模块
支持多种语音识别引擎：Whisper、FasterWhisper、SenseVoice
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

# 设置日志
logger = logging.getLogger(__name__)

# 全局配置
VOICE_RECOGNITION_INITIALIZED = False


# 语音识别引擎配置
class VoiceEngineConfig:
    """语音识别引擎配置"""

    def __init__(self):
        self.whisper_model = "small"  # medium
        self.device = "auto"  # auto, cpu, cuda
        self.language = "auto"
        self.compute_type = "float16"

        # 中文优化配置
        self.chinese_optimized = False
        self.preferred_chinese_model = "large"  # 对中文效果更好的模型

    def auto_detect_device(self):
        """自动检测最佳设备"""
        try:
            import torch

            if torch.cuda.is_available():
                self.device = "cuda"
                logger.info("🚀 检测到CUDA，使用GPU加速")
            else:
                self.device = "cpu"
                logger.info("🔧 使用CPU处理")
        except ImportError:
            self.device = "cpu"
            logger.info("🔧 PyTorch未安装，使用CPU处理")

    def optimize_for_chinese(self):
        """优化中文识别配置"""
        logger.info("🇨🇳 启用中文优化模式")
        self.chinese_optimized = True
        # 如果模型较小，建议升级到large以获得更好的中文效果
        if self.whisper_model in ["tiny", "base", "small"]:
            old_model = self.whisper_model
            self.whisper_model = "medium"  # 平衡性能和效果
            logger.info(f"🔄 中文优化：模型从 {old_model} 升级到 {self.whisper_model}")

        # 对于中文，建议特定参数
        self.language = "zh"


class BaseVoiceEngine:
    """语音识别引擎基类"""

    def __init__(self, config: VoiceEngineConfig):
        self.config = config
        self.model = None
        self.initialized = False

    def initialize(self) -> bool:
        """初始化引擎"""
        raise NotImplementedError

    def transcribe(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """转录音频文件"""
        raise NotImplementedError

    def transcribe_chunk(
        self, audio_data: bytes, language: str = "auto"
    ) -> Dict[str, Any]:
        """转录音频数据块"""
        raise NotImplementedError


class FasterWhisperEngine(BaseVoiceEngine):
    """FasterWhisper引擎实现"""

    def initialize(self) -> bool:
        """初始化FasterWhisper"""
        try:
            from faster_whisper import WhisperModel

            whisper_model = "small"

            logger.info(f"🎤 初始化FasterWhisper - 模型: {whisper_model}")

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

    def transcribe(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
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


class WhisperEngine(BaseVoiceEngine):
    """OpenAI Whisper引擎实现"""

    def initialize(self) -> bool:
        """初始化Whisper"""
        try:
            import whisper

            logger.info(f"🎤 初始化Whisper - 模型: {self.config.whisper_model}")

            self.model = whisper.load_model(self.config.whisper_model)

            self.initialized = True
            logger.info("✅ Whisper初始化成功")
            return True

        except ImportError:
            logger.warning("⚠️ openai-whisper 未安装")
            return False
        except Exception as e:
            logger.error(f"❌ Whisper初始化失败: {e}")
            return False

    def transcribe(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用Whisper转录"""
        if not self.initialized:
            raise RuntimeError("Whisper引擎未初始化")

        try:
            start_time = time.time()

            # 语言处理：如果配置了中文优化，使用中文
            transcribe_language = None
            if self.config.chinese_optimized or language == "zh":
                transcribe_language = "zh"
                logger.info("🇨🇳 使用中文优化转录")
            elif language != "auto":
                transcribe_language = language

            # 执行转录，针对中文使用优化参数
            transcribe_options = {
                "language": transcribe_language,
                "verbose": False,
            }

            # 中文优化参数
            if transcribe_language == "zh":
                transcribe_options.update(
                    {
                        "beam_size": 5,  # 增加beam search
                        "best_of": 5,  # 增加候选数量
                        "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),  # 多温度尝试
                    }
                )
                logger.info("🔧 应用中文优化参数：beam_size=5, best_of=5, 多温度")

            result = self.model.transcribe(audio_path, **transcribe_options)

            processing_time = time.time() - start_time

            # 检测是否为中文内容
            detected_chinese = self._detect_chinese_content(result.get("text", ""))
            if detected_chinese and not self.config.chinese_optimized:
                logger.info("🇨🇳 检测到中文内容，建议启用中文优化模式以获得更好效果")

            # 格式化结果
            return {
                "text": result["text"],
                "segments": result["segments"],
                "language": result["language"],
                "duration": len(result["segments"]) > 0
                and result["segments"][-1]["end"]
                or 0,
                "processing_time": processing_time,
                "model": f"whisper-{self.config.whisper_model}",
                "device": self.config.device,
            }

        except Exception as e:
            logger.error(f"❌ Whisper转录失败: {e}")
            raise

    def _detect_chinese_content(self, text: str) -> bool:
        """检测文本是否包含中文内容"""
        if not text:
            return False

        chinese_char_count = 0
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        for char in text:
            # 检测中文字符范围
            if "\u4e00" <= char <= "\u9fff":
                chinese_char_count += 1

        # 如果中文字符占比超过30%，认为是中文内容
        if total_chars > 0:
            chinese_ratio = chinese_char_count / total_chars
            return chinese_ratio > 0.3

        return False


class SenseVoiceEngine(BaseVoiceEngine):
    """SenseVoice引擎实现 - 专为中文优化"""

    def initialize(self) -> bool:
        """初始化SenseVoice"""
        try:
            from funasr import AutoModel

            logger.info("🇨🇳 初始化SenseVoice - 中文语音识别专用模型")

            # 使用SenseVoice-Small模型
            self.model = AutoModel(
                model="iic/SenseVoiceSmall",
                device=self.config.device,
                trust_remote_code=True,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
            )

            self.initialized = True
            logger.info("✅ SenseVoice初始化成功 - 中文识别准确率提升50%+")
            return True

        except ImportError:
            logger.warning("⚠️ funasr 未安装，请运行: pip install funasr")
            return False
        except Exception as e:
            logger.error(f"❌ SenseVoice初始化失败: {e}")
            return False

    def transcribe(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用SenseVoice转录 - 中文优化"""
        if not self.initialized:
            raise RuntimeError("SenseVoice引擎未初始化")

        try:
            start_time = time.time()

            logger.info("🇨🇳 使用SenseVoice进行中文优化转录")

            # SenseVoice推理
            result = self.model.generate(input=audio_path, language=language)

            processing_time = time.time() - start_time

            # 解析SenseVoice结果
            if result and len(result) > 0:
                # SenseVoice的结果格式
                transcription_result = result[0]

                # 提取文本
                if isinstance(transcription_result, dict):
                    text = transcription_result.get("text", "")
                else:
                    text = str(transcription_result)

                # 构建标准格式的segments（SenseVoice可能没有详细的时间戳信息）
                segments = [
                    {
                        "start": 0.0,
                        "end": processing_time,  # 估算
                        "text": text,
                    }
                ]

                # 检测语言（SenseVoice主要用于中文）
                detected_language = (
                    "zh" if self._detect_chinese_content(text) else "auto"
                )

                return {
                    "text": text,
                    "segments": segments,
                    "language": detected_language,
                    "duration": processing_time,
                    "processing_time": processing_time,
                    "model": "sensevoice-small",
                    "device": self.config.device,
                    "chinese_optimized": True,
                    "features": [
                        "emotion_detection",
                        "event_detection",
                        "multilingual",
                    ],
                }
            else:
                logger.warning("⚠️ SenseVoice返回空结果")
                return {
                    "text": "",
                    "segments": [],
                    "language": "unknown",
                    "duration": 0,
                    "processing_time": processing_time,
                    "model": "sensevoice-small",
                    "device": self.config.device,
                    "error": "empty_result",
                }

        except Exception as e:
            logger.error(f"❌ SenseVoice转录失败: {e}")
            raise

    def _detect_chinese_content(self, text: str) -> bool:
        """检测文本是否包含中文内容"""
        if not text:
            return False

        chinese_char_count = 0
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        for char in text:
            # 检测中文字符范围
            if "\u4e00" <= char <= "\u9fff":
                chinese_char_count += 1

        # 如果中文字符占比超过20%，认为是中文内容（SenseVoice阈值可以更低）
        if total_chars > 0:
            chinese_ratio = chinese_char_count / total_chars
            return chinese_ratio > 0.2

        return False


class DolphinEngine(BaseVoiceEngine):
    """DataoceanAI Dolphin引擎实现 - 支持40种东方语言和22种中文方言"""

    def initialize(self) -> bool:
        """初始化Dolphin"""
        try:
            import dolphin

            logger.info("🐬 初始化Dolphin - 支持40种东方语言和22种中文方言的语音大模型")

            self.model = dolphin.load_model(
                "small",
                model_dir="/Users/jiechengyang/src/py-app/ai-video2text/data/models/dolphin",
                device=self.config.device or "cpu",
            )

            self.initialized = True
            logger.info("✅ Dolphin初始化成功 - 东方语言识别准确率超越Whisper两代")
            return True

        except ImportError:
            logger.warning(
                "⚠️ dataoceanai-dolphin 未安装，请运行: pip install dataoceanai-dolphin"
            )
            return False
        except Exception as e:
            logger.error(f"❌ Dolphin初始化失败: {e}")
            return False

    def transcribe(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用Dolphin转录 - 多语言优化"""
        if not self.initialized:
            raise RuntimeError("Dolphin引擎未初始化")

        try:
            import dolphin

            start_time = time.time()

            logger.info("🐬 使用Dolphin进行多语言优化转录")

            # 加载音频
            audio_data = dolphin.load_audio(audio_path)

            # 执行转录 - 使用正确的参数名
            result = self.model(audio_data)
            processing_time = time.time() - start_time

            # 解析Dolphin结果
            if result:
                # 提取文本内容
                if isinstance(result, dict):
                    text = result.get("text", "")
                    detected_language = result.get("language", "auto")
                    segments = result.get("segments", [])

                    # 如果没有segments，创建一个
                    if not segments:
                        segments = [
                            {
                                "start": 0.0,
                                "end": processing_time,
                                "text": text,
                            }
                        ]
                else:
                    text = str(result)
                    detected_language = self._detect_content_language(text)
                    segments = [
                        {
                            "start": 0.0,
                            "end": processing_time,
                            "text": text,
                        }
                    ]

                return {
                    "text": text,
                    "segments": segments,
                    "language": detected_language,
                    "duration": processing_time,
                    "processing_time": processing_time,
                    "model": "dolphin-asr",
                    "device": self.config.device,
                    "multilingual_optimized": True,
                    "supported_languages": "40东方语言+22中文方言",
                    "features": [
                        "speech_recognition",
                        "voice_activity_detection",
                        "language_identification",
                        "multilingual_support",
                    ],
                }
            else:
                logger.warning("⚠️ Dolphin返回空结果")
                return {
                    "text": "",
                    "segments": [],
                    "language": "unknown",
                    "duration": 0,
                    "processing_time": processing_time,
                    "model": "dolphin-asr",
                    "device": self.config.device,
                    "error": "empty_result",
                }

        except Exception as e:
            logger.error(f"❌ Dolphin转录失败: {e}")
            raise

    def _detect_content_language(self, text: str) -> str:
        """检测文本语言类型"""
        if not text:
            return "unknown"

        # 中文字符检测
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        # 英文字符检测
        english_chars = sum(1 for char in text if char.isalpha() and ord(char) < 128)
        # 其他字符
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars == 0:
            return "unknown"

        chinese_ratio = chinese_chars / total_chars
        english_ratio = english_chars / total_chars

        if chinese_ratio > 0.3:
            return "zh"  # 中文（包括方言）
        elif english_ratio > 0.5:
            return "en"  # 英文
        else:
            return "auto"  # 其他东方语言


class VoiceRecognitionCore:
    """语音识别核心管理器"""

    def __init__(self):
        self.config = VoiceEngineConfig()
        self.config.auto_detect_device()

        self.engines = {}
        self.current_engine = None
        self.initialized = False

    def initialize(self, preferred_engine: str = "auto") -> bool:
        """初始化语音识别核心"""
        global VOICE_RECOGNITION_INITIALIZED

        logger.info("🔧 正在初始化语音识别核心...")

        # 智能引擎选择策略
        if preferred_engine == "auto":
            # 优先使用Dolphin（支持40种东方语言），然后SenseVoice（中文专用），最后FasterWhisper和Whisper
            engines_to_try = ["dolphin", "sensevoice", "faster_whisper", "whisper"]
        else:
            engines_to_try = [preferred_engine] + [
                e
                for e in ["dolphin", "sensevoice", "faster_whisper", "whisper"]
                if e != preferred_engine
            ]

        available_engines = []

        for engine_name in engines_to_try:
            try:
                engine = self._create_engine(engine_name)
                if engine and engine.initialize():
                    self.engines[engine_name] = engine
                    available_engines.append(engine_name)
                    if not self.current_engine:
                        self.current_engine = engine
                        logger.info(f"✅ 默认引擎设置为: {engine_name}")
            except Exception as e:
                logger.warning(f"⚠️ 引擎 {engine_name} 初始化失败: {e}")

        if not self.current_engine:
            logger.error("❌ 没有可用的语音识别引擎")
            return False

        # 记录可用引擎
        logger.info(f"🔧 可用引擎: {', '.join(available_engines)}")

        self.initialized = True
        VOICE_RECOGNITION_INITIALIZED = True
        logger.info("✅ 语音识别核心初始化完成")
        return True

    def _create_engine(self, engine_name: str) -> Optional[BaseVoiceEngine]:
        """创建指定引擎"""
        if engine_name == "faster_whisper":
            return FasterWhisperEngine(self.config)
        elif engine_name == "whisper":
            return WhisperEngine(self.config)
        elif engine_name == "sensevoice":
            return SenseVoiceEngine(self.config)
        elif engine_name == "dolphin":
            return DolphinEngine(self.config)
        else:
            logger.warning(f"⚠️ 未知引擎: {engine_name}")
            return None

    def transcribe(
        self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """转录音频文件"""
        if not self.initialized or not self.current_engine:
            logger.error("❌ 语音识别核心未初始化")
            return None

        try:
            logger.info(f"🎤 开始转录: {Path(audio_path).name}")

            # 第一次尝试转录
            result = self.current_engine.transcribe(audio_path, language)

            # 检测是否为中文内容，如果是且没有优化，进行第二次优化转录
            if (
                language == "auto"
                and hasattr(self.current_engine, "_detect_chinese_content")
                and self.current_engine._detect_chinese_content(result.get("text", ""))
                and not self.config.chinese_optimized
            ):

                logger.info("🇨🇳 检测到中文内容，启用中文优化进行重新转录...")
                self.config.optimize_for_chinese()

                # 重新创建引擎以应用优化配置
                engine_name = next(
                    (
                        name
                        for name, engine in self.engines.items()
                        if engine == self.current_engine
                    ),
                    None,
                )
                if engine_name:
                    optimized_engine = self._create_engine(engine_name)
                    if optimized_engine and optimized_engine.initialize():
                        self.engines[engine_name] = optimized_engine
                        self.current_engine = optimized_engine
                        logger.info("🔧 已应用中文优化配置，重新转录中...")
                        result = self.current_engine.transcribe(audio_path, "zh")

            logger.info(f"✅ 转录完成，用时: {result.get('processing_time', 0):.2f}秒")
            return result
        except Exception as e:
            logger.error(f"❌ 转录失败: {e}")
            return None

    def enable_chinese_optimization(self) -> bool:
        """手动启用中文优化模式"""
        if not self.config.chinese_optimized:
            self.config.optimize_for_chinese()
            logger.info("🇨🇳 已启用中文优化模式")
            return True
        return False

    def auto_select_best_engine(
        self, audio_path: str = None, language_hint: str = "auto"
    ) -> bool:
        """根据语言提示自动选择最佳引擎"""
        best_engine = None

        # 根据语言提示选择最佳引擎
        if language_hint in ["zh", "chinese", "中文"]:
            # 中文内容优先使用SenseVoice，其次Dolphin
            if "sensevoice" in self.engines:
                best_engine = "sensevoice"
                logger.info("🇨🇳 检测到中文内容，切换到SenseVoice引擎（中文专用）")
            elif "dolphin" in self.engines:
                best_engine = "dolphin"
                logger.info("🇨🇳 检测到中文内容，切换到Dolphin引擎（支持22种中文方言）")
            elif "whisper" in self.engines:
                # 如果没有专门的中文引擎，使用Whisper并启用中文优化
                best_engine = "whisper"
                self.config.optimize_for_chinese()
                logger.info("🇨🇳 检测到中文内容，使用Whisper中文优化模式")
        elif language_hint in ["auto", "unknown"]:
            # 自动检测优先使用Dolphin（支持40种东方语言），然后FasterWhisper
            if "dolphin" in self.engines:
                best_engine = "dolphin"
                logger.info("🌏 自动模式，使用Dolphin引擎（支持40种东方语言）")
            elif "faster_whisper" in self.engines:
                best_engine = "faster_whisper"
            elif "whisper" in self.engines:
                best_engine = "whisper"
        else:
            # 其他语言（如英文、日文、韩文等）优先使用Dolphin，再考虑Whisper系列
            if "dolphin" in self.engines:
                best_engine = "dolphin"
                logger.info(
                    f"🌏 检测到{language_hint}语言，使用Dolphin引擎（支持多东方语言）"
                )
            elif "faster_whisper" in self.engines:
                best_engine = "faster_whisper"
            elif "whisper" in self.engines:
                best_engine = "whisper"

        # 切换到最佳引擎
        if best_engine and best_engine != self.get_current_engine_name():
            return self.switch_engine(best_engine)

        return True

    def get_current_engine_name(self) -> str:
        """获取当前引擎名称"""
        for name, engine in self.engines.items():
            if engine == self.current_engine:
                return name
        return "unknown"

    def switch_engine(self, engine_name: str) -> bool:
        """切换语音识别引擎"""
        if engine_name in self.engines:
            self.current_engine = self.engines[engine_name]
            logger.info(f"🔄 已切换到引擎: {engine_name}")
            return True
        else:
            logger.warning(f"⚠️ 引擎 {engine_name} 不可用")
            return False

    def get_available_engines(self) -> List[str]:
        """获取可用引擎列表"""
        return list(self.engines.keys())

    def get_current_engine_info(self) -> Dict[str, Any]:
        """获取当前引擎信息"""
        if not self.current_engine:
            return {}

        return {
            "engine": self.current_engine.__class__.__name__,
            "model": self.config.whisper_model,
            "device": self.config.device,
            "initialized": self.current_engine.initialized,
        }


# 全局语音识别核心实例
voice_core = VoiceRecognitionCore()


def initialize_voice_recognition(preferred_engine: str = "auto") -> bool:
    """初始化语音识别系统"""
    return voice_core.initialize(preferred_engine)


def get_voice_core() -> VoiceRecognitionCore:
    """获取语音识别核心实例"""
    return voice_core


def is_voice_recognition_initialized() -> bool:
    """检查语音识别是否已初始化"""
    return VOICE_RECOGNITION_INITIALIZED


# 导出主要接口
__all__ = [
    "voice_core",
    "initialize_voice_recognition",
    "get_voice_core",
    "is_voice_recognition_initialized",
    "VoiceRecognitionCore",
    "VoiceEngineConfig",
]
