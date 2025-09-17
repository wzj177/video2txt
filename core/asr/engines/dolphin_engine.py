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
        self.model_path = self._get_model_path()  # 动态获取模型路径

        # 支持的模型尺寸
        self.supported_sizes = ["base", "small", "medium", "large"]

        # 获取模型尺寸配置
        if config and isinstance(config, dict):
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

    def _get_model_path(self) -> str:
        """动态获取模型路径"""
        try:
            # 尝试从model_api获取正确的路径
            from pathlib import Path

            # 获取项目根目录下的模型路径
            project_root = Path(__file__).parent.parent.parent.parent
            models_path = project_root / "data" / "models" / "dolphin"
            models_path.mkdir(parents=True, exist_ok=True)

            return str(models_path)

        except Exception as e:
            logger.warning(f"获取模型路径失败，使用默认路径: {e}")
            # 回退到默认路径
            from pathlib import Path

            project_root = Path(__file__).parent.parent.parent.parent
            default_path = project_root / "data" / "models" / "dolphin"
            default_path.mkdir(parents=True, exist_ok=True)
            return str(default_path)

    def _check_cuda(self) -> bool:
        """检查CUDA是否可用"""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def _configure_nltk_offline(self):
        """配置NLTK使用离线数据，避免网络下载"""
        try:
            import nltk
            import ssl
            import os

            # 设置环境变量禁用NLTK网络下载
            os.environ["NLTK_DATA_PATH"] = str(
                Path(__file__).parent.parent.parent.parent / "data" / "nltk_data"
            )

            # 禁用SSL证书验证（临时解决方案）
            try:
                _create_unverified_https_context = ssl._create_unverified_context
            except AttributeError:
                pass
            else:
                ssl._create_default_https_context = _create_unverified_https_context

            # 设置NLTK数据路径到项目目录
            project_root = Path(__file__).parent.parent.parent.parent
            nltk_data_path = project_root / "data" / "nltk_data"
            nltk_data_path.mkdir(parents=True, exist_ok=True)

            # 添加到NLTK数据路径（优先使用本地路径）
            nltk.data.path.insert(0, str(nltk_data_path))

            # 检查是否需要下载NLTK数据包
            required_packages = [
                ("averaged_perceptron_tagger", "taggers/averaged_perceptron_tagger"),
                ("cmudict", "corpora/cmudict"),
            ]

            missing_packages = []
            for package_name, package_path in required_packages:
                try:
                    nltk.data.find(package_path)
                    logger.debug(f"✅ NLTK数据包已存在: {package_name}")
                except LookupError:
                    missing_packages.append(package_name)

            # 如果有缺失的包，尝试下载（只在首次运行时）
            if missing_packages:
                logger.info(f"📦 检测到缺失的NLTK数据包: {missing_packages}")
                logger.info("💡 首次运行需要下载NLTK数据包，这可能需要一些时间...")

                for package_name in missing_packages:
                    try:
                        logger.info(f"📥 下载NLTK数据包: {package_name}")
                        success = nltk.download(
                            package_name, download_dir=str(nltk_data_path), quiet=False
                        )
                        if success:
                            logger.info(f"✅ {package_name} 下载成功")
                        else:
                            logger.warning(f"⚠️ {package_name} 下载失败")
                    except Exception as e:
                        logger.warning(f"⚠️ NLTK数据包 {package_name} 下载异常: {e}")
                        # 继续执行，不阻止模型初始化
                        pass
            else:
                logger.info("✅ 所有NLTK数据包已就绪")

        except ImportError:
            logger.info("📝 NLTK未安装，跳过NLTK配置")
        except Exception as e:
            logger.warning(f"⚠️ NLTK配置失败: {e}")
            # 不抛出异常，允许继续初始化

    def _parse_dolphin_output(self, raw_text: str) -> Dict[str, Any]:
        """
        解析Dolphin模型的原始输出，提取纯文本和时间戳信息

        输入格式示例：
        <zh><CN><asr><0.00> 安全帽的佩戴方法戴上安全帽一只手稳定帽檐另一只手旋转脑后的极轮调整至合适的松紧度之后调整下颗带长度到合适位置并拉紧扣号调整安全帽松紧并确保防滑条贴住额头<30.00>

        Args:
            raw_text: Dolphin模型的原始输出文本

        Returns:
            dict: 包含clean_text和segments的解析结果
        """
        import re
        from datetime import timedelta

        try:
            logger.debug(f"🔍 解析Dolphin原始输出: {raw_text[:100]}...")

            # 移除语言和地区标签 <zh><CN><asr>
            text = re.sub(r"<[a-zA-Z]+>", "", raw_text)

            # 提取时间戳和对应的文本内容
            # 匹配模式：<时间戳> 文本内容 <时间戳>
            timestamp_pattern = r"<(\d+\.?\d*)>"
            segments = []
            clean_text = ""

            # 分割文本，找到所有时间戳
            parts = re.split(timestamp_pattern, text)
            logger.debug(f"🔍 分割结果: {parts}")

            if len(parts) >= 3:
                # 对于格式 <0.00> 文本内容 <30.00>
                # parts[0] = '' (空字符串或前缀)
                # parts[1] = '0.00' (开始时间)
                # parts[2] = ' 文本内容 ' (实际内容)
                # parts[3] = '30.00' (结束时间)
                # parts[4] = '' (可能为空)

                # 检查是否是标准的开始-内容-结束格式
                if len(parts) == 4 and parts[0] == "" and parts[3] != "":
                    # 标准格式: <开始时间> 内容 <结束时间>
                    start_time = float(parts[1])
                    content = parts[2].strip()
                    end_time = float(parts[3])

                    if content:
                        segment = {
                            "start": start_time,
                            "end": end_time,
                            "text": content,
                        }
                        segments.append(segment)
                        clean_text = content

                        logger.debug(
                            f"📝 提取标准片段: {start_time:.2f}s-{end_time:.2f}s: {content[:50]}..."
                        )
                else:
                    # 复杂格式，可能有多个时间段
                    i = 1  # 从第一个时间戳开始
                    while i < len(parts) - 1:
                        if i + 2 < len(parts):
                            # 有开始时间、内容和结束时间
                            start_time = float(parts[i])
                            content = parts[i + 1].strip()
                            end_time = float(parts[i + 2])

                            if content:
                                segment = {
                                    "start": start_time,
                                    "end": end_time,
                                    "text": content,
                                }
                                segments.append(segment)
                                clean_text += content

                                logger.debug(
                                    f"📝 提取多段片段: {start_time:.2f}s-{end_time:.2f}s: {content[:50]}..."
                                )

                            i += 2  # 跳到下一个时间戳对
                        else:
                            break

            # 如果没有找到时间戳，直接清理文本
            if not segments:
                clean_text = re.sub(r"<[^>]*>", "", raw_text).strip()
                if clean_text:
                    segments = [
                        {"start": 0.0, "end": 0.0, "text": clean_text}  # 未知结束时间
                    ]

            # 最终清理文本
            clean_text = clean_text.strip()

            logger.info(
                f"✅ Dolphin输出解析完成: 提取了{len(segments)}个片段，总长度{len(clean_text)}字符"
            )

            return {"clean_text": clean_text, "segments": segments}

        except Exception as e:
            logger.warning(f"⚠️ Dolphin输出解析失败: {e}")
            # 回退到简单的标签移除
            fallback_text = re.sub(r"<[^>]*>", "", raw_text).strip()
            return {
                "clean_text": fallback_text,
                "segments": (
                    [{"start": 0.0, "end": 0.0, "text": fallback_text}]
                    if fallback_text
                    else []
                ),
            }

    def initialize(self) -> bool:
        """初始化Dolphin"""
        try:
            logger.info("🐬 初始化Dolphin方言识别模型...")

            # 配置NLTK使用离线数据，避免网络下载
            self._configure_nltk_offline()

            # 尝试导入Dolphin
            try:
                import dolphin
            except ImportError:
                logger.warning("⚠️ Dolphin 库未安装")
                logger.info("💡 请安装Dolphin: pip install dolphin")
                return False

            # 检查模型路径（路径已通过_get_model_path动态获取并创建）
            logger.info(f"🔧 使用Dolphin模型路径: {self.model_path}")

            # 确保Dolphin所需的缓存目录存在
            self._ensure_dolphin_cache_dirs()

            # 尝试加载模型，带重试机制
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"📥 加载Dolphin模型: {self.model_size} (尝试 {attempt + 1}/{max_retries})"
                    )

                    # 清理可能损坏的缓存并重新创建目录
                    if attempt > 0:
                        self._clear_dolphin_cache()
                        self._ensure_dolphin_cache_dirs()

                    self.model = dolphin.load_model(
                        self.model_size, self.model_path, self.device
                    )

                    self.initialized = True
                    logger.info(f"✅ Dolphin初始化成功 (设备: {self.device})")
                    return True

                except Exception as e:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次加载失败: {e}")
                    if attempt == max_retries - 1:
                        raise e
                    else:
                        logger.info("🔄 准备重试...")
                        import time

                        time.sleep(1)

        except Exception as e:
            logger.error(f"❌ Dolphin初始化失败: {e}")
            return False

    def _ensure_dolphin_cache_dirs(self):
        """确保Dolphin所需的缓存目录存在"""
        try:
            from pathlib import Path

            # 获取当前用户目录
            user_home = Path.home()

            # Dolphin需要的关键缓存目录
            required_cache_dirs = [
                user_home / ".cache" / "dolphin",
                user_home / ".cache" / "dolphin" / "speech_fsmn_vad",
                user_home / ".cache" / "dolphin" / "models",
            ]

            for cache_dir in required_cache_dirs:
                if not cache_dir.exists():
                    logger.info(f"📁 创建Dolphin缓存目录: {cache_dir}")
                    try:
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        logger.info(f"✅ 缓存目录创建成功: {cache_dir}")
                    except Exception as e:
                        logger.warning(f"⚠️ 缓存目录创建失败: {cache_dir}, 错误: {e}")
                else:
                    logger.debug(f"✅ 缓存目录已存在: {cache_dir}")

        except Exception as e:
            logger.warning(f"⚠️ 确保缓存目录时出错: {e}")

    def _clear_dolphin_cache(self):
        """清理Dolphin缓存"""
        try:
            import shutil
            from pathlib import Path

            # 常见的Dolphin缓存路径
            cache_paths = [
                Path.home() / ".cache" / "dolphin",
                Path.home() / ".dolphin",
                Path("/tmp/dolphin_cache") if hasattr(Path, "exists") else None,
            ]

            for cache_path in cache_paths:
                if cache_path and cache_path.exists():
                    logger.info(f"🧹 清理Dolphin缓存: {cache_path}")
                    try:
                        shutil.rmtree(cache_path)
                        logger.info(f"✅ 缓存清理成功: {cache_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ 缓存清理失败: {cache_path}, 错误: {e}")

        except Exception as e:
            logger.warning(f"⚠️ 清理缓存时出错: {e}")

    def recognize_file(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """使用Dolphin转录"""
        if not self.initialized or not self.model:
            raise RuntimeError("Dolphin引擎未初始化")

        try:
            # import dolphin
            from dolphin.transcribe import transcribe_long

            start_time = time.time()
            logger.info(f"🐬 Dolphin转录: {audio_path}")

            # 加载音频

            # 根据语言设置进行转录
            if language == "auto" or language == "zh":
                # 中文识别，可以指定地区
                results = transcribe_long(
                    model=self.model, audio=audio_path, lang_sym="zh", region_sym="CN"
                )
            elif language == "en":
                results = transcribe_long(
                    model=self.model, audio=audio_path, lang_sym="en"
                )
            else:
                # 其他语言或自动检测
                results = transcribe_long(model=self.model, audio=audio_path)

            processing_time = time.time() - start_time

            # 解析Dolphin输出，提取纯文本和时间戳信息
            text = ""
            first_result = results[0] if len(results) > 0 else None
            if first_result is None:
                logger.error("❌ Dolphin输出为空")
                return {
                    "text": "",
                    "segments": [],
                    "language": language,
                    "confidence": 0.0,
                    "processing_time": processing_time,
                    "model": "dolphin",
                    "device": self.device,
                    "sample_rate": 0.0,
                    "audio_length": 0.0,
                    "raw_text": "",
                }

            for result in results:
                # text: str
                # text_nospecial: str
                # language: str
                # region: str
                # rtf: float
                # start: float
                # end: float
                text += result.text
            # debug
            logger.info(f"🔍 Dolphin输出: {text}")
            parsed_result = self._parse_dolphin_output(text)

            # 构建返回结果
            return {
                "text": parsed_result["clean_text"],
                "segments": parsed_result["segments"],
                "language": getattr(first_result, "language", language),
                "confidence": getattr(first_result, "confidence", 0.9),
                "processing_time": processing_time,
                "model": "dolphin",
                "device": self.device,
                "sample_rate": getattr(first_result, "sample_rate", 16000),
                "audio_length": getattr(first_result, "audio_length", 0.0),
                "raw_text": text,  # 保留原始输出用于调试
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


def test_dolphin_parser():
    """测试Dolphin输出解析器"""
    engine = DolphinEngine()

    # 测试用例1: 标准格式
    test_input1 = "<zh><CN><asr><0.00> 安全帽的佩戴方法戴上安全帽一只手稳定帽檐另一只手旋转脑后的极轮调整至合适的松紧度之后调整下颗带长度到合适位置并拉紧扣号调整安全帽松紧并确保防滑条贴住额头<30.00>"

    result1 = engine._parse_dolphin_output(test_input1)
    print("🧪 测试用例1:")
    print(f"  原始文本: {test_input1}")
    print(f"  解析结果: {result1}")
    print()

    # 测试用例2: 多个时间段
    test_input2 = "<zh><CN><asr><0.00> 第一段内容<10.00><10.00> 第二段内容<20.00><20.00> 第三段内容<30.00>"

    result2 = engine._parse_dolphin_output(test_input2)
    print("🧪 测试用例2:")
    print(f"  原始文本: {test_input2}")
    print(f"  解析结果: {result2}")
    print()

    # 测试用例3: 没有时间戳
    test_input3 = "<zh><CN><asr> 纯文本内容没有时间戳"

    result3 = engine._parse_dolphin_output(test_input3)
    print("🧪 测试用例3:")
    print(f"  原始文本: {test_input3}")
    print(f"  解析结果: {result3}")


if __name__ == "__main__":
    test_dolphin_parser()
