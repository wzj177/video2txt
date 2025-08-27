#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频捕获模块 - 支持系统音频捕获
"""

import os
import sys
import logging
import threading
import queue
import time
import tempfile
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class AudioCapture:
    """音频捕获器"""

    def __init__(
        self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.is_capturing = False
        self.audio_queue = queue.Queue()
        self.capture_thread = None
        self.callback = None

        # 尝试导入音频库
        self.audio_backend = self._detect_audio_backend()

    def _detect_audio_backend(self) -> str:
        """检测可用的音频后端"""
        try:
            import pyaudio

            return "pyaudio"
        except ImportError:
            pass

        try:
            import sounddevice as sd

            return "sounddevice"
        except ImportError:
            pass

        # 如果没有可用的音频库，使用模拟模式
        logger.warning("未找到可用的音频库，将使用模拟音频模式")
        return "mock"

    def list_audio_devices(self) -> Dict[str, Any]:
        """列出可用的音频设备"""
        devices = []

        if self.audio_backend == "pyaudio":
            try:
                import pyaudio

                p = pyaudio.PyAudio()

                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:  # 输入设备
                        devices.append(
                            {
                                "index": i,
                                "name": info["name"],
                                "channels": info["maxInputChannels"],
                                "sample_rate": int(info["defaultSampleRate"]),
                            }
                        )

                p.terminate()

            except Exception as e:
                logger.error(f"获取PyAudio设备列表失败: {e}")

        elif self.audio_backend == "sounddevice":
            try:
                import sounddevice as sd

                device_list = sd.query_devices()

                for i, device in enumerate(device_list):
                    if device["max_input_channels"] > 0:
                        devices.append(
                            {
                                "index": i,
                                "name": device["name"],
                                "channels": device["max_input_channels"],
                                "sample_rate": int(device["default_samplerate"]),
                            }
                        )

            except Exception as e:
                logger.error(f"获取SoundDevice设备列表失败: {e}")

        return {
            "backend": self.audio_backend,
            "devices": devices,
            "default_device": self._get_default_device(),
        }

    def _get_default_device(self) -> Optional[int]:
        """获取默认音频设备"""
        if self.audio_backend == "pyaudio":
            try:
                import pyaudio

                p = pyaudio.PyAudio()
                default_device = p.get_default_input_device_info()
                p.terminate()
                return default_device["index"]
            except:
                return None

        elif self.audio_backend == "sounddevice":
            try:
                import sounddevice as sd

                return sd.default.device[0]  # 输入设备
            except:
                return None

        return None

    def start_capture(
        self, device_index: Optional[int] = None, callback: Optional[Callable] = None
    ):
        """开始音频捕获"""
        if self.is_capturing:
            logger.warning("音频捕获已在进行中")
            return False

        self.callback = callback
        self.is_capturing = True

        # 启动捕获线程
        self.capture_thread = threading.Thread(
            target=self._capture_loop, args=(device_index,), daemon=True
        )
        self.capture_thread.start()

        logger.info(f"音频捕获已启动 (后端: {self.audio_backend})")
        return True

    def stop_capture(self):
        """停止音频捕获"""
        if not self.is_capturing:
            return

        self.is_capturing = False

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)

        logger.info("音频捕获已停止")

    def _capture_loop(self, device_index: Optional[int]):
        """音频捕获循环"""
        if self.audio_backend == "pyaudio":
            self._pyaudio_capture(device_index)
        elif self.audio_backend == "sounddevice":
            self._sounddevice_capture(device_index)
        else:
            self._mock_capture()

    def _pyaudio_capture(self, device_index: Optional[int]):
        """PyAudio音频捕获"""
        try:
            import pyaudio

            p = pyaudio.PyAudio()

            # 配置音频流
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
            )

            logger.info(
                f"PyAudio流已启动 (设备: {device_index}, 采样率: {self.sample_rate})"
            )

            while self.is_capturing:
                try:
                    # 读取音频数据
                    data = stream.read(self.chunk_size, exception_on_overflow=False)

                    # 转换为numpy数组
                    audio_data = np.frombuffer(data, dtype=np.float32)

                    # 计算音量级别
                    volume_level = np.sqrt(np.mean(audio_data**2)) * 100

                    # 调用回调函数
                    if self.callback:
                        self.callback(
                            {
                                "audio_data": audio_data,
                                "volume_level": min(100, volume_level),
                                "timestamp": time.time(),
                            }
                        )

                except Exception as e:
                    if self.is_capturing:  # 只在仍在捕获时记录错误
                        logger.error(f"读取音频数据失败: {e}")
                    break

            # 清理资源
            stream.stop_stream()
            stream.close()
            p.terminate()

        except Exception as e:
            logger.error(f"PyAudio捕获失败: {e}")

    def _sounddevice_capture(self, device_index: Optional[int]):
        """SoundDevice音频捕获"""
        try:
            import sounddevice as sd

            logger.info(
                f"SoundDevice流已启动 (设备: {device_index}, 采样率: {self.sample_rate})"
            )

            def audio_callback(indata, frames, time, status):
                if status:
                    logger.warning(f"音频状态: {status}")

                if self.is_capturing and self.callback:
                    # 转换为单声道
                    if indata.shape[1] > 1:
                        audio_data = np.mean(indata, axis=1)
                    else:
                        audio_data = indata[:, 0]

                    # 计算音量级别
                    volume_level = np.sqrt(np.mean(audio_data**2)) * 100

                    self.callback(
                        {
                            "audio_data": audio_data,
                            "volume_level": min(100, volume_level),
                            "timestamp": time.inputBufferAdcTime,
                        }
                    )

            # 启动音频流
            with sd.InputStream(
                device=device_index,
                channels=self.channels,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                callback=audio_callback,
                dtype=np.float32,
            ):
                while self.is_capturing:
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"SoundDevice捕获失败: {e}")

    def _mock_capture(self):
        """模拟音频捕获"""
        logger.info("启动模拟音频捕获")

        import random

        while self.is_capturing:
            try:
                # 生成模拟音频数据
                duration = self.chunk_size / self.sample_rate
                t = np.linspace(0, duration, self.chunk_size)

                # 生成带噪声的正弦波
                frequency = random.uniform(200, 800)
                amplitude = random.uniform(0.1, 0.5)
                audio_data = amplitude * np.sin(2 * np.pi * frequency * t)
                audio_data += np.random.normal(0, 0.05, self.chunk_size)

                # 模拟音量变化
                volume_level = random.uniform(20, 80)

                if self.callback:
                    self.callback(
                        {
                            "audio_data": audio_data.astype(np.float32),
                            "volume_level": volume_level,
                            "timestamp": time.time(),
                        }
                    )

                time.sleep(duration)

            except Exception as e:
                logger.error(f"模拟音频捕获错误: {e}")
                break

    def test_capture(
        self, duration: float = 3.0, device_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """测试音频捕获"""
        test_results = {
            "success": False,
            "backend": self.audio_backend,
            "device": "unknown",
            "sample_rate": self.sample_rate,
            "volume_levels": [],
            "duration": duration,
            "error": None,
        }

        def test_callback(data):
            test_results["volume_levels"].append(data["volume_level"])

        try:
            # 获取设备信息
            devices_info = self.list_audio_devices()
            if devices_info["devices"]:
                device_name = "default"
                if device_index is not None:
                    for device in devices_info["devices"]:
                        if device["index"] == device_index:
                            device_name = device["name"]
                            break
                test_results["device"] = device_name

            # 开始测试捕获
            if self.start_capture(device_index, test_callback):
                time.sleep(duration)
                self.stop_capture()

                if test_results["volume_levels"]:
                    avg_volume = np.mean(test_results["volume_levels"])
                    max_volume = np.max(test_results["volume_levels"])

                    test_results.update(
                        {
                            "success": True,
                            "avg_volume": round(avg_volume, 2),
                            "max_volume": round(max_volume, 2),
                            "samples": len(test_results["volume_levels"]),
                        }
                    )
                else:
                    test_results["error"] = "未捕获到音频数据"
            else:
                test_results["error"] = "无法启动音频捕获"

        except Exception as e:
            test_results["error"] = str(e)
            logger.error(f"音频捕获测试失败: {e}")

        return test_results


class AudioBuffer:
    """音频缓冲器 - 用于实时音频处理"""

    def __init__(self, max_duration: float = 30.0, sample_rate: int = 16000):
        self.max_duration = max_duration
        self.sample_rate = sample_rate
        self.max_samples = int(max_duration * sample_rate)
        self.buffer = np.array([], dtype=np.float32)
        self.lock = threading.Lock()

    def add_audio(self, audio_data: np.ndarray):
        """添加音频数据到缓冲区"""
        with self.lock:
            self.buffer = np.concatenate([self.buffer, audio_data])

            # 保持缓冲区大小
            if len(self.buffer) > self.max_samples:
                self.buffer = self.buffer[-self.max_samples :]

    def get_audio(self, duration: float = None) -> np.ndarray:
        """获取指定时长的音频数据"""
        with self.lock:
            if duration is None:
                return self.buffer.copy()

            samples = int(duration * self.sample_rate)
            if len(self.buffer) >= samples:
                return self.buffer[-samples:].copy()
            else:
                return self.buffer.copy()

    def clear(self):
        """清空缓冲区"""
        with self.lock:
            self.buffer = np.array([], dtype=np.float32)

    def save_to_file(self, filepath: str, duration: float = None):
        """保存音频到文件"""
        try:
            import soundfile as sf

            audio_data = self.get_audio(duration)
            sf.write(filepath, audio_data, self.sample_rate)
            return True
        except ImportError:
            # 如果没有soundfile，使用wave
            try:
                import wave

                audio_data = self.get_audio(duration)

                # 转换为16位整数
                audio_int16 = (audio_data * 32767).astype(np.int16)

                with wave.open(filepath, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_int16.tobytes())

                return True
            except Exception as e:
                logger.error(f"保存音频文件失败: {e}")
                return False
