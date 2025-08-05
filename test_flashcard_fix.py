#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试闪卡生成修复效果
"""

import os
import sys
from pathlib import Path

# 导入需要的函数
sys.path.append(".")
from video2txt import export_anki_format


def test_flashcard_parsing():
    """测试闪卡解析功能"""

    # 测试不同格式的闪卡内容
    test_formats = [
        # 标准格式
        """## 闪卡 01 - 概念卡
**正面**: 什么是白宫记者晚宴？
**背面**: 美国白宫每年举办的传统活动，媒体记者和政府官员共同参与的晚宴
**标签**: #政治 #美国 #媒体

## 闪卡 02 - 应用卡  
**正面**: 白宫记者晚宴的作用是什么？
**背面**: 促进政府与媒体之间的交流，展示民主制度的开放性
**标签**: #政治 #民主 #交流""",
        # 简单问答格式
        """Q: 什么是白宫记者晚宴？
A: 美国白宫每年举办的传统活动，媒体记者和政府官员共同参与的晚宴

Q: 这个活动的意义是什么？
A: 促进政府与媒体之间的交流，展示民主制度的开放性""",
        # 中文冒号格式
        """## 闪卡 - 概念
正面：什么是白宫记者晚宴？
背面：美国白宫每年举办的传统活动
标签：#政治

## 闪卡 - 应用
正面：这个活动有什么作用？
背面：促进政府与媒体交流""",
    ]

    for i, content in enumerate(test_formats, 1):
        print(f"\n🧪 测试格式 {i}:")
        print("=" * 50)
        print(content[:100] + "...")

        # 测试解析
        test_output = f"test_anki_{i}.txt"
        success = export_anki_format(content, test_output)

        if success:
            print(f"✅ 格式 {i} 解析成功")
            # 读取生成的文件
            if os.path.exists(test_output):
                with open(test_output, "r", encoding="utf-8") as f:
                    result = f.read()
                print(f"📄 生成内容:\n{result}")
                os.remove(test_output)  # 清理测试文件
        else:
            print(f"❌ 格式 {i} 解析失败")


def test_existing_flashcard():
    """测试现有的闪卡文件"""
    flashcard_file = "outputs/374d7c0fb1f479adfb0f2923050a92e0/学习闪卡.md"

    if os.path.exists(flashcard_file):
        with open(flashcard_file, "r", encoding="utf-8") as f:
            content = f.read()

        print(f"\n📝 现有闪卡文件内容长度: {len(content)} 字符")
        if content.strip():
            print("📄 文件内容预览:")
            print(content[:500])

            # 尝试解析
            test_output = "test_existing_anki.txt"
            success = export_anki_format(content, test_output)
            print(f"解析结果: {'✅ 成功' if success else '❌ 失败'}")

            if os.path.exists(test_output):
                os.remove(test_output)
        else:
            print("⚠️ 文件为空")
    else:
        print(f"⚠️ 文件不存在: {flashcard_file}")


if __name__ == "__main__":
    print("🧪 开始测试闪卡解析修复...")

    # 测试不同格式
    test_flashcard_parsing()

    # 测试现有文件
    test_existing_flashcard()

    print("\n🎯 测试完成！")
