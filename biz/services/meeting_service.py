#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议处理服务 - 针对离线/上传音频的处理流程，仅保留转录与说话人分离
"""

import json
import logging
from pathlib import Path
import subprocess
import tempfile
import wave
import shutil
import warnings
import io
from contextlib import redirect_stderr
from typing import Any, Dict, List, Optional

import asyncio

from core.asr import initialize_voice_recognition
from core.asr.voice_recognition_core import get_voice_core

from .task_service import task_service

logger = logging.getLogger(__name__)


class MeetingService:
    """会议处理服务（上传音频版）"""

    diarization_model_path = (
        Path(__file__).parent.parent.parent
        / "models"
        / "speaker-diarization-community-1"
    )

    async def process_uploaded_audio(self, task_id: str, audio_file_path: str) -> bool:
        """
        处理上传的会议录音，仅输出转录文本与说话人日志

        Args:
            task_id: 会议任务ID
            audio_file_path: 已保存的会议录音文件
        """

        try:
            # 获取任务信息
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            if task.get("status") in ["stopped", "cancelled"]:
                logger.info("任务已被停止，跳过处理: %s", task_id)
                return False

            config = task.get("config") or {}
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except Exception:
                    logger.error(f"任务 {task_id} 配置解析失败")
                    config = {}

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "processing",
                    "progress": 10,
                    "current_step": "开始处理上传的音频文件...",
                },
            )

            # 初始化语音识别引擎
            engine = config.get("engine", "sensevoice")
            if engine == "qwen3_asr":
                model_name = config.get("model_name")
                base_http_api_url = config.get("base_http_api_url")
                logger.info(
                    "会议任务使用 Qwen3-ASR: model_name=%s base_http_api_url=%s",
                    model_name or "(default)",
                    base_http_api_url or "(default)",
                )
                overrides = {}
                if model_name:
                    overrides["model_name"] = model_name
                if base_http_api_url:
                    overrides["base_http_api_url"] = base_http_api_url
                if overrides:
                    voice_core = get_voice_core()
                    voice_core.set_engine_override("qwen3_asr", overrides, reset=True)
            initialize_voice_recognition(engine)
            voice_core = get_voice_core()

            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "processing",
                    "progress": 30,
                    "current_step": "正在执行转录与说话人分离...",
                },
            )

            # 执行语音识别
            result = voice_core.recognize_file(
                audio_file_path,
                language=config.get("language", "auto"),
                enable_diarization=config.get("enable_speaker_diarization", True),
            )

            transcript_text = self._extract_transcript_text(result)
            if not result or not transcript_text:
                error_message = "音频文件中未检测到有效的语音内容"
                if isinstance(result, dict) and result.get("error"):
                    error_message = str(result.get("error"))
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": "error",
                        "progress": 100,
                        "current_step": "未识别到有效音频内容",
                        "error": error_message,
                    },
                )
                return False

            # 若用户在处理中主动停止，避免覆盖状态
            latest_task = await task_service.get_task_by_id("meeting", task_id)
            if latest_task and latest_task.get("status") in ["stopped", "cancelled"]:
                logger.info("任务已停止，跳过结果写入: %s", task_id)
                return False

            if result is not None and transcript_text and not result.get("text"):
                result["text"] = transcript_text
            segments = result.get("segments", []) or []
            speakers_info = result.get("speakers", {}) or {}

            if engine == "qwen3_asr":
                speakers_info = {}
                for segment in segments:
                    if isinstance(segment, dict):
                        segment["speaker"] = ""

            total_words = len(transcript_text.split())
            total_duration = result.get("audio_length", 0)
            speaker_count = len(speakers_info)

            speaker_log = (
                self._build_speaker_log_from_segments(segments) if speakers_info else []
            )

            final_results: Dict[str, Any] = {
                "transcript": transcript_text,
                "segments": segments,
                "speakers": speakers_info,
                "speaker_log": speaker_log,
                "audio_file": audio_file_path,
            }

            config["audio_file_path"] = audio_file_path

            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "processing",
                    "progress": 70,
                    "current_step": "正在整理输出结果...",
                },
            )

            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "finished",
                    "progress": 100,
                    "current_step": "处理完成",
                    "results": final_results,
                    "transcript": transcript_text,
                    "transcripts": segments,
                    "total_words": total_words,
                    "speaker_count": speaker_count,
                    "total_duration": total_duration,
                    "engine": engine,
                    "config": config,
                },
            )

            logger.info(f"音频文件处理完成: {task_id}")
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(f"处理上传音频文件失败: {exc}")
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "error",
                    "progress": 100,
                    "current_step": "处理失败",
                    "error": str(exc),
                },
            )
            return False

    async def generate_speaker_log(self, task_id: str) -> bool:
        """基于 pyannote 模型生成说话人日志并合并结果"""
        try:
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                logger.error("任务不存在: %s", task_id)
                return False

            status = task.get("status")
            if status in ["recording", "paused", "monitoring", "starting_audio"]:
                logger.warning("会议仍在进行中，无法生成说话人日志: %s", task_id)
                return False

            config = self._parse_json(task.get("config")) or {}
            results = self._parse_json(task.get("results")) or {}
            base_status = status or "pending"
            base_progress = task.get("progress", 100)
            base_step = task.get("current_step")
            audio_path = config.get("audio_file_path") or results.get("audio_file")
            if not audio_path or not Path(audio_path).exists():
                logger.error("音频文件不存在，无法生成说话人日志: %s", audio_path)
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": base_status,
                        "progress": base_progress,
                        "current_step": base_step,
                        "results": {
                            **results,
                            "diarization_status": "failed",
                            "diarization_error": "找不到音频文件",
                        },
                    },
                )
                return False

            results["diarization_status"] = "processing"
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": base_status,
                    "progress": base_progress,
                    "current_step": base_step,
                    "results": results,
                },
            )

            diarization_segments = await asyncio.to_thread(
                self._run_diarization, str(audio_path)
            )
            if not diarization_segments:
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": base_status,
                        "progress": base_progress,
                        "current_step": base_step,
                        "results": {
                            **results,
                            "diarization_status": "failed",
                            "diarization_error": "未识别到说话人段落",
                        },
                    },
                )
                return False

            segments = results.get("segments") or []
            if segments:
                segments = self._assign_speakers_to_segments(
                    segments, diarization_segments
                )
            else:
                segments = [
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "duration": round(seg["end"] - seg["start"], 2),
                        "speaker": seg["speaker"],
                        "text": "",
                    }
                    for seg in diarization_segments
                ]

            speaker_log = self._build_speaker_log_from_segments(segments)
            speakers_info = self._summarize_speakers(segments)

            results["segments"] = segments
            results["speaker_log"] = speaker_log
            results["speakers"] = speakers_info
            results["diarization_model"] = str(self.diarization_model_path)
            results["diarization_status"] = "ready"

            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": base_status,
                    "progress": base_progress,
                    "current_step": base_step,
                    "results": results,
                    "speaker_count": len(speakers_info),
                },
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error("生成说话人日志失败: %s", exc)
            try:
                task = await task_service.get_task_by_id("meeting", task_id)
                if task:
                    status = task.get("status") or "pending"
                    results = self._parse_json(task.get("results")) or {}
                    await task_service.update_task(
                        "meeting",
                        task_id,
                        {
                            "status": status,
                            "progress": task.get("progress", 100),
                            "current_step": task.get("current_step"),
                            "results": {
                                **results,
                                "diarization_status": "failed",
                                "diarization_error": str(exc),
                            },
                        },
                    )
            except Exception:
                pass
            return False

    def _build_speaker_log_from_segments(
        self, segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """基于识别分段构建说话人日志"""
        speaker_log: List[Dict[str, Any]] = []

        for segment in segments:
            start = segment.get("start", 0) or 0
            end = segment.get("end", start) or start
            duration = max(end - start, 0)
            speaker_log.append(
                {
                    "speaker": segment.get("speaker", "Speaker"),
                    "start": start,
                    "end": end,
                    "duration": round(duration, 2),
                    "text": (segment.get("text") or "").strip(),
                    "time_label": self._format_timestamp(start),
                }
            )

        return speaker_log

    def _parse_json(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    def _run_diarization(self, audio_path: str) -> List[Dict[str, Any]]:
        if not self.diarization_model_path.exists():
            raise FileNotFoundError(
                f"未找到说话人模型: {self.diarization_model_path}"
            )
        warnings.filterwarnings(
            "ignore",
            message=r"torchcodec is not installed correctly.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r"torchaudio\._backend\.list_audio_backends has been deprecated.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r"std\(\): degrees of freedom is <= 0.*",
            category=UserWarning,
        )
        try:
            import importlib.metadata
            import torch
            from packaging.version import Version
            with io.StringIO() as stderr_buf, redirect_stderr(stderr_buf):
                from pyannote.audio import Pipeline
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"未安装 pyannote.audio 依赖: {exc}") from exc

        model_source = str(self.diarization_model_path)
        temp_configs: List[Path] = []
        config_path = self.diarization_model_path / "config.yaml"
        if config_path.exists():
            try:
                import yaml

                with open(config_path, "r", encoding="utf-8") as handle:
                    config_data = yaml.safe_load(handle) or {}
                required_version = (
                    config_data.get("dependencies", {}) or {}
                ).get("pyannote.audio")
                if required_version:
                    installed_version = importlib.metadata.version("pyannote.audio")
                    if Version(installed_version) < Version(str(required_version)):
                        raise RuntimeError(
                            "说话人模型需要 pyannote.audio>=%s，当前版本为 %s，请升级依赖。"
                            % (required_version, installed_version)
                        )
            except RuntimeError:
                raise
            except Exception:
                pass
        if config_path.exists():
            prepared = self._prepare_diarization_config(config_path)
            if prepared:
                model_source = str(prepared)
                temp_configs.append(prepared)

        try:
            with io.StringIO() as stderr_buf, redirect_stderr(stderr_buf):
                pipeline = Pipeline.from_pretrained(model_source)
        except TypeError as exc:
            if "plda" in str(exc).lower() and config_path.exists():
                logger.warning("检测到旧版 pyannote.audio，移除 plda 参数后重试")
                prepared = self._prepare_diarization_config(
                    config_path, remove_plda=True
                )
                if prepared:
                    model_source = str(prepared)
                    temp_configs.append(prepared)
                pipeline = Pipeline.from_pretrained(model_source)
            else:
                raise
        finally:
            for tmp_path in temp_configs:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)
        audio_input = self._prepare_diarization_audio(audio_path)
        with io.StringIO() as stderr_buf, redirect_stderr(stderr_buf):
            diarization = pipeline(audio_input)

        segments: List[Dict[str, Any]] = []
        diarization_tracks = None
        if hasattr(diarization, "speaker_diarization"):
            diarization_tracks = diarization.speaker_diarization
        elif hasattr(diarization, "itertracks"):
            diarization_tracks = diarization

        if diarization_tracks is not None:
            for turn, _, speaker in diarization_tracks.itertracks(yield_label=True):
                segments.append(
                    {
                        "start": round(turn.start, 2),
                        "end": round(turn.end, 2),
                        "speaker": str(speaker),
                    }
                )
        elif hasattr(diarization, "serialize"):
            serialized = diarization.serialize()
            for item in serialized.get("diarization", []):
                segments.append(
                    {
                        "start": round(float(item["start"]), 2),
                        "end": round(float(item["end"]), 2),
                        "speaker": str(item["speaker"]),
                    }
                )
        return segments

    def _prepare_diarization_config(
        self, config_path: Path, remove_plda: bool = False
    ) -> Optional[Path]:
        try:
            import tempfile
            import yaml

            with open(config_path, "r", encoding="utf-8") as handle:
                config_data = yaml.safe_load(handle) or {}

            config_data = self._replace_model_vars(config_data, self.diarization_model_path)

            if remove_plda:
                pipeline_cfg = config_data.get("pipeline", {})
                params = pipeline_cfg.get("params", {}) or {}
                params.pop("plda", None)
                pipeline_cfg["params"] = params
                config_data["pipeline"] = pipeline_cfg

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as tmp_file:
                yaml.safe_dump(config_data, tmp_file, allow_unicode=False)
                return Path(tmp_file.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("准备说话人模型配置失败: %s", exc)
            return None

    def _replace_model_vars(self, payload: Any, model_root: Path) -> Any:
        if isinstance(payload, str):
            if payload.startswith("$model/"):
                resolved = model_root / payload.replace("$model/", "")
                if resolved.is_dir():
                    plda_file = resolved / "plda.npz"
                    xvec_file = resolved / "xvec_transform.npz"
                    if plda_file.exists() and xvec_file.exists():
                        return str(resolved)
                    bin_file = resolved / "pytorch_model.bin"
                    if bin_file.exists():
                        return str(bin_file)
                return str(resolved)
            return payload
        if isinstance(payload, list):
            return [self._replace_model_vars(item, model_root) for item in payload]
        if isinstance(payload, dict):
            return {
                key: self._replace_model_vars(value, model_root)
                for key, value in payload.items()
            }
        return payload

    def _prepare_diarization_audio(self, audio_path: str) -> Dict[str, Any]:
        """Load audio as waveform dict to avoid torchcodec dependency."""
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        wav_path: Optional[Path] = None
        if path.suffix.lower() != ".wav":
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("未找到 ffmpeg，无法转换音频用于说话人日志")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                wav_path = Path(tmp_file.name)
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(wav_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                if wav_path.exists():
                    wav_path.unlink(missing_ok=True)
                raise RuntimeError(f"ffmpeg 转码失败: {result.stderr.strip()}")
            path = wav_path

        try:
            import numpy as np
            import torch

            with wave.open(str(path), "rb") as handle:
                channels = handle.getnchannels()
                sample_rate = handle.getframerate()
                sampwidth = handle.getsampwidth()
                if sampwidth != 2:
                    raise RuntimeError(f"不支持的采样位宽: {sampwidth * 8}bit")
                frames = handle.readframes(handle.getnframes())
            data = np.frombuffer(frames, dtype="<i2")
            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)
            waveform = torch.from_numpy(data.astype("float32") / 32768.0).unsqueeze(0)
            return {"waveform": waveform, "sample_rate": sample_rate}
        finally:
            if wav_path and wav_path.exists():
                wav_path.unlink(missing_ok=True)

    def _assign_speakers_to_segments(
        self,
        segments: List[Dict[str, Any]],
        diarization_segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not diarization_segments:
            return segments

        for segment in segments:
            start = float(segment.get("start", 0))
            end = float(segment.get("end", start))
            if end < start:
                end = start
            best_speaker = ""
            best_overlap = 0.0
            for diar in diarization_segments:
                d_start = diar["start"]
                d_end = diar["end"]
                overlap = max(0.0, min(end, d_end) - max(start, d_start))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = diar["speaker"]
            if not best_speaker:
                mid = (start + end) / 2.0
                nearest = min(
                    diarization_segments,
                    key=lambda d: abs(((d["start"] + d["end"]) / 2.0) - mid),
                )
                best_speaker = nearest["speaker"]
            segment["speaker"] = best_speaker
        return segments

    def _summarize_speakers(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        speakers: Dict[str, Dict[str, Any]] = {}
        for seg in segments:
            speaker = seg.get("speaker")
            if not speaker:
                continue
            speakers.setdefault(
                speaker,
                {
                    "id": speaker,
                    "name": speaker,
                    "segments_count": 0,
                    "total_duration": 0.0,
                    "words": [],
                },
            )
            speakers[speaker]["segments_count"] += 1
            speakers[speaker]["total_duration"] += (
                seg.get("end", 0) - seg.get("start", 0)
            )
            if seg.get("text"):
                speakers[speaker]["words"].append(seg["text"])
        return speakers

    def _extract_transcript_text(self, result: Dict[str, Any] | None) -> str:
        if not result:
            return ""
        text = (
            result.get("text")
            or result.get("transcript")
            or result.get("result")
            or ""
        )
        if not text:
            segments = result.get("segments") or []
            if isinstance(segments, list):
                text = " ".join(
                    seg.get("text", "").strip()
                    for seg in segments
                    if isinstance(seg, dict) and seg.get("text")
                )
        return text.strip()

    def _format_timestamp(self, seconds_value: float) -> str:
        """格式化时间戳为 mm:ss"""
        total_seconds = int(max(seconds_value or 0, 0))
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"


meeting_service = MeetingService()
