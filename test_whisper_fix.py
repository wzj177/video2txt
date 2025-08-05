#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Whisper 模型加载修复
"""

import sys
from pathlib import Path

# 导入需要的模块
sys.path.append(".")
from realtime_meeting import RealtimeTranscriber, MeetingConfig


def test_whisper_model_loading():
    """测试 Whisper 模型加载的各种回退机制"""
    print("🧪 开始测试 Whisper 模型加载修复...")

    # 创建基础配置
    config = MeetingConfig(
        whisper_model="base",
        whisper_device="cpu",
        whisper_compute_type="int8",
        primary_language="zh",
    )

    # 测试转录器初始化
    transcriber = RealtimeTranscriber(config)

    print("\n🔄 开始模型初始化测试...")
    print("=" * 60)

    success = transcriber.initialize()

    if success:
        print("\n✅ 模型加载成功！")

        # 检查使用的是哪种模型
        if (
            hasattr(transcriber, "_using_original_whisper")
            and transcriber._using_original_whisper
        ):
            print("📝 使用原版 Whisper 模型")
        else:
            print("⚡ 使用 faster-whisper 模型")

        # 显示模型信息
        if transcriber.model:
            print(f"🔧 模型对象类型: {type(transcriber.model)}")

        print(f"⚙️ 配置信息:")
        print(f"   - 模型大小: {config.whisper_model}")
        print(f"   - 设备: {config.whisper_device}")
        print(f"   - 计算类型: {config.whisper_compute_type}")
        print(f"   - 主要语言: {config.primary_language}")

    else:
        print("\n❌ 模型加载失败")
        print("💡 可能的解决方案:")
        print("   1. 检查网络连接")
        print("   2. 安装原版 Whisper: pip install openai-whisper")
        print("   3. 或更新 faster-whisper: pip install --upgrade faster-whisper")


def test_different_model_sizes():
    """测试不同大小的模型"""
    print("\n\n🧪 测试不同模型大小...")

    models_to_test = ["tiny", "base", "small"]

    for model_size in models_to_test:
        print(f"\n📦 测试模型: {model_size}")
        print("-" * 40)

        config = MeetingConfig(
            whisper_model=model_size, whisper_device="cpu", whisper_compute_type="int8"
        )

        transcriber = RealtimeTranscriber(config)
        success = transcriber.initialize()

        if success:
            model_type = (
                "原版 Whisper"
                if getattr(transcriber, "_using_original_whisper", False)
                else "faster-whisper"
            )
            print(f"✅ {model_size} 模型加载成功 - {model_type}")
        else:
            print(f"❌ {model_size} 模型加载失败")


def test_network_availability():
    """测试网络可用性"""
    print("\n\n🌐 测试网络连接...")

    try:
        import requests

        response = requests.get("https://huggingface.co", timeout=5)
        if response.status_code == 200:
            print("✅ Hugging Face 网络连接正常")
        else:
            print(f"⚠️ Hugging Face 连接异常: {response.status_code}")
    except Exception as e:
        print(f"❌ 网络连接失败: {e}")
        print("💡 这可能是导致 faster-whisper 模型下载失败的原因")


if __name__ == "__main__":
    # 测试网络
    test_network_availability()

    # 测试基础模型加载
    test_whisper_model_loading()

    # 测试不同大小的模型
    test_different_model_sizes()

    print("\n🎯 测试完成！")
    print("\n📋 总结:")
    print("   - 如果 faster-whisper 网络下载失败，系统会自动回退到原版 Whisper")
    print("   - 如果本地有缓存，会优先使用本地缓存")
    print("   - 系统会尝试多种模型名称格式")
    print("   - 建议在网络良好时先下载模型到本地缓存")
