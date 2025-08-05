#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper 模型预下载工具
在网络良好时预先下载模型到本地缓存
"""

import os
import sys
from pathlib import Path


def download_faster_whisper_models():
    """下载 faster-whisper 模型"""
    print("🚀 开始下载 faster-whisper 模型...")

    try:
        from faster_whisper import WhisperModel

        models = ["tiny", "base", "small", "medium"]

        for model_name in models:
            print(f"\n📦 下载 {model_name} 模型...")
            try:
                # 尝试标准模型名称
                print(f"   🔄 尝试下载: {model_name}")
                model = WhisperModel(
                    model_name,
                    device="cpu",
                    compute_type="int8",
                    local_files_only=False,  # 允许下载
                )
                print(f"   ✅ {model_name} 模型下载成功")
                del model  # 释放内存

            except Exception as e1:
                print(f"   ⚠️ 标准名称失败: {e1}")

                # 尝试 OpenAI 格式
                try:
                    openai_name = f"openai/whisper-{model_name}"
                    print(f"   🔄 尝试下载: {openai_name}")
                    model = WhisperModel(
                        openai_name,
                        device="cpu",
                        compute_type="int8",
                        local_files_only=False,
                    )
                    print(f"   ✅ {openai_name} 模型下载成功")
                    del model

                except Exception as e2:
                    print(f"   ❌ {model_name} 模型下载失败: {e2}")

    except ImportError:
        print("❌ faster-whisper 未安装，请先安装: pip install faster-whisper")
        return False

    return True


def download_original_whisper_models():
    """下载原版 Whisper 模型"""
    print("\n🚀 开始下载原版 Whisper 模型...")

    try:
        import whisper

        models = ["tiny", "base", "small", "medium"]

        for model_name in models:
            print(f"\n📦 下载 {model_name} 模型...")
            try:
                model = whisper.load_model(model_name)
                print(f"   ✅ {model_name} 模型下载成功")
                del model  # 释放内存

            except Exception as e:
                print(f"   ❌ {model_name} 模型下载失败: {e}")

    except ImportError:
        print("❌ openai-whisper 未安装，请先安装: pip install openai-whisper")
        return False

    return True


def check_model_cache():
    """检查已缓存的模型"""
    print("\n🔍 检查本地模型缓存...")

    # 检查 Hugging Face 缓存
    hf_cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if hf_cache_dir.exists():
        whisper_models = list(hf_cache_dir.glob("*whisper*"))
        if whisper_models:
            print("📁 Hugging Face 缓存中的 Whisper 模型:")
            for model_dir in whisper_models:
                print(f"   ✅ {model_dir.name}")
        else:
            print("⚠️ Hugging Face 缓存中无 Whisper 模型")
    else:
        print("⚠️ 未找到 Hugging Face 缓存目录")

    # 检查 Whisper 缓存
    whisper_cache_dir = Path.home() / ".cache" / "whisper"
    if whisper_cache_dir.exists():
        whisper_files = list(whisper_cache_dir.glob("*.pt"))
        if whisper_files:
            print("\n📁 Whisper 缓存中的模型:")
            for model_file in whisper_files:
                size_mb = model_file.stat().st_size / (1024 * 1024)
                print(f"   ✅ {model_file.name} ({size_mb:.1f} MB)")
        else:
            print("\n⚠️ Whisper 缓存中无模型文件")
    else:
        print("\n⚠️ 未找到 Whisper 缓存目录")


def test_network_connection():
    """测试网络连接"""
    print("🌐 测试网络连接...")

    try:
        import requests

        # 测试 Hugging Face
        print("   🔄 测试 Hugging Face...")
        response = requests.get("https://huggingface.co", timeout=10)
        if response.status_code == 200:
            print("   ✅ Hugging Face 连接正常")
        else:
            print(f"   ⚠️ Hugging Face 响应异常: {response.status_code}")

        # 测试 GitHub（原版 Whisper）
        print("   🔄 测试 GitHub...")
        response = requests.get("https://github.com", timeout=10)
        if response.status_code == 200:
            print("   ✅ GitHub 连接正常")
        else:
            print(f"   ⚠️ GitHub 响应异常: {response.status_code}")

        return True

    except Exception as e:
        print(f"   ❌ 网络连接失败: {e}")
        return False


def show_usage_tips():
    """显示使用建议"""
    print("\n💡 模型使用建议:")
    print("   - tiny: 最快，准确度较低，适合实时场景")
    print("   - base: 平衡性能和准确度，推荐一般使用")
    print("   - small: 较好准确度，中等速度")
    print("   - medium: 高准确度，速度较慢")
    print("   - large: 最高准确度，速度最慢")

    print("\n⚙️ 网络问题解决方案:")
    print("   1. 使用国内镜像: export HF_ENDPOINT=https://hf-mirror.com")
    print("   2. 设置代理: export http_proxy=your_proxy")
    print("   3. 离线使用: 预先下载模型到本地缓存")

    print("\n🔧 安装建议:")
    print("   - 优先: pip install faster-whisper")
    print("   - 备用: pip install openai-whisper")
    print("   - 同时安装两者以获得最佳兼容性")


def main():
    """主函数"""
    print("🎯 Whisper 模型下载工具")
    print("=" * 50)

    # 检查网络
    if not test_network_connection():
        print("\n❌ 网络连接失败，无法下载模型")
        print("💡 请检查网络连接后重试")
        return

    # 检查现有缓存
    check_model_cache()

    # 询问用户选择
    print("\n🤔 选择要下载的模型类型:")
    print("   1. faster-whisper (推荐，性能更好)")
    print("   2. 原版 Whisper (兼容性更好)")
    print("   3. 两者都下载 (最佳兼容性)")
    print("   4. 仅检查缓存")

    try:
        choice = input("\n请输入选择 (1-4): ").strip()

        if choice == "1":
            download_faster_whisper_models()
        elif choice == "2":
            download_original_whisper_models()
        elif choice == "3":
            download_faster_whisper_models()
            download_original_whisper_models()
        elif choice == "4":
            print("✅ 仅检查缓存，不下载新模型")
        else:
            print("❌ 无效选择")
            return

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断下载")
        return

    # 再次检查缓存
    print("\n" + "=" * 50)
    check_model_cache()

    # 显示使用建议
    show_usage_tips()

    print("\n🎉 完成！现在可以运行实时会议系统了")


if __name__ == "__main__":
    main()
