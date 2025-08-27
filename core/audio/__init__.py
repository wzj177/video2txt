#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频处理模块
"""

from .audio_capture import AudioCapture, AudioBuffer
from .system_audio_capture import SystemAudioCapture, AudioBuffer as SystemAudioBuffer
from .permission_checker import AudioPermissionChecker

__all__ = [
    "AudioCapture",
    "AudioBuffer",
    "SystemAudioCapture",
    "SystemAudioBuffer",
    "AudioPermissionChecker",
]
