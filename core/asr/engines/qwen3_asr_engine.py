#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen3 ASR engine using the embedded Python toolkit."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import base64
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, quote
from uuid import uuid4
from typing import Any, Dict, List, Optional

import numpy as np
import requests

try:  # dashscope is optional at import time
    import dashscope  # type: ignore
except Exception:  # pragma: no cover
    dashscope = None

try:  # realtime SDK (optional)
    from dashscope.audio.qwen_omni import (  # type: ignore
        OmniRealtimeConversation,
        OmniRealtimeCallback,
        MultiModality,
    )
    from dashscope.audio.qwen_omni.omni_realtime import (  # type: ignore
        TranscriptionParams,
    )
except Exception:  # pragma: no cover
    OmniRealtimeConversation = None
    OmniRealtimeCallback = None
    MultiModality = None
    TranscriptionParams = None
try:  # file transcription SDK (optional)
    from dashscope.audio.qwen_asr import QwenTranscription  # type: ignore
except Exception:  # pragma: no cover
    QwenTranscription = None
try:  # oss2 for filetrans uploads (optional)
    import oss2  # type: ignore
except Exception:  # pragma: no cover
    oss2 = None
try:  # silero VAD may be optional
    from silero_vad import load_silero_vad  # type: ignore
except Exception:  # pragma: no cover
    load_silero_vad = None

from ...vendors.qwen3_asr_toolkit import (
    QwenASR,
    WAV_SAMPLE_RATE,
    load_audio,
    process_vad,
    save_audio_file,
)
from ..base_asr import BaseVoiceEngine

logger = logging.getLogger(__name__)


class Qwen3ASREngine(BaseVoiceEngine):
    """Invoke DashScope's Qwen3 ASR through the embedded Python toolkit."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config or {})
        self.enabled: bool = bool(self.config.get("enabled", False))
        self.model_name: str = self.config.get("model_name", "qwen3-asr-flash")
        self.num_threads: int = max(1, int(self.config.get("num_threads", 4)))
        self.vad_segment_threshold: int = int(self.config.get("vad_segment_threshold", 120))
        self.max_segment_duration: int = int(self.config.get("max_segment_duration", 180))
        self.min_duration_for_vad: int = int(self.config.get("min_duration_for_vad", 180))
        self.tmp_dir: Path = Path(self.config.get("tmp_dir", "./data/qwen3/cache")).expanduser()
        self.silence_logs: bool = bool(self.config.get("silence", True))
        self.dashscope_key: str = self.config.get("dashscope_api_key", "")
        self.base_http_api_url: str = self.config.get("base_http_api_url", "")
        self.oss_access_key_id: str = self.config.get("oss_access_key_id", "")
        self.oss_access_key_secret: str = self.config.get("oss_access_key_secret", "")
        self.oss_endpoint: str = self.config.get("oss_endpoint", "")
        self.oss_bucket: str = self.config.get("oss_bucket", "")
        self.oss_prefix: str = self.config.get("oss_prefix", "qwen3/asr")
        self.oss_public_base_url: str = self.config.get("oss_public_base_url", "")
        self.filetrans_use_http: bool = bool(self.config.get("filetrans_use_http", True))
        self.filetrans_poll_interval: int = int(
            self.config.get("filetrans_poll_interval", 5)
        )
        self.filetrans_poll_timeout: int = int(
            self.config.get("filetrans_poll_timeout", 3600)
        )
        self.realtime_url: str = self.config.get(
            "realtime_url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )
        self.realtime_chunk_ms: int = int(self.config.get("realtime_chunk_ms", 200))
        self.realtime_send_delay: float = float(
            self.config.get("realtime_send_delay", 0.1)
        )
        self.realtime_sample_rate: int = int(
            self.config.get("realtime_sample_rate", WAV_SAMPLE_RATE)
        )
        self.realtime_format: str = str(self.config.get("realtime_format", "pcm"))
        self.realtime_finish_timeout: int = int(
            self.config.get("realtime_finish_timeout", 10)
        )
        self.client: Optional[QwenASR] = None
        self._vad_model = None

    def initialize(self) -> bool:
        if not self.enabled:
            logger.info("Qwen3-ASR 未启用，跳过初始化")
            return False

        if dashscope is None:
            logger.error("未安装 dashscope，请运行 pip install dashscope")
            return False

        api_key = self._resolve_api_key()
        if not api_key:
            logger.error("缺少 DashScope API Key，无法初始化 Qwen3-ASR")
            return False
        dashscope.api_key = api_key  # type: ignore[attr-defined]
        if self.base_http_api_url:
            dashscope.base_http_api_url = self.base_http_api_url  # type: ignore[attr-defined]

        try:
            self.client = QwenASR(model=self.model_name)
        except ImportError as exc:
            logger.error("初始化 QwenASR 失败: %s", exc)
            return False

        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.initialized = True
        logger.info("Qwen3-ASR 引擎初始化完成，model=%s", self.model_name)
        return True

    def recognize_file(
        self,
        audio_path: str,
        language: str = "auto",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        if not self.initialized and not self.initialize():
            return None
        if "realtime" in self.model_name:
            return self._recognize_realtime(audio_path, language)
        if "filetrans" in self.model_name:
            return self._recognize_filetrans(audio_path, language)
        assert self.client is not None

        try:
            wav = load_audio(audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("加载音频失败: %s", exc)
            return None

        if wav is None or len(wav) == 0:
            logger.error("音频数据为空，无法识别")
            return None

        if float(np.max(np.abs(wav))) < 1e-4:
            logger.error("音频为静音或能量过低，无法识别")
            return None

        start_time = time.time()
        segments = self._prepare_segments(wav)
        temp_root = Path(tempfile.mkdtemp(prefix="qwen3-asr-", dir=str(self.tmp_dir)))
        try:
            segment_files = self._persist_segments(segments, temp_root)
            trans_results = self._transcribe_segments(segment_files)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        if not trans_results:
            logger.error("Qwen3-ASR 未返回任何结果")
            return None

        normalized_segments = self._build_segments(trans_results)
        text = " ".join(seg.get("text", "") for seg in normalized_segments).strip()
        language = self._majority_language(trans_results) or language
        speakers = self._summarize_speakers(normalized_segments)
        result = {
            "text": text,
            "language": language,
            "segments": normalized_segments,
            "speakers": speakers,
            "model": self.model_name,
            "device": "cloud",
            "processing_time": time.time() - start_time,
            "audio_length": normalized_segments[-1]["end"] if normalized_segments else 0.0,
        }
        return self.format_result(result, audio_path)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _resolve_api_key(self) -> str:
        if self.dashscope_key:
            return self.dashscope_key
        return os.getenv("DASHSCOPE_API_KEY", "")

    def _prepare_segments(self, wav: np.ndarray):
        duration_seconds = len(wav) / WAV_SAMPLE_RATE
        if duration_seconds < self.min_duration_for_vad:
            return [(0, len(wav), wav)]

        vad_model = self._load_vad_model()
        if vad_model is None:
            logger.warning("未能加载 Silero VAD，改为固定分段")
            segments = process_vad(
                wav,
                None,
                segment_threshold_s=self.max_segment_duration,
                max_segment_threshold_s=self.max_segment_duration,
            )
        else:
            segments = process_vad(
                wav,
                vad_model,
                segment_threshold_s=self.vad_segment_threshold,
                max_segment_threshold_s=self.max_segment_duration,
            )

        filtered = [
            (start, end, data)
            for start, end, data in segments
            if data is not None and len(data) > 0 and end > start
        ]
        if not filtered and len(wav) > 0:
            logger.warning("VAD 分段后无有效片段，回退为整段音频")
            return [(0, len(wav), wav)]
        return filtered

    def _load_vad_model(self):
        if self._vad_model is not None or load_silero_vad is None:
            return self._vad_model
        try:
            self._vad_model = load_silero_vad(onnx=True)
            logger.info("Silero VAD 模型加载完成")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Silero VAD 加载失败: %s", exc)
            self._vad_model = None
        return self._vad_model

    def _persist_segments(self, segments, temp_root: Path):
        persisted = []
        for idx, (start, end, data) in enumerate(segments):
            if data is None or len(data) == 0 or end <= start:
                logger.warning("跳过空音频分片: index=%s start=%s end=%s", idx, start, end)
                continue
            if len(data) < int(WAV_SAMPLE_RATE * 0.2):
                logger.warning(
                    "跳过过短音频分片: index=%s samples=%s start=%s end=%s",
                    idx,
                    len(data),
                    start,
                    end,
                )
                continue
            if float(np.max(np.abs(data))) < 1e-4:
                logger.warning(
                    "跳过低能量音频分片: index=%s start=%s end=%s", idx, start, end
                )
                continue
            path = temp_root / f"segment_{idx:04d}.wav"
            save_audio_file(data, str(path))
            persisted.append(
                {
                    "index": idx,
                    "start_sample": start,
                    "end_sample": end,
                    "path": path,
                }
            )
        return persisted

    def _transcribe_segments(self, segment_files):
        if not segment_files:
            return []

        def _worker(seg):
            assert self.client is not None
            language, text = self.client.asr(str(seg["path"]))
            return {
                "index": seg["index"],
                "language": language,
                "text": text.strip(),
                "start_sample": seg["start_sample"],
                "end_sample": seg["end_sample"],
            }

        results: List[Dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            future_map = {executor.submit(_worker, seg): seg for seg in segment_files}
            for future in concurrent.futures.as_completed(future_map):
                seg = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.error("Qwen3-ASR 处理分片 %s 失败: %s", seg["path"], exc)
                    raise
        results.sort(key=lambda item: item["index"])
        return results

    def _recognize_realtime(
        self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        if OmniRealtimeConversation is None or TranscriptionParams is None:
            logger.error("未安装 Qwen Omni Realtime SDK，无法使用实时模型")
            return None

        try:
            wav = load_audio(audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("加载音频失败: %s", exc)
            return None

        duration = len(wav) / WAV_SAMPLE_RATE if WAV_SAMPLE_RATE else 0.0
        pcm = np.clip(wav, -1.0, 1.0)
        pcm_i16 = (pcm * 32767).astype(np.int16)
        pcm_bytes = pcm_i16.tobytes()

        class _RealtimeCollector(OmniRealtimeCallback):  # type: ignore[misc]
            def __init__(self):
                self.final_texts: List[str] = []
                self.last_partial: str = ""

            def on_event(self, response):
                try:
                    event_type = response.get("type")
                    if event_type == "conversation.item.input_audio_transcription.completed":
                        text = response.get("transcript") or ""
                        if text:
                            self.final_texts.append(text)
                    elif event_type == "conversation.item.input_audio_transcription.text":
                        self.last_partial = response.get("stash") or ""
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Realtime callback error: %s", exc)

        callback = _RealtimeCollector()
        conversation = OmniRealtimeConversation(
            model=self.model_name, url=self.realtime_url, callback=callback
        )

        try:
            conversation.connect()
            params = TranscriptionParams(
                language=None if language == "auto" else language,
                sample_rate=self.realtime_sample_rate,
                input_audio_format=self.realtime_format,
            )
            conversation.update_session(
                output_modalities=[MultiModality.TEXT],
                enable_input_audio_transcription=True,
                transcription_params=params,
            )

            chunk_size = int(
                self.realtime_sample_rate * (self.realtime_chunk_ms / 1000.0) * 2
            )
            for offset in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[offset : offset + chunk_size]
                audio_b64 = base64.b64encode(chunk).decode("ascii")
                conversation.append_audio(audio_b64)
                if self.realtime_send_delay:
                    time.sleep(self.realtime_send_delay)

            conversation.end_session()
            timeout = time.time() + max(self.realtime_finish_timeout, 1)
            while time.time() < timeout:
                if callback.final_texts:
                    time.sleep(0.1)
                else:
                    time.sleep(0.1)
        finally:
            conversation.close()

        full_text = " ".join(callback.final_texts).strip()
        if not full_text:
            full_text = callback.last_partial.strip()

        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": round(duration, 2),
                "duration": round(duration, 2),
                "text": full_text,
                "speaker": "Speaker_1",
                "words": [],
            }
        ]
        result = {
            "text": full_text,
            "language": language if language != "auto" else "unknown",
            "segments": segments,
            "speakers": self._summarize_speakers(segments),
            "model": self.model_name,
            "device": "cloud",
            "processing_time": 0.0,
            "audio_length": duration,
        }
        return self.format_result(result, audio_path)

    def _recognize_filetrans(
        self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        api_key = self._resolve_api_key()
        if not api_key:
            logger.error("缺少 DashScope API Key，无法初始化 Qwen3-ASR filetrans")
            return None
        dashscope.api_key = api_key  # type: ignore[attr-defined]
        if self.base_http_api_url:
            dashscope.base_http_api_url = self.base_http_api_url  # type: ignore[attr-defined]

        file_url = audio_path
        is_local_path = not file_url.startswith(("http://", "https://"))
        if is_local_path:
            file_url = self._upload_to_oss(audio_path)
            if not file_url:
                error_message = "Qwen3-ASR filetrans 需要配置 OSS 并提供公网可访问的 URL"
                logger.error(error_message)
                return {
                    "text": "",
                    "error": error_message,
                    "segments": [],
                }

        request_language = None if language == "auto" else language

        try:
            result_dict = None
            output = {}
            if self.filetrans_use_http:
                result_dict = self._filetrans_async_http_request(
                    file_url, request_language
                )
            elif QwenTranscription is None:
                logger.error("未安装 DashScope QwenTranscription SDK，无法使用 filetrans 模型")
                return None
            else:
                task_response = QwenTranscription.async_call(
                    model=self.model_name,
                    file_url=file_url,
                    language=request_language,
                    enable_itn=False,
                    enable_words=True,
                )
                logger.info(
                    "Qwen3-ASR filetrans task_response: %s",
                    self._safe_dump(task_response),
                )

                task_id = None
                if hasattr(task_response, "output"):
                    task_id = getattr(task_response.output, "task_id", None)
                if not task_id:
                    task_id = self._extract_task_id(task_response)
                if not task_id:
                    logger.error("Qwen3-ASR filetrans 未返回 task_id")
                    return None

                query_response = QwenTranscription.fetch(task=task_id)
                logger.info(
                    "Qwen3-ASR filetrans query_response: %s",
                    self._safe_dump(query_response),
                )

                task_result = QwenTranscription.wait(task=task_id)
                logger.info(
                    "Qwen3-ASR filetrans task_result: %s",
                    self._safe_dump(task_result),
                )

                result_dict = self._response_to_dict(task_result)

            output = (result_dict or {}).get("output") or {}
            task_status = str(output.get("task_status") or "").upper()
            if task_status and task_status not in ("SUCCEEDED", "SUCCESS"):
                error_code = output.get("code") or result_dict.get("code") or ""
                error_message = output.get("message") or result_dict.get("message") or ""
                if is_local_path:
                    logger.error(
                        "Qwen3-ASR filetrans 失败: %s %s (file_url 需要 http/https 可访问)",
                        error_code,
                        error_message,
                    )
                else:
                    logger.error(
                        "Qwen3-ASR filetrans 失败: %s %s",
                        error_code,
                        error_message,
                    )
                return None
            transcription_url = None
            if isinstance(output.get("result"), dict):
                transcription_url = output.get("result", {}).get("transcription_url")
            if transcription_url:
                transcription_payload = self._fetch_transcription_result(
                    transcription_url
                )
                if transcription_payload:
                    if isinstance(transcription_payload, dict) and "output" in transcription_payload:
                        output = transcription_payload.get("output") or output
                    elif isinstance(transcription_payload, dict) and "result" in transcription_payload:
                        output = transcription_payload.get("result") or output
                    else:
                        output = transcription_payload

            segments, full_text, detected_language = self._parse_filetrans_output(output)

            if not segments:
                segments = [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 0.0,
                        "duration": 0.0,
                        "text": full_text,
                        "speaker": "Speaker_1",
                        "words": [],
                    }
                ]

            audio_length = segments[-1].get("end", 0.0) if segments else 0.0
            result = {
                "text": full_text,
                "language": detected_language or language,
                "segments": segments,
                "speakers": self._summarize_speakers(segments),
                "model": self.model_name,
                "device": "cloud",
                "processing_time": 0.0,
                "audio_length": audio_length,
            }
            return self.format_result(result, audio_path)

        except Exception as exc:  # noqa: BLE001
            logger.error("Qwen3-ASR filetrans 调用失败: %s", exc)
            return None

    def _response_to_dict(self, response: Any) -> Dict[str, Any]:
        if response is None:
            return {}
        if isinstance(response, dict):
            return response
        if hasattr(response, "to_dict"):
            try:
                return response.to_dict()  # type: ignore[no-any-return]
            except Exception:  # noqa: BLE001
                pass
        try:
            import json as _json

            return _json.loads(str(response))
        except Exception:  # noqa: BLE001
            return {"raw": str(response)}

    def _extract_task_id(self, response: Any) -> Optional[str]:
        data = self._response_to_dict(response)
        output = data.get("output") or {}
        for key in ("task_id", "taskId", "id"):
            if key in output:
                return output.get(key)
        return None

    def _filetrans_async_http_request(
        self, file_url: str, language: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        base_url = (self.base_http_api_url or "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
        if base_url.endswith("/compatible-mode/v1"):
            base_url = base_url[: -len("/compatible-mode/v1")]
        submit_url = f"{base_url}/services/audio/asr/transcription"

        headers = {
            "Authorization": f"Bearer {self._resolve_api_key()}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "input": {"file_url": file_url},
            "parameters": {
                "channel_id": [0],
                "enable_itn": False,
                "enable_words": True,
            },
        }
        if language:
            payload["parameters"]["language"] = language

        response = requests.post(submit_url, headers=headers, json=payload, timeout=30)
        try:
            response_data = response.json()
        except Exception:  # noqa: BLE001
            logger.error("Qwen3-ASR filetrans 提交失败: %s", response.text[:200])
            return None

        if response.status_code != 200:
            logger.error("Qwen3-ASR filetrans 提交失败: %s", response_data)
            return None

        logger.info("Qwen3-ASR filetrans task_response: %s", self._safe_dump(response_data))
        task_id = self._extract_task_id(response_data)
        if not task_id:
            logger.error("Qwen3-ASR filetrans 未返回 task_id")
            return None

        tasks_url = f"{base_url}/tasks/{task_id}"
        start_time = time.time()
        while True:
            poll_response = requests.get(tasks_url, headers=headers, timeout=30)
            try:
                poll_data = poll_response.json()
            except Exception:  # noqa: BLE001
                logger.error(
                    "Qwen3-ASR filetrans 查询失败: %s",
                    poll_response.text[:200],
                )
                return None

            logger.info("Qwen3-ASR filetrans task_result: %s", self._safe_dump(poll_data))
            output = poll_data.get("output") or {}
            status = str(output.get("task_status") or "").upper()
            if status in ("SUCCEEDED", "SUCCESS", "FAILED"):
                return poll_data

            if time.time() - start_time > self.filetrans_poll_timeout:
                logger.error("Qwen3-ASR filetrans 超时未完成")
                return None

            time.sleep(max(self.filetrans_poll_interval, 1))

    def _safe_dump(self, response: Any) -> str:
        data = self._response_to_dict(response)
        try:
            import json as _json

            return _json.dumps(data, ensure_ascii=False)[:2000]
        except Exception:  # noqa: BLE001
            return str(response)

    def _parse_filetrans_output(
        self, output: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], str, str]:
        segments: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []
        detected_language = ""

        candidates = output.get("results") or output.get("transcripts") or output.get("result") or []
        if isinstance(candidates, dict):
            candidates = [candidates]

        if not candidates and output.get("text"):
            full_text_parts.append(output.get("text", ""))

        for item in candidates:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or ""
            if text:
                full_text_parts.append(text)
            if not detected_language:
                detected_language = item.get("language") or ""

            sentence_list = (
                item.get("sentences")
                or item.get("segments")
                or item.get("sentences_with_timestamps")
                or []
            )
            if isinstance(sentence_list, dict):
                sentence_list = [sentence_list]

            for idx, sentence in enumerate(sentence_list):
                if not isinstance(sentence, dict):
                    continue
                seg_text = sentence.get("text") or sentence.get("sentence") or ""
                start = self._extract_time(sentence, ["begin_time", "start_time", "start", "start_ms"])
                end = self._extract_time(sentence, ["end_time", "end", "end_ms"])
                if end < start:
                    end = start
                segments.append(
                    {
                        "id": sentence.get("index", idx),
                        "start": start,
                        "end": end,
                        "duration": round(end - start, 2),
                        "text": seg_text,
                        "speaker": "Speaker_1",
                        "words": sentence.get("words", []) or [],
                    }
                )

        full_text = " ".join(part.strip() for part in full_text_parts if part.strip()).strip()
        if segments and not full_text:
            full_text = " ".join(seg["text"] for seg in segments).strip()

        return segments, full_text, detected_language

    def _fetch_transcription_result(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(
                    "Qwen3-ASR filetrans 下载转录结果失败: %s %s",
                    response.status_code,
                    response.text[:200],
                )
                return None
            return response.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("Qwen3-ASR filetrans 下载转录结果异常: %s", exc)
            return None

    def _upload_to_oss(self, audio_path: str) -> Optional[str]:
        if oss2 is None:
            logger.error("未安装 oss2，无法上传到 OSS，请先执行 pip install oss2")
            return None
        if not (
            self.oss_access_key_id
            and self.oss_access_key_secret
            and self.oss_endpoint
            and self.oss_bucket
        ):
            logger.error("缺少 OSS 配置，无法上传到 OSS")
            return None

        endpoint = self.oss_endpoint.strip()
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"

        try:
            auth = oss2.Auth(self.oss_access_key_id, self.oss_access_key_secret)
            bucket = oss2.Bucket(auth, endpoint, self.oss_bucket)
            object_key = self._build_oss_object_key(audio_path)
            oss2.resumable_upload(bucket, object_key, audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("OSS 上传失败: %s", exc)
            return None

        return self._build_oss_public_url(object_key, endpoint)

    def _build_oss_object_key(self, audio_path: str) -> str:
        prefix = (self.oss_prefix or "").strip().strip("/")
        suffix = Path(audio_path).suffix or ".wav"
        filename = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}{suffix}"
        if prefix:
            return f"{prefix}/{filename}"
        return filename

    def _build_oss_public_url(self, object_key: str, endpoint: str) -> str:
        base = (self.oss_public_base_url or "").strip().rstrip("/")
        if not base:
            parsed = urlparse(endpoint)
            host = parsed.netloc or parsed.path
            scheme = parsed.scheme or "https"
            if host.startswith(f"{self.oss_bucket}."):
                base_host = host
            else:
                base_host = f"{self.oss_bucket}.{host}"
            base = f"{scheme}://{base_host}"
        safe_key = quote(object_key.lstrip("/"), safe="/")
        return f"{base}/{safe_key}"

    def _extract_time(self, payload: Dict[str, Any], keys: List[str]) -> float:
        for key in keys:
            if key in payload and payload[key] is not None:
                value = payload[key]
                try:
                    num = float(value)
                except Exception:  # noqa: BLE001
                    continue
                if num > 10000:
                    return round(num / 1000.0, 2)
                return round(num, 2)
        return 0.0

    def _build_segments(self, results: List[Dict[str, Any]]):
        segments: List[Dict[str, Any]] = []
        for item in results:
            start = round(item["start_sample"] / WAV_SAMPLE_RATE, 2)
            end = round(item["end_sample"] / WAV_SAMPLE_RATE, 2)
            segments.append(
                {
                    "id": item["index"],
                    "start": start,
                    "end": end,
                    "duration": round(max(end - start, 0.0), 2),
                    "text": item.get("text", ""),
                    "speaker": "Speaker_1",
                    "words": [],
                }
            )
        if not segments:
            segments.append(
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 0.0,
                    "duration": 0.0,
                    "text": "",
                    "speaker": "Speaker_1",
                    "words": [],
                }
            )
        return segments

    def _majority_language(self, results: List[Dict[str, Any]]) -> str:
        counter: Dict[str, int] = {}
        for item in results:
            lang = item.get("language") or ""
            if lang:
                counter[lang] = counter.get(lang, 0) + 1
        if not counter:
            return ""
        return max(counter.items(), key=lambda kv: kv[1])[0]

    def _summarize_speakers(self, segments: List[Dict[str, Any]]):
        speakers: Dict[str, Dict[str, Any]] = {}
        for seg in segments:
            speaker = seg.get("speaker", "Speaker_1")
            speakers.setdefault(
                speaker,
                {"id": speaker, "name": speaker, "segments_count": 0, "total_duration": 0.0, "words": []},
            )
            speakers[speaker]["segments_count"] += 1
            speakers[speaker]["total_duration"] += seg.get("end", 0.0) - seg.get("start", 0.0)
            if seg.get("text"):
                speakers[speaker]["words"].append(seg["text"])
        return speakers
