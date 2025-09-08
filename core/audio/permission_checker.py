#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 音频权限检查模块
检查和申请系统音频访问权限
"""

import platform
import subprocess
import os
from typing import Dict, Any, Optional

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import pyaudio
except ImportError:
    pyaudio = None


class AudioPermissionChecker:
    """音频权限检查器"""

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "python_version": platform.python_version(),
            "sounddevice_available": sd is not None,
            "pyaudio_available": pyaudio is not None,
        }

    @staticmethod
    def check_microphone_permission() -> Dict[str, Any]:
        """检查麦克风权限"""
        result = {
            "granted": False,
            "error": None,
            "device_count": 0,
            "test_successful": False,
        }

        try:
            if sd:
                # 使用sounddevice测试
                devices = sd.query_devices()
                input_devices = [d for d in devices if d["max_input_channels"] > 0]
                result["device_count"] = len(input_devices)

                if input_devices:
                    # 尝试短暂录制来测试权限
                    try:
                        # 录制0.1秒的静音来测试权限
                        test_recording = sd.rec(
                            frames=int(0.1 * 16000),
                            samplerate=16000,
                            channels=1,
                            dtype="float32",
                        )
                        sd.wait()  # 等待录制完成
                        result["test_successful"] = True
                        result["granted"] = True
                    except Exception as e:
                        result["error"] = f"权限测试失败: {str(e)}"
                        if "permission" in str(e).lower() or "access" in str(e).lower():
                            result["granted"] = False
                        else:
                            result["granted"] = True  # 可能是其他非权限问题

            elif pyaudio:
                # 使用pyaudio测试
                try:
                    p = pyaudio.PyAudio()
                    device_count = p.get_device_count()
                    input_devices = []

                    for i in range(device_count):
                        info = p.get_device_info_by_index(i)
                        if info["maxInputChannels"] > 0:
                            input_devices.append(info)

                    result["device_count"] = len(input_devices)

                    if input_devices:
                        # 测试录制
                        stream = p.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=16000,
                            input=True,
                            frames_per_buffer=1024,
                        )

                        # 读取少量数据测试
                        data = stream.read(1024, exception_on_overflow=False)
                        stream.close()
                        p.terminate()

                        result["test_successful"] = True
                        result["granted"] = True

                except Exception as e:
                    result["error"] = f"PyAudio测试失败: {str(e)}"
                    if "input overflowed" in str(e).lower():
                        result["granted"] = True  # 有权限但缓冲区问题
                    else:
                        result["granted"] = False

            else:
                result["error"] = "没有可用的音频库"

        except Exception as e:
            result["error"] = f"权限检查异常: {str(e)}"

        return result

    @staticmethod
    def check_system_audio_permission() -> Dict[str, Any]:
        """检查系统音频捕获权限"""
        result = {
            "granted": False,
            "error": None,
            "loopback_devices": 0,
            "recommended_setup": None,
        }

        system = platform.system()

        try:
            if system == "Windows":
                result.update(AudioPermissionChecker._check_windows_system_audio())
            elif system == "Darwin":  # macOS
                result.update(AudioPermissionChecker._check_macos_system_audio())
            else:  # Linux
                result.update(AudioPermissionChecker._check_linux_system_audio())

        except Exception as e:
            result["error"] = f"系统音频权限检查失败: {str(e)}"

        return result

    @staticmethod
    def _check_windows_system_audio() -> Dict[str, Any]:
        """检查Windows系统音频权限"""
        result = {
            "granted": False,
            "loopback_devices": 0,
            "recommended_setup": "启用'立体声混音'或安装虚拟音频设备",
        }

        if not sd:
            result["error"] = "sounddevice不可用"
            return result

        try:
            devices = sd.query_devices()
            loopback_devices = []

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
                        loopback_devices.append(device)

            result["loopback_devices"] = len(loopback_devices)

            if loopback_devices:
                # 测试是否可以使用loopback设备
                try:
                    test_device = None
                    for i, device in enumerate(devices):
                        if device in loopback_devices:
                            test_device = i
                            break

                    if test_device is not None:
                        # 短暂测试录制
                        test_recording = sd.rec(
                            frames=int(0.1 * 16000),
                            samplerate=16000,
                            channels=1,
                            device=test_device,
                            dtype="float32",
                        )
                        sd.wait()
                        result["granted"] = True

                except Exception as e:
                    result["error"] = f"Loopback设备测试失败: {str(e)}"

            else:
                result["recommended_setup"] = (
                    "未找到立体声混音设备。请在Windows声音设置中启用'立体声混音'，"
                    "或安装VB-Cable等虚拟音频设备"
                )

        except Exception as e:
            result["error"] = f"Windows音频检查失败: {str(e)}"

        return result

    @staticmethod
    def _check_macos_system_audio() -> Dict[str, Any]:
        """检查macOS系统音频权限"""
        result = {
            "granted": False,
            "loopback_devices": 0,
            "recommended_setup": "安装BlackHole或Soundflower虚拟音频设备",
        }

        if not sd:
            result["error"] = "sounddevice不可用"
            return result

        try:
            devices = sd.query_devices()
            virtual_devices = []

            for device in devices:
                name = device["name"].lower()
                if any(
                    keyword in name
                    for keyword in ["blackhole", "soundflower", "loopback"]
                ):
                    if device["max_input_channels"] > 0:
                        virtual_devices.append(device)

            result["loopback_devices"] = len(virtual_devices)

            if virtual_devices:
                result["granted"] = True
                result["recommended_setup"] = "已找到虚拟音频设备，可以进行系统音频捕获"
            else:
                result["recommended_setup"] = (
                    "建议安装BlackHole (https://github.com/ExistentialAudio/BlackHole) "
                    "或Soundflower来捕获系统音频"
                )

        except Exception as e:
            result["error"] = f"macOS音频检查失败: {str(e)}"

        return result

    @staticmethod
    def _check_linux_system_audio() -> Dict[str, Any]:
        """检查Linux系统音频权限"""
        result = {
            "granted": False,
            "loopback_devices": 0,
            "recommended_setup": "配置PulseAudio monitor设备",
        }

        if not sd:
            result["error"] = "sounddevice不可用"
            return result

        try:
            devices = sd.query_devices()
            monitor_devices = []

            for device in devices:
                name = device["name"].lower()
                if "monitor" in name and device["max_input_channels"] > 0:
                    monitor_devices.append(device)

            result["loopback_devices"] = len(monitor_devices)

            if monitor_devices:
                result["granted"] = True
                result["recommended_setup"] = (
                    "找到PulseAudio monitor设备，可以捕获系统音频"
                )
            else:
                result["recommended_setup"] = (
                    "请确保PulseAudio正在运行，并配置monitor设备来捕获系统音频"
                )

        except Exception as e:
            result["error"] = f"Linux音频检查失败: {str(e)}"

        return result

    @staticmethod
    def request_microphone_permission() -> Dict[str, Any]:
        """主动请求麦克风权限"""
        result = {"success": False, "error": None, "permission_dialog_triggered": False}

        try:
            if sd:
                # 尝试短暂录制来触发权限对话框
                test_recording = sd.rec(
                    frames=int(0.5 * 16000),  # 0.5秒
                    samplerate=16000,
                    channels=1,
                    dtype="float32",
                )
                sd.wait()

                result["success"] = True
                result["permission_dialog_triggered"] = True

            elif pyaudio:
                # 使用PyAudio触发权限请求
                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=1024,
                )

                # 读取少量数据
                data = stream.read(1024, exception_on_overflow=False)
                stream.close()
                p.terminate()

                result["success"] = True
                result["permission_dialog_triggered"] = True

        except Exception as e:
            result["error"] = f"权限请求失败: {str(e)}"
            # 即使失败，也可能已经触发了权限对话框
            if "permission" in str(e).lower() or "access" in str(e).lower():
                result["permission_dialog_triggered"] = True

        return result

    @staticmethod
    def get_permission_help() -> Dict[str, Any]:
        """获取权限设置帮助信息"""
        system = platform.system()

        help_info = {
            "platform": system,
            "microphone_help": "",
            "system_audio_help": "",
            "troubleshooting": [],
        }

        if system == "Windows":
            help_info["microphone_help"] = (
                "1. 打开Windows设置 > 隐私 > 麦克风\n"
                "2. 确保'允许应用访问麦克风'已开启\n"
                "3. 在应用列表中找到听语AI并允许访问"
            )
            help_info["system_audio_help"] = (
                "1. 右键点击任务栏音量图标 > 声音设置\n"
                "2. 在'输入'部分查找'立体声混音'\n"
                "3. 如果没有，右键空白处选择'显示已禁用的设备'\n"
                "4. 启用'立体声混音'设备"
            )
            help_info["troubleshooting"] = [
                "如果没有立体声混音选项，可能需要更新声卡驱动",
                "可以安装VB-Cable等虚拟音频设备作为替代方案",
                "确保Windows音频服务正在运行",
            ]

        elif system == "Darwin":  # macOS
            help_info["microphone_help"] = (
                "1. 打开系统偏好设置 > 安全性与隐私 > 隐私\n"
                "2. 选择左侧的'麦克风'\n"
                "3. 确保听语AI已勾选并允许访问"
            )
            help_info["system_audio_help"] = (
                "1. 安装BlackHole虚拟音频设备\n"
                "2. 下载地址: https://github.com/ExistentialAudio/BlackHole\n"
                "3. 安装后在系统音频设置中配置多输出设备\n"
                "4. 将BlackHole设置为输入源"
            )
            help_info["troubleshooting"] = [
                "如果权限对话框没有出现，请手动在隐私设置中添加",
                "BlackHole安装后需要重启音频应用",
                "可以使用Audio MIDI Setup配置聚合设备",
            ]

        else:  # Linux
            help_info["microphone_help"] = (
                "1. 确保用户在audio组中: sudo usermod -a -G audio $USER\n"
                "2. 检查PulseAudio状态: pulseaudio --check -v\n"
                "3. 重启PulseAudio: pulseaudio -k && pulseaudio --start"
            )
            help_info["system_audio_help"] = (
                "1. 使用pavucontrol查看音频设备\n"
                "2. 在'输入设备'标签中查找monitor设备\n"
                "3. 确保monitor设备未被静音\n"
                "4. 可以使用pactl list sources查看所有音频源"
            )
            help_info["troubleshooting"] = [
                "检查ALSA和PulseAudio配置",
                "确保没有其他应用独占音频设备",
                "可以尝试使用JACK音频系统",
            ]

        return help_info
