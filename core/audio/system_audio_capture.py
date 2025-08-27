#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 系统音频捕获模块
支持监控系统音频输出，可捕获浏览器、软件等所有音频内容
"""

import asyncio
import platform
import threading
import time
from typing import Callable, Optional, Dict, Any
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import pyaudio
except ImportError:
    pyaudio = None


class SystemAudioCapture:
    """系统音频捕获器"""

    def __init__(
        self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_recording = False
        self.audio_callback = None
        self.stream = None
        self.thread = None

        # 检查音频库可用性
        if not sd and not pyaudio:
            raise ImportError(
                "需要安装 sounddevice 或 pyaudio: pip install sounddevice pyaudio"
            )

    def get_audio_devices(self) -> Dict[str, Any]:
        """获取可用的音频设备列表"""
        devices = {"input": [], "output": [], "loopback": []}

        if sd:
            try:
                device_list = sd.query_devices()
                for i, device in enumerate(device_list):
                    device_info = {
                        "id": i,
                        "name": device["name"],
                        "max_input_channels": device["max_input_channels"],
                        "max_output_channels": device["max_output_channels"],
                        "default_samplerate": device["default_samplerate"],
                    }

                    if device["max_input_channels"] > 0:
                        devices["input"].append(device_info)
                    if device["max_output_channels"] > 0:
                        devices["output"].append(device_info)

                    # 检查是否为loopback设备
                    name_lower = device["name"].lower()
                    if any(
                        keyword in name_lower
                        for keyword in [
                            "loopback",
                            "立体声混音",
                            "stereo mix",
                            "what u hear",
                            "monitor",
                        ]
                    ):
                        devices["loopback"].append(device_info)

            except Exception as e:
                print(f"获取音频设备失败: {e}")

        return devices

    def get_system_audio_device(self) -> Optional[int]:
        """获取系统音频监听设备ID"""
        system = platform.system()

        if system == "Windows":
            return self._get_windows_loopback_device()
        elif system == "Darwin":  # macOS
            return self._get_macos_audio_device()
        else:  # Linux
            return self._get_linux_monitor_device()

    def _get_windows_loopback_device(self) -> Optional[int]:
        """Windows系统音频捕获设备"""
        if not sd:
            return None

        try:
            devices = sd.query_devices()

            # 优先查找专门的loopback设备
            for i, device in enumerate(devices):
                name = device["name"].lower()
                if any(
                    keyword in name
                    for keyword in [
                        "立体声混音",
                        "stereo mix",
                        "loopback",
                        "what u hear",
                    ]
                ):
                    if device["max_input_channels"] > 0:
                        return i

            # 如果没找到，尝试使用默认输出设备（某些驱动支持）
            default_output = sd.default.device[1]
            if default_output is not None:
                return default_output

        except Exception as e:
            print(f"获取Windows音频设备失败: {e}")

        return None

    def _get_macos_audio_device(self) -> Optional[int]:
        """macOS系统音频捕获设备"""
        if not sd:
            return None

        try:
            devices = sd.query_devices()

            # 查找BlackHole、Soundflower等虚拟音频设备
            for i, device in enumerate(devices):
                name = device["name"].lower()
                if any(
                    keyword in name
                    for keyword in ["blackhole", "soundflower", "loopback"]
                ):
                    if device["max_input_channels"] > 0:
                        return i

            # 如果没有虚拟设备，返回默认输入设备
            return sd.default.device[0]

        except Exception as e:
            print(f"获取macOS音频设备失败: {e}")

        return None

    def _get_linux_monitor_device(self) -> Optional[int]:
        """Linux系统音频监听设备"""
        if not sd:
            return None

        try:
            devices = sd.query_devices()

            # 查找PulseAudio monitor设备
            for i, device in enumerate(devices):
                name = device["name"].lower()
                if "monitor" in name and device["max_input_channels"] > 0:
                    return i

            return sd.default.device[0]

        except Exception as e:
            print(f"获取Linux音频设备失败: {e}")

        return None

    def start_capture(
        self, callback: Callable[[np.ndarray], None], device_id: Optional[int] = None
    ) -> bool:
        """开始音频捕获

        Args:
            callback: 音频数据回调函数，接收numpy数组
            device_id: 音频设备ID，None表示自动选择

        Returns:
            bool: 是否成功开始捕获
        """
        if self.is_recording:
            print("音频捕获已在运行中")
            return False

        if device_id is None:
            device_id = self.get_system_audio_device()

        if device_id is None:
            print("未找到可用的音频设备")
            return False

        self.audio_callback = callback
        self.is_recording = True

        # 使用线程运行音频捕获
        self.thread = threading.Thread(target=self._capture_thread, args=(device_id,))
        self.thread.daemon = True
        self.thread.start()

        print(f"开始捕获音频设备 {device_id}")
        return True

    def _capture_thread(self, device_id: int):
        """音频捕获线程"""
        try:

            def audio_callback_wrapper(indata, frames, time_info, status):
                if status:
                    print(f"音频状态: {status}")

                if self.audio_callback and self.is_recording:
                    # 转换为单声道
                    if indata.shape[1] > 1:
                        audio_data = np.mean(indata, axis=1)
                    else:
                        audio_data = indata[:, 0]

                    # 调用用户回调
                    self.audio_callback(audio_data)

            # 开始音频流
            with sd.InputStream(
                device=device_id,
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=audio_callback_wrapper,
                blocksize=self.chunk_size,
            ):
                print(f"音频流已启动，设备ID: {device_id}")

                # 保持捕获状态
                while self.is_recording:
                    time.sleep(0.1)

        except Exception as e:
            print(f"音频捕获异常: {e}")
            self.is_recording = False

    def stop_capture(self):
        """停止音频捕获"""
        if not self.is_recording:
            return

        print("停止音频捕获...")
        self.is_recording = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        self.stream = None
        self.thread = None
        self.audio_callback = None
        print("音频捕获已停止")

    def get_device_info(self, device_id: int) -> Optional[Dict[str, Any]]:
        """获取指定设备的详细信息"""
        if not sd:
            return None

        try:
            device = sd.query_devices(device_id)
            return {
                "name": device["name"],
                "max_input_channels": device["max_input_channels"],
                "max_output_channels": device["max_output_channels"],
                "default_samplerate": device["default_samplerate"],
                "hostapi": device["hostapi"],
            }
        except Exception as e:
            print(f"获取设备信息失败: {e}")
            return None


class AudioBuffer:
    """音频数据缓冲器"""

    def __init__(self, buffer_duration: float = 2.0, sample_rate: int = 16000):
        self.buffer_duration = buffer_duration
        self.sample_rate = sample_rate
        self.buffer_size = int(buffer_duration * sample_rate)
        self.buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.write_pos = 0
        self.is_ready = False

    def add_chunk(self, chunk: np.ndarray):
        """添加音频块到缓冲区"""
        chunk_size = len(chunk)

        if self.write_pos + chunk_size <= self.buffer_size:
            # 直接写入
            self.buffer[self.write_pos : self.write_pos + chunk_size] = chunk
            self.write_pos += chunk_size
        else:
            # 环形缓冲区处理
            remaining = self.buffer_size - self.write_pos
            self.buffer[self.write_pos :] = chunk[:remaining]
            self.buffer[: chunk_size - remaining] = chunk[remaining:]
            self.write_pos = chunk_size - remaining

        # 检查缓冲区是否已满
        if self.write_pos >= self.buffer_size * 0.8:  # 80%满时标记为准备就绪
            self.is_ready = True

    def get_segment(self, duration: float = 1.0) -> np.ndarray:
        """获取指定时长的音频段"""
        segment_size = int(duration * self.sample_rate)
        segment_size = min(segment_size, self.write_pos)

        if segment_size <= 0:
            return np.array([], dtype=np.float32)

        # 获取最新的音频数据
        if self.write_pos >= segment_size:
            segment = self.buffer[self.write_pos - segment_size : self.write_pos].copy()
        else:
            # 环形缓冲区情况
            segment = np.concatenate(
                [
                    self.buffer[self.buffer_size - (segment_size - self.write_pos) :],
                    self.buffer[: self.write_pos],
                ]
            )

        return segment

    def clear(self):
        """清空缓冲区"""
        self.buffer.fill(0)
        self.write_pos = 0
        self.is_ready = False
