#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 系统信息服务
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
            # 模拟GPU信息（用于开发环境）
            return {
                "gpu": True,
                "gpu_name": "模拟GPU (开发环境)",
                "gpu_usage": 25,
                "gpu_memory_usage": 30,
            }
        except Exception:
            return {"gpu": False, "gpu_usage": 0}


# 全局系统服务实例
system_service = SystemService()
