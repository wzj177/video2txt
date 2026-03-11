#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR引擎模块
包含各种语音识别引擎的具体实现
"""

from .whisper_engine import WhisperEngine
from .faster_whisper_engine import FasterWhisperEngine
from .sensevoice_engine import SenseVoiceEngine
from .dolphin_engine import DolphinEngine
from .whisperx_engine import WhisperXEngine
from .remote_api_engine import RemoteAPIEngine
from .parakeet_engine import ParakeetEngine
from .qwen3_asr_engine import Qwen3ASREngine

__all__ = [
    "WhisperEngine",
    "FasterWhisperEngine",
    "SenseVoiceEngine",
    "DolphinEngine",
    "WhisperXEngine",
    "RemoteAPIEngine",
    "ParakeetEngine",
    "Qwen3ASREngine",
]
