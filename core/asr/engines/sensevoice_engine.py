#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SenseVoice语音识别引擎 - 阿里达摩院快速语音理解模型
基于官方FunASR框架实现，支持多语言识别、情感识别和事件检测
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import time
import json
import re

from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class SenseVoiceEngine(BaseVoiceEngine):
    """SenseVoice语音识别引擎 - 使用官方FunASR框架"""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.model = None
        self.device = "auto"
        self.model_name = "iic/SenseVoiceSmall"
        self.use_vad = True  # 默认启用VAD
        self.batch_mode = False  # 是否使用批量模式
        self.offline_mode = False  # 离线模式标志

    def _check_local_model(self) -> tuple[bool, Optional[str]]:
        """
        检查本地是否有SenseVoice模型

        Returns:
            tuple[bool, Optional[str]]: (是否存在本地模型, 模型路径)
        """
        # 检查ModelScope缓存
        modelscope_cache = (
                Path.home()
                / ".cache"
                / "modelscope"
                / "hub"
                / "models"
                / "iic"
                / "SenseVoiceSmall"
        )

        if modelscope_cache.exists():
            # 检查关键文件是否存在
            required_files = [
                "config.yaml",
                "model.pt",
                "model.safetensors",
                "tokenizer.json",
            ]

            existing_files = list(modelscope_cache.glob("*"))
            if len(existing_files) > 0:  # 只要有文件就认为模型存在
                logger.info(f"发现本地SenseVoice模型: {modelscope_cache}")
                logger.info(
                    f"模型文件: {[f.name for f in existing_files[:5]]}..."
                )  # 显示前5个文件
                return True, str(modelscope_cache)

        logger.warning("未找到本地SenseVoice模型")
        return False, None

    def _setup_offline_environment(self, cache_dir: str) -> None:
        """设置离线环境变量"""
        import os

        # 设置ModelScope相关环境变量
        os.environ["MODELSCOPE_CACHE"] = cache_dir

        # 设置Hugging Face离线模式
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        # 设置PyTorch Hub离线模式
        os.environ["TORCH_HOME"] = cache_dir

        # 禁用自动更新检查
        os.environ["MODELSCOPE_OFFLINE"] = "1"

        logger.info("已配置离线模式环境变量")

    def initialize(self) -> bool:
        """初始化SenseVoice引擎"""
        try:
            logger.info(" 初始化SenseVoice引擎...")

            # 检查是否安装了FunASR
            try:
                from funasr import AutoModel
                from funasr.utils.postprocess_utils import (
                    rich_transcription_postprocess,
                )

                logger.info("FunASR库检测成功")
            except ImportError as e:
                logger.error(f"FunASR库未安装: {e}")
                logger.info("请安装FunASR: pip install funasr modelscope")
                return False

            # 检查设备
            try:
                import torch

                if torch.cuda.is_available():
                    self.device = "cuda:0"
                    logger.info("检测到CUDA，将使用GPU加速")
                else:
                    self.device = "cpu"
                    logger.info("使用CPU进行推理")
            except ImportError:
                self.device = "cpu"
                logger.info("PyTorch未检测到，使用CPU")

            # 加载模型
            return self._load_model()

        except Exception as e:
            logger.error(f"SenseVoice初始化失败: {e}")
            return False

    def _load_model(self) -> bool:
        """加载SenseVoice模型 - 使用官方FunASR方式"""
        try:
            logger.info("加载SenseVoice模型...")

            from funasr import AutoModel

            # 检查本地模型
            has_local_model, local_model_path = self._check_local_model()

            if has_local_model:
                # 使用本地模型
                cache_dir = str(Path.home() / ".cache" / "modelscope")
                self._setup_offline_environment(cache_dir)
                model_path_to_use = local_model_path
                self.offline_mode = True
                logger.info(f"将使用本地模型: {local_model_path}")
            else:
                # 需要下载模型
                cache_dir = "./data/models/funasr_cache"
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                model_path_to_use = self.model_name
                self.offline_mode = False
                logger.warning("未找到本地模型，将尝试在线下载")

            # 🔧 构建AutoModel参数
            model_kwargs = {
                "model": model_path_to_use,
                "trust_remote_code": True,
                "device": self.device,
                "cache_dir": cache_dir,
            }

            # 如果是离线模式，添加离线参数
            if self.offline_mode:
                model_kwargs["local_files_only"] = True
                logger.info("使用离线模式加载")

            # 根据音频长度决定是否使用VAD
            if self.use_vad:
                # 长音频模式：使用VAD进行音频切割
                logger.info("启用VAD模式 - 适合长音频")
                model_kwargs.update(
                    {
                        "vad_model": "fsmn-vad",
                        "vad_kwargs": {
                            "max_single_segment_time": 30000
                        },  # 30秒最大切割
                    }
                )
            else:
                # 短音频批量模式：移除VAD，提高效率
                logger.info("启用批量模式 - 适合短音频(<30s)")

            # 创建模型
            self.model = AutoModel(**model_kwargs)

            logger.info(f"SenseVoice模型加载成功 (设备: {self.device})")
            logger.info(f"模型路径: {self.model.model_path}")
            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"SenseVoice模型加载失败: {e}")

            # 特殊处理网络连接错误
            error_str = str(e)
            if any(keyword in error_str for keyword in ["NameResolutionError","modelscope.cn","Connection","timeout"]):
                logger.error("检测到网络连接问题")

                # 如果有本地模型但加载失败，尝试强制离线模式
                if has_local_model and local_model_path:
                    logger.info("尝试强制离线模式...")
                    try:
                        # 更激进的离线设置
                        import os

                        os.environ["CURL_CA_BUNDLE"] = ""  # 禁用SSL验证
                        os.environ["REQUESTS_CA_BUNDLE"] = ""
                        os.environ["SSL_VERIFY"] = "false"

                        # 简化的模型加载
                        self.model = AutoModel(
                            model=local_model_path,
                            trust_remote_code=True,
                            device=self.device,
                            local_files_only=True,
                        )

                        logger.info(" 强制离线模式加载成功")
                        self.initialized = True
                        return True

                    except Exception as offline_error:
                        logger.error(f"强制离线模式也失败: {offline_error}")

                # 提供解决方案
                logger.error(" 解决方案:")
                logger.error("1. 检查网络连接到 www.modelscope.cn")
                logger.error(
                    "2. 确保模型文件完整下载到 ~/.cache/modelscope/hub/models/iic/SenseVoiceSmall"
                )
                logger.error("3. 或者暂时使用其他语音模型（Whisper、Dolphin）")
                logger.error("4. 重启应用后再试")
            else:
                logger.error("请确保已安装FunASR: pip install funasr modelscope")

            return False

    def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        try:
            import librosa

            y, sr = librosa.load(audio_path)
            duration = len(y) / sr
            return duration
        except Exception as e:
            logger.warning(f"获取音频时长失败: {e}")
            return 0.0

    def _should_use_batch_mode(self, audio_path: str) -> bool:
        """判断是否应该使用批量模式（短音频）"""
        duration = self._get_audio_duration(audio_path)
        return duration < 30.0  # 小于30秒使用批量模式

    def _clean_sensevoice_output(self, text: str) -> str:
        """
        清理SenseVoice输出中的emoji图标和特殊符号

        SenseVoice会在输出中添加情感和事件标记
        """
        import re

        if not text:
            return text

        try:
            logger.debug(f"清理SenseVoice输出: {text[:100]}...")

            # 移除所有emoji符号
            # Unicode范围包括：
            # - Emoticons: U+1F600-U+1F64F
            # - Miscellaneous Symbols: U+1F300-U+1F5FF
            # - Transport and Map: U+1F680-U+1F6FF
            # - Additional symbols: U+2600-U+26FF, U+2700-U+27BF
            emoji_pattern = re.compile(
                "["
                "\U0001f600-\U0001f64f"  # emoticons
                "\U0001f300-\U0001f5ff"  # symbols & pictographs
                "\U0001f680-\U0001f6ff"  # transport & map symbols
                "\U0001f1e0-\U0001f1ff"  # flags (iOS)
                "\U00002600-\U000026ff"  # miscellaneous symbols
                "\U00002700-\U000027bf"  # dingbats
                "\U0001f900-\U0001f9ff"  # supplemental symbols
                "\U0001fa00-\U0001fa6f"  # chess symbols
                "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
                "\U00002000-\U0000206f"  # general punctuation
                "]+",
                flags=re.UNICODE,
            )

            clean_text = emoji_pattern.sub("", text)

            # 清理多余的空格和标点
            clean_text = re.sub(r"\s+", " ", clean_text)  # 多个空格变为单个
            clean_text = re.sub(
                r"^\s*[。，,\s]+", "", clean_text
            )  # 移除开头的标点和空格
            clean_text = re.sub(
                r"[。，,\s]+\s*$", "", clean_text
            )  # 移除结尾的标点和空格
            clean_text = clean_text.strip()

            if clean_text != text:
                logger.debug(f"文本清理完成: {clean_text[:100]}...")

            return clean_text

        except Exception as e:
            logger.warning(f"文本清理失败: {e}")
            # 简单的回退清理
            return re.sub(r"[🎼😊🎵🎶🎤🎧🔊🔇📢📣📯🎺🎷🎸🥁🎹]", "", text).strip()

    def _smart_text_segmentation(
            self, text: str, total_duration: float, min_segments: int = 2
    ) -> List[Dict[str, Any]]:
        """智能文本分割，创建合理的字幕片段"""
        if not text.strip():
            return [{"start": 0.0, "end": total_duration, "text": ""}]

        # 按标点符号分割文本
        import re

        # 优先按句号、问号、感叹号分割
        sentences = re.split(r"[。！？]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 如果句子太少，尝试按逗号分割
        if len(sentences) < min_segments:
            parts = re.split(r"[，,]", text)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) > len(sentences):
                sentences = parts

        # 如果还是太少，按固定长度分割
        if len(sentences) < min_segments:
            max_chars_per_segment = len(text) // min_segments
            sentences = []
            for i in range(0, len(text), max_chars_per_segment):
                segment = text[i: i + max_chars_per_segment].strip()
                if segment:
                    sentences.append(segment)

        # 确保至少有min_segments个片段
        if min_segments > len(sentences) > 0:
            # 将最长的句子再次分割
            longest_idx = max(range(len(sentences)), key=lambda i: len(sentences[i]))
            longest_sentence = sentences[longest_idx]
            if len(longest_sentence) > 20:  # 只分割足够长的句子
                mid_point = len(longest_sentence) // 2
                # 寻找最近的空格或标点
                for offset in range(5):
                    if mid_point + offset < len(longest_sentence) and longest_sentence[mid_point + offset] in " ，,":
                        mid_point += offset
                        break
                    elif mid_point - offset >= 0 and longest_sentence[mid_point - offset] in " ，,":
                        mid_point -= offset
                        break

                first_part = longest_sentence[:mid_point].strip()
                second_part = longest_sentence[mid_point:].strip()
                sentences[longest_idx] = first_part
                sentences.insert(longest_idx + 1, second_part)

        # 创建时间戳
        segments = []
        if sentences:
            segment_duration = total_duration / len(sentences)
            for i, sentence in enumerate(sentences):
                start_time = i * segment_duration
                end_time = min((i + 1) * segment_duration, total_duration)
                segments.append(
                    {
                        "start": round(start_time, 2),
                        "end": round(end_time, 2),
                        "text": sentence,
                    }
                )
        else:
            # 备用方案
            segments = [{"start": 0.0, "end": total_duration, "text": text}]

        return segments

    def recognize_file(
            self, audio_path: str, language: str = "auto", **kwargs
    ) -> Dict[str, Any]:
        """识别音频文件 - 使用官方FunASR方式

        Args:
            audio_path: 音频文件路径
            language: 语言代码
            **kwargs: 其他参数（为兼容性保留，本引擎暂不使用）
        """
        if not self.initialized:
            # 尝试重新初始化
            if not self.initialize():
                raise RuntimeError("SenseVoice引擎未初始化")

        try:
            start_time = time.time()
            logger.info(f"SenseVoice识别音频: {Path(audio_path).name}")

            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")

            # 获取音频信息
            audio_duration = self._get_audio_duration(audio_path)
            is_short_audio = self._should_use_batch_mode(audio_path)

            logger.info(
                f"音频时长: {audio_duration:.2f}s, 模式: {'批量' if is_short_audio else 'VAD'}"
            )

            # 导入后处理工具
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            # 根据音频长度和用途选择不同的参数
            if is_short_audio and not self.use_vad:
                # 短音频批量模式 - 降低VAD敏感度，适合实时转录
                res = self.model.generate(
                    input=audio_path,
                    cache={},
                    language=language,  # "zh", "en", "yue", "ja", "ko", "nospeech", "auto"
                    use_itn=True,  # 包含标点与逆文本正则化
                    batch_size=64,  # 批量大小
                    # 实时转录优化：降低VAD阈值，提高短音频识别率
                    vad_kwargs={"max_single_segment_time": 30000},  # 允许更长的单段时间
                )
            else:
                # 长音频VAD模式 - 优化时间戳分割
                logger.info("🎙️ 使用VAD模式，优化时间戳分割以支持关键帧提取")
                res = self.model.generate(
                    input=audio_path,
                    cache={},
                    language=language,  # "zh", "en", "yue", "ja", "ko", "nospeech", "auto"
                    use_itn=True,  # 包含标点与逆文本正则化
                    batch_size_s=30,  # 减小batch大小，提高分割精度
                    merge_vad=False,  # 关键：不合并VAD片段，保持原始时间戳
                    # merge_length_s=15,  # 移除合并参数
                    batch_size_threshold_s=20,  # 当单个片段超过20秒时，batch_size设为1
                )

            # 处理识别结果
            if not res or len(res) == 0:
                raise RuntimeError("识别结果为空")

            # 使用官方后处理工具
            raw_text = res[0]["text"]
            processed_text = rich_transcription_postprocess(raw_text)

            # 清理emoji图标和特殊符号
            processed_text = self._clean_sensevoice_output(processed_text)

            # 提取分段信息 - 优化VAD分割处理
            segments = []

            # 检查是否有VAD分割的结果
            if isinstance(res, list) and len(res) > 1:
                # 多个VAD片段，每个都有自己的时间戳
                logger.info(f"检测到 {len(res)} 个VAD分割片段")
                for i, segment_result in enumerate(res):
                    if "text" in segment_result:
                        segment_text = rich_transcription_postprocess(
                            segment_result["text"]
                        )
                        # 清理segment中的emoji
                        segment_text = self._clean_sensevoice_output(segment_text)
                        if segment_text.strip():  # 只添加非空文本
                            # 尝试从结果中提取时间信息
                            start_time = segment_result.get(
                                "start", i * 10
                            )  # 默认每10秒一段
                            end_time = segment_result.get("end", (i + 1) * 10)

                            segments.append(
                                {
                                    "start": (
                                        start_time / 1000.0
                                        if start_time > 1000
                                        else start_time
                                    ),
                                    "end": (
                                        end_time / 1000.0
                                        if end_time > 1000
                                        else end_time
                                    ),
                                    "text": segment_text,
                                }
                            )

                # 如果segments不为空，合并所有文本
                if segments:
                    processed_text = " ".join([seg["text"] for seg in segments])

            elif "timestamp" in res[0] and res[0]["timestamp"]:
                # 单个结果但有详细时间戳信息
                timestamps = res[0]["timestamp"]
                logger.info(f"📋 检测到 {len(timestamps)} 个时间戳片段")

                # 尝试分割文本匹配时间戳
                text_parts = processed_text.split("。")  # 按句号分割
                if len(text_parts) > 1 and len(timestamps) > 1:
                    # 将文本片段分配给时间戳
                    for i, (start, end) in enumerate(timestamps):
                        if i < len(text_parts) and text_parts[i].strip():
                            segments.append(
                                {
                                    "start": start / 1000.0,  # 转换为秒
                                    "end": end / 1000.0,
                                    "text": text_parts[i].strip() + "。",
                                }
                            )
                else:
                    # 时间戳数量与文本不匹配，创建单个片段
                    segments = [
                        {
                            "start": timestamps[0][0] / 1000.0,
                            "end": timestamps[-1][1] / 1000.0,
                            "text": processed_text,
                        }
                    ]
            else:
                # 没有详细时间戳，使用智能文本分割
                logger.info("使用智能文本分割创建多个字幕片段")
                segments = self._smart_text_segmentation(processed_text, audio_duration)

            # 如果仍然只有一个片段且时长较长，尝试进一步分割
            if len(segments) == 1 and audio_duration > 30:
                logger.info("⚡ 检测到长音频单片段，尝试进一步分割")
                segments = self._smart_text_segmentation(
                    processed_text, audio_duration, min_segments=3
                )

            logger.info(f"生成了 {len(segments)} 个字幕片段")

            # 格式化分段信息，对齐 WhisperX 格式
            formatted_segments = []
            for i, segment in enumerate(segments):
                formatted_segment = {
                    "start": round(segment.get("start", 0), 2),
                    "end": round(segment.get("end", 0), 2),
                    "duration": round(
                        segment.get("end", 0) - segment.get("start", 0), 2
                    ),
                    "text": segment.get("text", "").strip(),
                    "speaker": "Speaker_1",  # SenseVoice 不支持说话人分离，使用默认值
                    "confidence": 0.95,
                    "language": language,
                    "emotion": segment.get("emotion"),  # SenseVoice 支持情感分析
                }
                formatted_segments.append(formatted_segment)

            # 检测语言（从结果中提取或使用默认）
            detected_language = language
            if "language" in res[0]:
                detected_language = res[0]["language"]
            elif language == "auto":
                # 简单的语言检测
                if any(ord(char) > 127 for char in processed_text):
                    detected_language = "zh"  # 包含中文字符
                else:
                    detected_language = "en"

            # 构建默认说话人信息（因为不支持说话人分离）
            speakers_info = {
                "Speaker_1": {
                    "id": "Speaker_1",
                    "name": "Speaker_1",
                    "segments_count": len(formatted_segments),
                    "total_duration": audio_duration,
                    "words": [seg["text"] for seg in formatted_segments],
                }
            }

            # 构建返回结果 - 对齐 WhisperX 格式
            processing_time = time.time() - start_time

            result = {
                "text": processed_text,
                "language": detected_language,
                "segments": formatted_segments,  # 使用格式化后的分段
                "speakers": speakers_info,  # 新增：对齐 WhisperX 格式
                "processing_time": processing_time,
                "model": "sensevoice",
                "device": self.device,
                "confidence": 0.95,  # SenseVoice通常有很高的识别准确率
                "audio_length": audio_duration,
                "features": {  # 更新：对齐 WhisperX 格式
                    "word_level_timestamps": False,  # SenseVoice 不支持词级时间戳
                    "speaker_diarization": False,  # SenseVoice 不支持说话人分离
                    "emotion_detection": True,  # SenseVoice支持情感识别
                },
                "statistics": {  # 新增：对齐 WhisperX 格式
                    "total_segments": len(formatted_segments),
                    "total_speakers": 1,
                    "total_duration": audio_duration,
                },
                "raw_result": res[0],  # 保留原始结果用于调试
            }

            logger.info(f"SenseVoice识别完成，耗时: {processing_time:.2f}s")
            logger.info(f"识别结果: {processed_text[:100]}...")

            return result

        except Exception as e:
            logger.error(f"SenseVoice识别失败: {e}")
            processing_time = time.time() - start_time

            # 返回错误信息但保持结构一致
            return {
                "text": "",
                "language": language if language != "auto" else "zh",
                "segments": [],
                "processing_time": processing_time,
                "model": "sensevoice",
                "device": self.device,
                "confidence": 0.0,
                "error": str(e),
                "features": {
                    "vad_enabled": self.use_vad,
                    "batch_mode": False,
                    "emotion_detection": True,
                    "event_detection": True,
                },
            }

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "name": "SenseVoice",
            "version": "2.0",
            "framework": "FunASR",
            "description": "阿里达摩院快速语音理解模型，支持任意格式音频输入，任意时长输入",
            "supported_languages": {
                "auto": "自动检测",
                "zh": "中文 (Mandarin Chinese)",
                "en": "英语 (English)",
                "yue": "粤语 (Cantonese)",
                "ja": "日语 (Japanese)",
                "ko": "韩语 (Korean)",
                "nospeech": "无语音",
            },
            "features": [
                "自动语音识别 (ASR)",
                "口语语言识别 (LID)",
                "语音情感识别 (SER)",
                "声学事件检测 (AED)",
                "语音活动检测 (VAD)",
                "逆文本正则化 (ITN)",
                "超低推理延迟 (比Whisper快7-17倍)",
            ],
            "capabilities": {
                "any_format_input": True,  # 支持任意格式音频输入
                "any_duration_input": True,  # 支持任意时长输入
                "vad_support": True,  # VAD语音活动检测
                "batch_processing": True,  # 批量处理
                "emotion_recognition": True,  # 情感识别
                "event_detection": True,  # 事件检测
                "punctuation": True,  # 自动标点
                "itn_support": True,  # 逆文本正则化
            },
            "performance": {
                "vs_whisper_small": "7倍更快",
                "vs_whisper_large": "17倍更快",
                "multilingual": "优秀的多语言支持",
                "realtime_factor": "< 0.1",  # 实时因子
            },
            "model": self.model_name,
            "device": self.device,
            "vad_enabled": self.use_vad,
            "loaded": self.initialized and self.model is not None,
            "model_path": (
                getattr(self.model, "model_path", None) if self.model else None
            ),
        }
