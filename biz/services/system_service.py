#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 系统信息服务
"""

import psutil
import platform
from typing import Dict, Any
from datetime import datetime


class SystemService:
    """系统信息服务"""

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """获取系统信息"""
        try:
            # 获取基础系统信息
            system_info = {
                "os": platform.system(),
                "platform": platform.platform(),
                "cpu_count": psutil.cpu_count(),
                "cpu_usage": psutil.cpu_percent(interval=1),
                "memory": dict(psutil.virtual_memory()._asdict()),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage("/").percent,
                "timestamp": datetime.now().isoformat(),
            }

            # 检查GPU支持
            gpu_info = SystemService._get_gpu_info()
            system_info.update(gpu_info)

            return system_info

        except Exception as e:
            raise Exception(f"获取系统信息失败: {str(e)}")

    @staticmethod
    def _get_gpu_info() -> Dict[str, Any]:
        """获取GPU信息"""
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                return {
                    "gpu": True,
                    "gpu_name": gpu.name,
                    "gpu_usage": gpu.load * 100,
                    "gpu_memory_usage": gpu.memoryUtil * 100,
                }
            else:
                return {"gpu": False, "gpu_usage": 0}

        except ImportError:
            # 尝试其他方式检测GPU
            return SystemService._get_gpu_info_fallback()
        except Exception:
            return {"gpu": False, "gpu_usage": 0}

    @staticmethod
    def _get_gpu_info_fallback() -> Dict[str, Any]:
        """备用GPU检测方法"""
        try:
            # 尝试使用torch检测CUDA
            import torch

            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                return {
                    "gpu": True,
                    "gpu_name": gpu_name,
                    "gpu_usage": 0,  # torch不提供实时使用率
                    "gpu_memory_usage": 0,
                }
        except ImportError:
            pass

        try:
            # 尝试使用nvidia-ml-py检测NVIDIA GPU
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")

            # 获取使用率
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)

            return {
                "gpu": True,
                "gpu_name": name,
                "gpu_usage": util.gpu,
                "gpu_memory_usage": util.memory,
            }
        except (ImportError, Exception):
            pass

        # 如果所有方法都失败，返回无GPU状态
        return {"gpu": False, "gpu_usage": 0}


# 全局系统服务实例
system_service = SystemService()
