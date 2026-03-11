#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音识别模块
统一的语音识别接口，支持多种ASR引擎
"""

from .voice_recognition_core import (
    voice_core,
    initialize_voice_recognition,
    get_voice_core,
    is_voice_recognition_initialized,
    VoiceRecognitionCore,
    VoiceEngineConfig,
)


# 兼容性接口
def transcribe_audio(audio_path: str, language: str = "auto"):
    """兼容性接口：转录音频文件"""
    if not is_voice_recognition_initialized():
        initialize_voice_recognition()

    return voice_core.recognize_file(audio_path, language)


def get_available_engines():
    """获取可用的语音识别引擎列表"""
    return voice_core.get_supported_engines()


__all__ = [
    "voice_core",
    "initialize_voice_recognition",
    "get_voice_core",
    "is_voice_recognition_initialized",
    "VoiceRecognitionCore",
    "VoiceEngineConfig",
    "transcribe_audio",
    "get_available_engines",
]
