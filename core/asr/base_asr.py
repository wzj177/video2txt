#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音识别引擎基类
定义统一的语音识别接口
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
import os


class BaseVoiceEngine(ABC):
    """语音识别引擎基类"""

    def __init__(self, config):
        self.config = config
        self.model = None
        self.align_model = None
        self.device = "cpu"
        self.align_metadata = None
        self.diarize_model = None
        self.initialized = False
        self.hf_token = None
        self.project_root = Path(__file__).parent.parent.parent

    @abstractmethod
    def initialize(self) -> bool:
        """初始化引擎"""
        pass

    @abstractmethod
    def recognize_file(
            self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """识别音频文件"""
        pass


    def _detect_device(self):
        """检测并设置最佳设备"""
        try:
            import torch

            if torch.cuda.is_available():
                self.device = "cuda"
                self.compute_type = "float16"
            else:
                self.device = "cpu"
                self.compute_type = "int8"

        except ImportError:
            self.device = "cpu"
            self.compute_type = "int8"

    def _get_huggingface_token(self) -> Optional[str]:
        """从配置文件获取 Hugging Face Token"""
        try:
            # 首先尝试从环境变量获取
            env_token = os.getenv("HUGGINGFACE_TOKEN")
            if env_token:
                return env_token

            # 然后从配置文件获取
            config_path = self.project_root / "config" / "settings.json"

            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    system = config.get("system", {})
                    token = system.get("huggingface", {}).get("token")
                    if token:
                        return token

            return None

        except Exception as e:
            return None

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "engine": self.__class__.__name__,
            "initialized": self.initialized,
            "config": vars(self.config) if self.config else {},
        }

    def align_timestamps(self, detected_language: str, whisperx: Any, result: Dict[str, Any], audio: Any):
        align_model, align_metadata = self._load_align_model(detected_language)
        if align_model and align_metadata:
            try:
                result = whisperx.align(
                    result["segments"],
                    align_model,
                    align_metadata,
                    audio,
                    self.device,
                    return_char_alignments=False,
                )
            except Exception as e:
                return result
        else:
            return result

    def _load_align_model(self, language: str) -> tuple:
        """
        加载对齐模型（用于词级时间戳）
        优先使用 ModelScope wav2vec2 -> 回退 WhisperX 官方模型 -> 放弃词级对齐
        Returns:
            (model, metadata) 元组，如果失败返回 (None, None)
        """

        if self.align_model is not None:
            return (self.align_model, self.align_metadata)

        import whisperx
        try:
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")
            model, metadata = whisperx.load_align_model(
                language_code=language,
                device=self.device,
                model_name=self.project_root / "data" / "models" / "zh-align"
            )

            self.align_model = model
            self.align_metadata = metadata
            return (model, metadata)

        except Exception as e:
            return (None, None)

    def _load_diarization_model(self) -> bool:
        """加载说话人分离模型"""
        try:
            if self.diarize_model is not None:
                return True

            if not self.hf_token:
                return False

            import whisperx
            from whisperx.diarize import DiarizationPipeline  # 新增导入

            # 使用WhisperX的DiarizationPipeline
            self.diarize_model = DiarizationPipeline(
                model_name="pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token,
                device=self.device
            )

            return True

        except Exception as e:
            return False

    def speak_digitization(self, whisperx: Any, result: Dict[str, Any], audio_path: str):
        speakers_info = {}
        if self._load_diarization_model():
            try:
                # 执行说话人分离
                diarize_segments = self.diarize_model(audio_path)
                # 将说话人信息与转录结果关联
                result = whisperx.assign_word_speakers(diarize_segments, result)
                # 统计说话人信息
                for segment in result.get("segments", []):
                    speaker = segment.get("speaker")
                    if speaker:
                        if speaker not in speakers_info:
                            speakers_info[speaker] = {
                                "id": speaker,
                                "name": speaker,
                                "segments_count": 0,
                                "total_duration": 0.0,
                                "words": [],
                            }

                        speakers_info[speaker]["segments_count"] += 1
                        duration = segment.get("end", 0) - segment.get(
                            "start", 0
                        )
                        speakers_info[speaker]["total_duration"] += duration
                        speakers_info[speaker]["words"].append(
                            segment.get("text", "")
                        )

            except Exception as e:
                pass

        return speakers_info

    def format_result(self, result: Dict[str, Any], audio_path: str) -> Dict[str, Any]:
        """
        所有引擎统一调用此方法来统一格式输出
        :param result:
        :param audio_path:
        :return:
        """
        pass

    def cleanup(self):
        """清理资源"""
        self.model = None
        self.initialized = False
