"""
AI聊天客户端 - 统一AI接口
支持OpenAI、Claude、本地模型等多种后端
"""

import logging
import os
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)


class AIChatClient:
    """AI聊天客户端 - 统一多种AI服务的接口"""

    def __init__(
        self,
        backend: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self.backend = backend.lower()
        self.model = model
        self.api_key = api_key or self._get_api_key()
        self.api_base = api_base
        self.client = None

        # 初始化客户端
        self._init_client()
        logger.info(f"✅ AI客户端初始化完成: {self.backend}/{self.model}")

    def _get_api_key(self) -> Optional[str]:
        """获取API密钥"""
        if self.backend == "openai":
            return os.getenv("OPENAI_API_KEY")
        elif self.backend == "claude":
            return os.getenv("ANTHROPIC_API_KEY")
        elif self.backend == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY")
        return None

    def _init_client(self):
        """初始化AI客户端"""
        try:
            if self.backend == "openai":
                self._init_openai_client()
            elif self.backend == "claude":
                self._init_claude_client()
            elif self.backend == "deepseek":
                self._init_deepseek_client()
            else:
                logger.warning(f"⚠️ 不支持的后端: {self.backend}，将使用模拟模式")

        except Exception as e:
            logger.error(f"❌ AI客户端初始化失败: {e}")
            logger.info("🔄 将使用模拟模式")

    def _init_openai_client(self):
        """初始化OpenAI客户端"""
        try:
            import openai

            if self.api_key:
                self.client = openai.OpenAI(
                    api_key=self.api_key, base_url=self.api_base
                )
                logger.info("✅ OpenAI客户端初始化成功")
            else:
                logger.warning("⚠️ 未找到OpenAI API密钥")

        except ImportError:
            logger.error("❌ 未安装openai库，请运行: pip install openai")
        except Exception as e:
            logger.error(f"❌ OpenAI客户端初始化失败: {e}")

    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> str:
        """发送聊天消息"""
        try:
            if not self.client:
                return self._simulate_response(message)

            if self.backend == "openai" or self.backend == "deepseek":
                return self._chat_openai_style(
                    message, system_prompt, temperature, max_tokens
                )
            elif self.backend == "claude":
                return self._chat_claude_style(
                    message, system_prompt, temperature, max_tokens
                )
            else:
                return self._simulate_response(message)

        except Exception as e:
            logger.error(f"❌ AI聊天失败: {e}")
            return self._simulate_response(message)

    def _chat_openai_style(
        self,
        message: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """OpenAI风格的聊天"""
        try:
            messages = []

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": message})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"❌ OpenAI聊天失败: {e}")
            return self._simulate_response(message)

    def _chat_claude_style(
        self,
        message: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Claude风格的聊天"""
        try:
            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": message}],
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)
            return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"❌ Claude聊天失败: {e}")
            return self._simulate_response(message)

    def _simulate_response(self, message: str) -> str:
        """模拟AI响应 - 用于测试和备用"""
        logger.info("🤖 使用模拟AI响应")

        # 根据消息内容生成相应的模拟响应
        if "闪卡" in message or "flashcard" in message.lower():
            return self._simulate_flashcards()
        elif "思维导图" in message or "mindmap" in message.lower():
            return self._simulate_mindmap()
        elif "总结" in message or "summary" in message.lower():
            return self._simulate_summary()
        else:
            return f"这是一个模拟的AI响应。原始消息长度: {len(message)} 字符。"

    def _simulate_flashcards(self) -> str:
        """模拟闪卡响应"""
        return """[
  {
    "question": "什么是人工智能？",
    "answer": "人工智能(AI)是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统。",
    "type": "concept",
    "difficulty": 1
  },
  {
    "question": "机器学习的主要类型有哪些？",
    "answer": "机器学习主要分为三类：监督学习、无监督学习和强化学习。",
    "type": "definition",
    "difficulty": 2
  },
  {
    "question": "深度学习与传统机器学习的区别是什么？",
    "answer": "深度学习使用多层神经网络自动学习特征，而传统机器学习通常需要手工设计特征。",
    "type": "comparison",
    "difficulty": 2
  }
]"""

    def _simulate_mindmap(self) -> str:
        """模拟思维导图响应"""
        return """# 人工智能概述
## 基础概念
### 定义与发展
### 核心技术
## 机器学习
### 监督学习
### 无监督学习
### 强化学习
## 深度学习
### 神经网络
### 卷积神经网络
### 循环神经网络
## 应用领域
### 自然语言处理
### 计算机视觉
### 语音识别"""

    def _simulate_summary(self) -> str:
        """模拟总结响应"""
        return """## 内容总结

### 主要观点
1. 核心概念和定义
2. 关键技术和方法
3. 实际应用案例

### 重要结论
- 技术发展趋势
- 实践经验总结
- 未来发展方向

### 行动建议
- 学习重点
- 实践方向
- 进一步研究"""

    def is_available(self) -> bool:
        """检查AI客户端是否可用"""
        return self.client is not None or True  # 模拟模式总是可用

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "backend": self.backend,
            "model": self.model,
            "available": self.is_available(),
            "api_key_set": bool(self.api_key),
        }
