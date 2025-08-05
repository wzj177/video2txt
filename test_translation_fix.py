#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试翻译模块修复
"""

import sys
from pathlib import Path

# 导入需要的模块
sys.path.append(".")
from realtime_meeting import MultiLanguageTranslator, MeetingConfig


def test_translation_system():
    """测试翻译系统的各种回退机制"""
    print("🧪 开始测试翻译系统修复...")

    # 创建配置（启用翻译）
    config = MeetingConfig(enable_translation=True, target_languages=["en", "ja", "ko"])

    # 测试翻译器初始化
    translator = MultiLanguageTranslator(config)

    print("\n🔄 开始翻译系统初始化测试...")
    print("=" * 60)

    success = translator.initialize()

    if success:
        print("\n✅ 翻译系统初始化成功！")

        # 检查使用的翻译系统类型
        if translator.smart_translator:
            print("🚀 使用智能翻译系统")
            if translator.smart_translator.fallback_mode:
                print("⚠️ 运行在回退模式")
            else:
                print("✅ 运行在完整模式")
        elif hasattr(translator, "translators") and translator.translators:
            print(f"📚 使用原始翻译器 ({len(translator.translators)} 个模型)")
        else:
            print("⚠️ 仅基础翻译功能可用")

        # 测试翻译功能
        print("\n🔤 测试翻译功能:")
        test_texts = [
            ("你好", "zh", "en"),
            ("会议开始了", "zh", "en"),
            ("thank you", "en", "zh"),
            ("hello", "en", "zh"),
        ]

        for text, src_lang, tgt_lang in test_texts:
            result = translator.translate_text(text, src_lang, tgt_lang)
            status = "✅" if result and result != text else "⚠️"
            print(f"   {status} {text} ({src_lang}→{tgt_lang}) → {result}")

    else:
        print("\n❌ 翻译系统初始化失败")


def test_simple_translator():
    """测试简单翻译器"""
    print("\n\n🧪 测试简单翻译器...")

    try:
        from translation_loader import SimpleTranslator

        translator = SimpleTranslator()

        test_cases = [
            ("你好", "zh", "en"),
            ("谢谢", "zh", "en"),
            ("会议", "zh", "en"),
            ("hello", "en", "zh"),
            ("thank you", "en", "zh"),
            ("こんにちは", "ja", "zh"),
            ("ありがとう", "ja", "zh"),
            ("안녕하세요", "ko", "zh"),
        ]

        print("📚 简单翻译测试结果:")
        for text, src, tgt in test_cases:
            result = translator.translate(text, src, tgt)
            print(f"   {text} ({src}→{tgt}) → {result}")

    except ImportError as e:
        print(f"⚠️ 简单翻译器导入失败: {e}")


def test_disabled_translation():
    """测试禁用翻译的情况"""
    print("\n\n🧪 测试禁用翻译...")

    config = MeetingConfig(
        enable_translation=False, target_languages=["en"]  # 禁用翻译
    )

    translator = MultiLanguageTranslator(config)
    success = translator.initialize()

    if success:
        print("✅ 禁用翻译模式初始化成功")
        result = translator.translate_text("你好", "zh", "en")
        if result is None:
            print("✅ 正确返回 None（翻译已禁用）")
        else:
            print("⚠️ 意外返回翻译结果")
    else:
        print("❌ 禁用翻译模式初始化失败")


def test_network_timeout():
    """测试网络超时情况"""
    print("\n\n🧪 测试网络超时处理...")

    try:
        from translation_loader import SmartTranslationSystem

        # 使用很短的超时时间来模拟网络问题
        system = SmartTranslationSystem(["en"], timeout_seconds=1)
        success = system.initialize()

        if success:
            print("✅ 短超时翻译系统初始化成功（使用了回退机制）")
            if system.fallback_mode:
                print("✅ 正确启用了回退模式")
            else:
                print("⚠️ 未启用回退模式（可能模型已缓存）")
        else:
            print("❌ 短超时翻译系统初始化失败")

    except Exception as e:
        print(f"⚠️ 网络超时测试异常: {e}")


if __name__ == "__main__":
    # 测试禁用翻译
    test_disabled_translation()

    # 测试简单翻译器
    test_simple_translator()

    # 测试网络超时处理
    test_network_timeout()

    # 测试完整翻译系统
    test_translation_system()

    print("\n🎯 翻译系统测试完成！")
    print("\n📋 总结:")
    print("   - 翻译系统现在有多层回退机制")
    print("   - 网络问题不会长时间卡住")
    print("   - 提供基础的规则翻译作为备用")
    print("   - 翻译功能失败不会阻止整个系统运行")
