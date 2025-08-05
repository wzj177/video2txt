#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper 模型加载器 - 带网络检测和超时控制
"""

import os
import time
import threading
import signal
from typing import Optional, Tuple


class TimeoutException(Exception):
    """超时异常"""

    pass


class WhisperModelLoader:
    """Whisper 模型加载器，支持超时和回退"""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
        self.model = None
        self.exception = None
        self.using_original_whisper = False

    def _load_with_timeout(self, loader_func, *args, **kwargs):
        """带超时控制的模型加载"""

        def target():
            try:
                self.model = loader_func(*args, **kwargs)
            except Exception as e:
                self.exception = e

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        if thread.is_alive():
            # 超时了，抛出异常
            raise TimeoutException(f"模型加载超时 ({self.timeout_seconds}s)")

        if self.exception:
            raise self.exception

        return self.model

    def load_faster_whisper(
        self, model_name: str, device: str = "cpu", compute_type: str = "int8"
    ):
        """加载 faster-whisper 模型"""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError("faster-whisper 未安装")

        # 设置环境变量控制超时
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(self.timeout_seconds)

        # 仅尝试本地缓存，避免网络下载
        try:
            print(f"🔄 检查本地缓存: {model_name}")
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                local_files_only=True,  # 仅使用本地缓存
            )
            print(f"✅ 本地模型加载成功: {model_name}")
            return model
        except Exception as e:
            print(f"⚠️ 本地缓存不可用: {e}")

        # 尝试标准模型名称（仅本地）
        try:
            print("🔄 尝试标准模型名称（本地缓存）...")
            standard_models = {
                "base": "openai/whisper-base",
                "small": "openai/whisper-small",
                "medium": "openai/whisper-medium",
                "large": "openai/whisper-large-v3",
                "tiny": "openai/whisper-tiny",
            }

            standard_name = standard_models.get(
                model_name, f"openai/whisper-{model_name}"
            )

            model = WhisperModel(
                standard_name,
                device=device,
                compute_type=compute_type,
                local_files_only=True,  # 仅使用本地缓存
            )
            print(f"✅ 标准模型加载成功: {standard_name}")
            return model

        except Exception as e:
            print(f"⚠️ 标准模型本地缓存不可用: {e}")

        print("💡 提示: 可运行 download_whisper_models.py 预下载模型")
        return None

    def load_original_whisper(self, model_name: str):
        """加载原版 Whisper 模型"""
        try:
            import whisper
        except ImportError:
            raise ImportError("openai-whisper 未安装")

        try:
            print("🔄 加载原版 Whisper...")
            return self._load_with_timeout(whisper.load_model, model_name)
        except (TimeoutException, Exception) as e:
            print(f"⚠️ 原版 Whisper 加载失败: {e}")
            return None

    def load_best_available(
        self, model_name: str, device: str = "cpu", compute_type: str = "int8"
    ):
        """加载最佳可用模型"""
        print(f"🚀 智能加载 Whisper 模型: {model_name}")

        # 优先尝试 faster-whisper
        try:
            model = self.load_faster_whisper(model_name, device, compute_type)
            if model:
                print("✅ faster-whisper 模型加载成功")
                self.using_original_whisper = False
                return model
        except Exception as e:
            print(f"⚠️ faster-whisper 完全失败: {e}")

        # 回退到原版 whisper
        try:
            model = self.load_original_whisper(model_name)
            if model:
                print("✅ 原版 Whisper 模型加载成功")
                self.using_original_whisper = True
                return model
        except Exception as e:
            print(f"⚠️ 原版 Whisper 失败: {e}")

        print("❌ 所有模型加载方式都失败")
        return None


def quick_network_test(timeout: int = 5) -> bool:
    """快速网络连通性测试"""
    try:
        import requests

        response = requests.get("https://huggingface.co", timeout=timeout)
        return response.status_code == 200
    except:
        return False


# 使用示例
if __name__ == "__main__":
    print("🧪 测试智能 Whisper 模型加载器...")

    # 快速网络测试
    print("\n🌐 快速网络测试...")
    network_ok = quick_network_test(timeout=5)
    print(f"网络状态: {'✅ 正常' if network_ok else '❌ 异常'}")

    # 加载模型
    loader = WhisperModelLoader(timeout_seconds=15)  # 15秒超时

    model = loader.load_best_available("base")

    if model:
        model_type = (
            "原版 Whisper" if loader.using_original_whisper else "faster-whisper"
        )
        print(f"\n🎉 模型加载成功！使用: {model_type}")
        print(f"模型类型: {type(model)}")
    else:
        print("\n❌ 模型加载失败")
        print("💡 建议:")
        print("   1. 检查网络连接")
        print("   2. 安装模型: pip install openai-whisper")
        print("   3. 或: pip install faster-whisper")
