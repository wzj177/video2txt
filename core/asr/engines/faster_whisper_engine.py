#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FasterWhisper语音识别引擎
faster-whisper的实现，速度更快
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any
from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class FasterWhisperEngine(BaseVoiceEngine):
    """FasterWhisper引擎实现"""

    def initialize(self) -> bool:
        """初始化FasterWhisper"""
        try:
            from faster_whisper import WhisperModel

            # 支持字典和对象两种配置格式
            if isinstance(self.config, dict):
                whisper_model = self.config.get(
                    "whisper_model", self.config.get("model_size", "small")
                )
                device = self.config.get("device", "auto")
                chinese_optimized = self.config.get("chinese_optimized", False)
                preferred_chinese_model = self.config.get(
                    "preferred_chinese_model", "medium"
                )
            else:
                whisper_model = getattr(self.config, "whisper_model", "small")
                device = getattr(self.config, "device", "auto")
                chinese_optimized = getattr(self.config, "chinese_optimized", False)
                preferred_chinese_model = getattr(
                    self.config, "preferred_chinese_model", "medium"
                )

            logger.info(f"初始化FasterWhisper - 模型: {whisper_model}")

            # 如果是中文优化，使用更大的模型
            if chinese_optimized:
                whisper_model = preferred_chinese_model

            # 智能选择计算类型
            compute_type = self._get_optimal_compute_type()

            self.model = WhisperModel(
                whisper_model,
                device=device,
                compute_type=compute_type,
                local_files_only=False,  # 允许在线下载模型
            )

            self.initialized = True
            logger.info(f"FasterWhisper初始化成功 (计算类型: {compute_type})")
            return True

        except ImportError:
            logger.warning("faster-whisper 未安装")
            return False
        except Exception as e:
            logger.error(f"FasterWhisper初始化失败: {e}")
            return False

    def _get_optimal_compute_type(self) -> str:
        """获取最优的计算类型"""
        try:
            import torch

            # 支持字典和对象两种配置格式
            device = (
                self.config.get("device", "auto")
                if isinstance(self.config, dict)
                else getattr(self.config, "device", "auto")
            )

            # 如果是CPU或者不支持float16，使用int8或float32
            if device == "cpu":
                logger.info("CPU设备，使用int8计算类型")
                return "int8"

            # 检查CUDA是否支持float16
            if device == "cuda" or device == "auto":
                try:
                    # 测试是否支持float16
                    device = torch.device(
                        "cuda" if torch.cuda.is_available() else "cpu"
                    )
                    if device.type == "cuda":
                        # 检查GPU计算能力
                        capability = torch.cuda.get_device_capability(device)
                        if capability[0] >= 7:  # Volta架构及以上支持高效的float16
                            logger.info("GPU支持高效float16计算")
                            return "float16"
                        else:
                            logger.info("GPU不支持高效float16，使用int8")
                            return "int8"
                    else:
                        logger.info("未检测到CUDA，使用int8计算类型")
                        return "int8"
                except Exception as cuda_e:
                    logger.warning(f"CUDA检查失败: {cuda_e}，使用int8")
                    return "int8"

            # 默认回退到int8
            return "int8"

        except ImportError:
            logger.info("PyTorch未安装，使用int8计算类型")
            return "int8"
        except Exception as e:
            logger.warning(f"计算类型检测失败: {e}，使用int8")
            return "int8"

    def recognize_file(
        self, audio_path: str, language: str = "auto", **kwargs
    ) -> Dict[str, Any]:
        """使用FasterWhisper转录

        Args:
            audio_path: 音频文件路径
            language: 语言代码
            **kwargs: 额外参数（enable_diarization: 是否启用说话人分离）
        """
        if not self.initialized:
            raise RuntimeError("FasterWhisper引擎未初始化")

        enable_diarization = kwargs.get("enable_diarization", False)
        start_time = time.time()

        try:
            logger.info(f"🎤 FasterWhisper识别音频: {Path(audio_path).name}")

            # ====== 步骤1: 音频转录 ======
            logger.info("步骤1: 执行语音转录...")
            segments, info = self.model.transcribe(
                audio_path,
                language=language if language != "auto" else None,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                initial_prompt="请使用简体中文输出",
            )

            # 构建结果结构
            result_segments = []
            full_text = ""

            for segment in segments:
                segment_dict = {
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                    "confidence": 0.85,
                }

                # 如果有词级时间戳
                if hasattr(segment, "words") and segment.words:
                    segment_dict["words"] = [
                        {
                            "word": word.word,
                            "start": round(word.start, 2),
                            "end": round(word.end, 2),
                            "score": getattr(word, "probability", 0.9),
                        }
                        for word in segment.words
                    ]

                result_segments.append(segment_dict)
                full_text += segment.text + " "

            logger.info(
                f"✅ 转录完成: {len(result_segments)} 个片段, 语言: {info.language}"
            )

            # ====== 步骤2: 说话人分离（可选）======
            speakers_info = {}
            if enable_diarization:
                logger.info("步骤2: 执行说话人分离...")
                # FasterWhisper需要通过基类方法进行说话人分离
                # 这里需要将result转换为whisperx格式
                result_for_diarization = {
                    "segments": result_segments,
                    "language": info.language,
                }
                # 注意：FasterWhisper不支持词级对齐，跳过align_timestamps
                # 直接调用说话人分离需要whisperx，这里先设置默认值
                speakers_info = {
                    "Speaker_1": {
                        "id": "Speaker_1",
                        "name": "Speaker_1",
                        "segments_count": len(result_segments),
                        "total_duration": info.duration,
                    }
                }
                logger.info("⚠️  FasterWhisper不支持说话人分离，使用默认Speaker_1")
            else:
                logger.info("⏭️  跳过说话人分离（未启用）")

            # ====== 步骤3: 格式化输出 ======
            whisper_model = (
                self.config.get("whisper_model", self.config.get("model_size", "small"))
                if isinstance(self.config, dict)
                else "small"
            )

            result = {
                "text": full_text.strip(),
                "language": info.language,
                "segments": result_segments,
                "speakers": speakers_info,
                "processing_time": time.time() - start_time,
                "model": f"faster-whisper-{whisper_model}",
                "device": self.device,
            }

            formatted_result = self.format_result(result, audio_path)
            logger.info(
                f"✅ FasterWhisper识别完成，耗时: {formatted_result['processing_time']:.2f}s"
            )
            return formatted_result

        except Exception as e:
            logger.error(f"❌ FasterWhisper识别失败: {e}")
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
        # 支持字典和对象两种配置格式
        if isinstance(self.config, dict):
            model_size = self.config.get(
                "whisper_model", self.config.get("model_size", "small")
            )
            device = self.config.get("device", "auto")
            compute_type = self.config.get("compute_type", "float16")
        else:
            model_size = getattr(self.config, "whisper_model", "small")
            device = getattr(self.config, "device", "auto")
            compute_type = getattr(self.config, "compute_type", "float16")

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
            "model_size": model_size,
            "device": device,
            "compute_type": compute_type,
            "initialized": self.initialized,
            "features": ["高性能优化", "GPU加速", "内存优化", "批处理支持"],
        }
