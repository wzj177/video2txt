#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试实时会议系统 - 跳过网络下载
"""

import sys
from pathlib import Path

# 导入需要的模块
sys.path.append(".")
from realtime_meeting import MeetingRecorder, MeetingConfig


def test_quick_initialization():
    """测试快速初始化（仅本地模型）"""
    print("🚀 快速测试实时会议系统初始化...")

    # 创建最基础的配置
    config = MeetingConfig(
        # Whisper 设置
        whisper_model="base",
        whisper_device="cpu",
        whisper_compute_type="int8",
        primary_language="zh",
        # 输出设置
        output_dir="test_meeting_records",
        realtime_display=True,
        save_audio=False,  # 跳过音频保存
        # 禁用高级功能以加快测试
        enable_speaker_diarization=False,
        enable_translation=False,  # 禁用翻译避免网络请求
        enable_summarization=False,
        enable_meeting_integration=False,
    )

    print(f"📋 测试配置:")
    print(f"   - Whisper模型: {config.whisper_model}")
    print(f"   - 设备: {config.whisper_device}")
    print(f"   - 语言: {config.primary_language}")
    print(f"   - 说话人分离: {config.enable_speaker_diarization}")
    print(f"   - 翻译功能: {config.enable_translation}")
    print(f"   - 会议集成: {config.enable_meeting_integration}")

    # 创建会议记录器
    recorder = MeetingRecorder(config)

    print("\n🔄 开始系统初始化...")
    print("=" * 60)

    # 测试初始化
    success = recorder.initialize()

    if success:
        print("\n✅ 系统初始化成功！")

        # 检查各组件状态
        print("\n📊 组件状态检查:")

        # 音频捕获
        if recorder.audio_capture:
            print("   🎤 音频捕获: 已初始化")
        else:
            print("   ⚠️ 音频捕获: 未初始化")

        # 转录器
        if recorder.transcriber and recorder.transcriber.model:
            model_type = (
                "原版 Whisper"
                if getattr(recorder.transcriber, "_using_original_whisper", False)
                else "faster-whisper"
            )
            print(f"   🗣️ 转录器: 已初始化 ({model_type})")
        else:
            print("   ❌ 转录器: 初始化失败")

        # 翻译器
        if recorder.translator:
            print("   🌐 翻译器: 已初始化")
        else:
            print("   ⚠️ 翻译器: 未启用")

        # 说话人分离
        if (
            recorder.speaker_diarizer
            and hasattr(recorder.speaker_diarizer, "pipeline")
            and recorder.speaker_diarizer.pipeline
        ):
            print("   👥 说话人分离: 已初始化")
        elif recorder.speaker_diarizer:
            print("   ⚠️ 说话人分离: 已创建但未初始化")
        else:
            print("   ⚠️ 说话人分离: 未启用")

        # 会议集成
        if recorder.meeting_integration:
            print("   📱 会议集成: 已初始化")
        else:
            print("   ⚠️ 会议集成: 未启用")

        return True

    else:
        print("\n❌ 系统初始化失败")
        return False


def test_minimal_config():
    """测试最小配置"""
    print("\n\n🎯 测试最小配置（仅转录功能）...")

    config = MeetingConfig(
        whisper_model="tiny",  # 使用最小模型
        primary_language="zh",
        enable_speaker_diarization=False,
        enable_translation=False,
        enable_summarization=False,
        enable_meeting_integration=False,
        realtime_display=False,
        save_audio=False,
    )

    recorder = MeetingRecorder(config)
    success = recorder.initialize()

    if success:
        print("✅ 最小配置初始化成功")

        # 检查基础功能
        if recorder.transcriber and recorder.transcriber.model:
            print("✅ 基础转录功能可用")
        else:
            print("❌ 基础转录功能不可用")

        return True
    else:
        print("❌ 最小配置初始化失败")
        return False


def test_component_isolation():
    """测试组件隔离（单独测试各个组件）"""
    print("\n\n🧪 测试组件隔离...")

    from realtime_meeting import (
        RealtimeTranscriber,
        MultiLanguageTranslator,
        SpeakerDiarizer,
    )

    # 测试转录器单独初始化
    print("\n🗣️ 测试转录器:")
    transcriber_config = MeetingConfig(whisper_model="base", primary_language="zh")
    transcriber = RealtimeTranscriber(transcriber_config)

    if transcriber.initialize():
        print("✅ 转录器单独初始化成功")
    else:
        print("❌ 转录器单独初始化失败")

    # 测试翻译器单独初始化（禁用状态）
    print("\n🌐 测试翻译器（禁用状态）:")
    translator_config = MeetingConfig(enable_translation=False)
    translator = MultiLanguageTranslator(translator_config)

    if translator.initialize():
        print("✅ 翻译器（禁用）初始化成功")
    else:
        print("❌ 翻译器（禁用）初始化失败")

    # 测试说话人分离器单独初始化
    print("\n👥 测试说话人分离器:")
    diarizer = SpeakerDiarizer()

    # 说话人分离器通常需要网络下载模型，这里只测试创建
    print("✅ 说话人分离器对象创建成功")


if __name__ == "__main__":
    print("🚀 快速实时会议系统测试")
    print("=" * 60)
    print("💡 此测试跳过网络下载，仅测试本地初始化")
    print("")

    try:
        # 测试完整初始化
        success1 = test_quick_initialization()

        # 测试最小配置
        success2 = test_minimal_config()

        # 测试组件隔离
        test_component_isolation()

        print("\n" + "=" * 60)
        print("🎯 测试总结:")

        if success1:
            print("✅ 完整系统初始化: 成功")
        else:
            print("❌ 完整系统初始化: 失败")

        if success2:
            print("✅ 最小配置初始化: 成功")
        else:
            print("❌ 最小配置初始化: 失败")

        print("\n💡 建议:")
        print("   - 如果转录功能失败，可能需要安装: pip install openai-whisper")
        print("   - 如果需要完整功能，可运行: python download_whisper_models.py")
        print("   - 网络良好时可启用翻译和会议集成功能")

        if success1 or success2:
            print("\n🎉 基础功能可用，可以开始使用实时会议系统！")
        else:
            print("\n⚠️ 需要解决基础组件问题后才能使用")

    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生异常: {e}")
        import traceback

        traceback.print_exc()
