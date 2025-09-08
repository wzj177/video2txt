#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音识别核心模块
支持多种语音识别引擎：Whisper、FasterWhisper、SenseVoice、Dolphin
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

# 引入新的引擎
from .engines import WhisperEngine, FasterWhisperEngine, SenseVoiceEngine, DolphinEngine
from .base_asr import BaseVoiceEngine

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


class VoiceRecognitionCore:
    """语音识别核心管理器"""

    def __init__(self):
        self.config = VoiceEngineConfig()
        self.config.auto_detect_device()

        self.engines = {}
        self.current_engine = None
        self.initialized = False
        self.preferred_engine = "auto"
        self.model_size = "small"

    def initialize(
        self, preferred_engine: str = "auto", model_size: str = "small"
    ) -> bool:
        """初始化语音识别核心（延迟加载）"""
        global VOICE_RECOGNITION_INITIALIZED

        logger.info("🔧 语音识别核心准备就绪（延迟加载模式）...")

        # 设置首选引擎，但不立即加载
        self.preferred_engine = preferred_engine
        self.model_size = model_size

        # 更新配置以支持不同引擎的模型大小
        if hasattr(self.config, "whisper_model"):
            self.config.whisper_model = model_size

        logger.info(f"🎯 设置引擎: {preferred_engine}, 模型大小: {model_size}")

        # 标记为已初始化（准备状态）
        self.initialized = True
        VOICE_RECOGNITION_INITIALIZED = True
        logger.info("✅ 语音识别核心已准备就绪，将在首次使用时加载引擎")
        return True

    def _ensure_engine_loaded(self, engine_name: str = None) -> bool:
        """确保指定引擎已加载"""
        target_engine = engine_name or self.preferred_engine

        # 如果引擎已经加载，直接返回
        if target_engine in self.engines and self.engines[target_engine].initialized:
            if not self.current_engine:
                self.current_engine = self.engines[target_engine]
            return True

        logger.info(f"🔧 首次使用，正在加载 {target_engine} 引擎...")

        # 智能引擎选择策略 - 优先使用更稳定的引擎
        if target_engine == "auto":
            # 按稳定性和成功率排序：whisper > faster_whisper > sensevoice > dolphin
            engines_to_try = ["whisper", "faster_whisper", "sensevoice", "dolphin"]
        else:
            engines_to_try = [target_engine] + [
                e
                for e in ["whisper", "faster_whisper", "sensevoice", "dolphin"]
                if e != target_engine
            ]

        successful_engines = []
        failed_engines = []

        for engine_name in engines_to_try:
            try:
                logger.info(f"🔄 尝试加载引擎: {engine_name}")

                if engine_name not in self.engines:
                    engine = self._create_engine(engine_name)
                    if engine:
                        self.engines[engine_name] = engine
                    else:
                        failed_engines.append((engine_name, "引擎创建失败"))
                        continue

                engine = self.engines[engine_name]
                if not engine.initialized:
                    if engine.initialize():
                        successful_engines.append(engine_name)
                        if not self.current_engine:
                            self.current_engine = engine
                            logger.info(f"✅ 引擎加载成功: {engine_name}")
                        return True
                    else:
                        failed_engines.append((engine_name, "初始化失败"))
                else:
                    successful_engines.append(engine_name)
                    if not self.current_engine:
                        self.current_engine = engine
                        logger.info(f"✅ 引擎已加载: {engine_name}")
                    return True

            except Exception as e:
                failed_engines.append((engine_name, str(e)))
                logger.warning(f"⚠️ 引擎 {engine_name} 加载失败: {e}")

        # 记录失败详情
        if failed_engines:
            logger.error("❌ 引擎加载失败详情:")
            for engine_name, error in failed_engines:
                logger.error(f"  - {engine_name}: {error}")

        # 提供解决方案建议
        logger.error("❌ 没有可用的语音识别引擎")
        logger.info("💡 解决方案建议:")
        logger.info("  1. 安装基础Whisper: pip install openai-whisper")
        logger.info("  2. 检查网络连接，确保可以下载模型")
        logger.info("  3. 如果网络有问题，可手动下载模型到 ~/.cache/whisper/")
        logger.info("  4. 检查系统是否支持CUDA（GPU加速）")

        return False

    def _create_engine(self, engine_name: str) -> Optional[BaseVoiceEngine]:
        """创建指定引擎"""
        # 创建引擎配置，包含模型大小信息
        engine_config = {
            "model_name": engine_name,
            "model_size": self.model_size,
            "device": getattr(self.config, "device", "auto"),
            "language": getattr(self.config, "language", "auto"),
        }

        # print(f"engine_config: {engine_config}")

        # 根据引擎类型添加特定配置
        if engine_name in ["whisper", "faster_whisper"]:
            engine_config["whisper_model"] = self.model_size
        elif engine_name == "sensevoice":
            # SenseVoice目前主要是small模型
            engine_config["model_name"] = "iic/SenseVoiceSmall"
        elif engine_name == "dolphin":
            # Dolphin引擎直接使用model_size参数，不需要额外的model_name
            # engine_config["model_size"] 已经在上面设置了
            pass

        logger.info(f"🔧 创建{engine_name}引擎，配置: {engine_config}")

        if engine_name == "faster_whisper":
            return FasterWhisperEngine(engine_config)
        elif engine_name == "whisper":
            return WhisperEngine(engine_config)
        elif engine_name == "sensevoice":
            return SenseVoiceEngine(engine_config)
        elif engine_name == "dolphin":
            return DolphinEngine(engine_config)
        else:
            logger.warning(f"⚠️ 未知引擎: {engine_name}")
            return None

    def recognize_file(
        self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """识别音频文件"""
        if not self.initialized:
            logger.error("❌ 语音识别核心未初始化")
            return {
                "text": "",
                "error": "语音识别核心未初始化",
                "success": False,
                "processing_time": 0.0,
            }

        # 延迟加载引擎
        if not self._ensure_engine_loaded():
            logger.error("❌ 无法加载语音识别引擎")
            return {
                "text": "",
                "error": "无法加载任何语音识别引擎，请检查网络连接或安装相关依赖",
                "success": False,
                "processing_time": 0.0,
                "suggestions": [
                    "pip install openai-whisper",
                    "检查网络连接",
                    "手动下载模型到 ~/.cache/whisper/",
                    "检查CUDA支持",
                ],
            }

        try:
            logger.info(f"🎤 开始识别: {Path(audio_path).name}")

            # 自动模式下，根据语言提示自动选择最佳引擎
            if language == "auto":
                self.auto_select_best_engine(language_hint=language)

            # 执行转录
            result = self.current_engine.recognize_file(audio_path, language=language)

            # 检测是否为中文内容，如果是且没有优化，进行第二次优化转录
            if (
                language == "auto"
                and hasattr(self.current_engine, "_detect_chinese_content")
                and self.current_engine._detect_chinese_content(result.get("text", ""))
                and not self.config.chinese_optimized
            ):

                logger.info("🇨🇳 检测到中文内容，启用中文优化进行重新识别...")
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
                        logger.info("🔧 已应用中文优化配置，重新识别中...")
                        result = self.current_engine.recognize_file(
                            audio_path, language="zh"
                        )

            logger.info(f"✅ 识别完成，用时: {result.get('processing_time', 0):.2f}秒")
            return result
        except Exception as e:
            logger.error(f"❌ 识别失败: {e}")
            return None

    def batch_recognize(self, audio_files: List[str], **kwargs) -> List[Dict[str, Any]]:
        """批量识别音频文件"""
        results = []

        for audio_file in audio_files:
            logger.info(
                f"🔄 处理文件 {len(results)+1}/{len(audio_files)}: {audio_file}"
            )
            result = self.recognize_file(audio_file, **kwargs)
            if result:
                results.append(result)
            else:
                logger.warning(f"⚠️ 文件识别失败: {audio_file}")

        logger.info(f"✅ 批量识别完成，成功: {len(results)}/{len(audio_files)}")
        return results

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

    def get_supported_engines(self) -> List[str]:
        """获取支持的引擎列表"""
        return ["whisper", "faster_whisper", "sensevoice", "dolphin"]

    def get_available_engines(self) -> List[str]:
        """获取可用引擎列表"""
        return list(self.engines.keys())

    def get_engine_info(self) -> Dict[str, Any]:
        """获取当前引擎信息"""
        if not self.current_engine:
            return {"engine": "none", "initialized": False}

        try:
            engine_info = (
                self.current_engine.get_engine_info()
                if hasattr(self.current_engine, "get_engine_info")
                else {}
            )
            engine_info.update(
                {
                    "engine": self.current_engine.__class__.__name__,
                    "model": self.config.whisper_model,
                    "device": self.config.device,
                    "initialized": self.current_engine.initialized,
                }
            )
            return engine_info
        except Exception as e:
            logger.error(f"获取引擎信息失败: {str(e)}")
            return {
                "engine": self.current_engine.__class__.__name__,
                "initialized": False,
                "error": str(e),
            }

    def cleanup(self):
        """清理资源"""
        if self.current_engine:
            try:
                if hasattr(self.current_engine, "cleanup"):
                    self.current_engine.cleanup()
                logger.info("✅ 引擎资源清理完成")
            except Exception as e:
                logger.error(f"❌ 引擎清理失败: {str(e)}")

        self.initialized = False
        self.current_engine = None


# 全局语音识别核心实例
voice_core = VoiceRecognitionCore()


def initialize_voice_recognition(
    model: str = "whisper", model_size: str = "small"
) -> bool:
    """初始化语音识别系统"""
    # 解析模型格式：支持 "engine-size" 格式或传统的单独参数
    if "-" in model and model != "auto":
        # 新格式：engine-size (如 "sensevoice-small", "whisper-medium")
        parts = model.split("-", 1)  # 只分割第一个 "-"
        engine_name = parts[0]
        model_size = parts[1] if len(parts) > 1 else "small"
        logger.info(f"🔧 解析模型格式: 引擎={engine_name}, 大小={model_size}")
        return voice_core.initialize(engine_name, model_size)
    else:
        # 传统格式：分别传递引擎和大小
        return voice_core.initialize(model, model_size)


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
