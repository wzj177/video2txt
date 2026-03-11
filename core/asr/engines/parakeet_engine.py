#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parakeet / NeMo 语音识别引擎

封装 NVIDIA NeMo ASR 模型 (Parakeet TDT / CTC) 并输出统一格式。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class ParakeetEngine(BaseVoiceEngine):
    """NVIDIA NeMo Parakeet 引擎"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config or {})
        self.model_name: str = self.config.get("model_name", "parakeet-tdt-0.6b-v2")
        self.selected_model: str = self.config.get("selected_model", "tdt-0.6b-v2")
        self.device_preference: str = self.config.get("device", "auto")
        self.batch_size: int = int(self.config.get("batch_size", 2))
        self.segment_duration: float = float(self.config.get("segment_duration", 18.0))
        self.words_per_segment: int = int(self.config.get("words_per_segment", 32))
        self.diarization_config: Dict[str, Any] = self.config.get("diarization", {})
        self.model = None
        self._nemo_model_cls = None
        self._nemo_module = None

    def initialize(self) -> bool:
        """加载 NeMo 模型"""
        try:
            self._lazy_import_nemo()

            if self.device_preference == "auto":
                self._detect_device()
            else:
                self.device = self.device_preference

            model_cls = self._select_model_class()
            if not model_cls:
                logger.error("未找到可用的 NeMo 模型类型")
                return False

            logger.info("加载 Parakeet 模型: %s (device=%s)", self.model_name, self.device)
            self.model = model_cls.from_pretrained(model_name=self.model_name, map_location=self.device)
            self.model.eval()
            self.initialized = True
            return True
        except ImportError:
            logger.error("未安装 nemo_toolkit，请运行 pip install nemo_toolkit[nlp]==1.23.0")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Parakeet 模型加载失败: {exc}")
            return False

    def _lazy_import_nemo(self):
        if self._nemo_model_cls:
            return

        from nemo.collections.asr.models import EncDecRNNTBPEModel, EncDecCTCModel  # type: ignore

        self._rnnt_cls = EncDecRNNTBPEModel
        self._ctc_cls = EncDecCTCModel

    def _select_model_class(self):
        name = self.model_name.lower()
        if "ctc" in name:
            return getattr(self, "_ctc_cls", None)
        return getattr(self, "_rnnt_cls", None)

    def recognize_file(
        self,
        audio_path: str,
        language: str = "auto",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        if not self.initialized and not self.initialize():
            return None

        try:
            start_time = time.time()
            transcribe_kwargs: Dict[str, Any] = {
                "paths2audio_files": [audio_path],
                "batch_size": self.batch_size,
                "num_workers": 0,
                "return_hypotheses": True,
            }
            transcripts, hypotheses = self.model.transcribe(**transcribe_kwargs)

            text = transcripts[0] if isinstance(transcripts, list) else transcripts
            all_hypotheses = hypotheses[0] if isinstance(hypotheses, list) else hypotheses
            best_hypothesis = all_hypotheses[0] if isinstance(all_hypotheses, list) and all_hypotheses else all_hypotheses

            word_timestamps = getattr(best_hypothesis, "word_timestamps", None) or []
            segments = self._build_segments_from_words(word_timestamps, text)

            diarization_enabled = kwargs.get("enable_diarization", True) and self.diarization_config.get("enabled", True)
            speakers = {}
            if diarization_enabled:
                segments, speakers = self._apply_diarization_if_available(segments, audio_path)

            normalized = {
                "text": text,
                "language": language,
                "segments": segments,
                "speakers": speakers,
                "model": self.model_name,
                "device": self.device,
                "processing_time": time.time() - start_time,
                "audio_length": segments[-1]["end"] if segments else 0.0,
            }
            return self.format_result(normalized, audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Parakeet 识别失败: {exc}")
            return None

    def _build_segments_from_words(
        self, word_timestamps: List[Dict[str, Any]], fallback_text: str
    ) -> List[Dict[str, Any]]:
        if not word_timestamps:
            fallback_text = fallback_text.strip()
            return [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 0.0,
                    "duration": 0.0,
                    "text": fallback_text,
                    "speaker": "Speaker_1",
                    "words": [],
                }
            ]

        segments: List[Dict[str, Any]] = []
        buffer: Dict[str, Any] = {"start": None, "end": None, "words": []}

        for index, word in enumerate(word_timestamps):
            start = float(word.get("start_time") or word.get("start") or 0.0)
            end = float(word.get("end_time") or word.get("end") or start)
            token = str(word.get("word") or word.get("text") or "").strip()

            if buffer["start"] is None:
                buffer["start"] = start
            buffer["end"] = end
            buffer["words"].append({"start": start, "end": end, "word": token})

            duration = (buffer["end"] or 0) - (buffer["start"] or 0)
            if (
                len(buffer["words"]) >= self.words_per_segment
                or duration >= self.segment_duration
                or index == len(word_timestamps) - 1
            ):
                segments.append(self._finalize_segment(buffer))
                buffer = {"start": None, "end": None, "words": []}

        return segments

    def _finalize_segment(self, buffer: Dict[str, Any]) -> Dict[str, Any]:
        words = buffer.get("words", [])
        text = " ".join(w.get("word", "") for w in words).strip()
        start = float(buffer.get("start") or (words[0].get("start") if words else 0.0))
        end = float(buffer.get("end") or (words[-1].get("end") if words else start))
        return {
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(max(end - start, 0.0), 2),
            "text": text,
            "speaker": "Speaker_1",
            "words": words,
            "confidence": 0.9,
        }

    def _apply_diarization_if_available(
        self, segments: List[Dict[str, Any]], audio_path: str
    ) -> (List[Dict[str, Any]], Dict[str, Any]):
        try:
            import whisperx  # type: ignore
        except Exception:  # noqa: BLE001
            logger.warning("未安装 whisperx，跳过 Parakeet 说话人分离")
            return segments, {}

        if not self._load_diarization_model():
            return segments, {}

        try:
            diarization = self.diarize_model(audio_path)
            enriched = whisperx.assign_word_speakers(diarization, {"segments": segments})
            diarized_segments = enriched.get("segments", segments)
            speakers = self._summarize_speakers(diarized_segments)
            return diarized_segments, speakers
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Parakeet 说话人分离失败: {exc}")
            return segments, {}

    @staticmethod
    def _summarize_speakers(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for segment in segments:
            speaker = segment.get("speaker") or "Speaker_1"
            info = summary.setdefault(
                speaker,
                {"id": speaker, "name": speaker, "segments_count": 0, "total_duration": 0.0},
            )
            info["segments_count"] += 1
            info["total_duration"] += max(segment.get("end", 0) - segment.get("start", 0), 0.0)
        return summary
