#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试闪卡生成功能（模拟）
"""

import os
import sys
from pathlib import Path

# 导入需要的函数
sys.path.append(".")
from video2txt import generate_flashcards, export_anki_format


def mock_openai_client():
    """模拟OpenAI客户端"""

    class MockClient:
        def __init__(self):
            pass

        class Chat:
            class Completions:
                def create(self, **kwargs):
                    # 模拟返回闪卡内容
                    class MockResponse:
                        def __init__(self):
                            self.choices = [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Message",
                                            (),
                                            {
                                                "content": """## 闪卡 01 - 概念卡
**正面**: 什么是白宫记者晚宴？
**背面**: 美国白宫每年举办的传统活动，汇聚全美各大媒体名流和政府官员的重要社交场合
**标签**: #政治 #美国 #媒体

## 闪卡 02 - 历史卡
**正面**: 2011年白宫记者晚宴有什么特别之处？
**背面**: 这一年的晚宴在希尔顿酒店举行，是一场轻松欢快有趣的传统活动
**标签**: #历史 #2011 #希尔顿酒店

## 闪卡 03 - 应用卡
**正面**: 白宫记者晚宴的社会意义是什么？
**背面**: 体现了美国民主制度的开放性，促进政府与媒体之间的良性互动
**标签**: #民主 #媒体关系 #开放"""
                                            },
                                        )()
                                    },
                                )()
                            ]

                    return MockResponse()

            def __init__(self):
                self.completions = self.Completions()

        def __init__(self):
            self.chat = self.Chat()

    return MockClient()


def test_flashcard_generation():
    """测试闪卡生成流程"""
    print("🧪 开始测试闪卡生成...")

    # 模拟的视频内容（基于SRT文件内容）
    mock_content = """
    2011年4月30日华盛顿特区，一年一度的白宫记者晚宴在希尔顿酒店如期召开。
    全美上下的各大媒体名流都应邀参加，这是一场轻松欢快有趣的活动。
    按照惯例，这个活动体现了美国政府与媒体之间的良好关系。
    """

    # 模拟思维导图内容
    mock_mindmap = """
    # 白宫记者晚宴
    ## 基本信息
    - 时间：2011年4月30日
    - 地点：华盛顿特区希尔顿酒店
    ## 参与者
    - 媒体名流
    - 政府官员
    ## 意义
    - 传统活动
    - 政媒关系
    """

    # 创建mock客户端
    mock_client = mock_openai_client()

    try:
        # 测试生成闪卡
        print("📝 生成闪卡内容...")
        flashcards = generate_flashcards(
            mock_client, mock_content, "gpt-4o-2024-11-20", mock_mindmap
        )

        print(f"✅ 闪卡生成成功，长度: {len(flashcards)} 字符")
        print("📄 闪卡内容预览:")
        print("=" * 50)
        print(flashcards[:300] + "...")
        print("=" * 50)

        # 测试导出Anki格式
        print("\n📱 测试Anki格式导出...")
        test_anki_file = "test_generated_anki.txt"
        success = export_anki_format(flashcards, test_anki_file)

        if success:
            print("✅ Anki格式导出成功")
            if os.path.exists(test_anki_file):
                with open(test_anki_file, "r", encoding="utf-8") as f:
                    anki_content = f.read()
                print(f"📄 Anki内容:\n{anki_content}")
                os.remove(test_anki_file)
        else:
            print("❌ Anki格式导出失败")

        # 测试保存闪卡文件
        print("\n💾 测试保存闪卡文件...")
        test_flashcard_file = "test_flashcards.md"
        Path(test_flashcard_file).write_text(flashcards, encoding="utf-8")
        print(f"✅ 闪卡已保存到: {test_flashcard_file}")

        # 验证文件不为空
        if os.path.getsize(test_flashcard_file) > 0:
            print(f"✅ 文件大小: {os.path.getsize(test_flashcard_file)} 字节")
        else:
            print("❌ 文件为空")

        # 清理测试文件
        os.remove(test_flashcard_file)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_flashcard_generation()
    print("\n🎯 测试完成！")
