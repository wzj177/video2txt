#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议软件集成模块
支持腾讯会议、钉钉、飞书等主流会议软件的音频捕获
"""

import os
import sys
import time
import psutil
import threading
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
import subprocess
import platform

# 音频捕获
try:
    import pyaudio
    import numpy as np

    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


@dataclass
class MeetingApp:
    """会议应用信息"""

    name: str
    process_name: str
    display_name: str
    audio_device_hint: Optional[str] = None
    window_title_pattern: Optional[str] = None


class MeetingDetector:
    """会议软件检测器"""

    # 支持的会议软件列表
    SUPPORTED_APPS = [
        MeetingApp(
            name="tencent_meeting",
            process_name="wemeetapp" if platform.system() == "Darwin" else "wemeet.exe",
            display_name="腾讯会议",
            window_title_pattern="腾讯会议",
        ),
        MeetingApp(
            name="dingtalk",
            process_name=(
                "dingtalk" if platform.system() == "Darwin" else "dingtalk.exe"
            ),
            display_name="钉钉",
            window_title_pattern="钉钉",
        ),
        MeetingApp(
            name="feishu",
            process_name="feishu" if platform.system() == "Darwin" else "feishu.exe",
            display_name="飞书",
            window_title_pattern="飞书",
        ),
        MeetingApp(
            name="zoom",
            process_name="zoom.us" if platform.system() == "Darwin" else "zoom.exe",
            display_name="Zoom",
            window_title_pattern="Zoom",
        ),
        MeetingApp(
            name="teams",
            process_name=(
                "microsoft teams" if platform.system() == "Darwin" else "teams.exe"
            ),
            display_name="Microsoft Teams",
            window_title_pattern="Teams",
        ),
        MeetingApp(
            name="webex",
            process_name=(
                "cisco webex meetings"
                if platform.system() == "Darwin"
                else "ciscowebexstart.exe"
            ),
            display_name="Cisco Webex",
            window_title_pattern="Webex",
        ),
    ]

    def __init__(self):
        self.running_apps: List[MeetingApp] = []
        self.detection_callback: Optional[Callable] = None
        self.monitoring_thread: Optional[threading.Thread] = None
        self.is_monitoring = False

    def detect_running_meeting_apps(self) -> List[MeetingApp]:
        """检测当前运行的会议软件"""
        running_apps = []

        try:
            # 获取所有运行中的进程
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    process_name = proc.info["name"].lower()

                    # 检查是否匹配已知的会议软件
                    for app in self.SUPPORTED_APPS:
                        if app.process_name.lower() in process_name:
                            if app not in running_apps:
                                running_apps.append(app)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            print(f"⚠️ 进程检测失败: {e}")

        return running_apps

    def start_monitoring(self, callback: Callable[[List[MeetingApp]], None]):
        """开始监控会议软件"""
        self.detection_callback = callback
        self.is_monitoring = True

        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self.monitoring_thread.start()

        print("🔍 开始监控会议软件...")

    def stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1)
        print("🛑 停止监控会议软件")

    def _monitoring_loop(self):
        """监控循环"""
        last_apps = []

        while self.is_monitoring:
            try:
                current_apps = self.detect_running_meeting_apps()

                # 检查是否有变化
                if current_apps != last_apps:
                    if self.detection_callback:
                        self.detection_callback(current_apps)
                    last_apps = current_apps.copy()

                time.sleep(5)  # 每5秒检测一次

            except Exception as e:
                print(f"⚠️ 监控循环异常: {e}")
                time.sleep(10)


class SystemAudioManager:
    """系统音频管理器"""

    def __init__(self):
        self.audio = None
        self.loopback_stream = None
        self.is_capturing = False
        self.audio_callback = None

    def initialize(self) -> bool:
        """初始化音频系统"""
        if not HAS_PYAUDIO:
            print("❌ 需要安装pyaudio: pip install pyaudio")
            return False

        try:
            self.audio = pyaudio.PyAudio()
            return True
        except Exception as e:
            print(f"❌ 音频系统初始化失败: {e}")
            return False

    def find_loopback_device(self) -> Optional[int]:
        """寻找系统音频回环设备"""
        if not self.audio:
            return None

        try:
            device_count = self.audio.get_device_count()

            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                device_name = device_info.get("name", "").lower()

                # 寻找回环设备的关键词
                loopback_keywords = [
                    "loopback",
                    "stereo mix",
                    "what u hear",
                    "wave out mix",
                    "立体声混音",
                    "系统音频",
                ]

                if any(keyword in device_name for keyword in loopback_keywords):
                    if device_info.get("maxInputChannels", 0) > 0:
                        print(f"✅ 找到系统音频设备: {device_info['name']}")
                        return i

            # 如果没找到专门的回环设备，尝试使用默认输入设备
            default_input = self.audio.get_default_input_device_info()
            print(f"⚠️ 未找到专门的系统音频设备，使用默认输入: {default_input['name']}")
            return default_input["index"]

        except Exception as e:
            print(f"⚠️ 音频设备检测失败: {e}")
            return None

    def start_system_audio_capture(
        self, callback: Callable[[np.ndarray, float], None]
    ) -> bool:
        """开始系统音频捕获"""
        if self.is_capturing:
            return True

        device_index = self.find_loopback_device()
        if device_index is None:
            print("❌ 无法找到合适的音频捕获设备")
            return False

        self.audio_callback = callback

        try:
            # 音频参数
            sample_rate = 16000
            chunk_size = 1024
            channels = 1

            self.loopback_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
                stream_callback=self._audio_stream_callback,
            )

            self.loopback_stream.start_stream()
            self.is_capturing = True

            print("🎤 开始系统音频捕获...")
            return True

        except Exception as e:
            print(f"❌ 系统音频捕获启动失败: {e}")
            return False

    def _audio_stream_callback(self, in_data, frame_count, time_info, status):
        """音频流回调"""
        if self.audio_callback and self.is_capturing:
            try:
                audio_data = np.frombuffer(in_data, dtype=np.int16)
                timestamp = time.time()
                self.audio_callback(audio_data, timestamp)
            except Exception as e:
                print(f"⚠️ 音频回调处理失败: {e}")

        return (in_data, pyaudio.paContinue)

    def stop_system_audio_capture(self):
        """停止系统音频捕获"""
        self.is_capturing = False

        if self.loopback_stream:
            try:
                self.loopback_stream.stop_stream()
                self.loopback_stream.close()
            except:
                pass
            self.loopback_stream = None

        print("🛑 系统音频捕获已停止")

    def cleanup(self):
        """清理资源"""
        self.stop_system_audio_capture()
        if self.audio:
            self.audio.terminate()


class MeetingIntegration:
    """会议软件集成主控制器"""

    def __init__(self, on_audio_data: Callable[[np.ndarray, float], None]):
        self.detector = MeetingDetector()
        self.audio_manager = SystemAudioManager()
        self.on_audio_data = on_audio_data
        self.current_meeting_apps: List[MeetingApp] = []
        self.is_integrated = False

    def initialize(self) -> bool:
        """初始化会议集成"""
        print("🚀 初始化会议软件集成...")

        if not self.audio_manager.initialize():
            return False

        # 检查当前运行的会议软件
        running_apps = self.detector.detect_running_meeting_apps()
        if running_apps:
            print("📱 检测到运行中的会议软件:")
            for app in running_apps:
                print(f"   ✅ {app.display_name}")
        else:
            print("⚠️ 未检测到支持的会议软件")

        print("✅ 会议集成初始化完成")
        return True

    def start_integration(self):
        """开始会议集成"""
        # 开始监控会议软件
        self.detector.start_monitoring(self._on_meeting_apps_changed)

        # 检查当前状态
        current_apps = self.detector.detect_running_meeting_apps()
        if current_apps:
            self._start_audio_capture()

        self.is_integrated = True
        print("🎬 会议集成已启动")

    def stop_integration(self):
        """停止会议集成"""
        self.detector.stop_monitoring()
        self.audio_manager.stop_system_audio_capture()
        self.is_integrated = False
        print("⏹️ 会议集成已停止")

    def _on_meeting_apps_changed(self, apps: List[MeetingApp]):
        """会议软件状态变化回调"""
        new_apps = [app for app in apps if app not in self.current_meeting_apps]
        stopped_apps = [app for app in self.current_meeting_apps if app not in apps]

        # 处理新启动的会议软件
        for app in new_apps:
            print(f"🆕 检测到会议软件启动: {app.display_name}")

        # 处理停止的会议软件
        for app in stopped_apps:
            print(f"❌ 检测到会议软件停止: {app.display_name}")

        self.current_meeting_apps = apps.copy()

        # 根据会议软件状态调整音频捕获
        if apps and not self.audio_manager.is_capturing:
            self._start_audio_capture()
        elif not apps and self.audio_manager.is_capturing:
            self._stop_audio_capture()

    def _start_audio_capture(self):
        """开始音频捕获"""
        if self.audio_manager.start_system_audio_capture(self.on_audio_data):
            print("🎤 已开始捕获会议音频")
        else:
            print("❌ 音频捕获启动失败")

    def _stop_audio_capture(self):
        """停止音频捕获"""
        self.audio_manager.stop_system_audio_capture()
        print("🛑 已停止捕获会议音频")

    def get_meeting_status(self) -> Dict:
        """获取会议状态"""
        return {
            "is_integrated": self.is_integrated,
            "is_capturing_audio": self.audio_manager.is_capturing,
            "running_apps": [
                {"name": app.name, "display_name": app.display_name}
                for app in self.current_meeting_apps
            ],
        }


def demo_integration():
    """演示会议集成功能"""

    def on_audio_data(audio_data: np.ndarray, timestamp: float):
        # 这里可以将音频数据传递给实时转录系统
        print(f"📊 接收到音频数据: {len(audio_data)} samples at {timestamp}")

    # 创建会议集成
    integration = MeetingIntegration(on_audio_data)

    try:
        if integration.initialize():
            integration.start_integration()

            print("🎯 会议集成运行中...")
            print("💡 请启动或停止会议软件来测试检测功能")
            print("💡 按 Ctrl+C 停止")

            while True:
                status = integration.get_meeting_status()
                print(
                    f"📊 状态: 集成={status['is_integrated']}, 音频捕获={status['is_capturing_audio']}, 运行的应用={len(status['running_apps'])}"
                )
                time.sleep(10)

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    finally:
        integration.stop_integration()


if __name__ == "__main__":
    demo_integration()
