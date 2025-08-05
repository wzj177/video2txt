#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时会议记录系统 - 安装和测试脚本
"""

import os
import sys
import subprocess
import importlib.util


def check_dependency(package_name, import_name=None):
    """检查依赖包是否已安装"""
    if import_name is None:
        import_name = package_name

    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def install_dependencies():
    """安装必要依赖"""
    print("🔧 检查和安装依赖包...")

    # 核心依赖
    core_deps = [
        ("numpy", "numpy"),
        ("torch", "torch"),
        ("transformers", "transformers"),
        ("pyaudio", "pyaudio"),
    ]

    # 可选依赖
    optional_deps = [
        ("faster-whisper", "faster_whisper"),
        ("pyannote.audio", "pyannote.audio"),
        ("ollama", "ollama"),
    ]

    missing_core = []
    missing_optional = []

    # 检查核心依赖
    for pkg, imp in core_deps:
        if not check_dependency(imp):
            missing_core.append(pkg)
            print(f"❌ 缺少核心依赖: {pkg}")
        else:
            print(f"✅ 核心依赖已安装: {pkg}")

    # 检查可选依赖
    for pkg, imp in optional_deps:
        if not check_dependency(imp):
            missing_optional.append(pkg)
            print(f"⚠️ 缺少可选依赖: {pkg}")
        else:
            print(f"✅ 可选依赖已安装: {pkg}")

    # 安装缺少的依赖
    if missing_core:
        print(f"\n🔄 安装核心依赖: {', '.join(missing_core)}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install"] + missing_core
            )
            print("✅ 核心依赖安装完成")
        except subprocess.CalledProcessError:
            print("❌ 核心依赖安装失败")
            return False

    if missing_optional:
        print(f"\n🔄 安装可选依赖: {', '.join(missing_optional)}")
        try:
            # 对于一些特殊的包，提供安装提示
            for pkg in missing_optional:
                if pkg == "pyaudio":
                    print("💡 pyaudio安装提示:")
                    print("   - Windows: pip install pyaudio")
                    print("   - macOS: brew install portaudio && pip install pyaudio")
                    print(
                        "   - Linux: sudo apt-get install portaudio19-dev && pip install pyaudio"
                    )
                elif pkg == "faster-whisper":
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "faster-whisper"]
                    )
                elif pkg == "pyannote.audio":
                    print("💡 pyannote.audio需要额外配置:")
                    print("   pip install pyannote.audio")
                    print("   可能需要HuggingFace账号和token")
                elif pkg == "ollama":
                    print("💡 Ollama安装提示:")
                    print("   1. 下载并安装Ollama: https://ollama.ai/")
                    print("   2. 运行: ollama pull qwen:1.8b")
                    print("   3. pip install ollama")

            print("✅ 可选依赖安装完成（部分可能需要手动安装）")
        except subprocess.CalledProcessError:
            print("⚠️ 部分可选依赖安装失败，但不影响基础功能")

    return True


def test_basic_functionality():
    """测试基本功能"""
    print("\n🧪 测试基本功能...")

    try:
        # 测试音频捕获
        print("🎤 测试音频捕获...")
        if check_dependency("pyaudio"):
            import pyaudio

            audio = pyaudio.PyAudio()
            devices = audio.get_device_count()
            print(f"   检测到 {devices} 个音频设备")
            audio.terminate()
            print("   ✅ 音频捕获功能正常")
        else:
            print("   ⚠️ pyaudio未安装，音频捕获不可用")

        # 测试语音识别
        print("🗣️ 测试语音识别...")
        if check_dependency("faster_whisper"):
            from faster_whisper import WhisperModel

            print("   ✅ faster-whisper可用")
        elif check_dependency("whisper"):
            import whisper

            print("   ✅ openai-whisper可用")
        else:
            print("   ❌ 语音识别模型不可用")
            return False

        # 测试翻译功能
        print("🌐 测试翻译功能...")
        if check_dependency("transformers"):
            print("   ✅ transformers可用，支持翻译")
        else:
            print("   ⚠️ transformers未安装，翻译不可用")

        # 测试说话人分离
        print("👥 测试说话人分离...")
        if check_dependency("pyannote.audio"):
            print("   ✅ pyannote.audio可用")
        else:
            print("   ⚠️ pyannote.audio未安装，说话人分离不可用")

        # 测试Ollama
        print("🤖 测试Ollama连接...")
        try:
            import requests

            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            if response.status_code == 200:
                models = response.json().get("models", [])
                print(f"   ✅ Ollama服务运行中，可用模型: {len(models)}个")
            else:
                print("   ⚠️ Ollama服务未响应")
        except:
            print("   ⚠️ Ollama服务未运行")

        print("\n✅ 基本功能测试完成")
        return True

    except Exception as e:
        print(f"❌ 功能测试失败: {e}")
        return False


def create_sample_config():
    """创建示例配置文件"""
    config_content = """# 实时会议记录系统配置

# 音频设置
sample_rate: 16000
chunk_size: 1024
channels: 1

# 模型设置
whisper_model: "base"  # tiny, base, small, medium, large
whisper_device: "cpu"
whisper_compute_type: "int8"

# 语言设置
primary_language: "zh"  # zh, en, ja, ko, auto
target_languages:
  - "en"
  - "ja"
  - "ko"

# 输出设置
output_dir: "meeting_records"
realtime_display: true
save_audio: true

# 高级功能
enable_speaker_diarization: false  # 需要pyannote.audio
enable_translation: false  # 需要transformers
enable_summarization: false  # 需要Ollama

# Ollama设置
ollama_model: "qwen:1.8b"  # 或其他已安装的模型
ollama_url: "http://localhost:11434"
"""

    with open("meeting_config.yaml", "w", encoding="utf-8") as f:
        f.write(config_content)

    print("✅ 示例配置文件已创建: meeting_config.yaml")


def show_usage_examples():
    """显示使用示例"""
    print("\n📚 使用示例:")
    print()
    print("1. 基础实时转录:")
    print("   python realtime_meeting.py")
    print()
    print("2. 启用翻译功能:")
    print("   python realtime_meeting.py --enable-translation --languages zh,en,ja")
    print()
    print("3. 完整功能:")
    print("   python realtime_meeting.py \\")
    print("     --enable-translation \\")
    print("     --enable-speaker-diarization \\")
    print("     --languages zh,en,ja,ko \\")
    print("     --whisper-model medium")
    print()
    print("4. 分析已录制的会议:")
    print(
        "   python meeting_advanced.py meeting_records/20240115_143022/transcriptions.jsonl"
    )
    print()
    print("5. 自定义输出目录:")
    print("   python realtime_meeting.py --output-dir /path/to/your/meetings")


def main():
    """主函数"""
    print("🚀 实时会议记录系统 - 安装和测试")
    print("=" * 50)

    # 安装依赖
    if not install_dependencies():
        print("❌ 依赖安装失败")
        return

    # 测试功能
    if not test_basic_functionality():
        print("❌ 功能测试失败")
        return

    # 创建配置文件
    if not os.path.exists("meeting_config.yaml"):
        create_sample_config()

    # 显示使用示例
    show_usage_examples()

    print("\n🎉 安装和测试完成！")
    print("💡 现在可以运行: python realtime_meeting.py")


if __name__ == "__main__":
    main()
