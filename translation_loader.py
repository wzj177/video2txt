#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译模型加载器 - 带网络检测和超时控制
"""

import os
import time
import threading
from typing import Optional, Dict, Any


class TranslationTimeoutException(Exception):
    """翻译模型加载超时异常"""

    pass


class TranslationModelLoader:
    """翻译模型加载器，支持超时和回退"""

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds
        self.model = None
        self.exception = None

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
            raise TranslationTimeoutException(
                f"翻译模型加载超时 ({self.timeout_seconds}s)"
            )

        if self.exception:
            raise self.exception

        return self.model

    def load_translation_pipeline(self, model_name: str, device: int = -1):
        """加载翻译管道"""
        try:
            from transformers import pipeline
        except ImportError:
            raise ImportError("transformers 未安装")

        # 设置环境变量减少输出和控制超时
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        os.environ["TRANSFORMERS_VERBOSITY"] = "error"
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(self.timeout_seconds)
        os.environ["REQUESTS_TIMEOUT"] = str(self.timeout_seconds)

        # 先尝试本地缓存（快速失败）
        try:
            print(f"🔄 检查本地缓存: {model_name}")
            model = pipeline(
                "translation",
                model=model_name,
                device=device,
                local_files_only=True,  # 仅本地缓存
            )
            print(f"✅ 本地模型加载成功: {model_name}")
            return model
        except Exception as e:
            print(f"⚠️ 本地缓存不可用: {e}")

            # 如果本地加载失败，尝试在线下载（受控超时）
            try:
                print(f"🔄 尝试在线下载: {model_name} (超时: {self.timeout_seconds}s)")

                # 使用受控的超时加载
                import signal

                def timeout_handler(signum, frame):
                    raise TranslationTimeoutException(
                        f"模型下载超时 ({self.timeout_seconds}s)"
                    )

                # 设置信号处理器
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.timeout_seconds)

                try:
                    model = pipeline(
                        "translation",
                        model=model_name,
                        device=device,
                        local_files_only=False,
                    )
                    signal.alarm(0)  # 取消超时
                    signal.signal(signal.SIGALRM, old_handler)  # 恢复原处理器
                    print(f"✅ 在线模型加载成功: {model_name}")
                    return model

                except Exception as e:
                    signal.alarm(0)  # 确保取消超时
                    signal.signal(signal.SIGALRM, old_handler)  # 恢复原处理器
                    raise e

            except (TranslationTimeoutException, Exception) as e:
                print(f"⚠️ 在线下载失败: {e}")
                return None


class SimpleTranslator:
    """简单的基于规则的翻译器（作为备用）"""

    def __init__(self):
        # 基础词汇映射
        self.zh_to_en = {
            "你好": "hello",
            "谢谢": "thank you",
            "再见": "goodbye",
            "是": "yes",
            "不": "no",
            "会议": "meeting",
            "开始": "start",
            "结束": "end",
            "时间": "time",
            "讨论": "discussion",
            "问题": "question",
            "回答": "answer",
            "同意": "agree",
            "反对": "disagree",
        }

        self.en_to_zh = {v: k for k, v in self.zh_to_en.items()}

        # 扩展其他语言的基础映射
        self.ja_to_zh = {
            "こんにちは": "你好",
            "ありがとう": "谢谢",
            "さようなら": "再见",
            "はい": "是",
            "いいえ": "不",
            "会議": "会议",
            "開始": "开始",
            "終了": "结束",
        }

        self.ko_to_zh = {
            "안녕하세요": "你好",
            "감사합니다": "谢谢",
            "안녕히 가세요": "再见",
            "네": "是",
            "아니요": "不",
            "회의": "会议",
            "시작": "开始",
            "끝": "结束",
        }

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """简单的基于规则的翻译"""
        text = text.strip()

        # 根据语言对选择词典
        if source_lang == "zh" and target_lang == "en":
            word_dict = self.zh_to_en
        elif source_lang == "en" and target_lang == "zh":
            word_dict = self.en_to_zh
        elif source_lang == "ja" and target_lang == "zh":
            word_dict = self.ja_to_zh
        elif source_lang == "ko" and target_lang == "zh":
            word_dict = self.ko_to_zh
        else:
            # 不支持的语言对，返回原文
            return f"[{source_lang}→{target_lang}] {text}"

        # 简单的词汇替换
        words = text.split()
        translated_words = []

        for word in words:
            # 移除标点符号进行匹配
            clean_word = word.strip(".,!?;:").lower()
            if clean_word in word_dict:
                translated_words.append(word_dict[clean_word])
            else:
                translated_words.append(word)  # 保持原词

        result = " ".join(translated_words)

        # 如果没有任何翻译，返回带标记的原文
        if result == text:
            return f"[{source_lang}→{target_lang}] {text}"

        return result


class SmartTranslationSystem:
    """智能翻译系统，集成模型翻译和规则翻译"""

    def __init__(self, target_languages: list, timeout_seconds: int = 20):
        self.target_languages = target_languages
        self.model_translators = {}
        self.simple_translator = SimpleTranslator()
        self.loader = TranslationModelLoader(timeout_seconds)
        self.fallback_mode = False

    def initialize(self) -> bool:
        """初始化翻译系统"""
        print("🚀 初始化智能翻译系统...")

        # 检查是否需要翻译
        if not self.target_languages:
            print("⚠️ 未配置目标语言，跳过翻译初始化")
            return True

        # 尝试加载机器翻译模型
        success_count = 0
        total_models = 0

        # 定义支持的翻译模型
        translation_models = {
            "zh-en": "Helsinki-NLP/opus-mt-zh-en",
            "en-zh": "Helsinki-NLP/opus-mt-en-zh",
            "ja-zh": "Helsinki-NLP/opus-mt-ja-zh",
            "ko-zh": "Helsinki-NLP/opus-mt-ko-zh",
        }

        # 根据目标语言加载对应模型
        for target_lang in self.target_languages:
            if target_lang == "en":
                # 中英互译
                for pair in ["zh-en", "en-zh"]:
                    if pair in translation_models:
                        total_models += 1
                        model = self.loader.load_translation_pipeline(
                            translation_models[pair], device=-1  # 使用CPU
                        )
                        if model:
                            self.model_translators[pair] = model
                            success_count += 1
                            print(f"✅ {pair} 翻译模型加载成功")
                        else:
                            print(f"⚠️ {pair} 翻译模型加载失败")

            elif target_lang in ["ja", "ko"]:
                # 其他语言到中文
                pair = f"{target_lang}-zh"
                if pair in translation_models:
                    total_models += 1
                    model = self.loader.load_translation_pipeline(
                        translation_models[pair], device=-1
                    )
                    if model:
                        self.model_translators[pair] = model
                        success_count += 1
                        print(f"✅ {pair} 翻译模型加载成功")
                    else:
                        print(f"⚠️ {pair} 翻译模型加载失败")

        # 判断是否需要启用回退模式
        if success_count == 0 and total_models > 0:
            print("⚠️ 所有翻译模型加载失败，启用简单翻译模式")
            self.fallback_mode = True
            return True
        elif success_count < total_models:
            print(
                f"⚠️ 部分翻译模型加载失败 ({success_count}/{total_models})，混合模式运行"
            )
            self.fallback_mode = True
            return True
        else:
            print(f"✅ 翻译模型初始化完成 ({success_count}/{total_models})")
            return True

    def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> Optional[str]:
        """翻译文本"""
        if not text.strip():
            return text

        translation_key = f"{source_lang}-{target_lang}"

        # 优先使用模型翻译
        if translation_key in self.model_translators:
            try:
                result = self.model_translators[translation_key](text)
                if result and len(result) > 0:
                    # 提取翻译文本
                    if isinstance(result, list) and len(result) > 0:
                        translated = result[0].get("translation_text", text)
                    else:
                        translated = str(result)

                    return translated
            except Exception as e:
                print(f"⚠️ 模型翻译失败: {e}")

        # 回退到简单翻译
        if self.fallback_mode or translation_key not in self.model_translators:
            return self.simple_translator.translate(text, source_lang, target_lang)

        return text  # 无法翻译，返回原文


# 测试代码
if __name__ == "__main__":
    print("🧪 测试智能翻译系统...")

    # 测试简单翻译器
    simple = SimpleTranslator()
    print("\n📚 简单翻译测试:")
    print(f"你好 → {simple.translate('你好', 'zh', 'en')}")
    print(f"thank you → {simple.translate('thank you', 'en', 'zh')}")
    print(f"こんにちは → {simple.translate('こんにちは', 'ja', 'zh')}")

    # 测试智能翻译系统
    smart_system = SmartTranslationSystem(["en", "ja"], timeout_seconds=10)
    success = smart_system.initialize()

    if success:
        print("\n🎯 智能翻译系统初始化成功")
        test_text = "你好，欢迎参加会议"
        result = smart_system.translate_text(test_text, "zh", "en")
        print(f"翻译测试: {test_text} → {result}")
    else:
        print("\n❌ 智能翻译系统初始化失败")
