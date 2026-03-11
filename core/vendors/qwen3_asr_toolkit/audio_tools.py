#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal audio utilities extracted from the Qwen3-ASR toolkit."""

from __future__ import annotations

import io
import os
import subprocess
from typing import List, Sequence, Tuple

import librosa
import numpy as np
import soundfile as sf

try:  # silero-vad is optional at runtime
    from silero_vad import get_speech_timestamps  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    get_speech_timestamps = None


WAV_SAMPLE_RATE = 16000


def load_audio(file_path: str) -> np.ndarray:
    """Load audio and resample to 16k mono using librosa/ffmpeg fallbacks."""

    if file_path.startswith(("http://", "https://")):
        raise ValueError("Remote audio loading should be handled upstream")

    try:
        wav_data, _ = librosa.load(file_path, sr=WAV_SAMPLE_RATE, mono=True)
        return wav_data
    except Exception:
        command = [
            "ffmpeg",
            "-i",
            file_path,
            "-ar",
            str(WAV_SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-",
        ]
        process = subprocess.Popen(  # noqa: S603, S404 - controlled args
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout_data, stderr_data = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"FFmpeg error processing local file: {stderr_data.decode(utf-8, errors=ignore)}"
            )
        with io.BytesIO(stdout_data) as data_io:
            wav_data, _ = sf.read(data_io, dtype="float32")
        return wav_data


def process_vad(
    wav: np.ndarray,
    worker_vad_model,
    segment_threshold_s: int = 120,
    max_segment_threshold_s: int = 180,
) -> List[Tuple[int, int, np.ndarray]]:
    """Split waveform using Silero-VAD timestamps as guidance."""

    if get_speech_timestamps is None or worker_vad_model is None:
        return _fallback_chunking(wav, max_segment_threshold_s)

    vad_params = {
        "sampling_rate": WAV_SAMPLE_RATE,
        "return_seconds": False,
        "min_speech_duration_ms": 1500,
        "min_silence_duration_ms": 500,
    }

    speech_timestamps = get_speech_timestamps(wav, worker_vad_model, **vad_params)
    if not speech_timestamps:
        return _fallback_chunking(wav, max_segment_threshold_s)

    potential_split_points = {0, len(wav)}
    for timestamp in speech_timestamps:
        potential_split_points.add(timestamp["start"])  # type: ignore[index]

    sorted_points = sorted(potential_split_points)
    segment_thr_samples = segment_threshold_s * WAV_SAMPLE_RATE
    target = segment_thr_samples
    while target < len(wav):
        closest = min(sorted_points, key=lambda p: abs(p - target))
        potential_split_points.add(closest)
        target += segment_thr_samples

    ordered = sorted(potential_split_points)
    final_points: List[int] = [0]
    max_thr_samples = max_segment_threshold_s * WAV_SAMPLE_RATE

    for i in range(1, len(ordered)):
        start = ordered[i - 1]
        end = ordered[i]
        segment_len = end - start
        if segment_len <= max_thr_samples:
            final_points.append(end)
            continue
        num_subsegments = int(np.ceil(segment_len / max_thr_samples))
        sub_len = segment_len / num_subsegments
        for j in range(1, num_subsegments):
            final_points.append(int(start + j * sub_len))
        final_points.append(end)

    splits: List[Tuple[int, int, np.ndarray]] = []
    for i in range(1, len(final_points)):
        start_sample = int(final_points[i - 1])
        end_sample = int(final_points[i])
        segment = wav[start_sample:end_sample]
        if len(segment) > 0:
            splits.append((start_sample, end_sample, segment))
    return splits or _fallback_chunking(wav, max_segment_threshold_s)


def _fallback_chunking(
    wav: np.ndarray, max_segment_threshold_s: int
) -> List[Tuple[int, int, np.ndarray]]:
    segments: List[Tuple[int, int, np.ndarray]] = []
    chunk = max_segment_threshold_s * WAV_SAMPLE_RATE
    total = len(wav)
    for start in range(0, total, chunk):
        end = min(start + chunk, total)
        segment = wav[start:end]
        if len(segment) > 0:
            segments.append((start, end, segment))
    return segments or [(0, total, wav)]


def save_audio_file(wav: np.ndarray, file_path: str) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    sf.write(file_path, wav, WAV_SAMPLE_RATE)

