#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dolphin语音识别引擎
支持方言识别的专用模型
"""

import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class DolphinEngine(BaseVoiceEngine):
    """Dolphin引擎实现"""

    def __init__(self, config=None):
        # 处理VoiceEngineConfig对象或字典
        if config is not None:
            if hasattr(config, "__dict__"):
                # VoiceEngineConfig对象，转换为字典
                config_dict = {
                    "model_size": getattr(config, "whisper_model", "small"),
                    "device": getattr(config, "device", "auto"),
                    "language": getattr(config, "language", "auto"),
                }
                super().__init__(config_dict)
            else:
                # 已经是字典
                super().__init__(config)
        else:
            super().__init__({})

        self.model = None
        self.model_path = "/data/models/dolphin"  # 默认模型路径

        # 支持的模型尺寸
        self.supported_sizes = ["base", "small", "medium", "large"]

        # 获取模型尺寸配置
        if hasattr(config, "whisper_model"):
            self.model_size = config.whisper_model
        elif config and isinstance(config, dict):
            self.model_size = config.get("model_size", "small")
        else:
            self.model_size = "small"

        # 验证模型尺寸
        if self.model_size not in self.supported_sizes:
            logger.warning(
                f"⚠️ 不支持的Dolphin模型尺寸: {self.model_size}, 使用默认: small"
            )
            self.model_size = "small"

        self.device = "cuda" if self._check_cuda() else "cpu"

    def _check_cuda(self) -> bool:
        """检查CUDA是否可用"""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def initialize(self) -> bool:
        """初始化Dolphin"""
        try:
            logger.info("🐬 初始化Dolphin方言识别模型...")

            # 尝试导入Dolphin
            try:
                import dolphin
            except ImportError:
                logger.warning("⚠️ Dolphin 库未安装")
                logger.info("💡 请安装Dolphin: pip install dolphin")
                return False

            # 检查模型路径
            model_path = Path(self.model_path)
            if not model_path.exists():
                logger.warning(f"⚠️ Dolphin模型路径不存在: {self.model_path}")
                # 尝试使用项目内的模型路径
                project_model_path = (
                    Path(__file__).parent.parent.parent.parent
                    / "data"
                    / "models"
                    / "dolphin"
                )
                if project_model_path.exists():
                    self.model_path = str(project_model_path)
                    logger.info(f"🔄 使用项目模型路径: {self.model_path}")
                else:
                    logger.warning("⚠️ 未找到Dolphin模型文件，将尝试在线加载")

            # 加载模型
            logger.info(f"📥 加载Dolphin模型: {self.model_size}")
            self.model = dolphin.load_model(
                self.model_size, self.model_path, self.device
            )

            self.initialized = True
            logger.info(f"✅ Dolphin初始化成功 (设备: {self.device})")
            return True

        except Exception as e:
            logger.error(f"❌ Dolphin初始化失败: {e}")
            return False

    def recognize_file(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用Dolphin转录"""
        if not self.initialized or not self.model:
            raise RuntimeError("Dolphin引擎未初始化")

        try:
            import dolphin

            start_time = time.time()
            logger.info(f"🐬 Dolphin转录: {audio_path}")

            # 加载音频
            waveform = dolphin.load_audio(audio_path)

            # 根据语言设置进行转录
            if language == "auto" or language == "zh":
                # 中文识别，可以指定地区
                result = self.model(waveform, lang_sym="zh", region_sym="CN")
            elif language == "en":
                result = self.model(waveform, lang_sym="en")
            else:
                # 其他语言或自动检测
                result = self.model(waveform)

            processing_time = time.time() - start_time

            # 构建返回结果
            return {
                "text": result.text,
                "segments": getattr(result, "segments", []),
                "language": getattr(result, "language", language),
                "confidence": getattr(result, "confidence", 0.9),
                "processing_time": processing_time,
                "model": "dolphin",
                "device": self.device,
                "sample_rate": getattr(result, "sample_rate", 16000),
                "audio_length": getattr(result, "audio_length", 0.0),
            }

        except ImportError:
            logger.error("❌ Dolphin库未安装")
            raise RuntimeError("Dolphin库未安装")
        except Exception as e:
            logger.error(f"❌ Dolphin转录失败: {e}")
            raise

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "Dolphin",
            "version": "unknown",
            "description": "支持方言识别的语音识别引擎，在东西方语言ASR性能上表现优异",
            "supported_languages": {
                "zh": "中文 (Mandarin Chinese)",
                "ja": "日语 (Japanese)",
                "th": "泰语 (Thai)",
                "ru": "俄语 (Russian)",
                "ko": "韩语 (Korean)",
                "id": "印度尼西亚语 (Indonesian)",
                "vi": "越南语 (Vietnamese)",
                "ct": "粤语 (Yue Chinese)",
                "hi": "印地语 (Hindi)",
                "ur": "乌尔都语 (Urdu)",
                "ms": "马来语 (Malay)",
                "uz": "乌兹别克语 (Uzbek)",
                "ar": "阿拉伯语 (Arabic)",
                "fa": "波斯语 (Persian)",
                "bn": "孟加拉语 (Bengali)",
                "ta": "泰米尔语 (Tamil)",
                "te": "泰卢固语 (Telugu)",
                "ug": "维吾尔语 (Uighur)",
                "gu": "古吉拉特语 (Gujarati)",
                "my": "缅甸语 (Burmese)",
                "tl": "塔加洛语 (Tagalog)",
                "kk": "哈萨克语 (Kazakh)",
                "or": "奥里亚语 (Oriya/Odia)",
                "ne": "尼泊尔语 (Nepali)",
                "mn": "蒙古语 (Mongolian)",
                "km": "高棉语 (Khmer)",
                "jv": "爪哇语 (Javanese)",
                "lo": "老挝语 (Lao)",
                "si": "僧伽罗语 (Sinhala)",
                "fil": "菲律宾语 (Filipino)",
                "ps": "普什图语 (Pushto)",
                "pa": "旁遮普语 (Panjabi)",
                "auto": "自动检测",
            },
            "supported_regions": {
                "zh-CN": "中文(普通话)",
                "zh-TW": "中文(台湾)",
                "zh-WU": "中文(吴语)",
                "zh-SICHUAN": "中文(四川话)",
                "zh-SHANXI": "中文(山西话)",
                "zh-ANHUI": "中文(安徽话)",
                "zh-TIANJIN": "中文(天津话)",
                "zh-NINGXIA": "中文(宁夏话)",
                "zh-SHAANXI": "中文(陕西话)",
                "zh-HEBEI": "中文(河北话)",
                "zh-SHANDONG": "中文(山东话)",
                "zh-GUANGDONG": "中文(广东话)",
                "zh-SHANGHAI": "中文(上海话)",
                "zh-HUBEI": "中文(湖北话)",
                "zh-LIAONING": "中文(辽宁话)",
                "zh-GANSU": "中文(甘肃话)",
                "zh-FUJIAN": "中文(福建话)",
                "zh-HUNAN": "中文(湖南话)",
                "zh-HENAN": "中文(河南话)",
                "zh-YUNNAN": "中文(云南话)",
                "zh-MINNAN": "中文(闽南语)",
                "zh-WENZHOU": "中文(温州话)",
                "ct-HK": "粤语(香港)",
                "ct-GZ": "粤语(广东)",
            },
            "supported_sizes": self.supported_sizes,
            "current_size": self.model_size,
            "model_path": self.model_path,
            "device": self.device,
            "initialized": self.initialized,
            "features": [
                "方言识别",
                "多尺寸模型 (base/small/medium/large)",
                "语言和地区指定",
                "CUDA加速支持",
                "与Whisper性能对比优势",
            ],
            "performance_notes": {
                "small_vs_base": "平均24.5%的WER改进",
                "medium_vs_small": "额外8.3%的WER改进",
                "large_vs_medium": "额外6.5%的WER改进",
                "comparison": "base/small/medium模型可达到Whisper large-v3的性能",
            },
        }
