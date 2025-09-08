#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI聊天客户端 - 统一封装多种大模型
支持OpenAI、阿里通义、智谱等，统一使用OpenAI接口
支持Chat和SSE流式响应
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
from dataclasses import dataclass
from pathlib import Path

# OpenAI库
from openai import OpenAI, AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置 - 对应settings.json结构"""

    api_key: str
    base_url: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60


class AIChatClient:
    """AI聊天客户端 - 统一接口"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = self._create_client()

    def _create_client(self) -> Union[OpenAI, AsyncOpenAI]:
        """创建OpenAI客户端"""
        client_kwargs = {
            "api_key": self.config.api_key,
            "base_url": self.config.base_url,
            "timeout": self.config.timeout,
        }

        # 根据是否异步创建客户端
        if asyncio.iscoroutinefunction(self._chat_completion):
            return AsyncOpenAI(**client_kwargs)
        else:
            return OpenAI(**client_kwargs)

    async def chat_completion(
        self, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        聊天完成 - 统一接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            stream: 是否流式响应
            **kwargs: 其他参数

        Returns:
            同步模式返回字符串，流式模式返回生成器
        """
        try:
            # 合并配置参数
            request_params = {
                "model": self.config.model,
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "stream": stream,
            }

            if stream:
                return await self._stream_chat_completion(request_params)
            else:
                return await self._chat_completion(request_params)

        except Exception as e:
            logger.error(f"聊天完成失败: {e}")
            raise

    async def _chat_completion(self, params: Dict[str, Any]) -> str:
        """同步聊天完成"""
        try:
            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"同步聊天完成失败: {e}")
            raise

    async def _stream_chat_completion(
        self, params: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """流式聊天完成 - SSE"""
        try:
            async for chunk in self.client.chat.completions.create(**params):
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"流式聊天完成失败: {e}")
            raise

    async def generate_content(
        self, prompt: str, system_prompt: str = "", stream: bool = False, **kwargs
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        生成内容 - 简化接口

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            stream: 是否流式
            **kwargs: 其他参数

        Returns:
            内容字符串或流式生成器
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat_completion(messages, stream=stream, **kwargs)


class AIClientFactory:
    """AI客户端工厂"""

    @staticmethod
    def create_client_from_settings(
        provider: str, settings: Dict[str, Any]
    ) -> AIChatClient:
        """从settings.json创建AI客户端"""
        provider_config = settings.get(provider, {})

        config = ModelConfig(
            api_key=provider_config.get("api_key", ""),
            base_url=provider_config.get("base_url", ""),
            model=provider_config.get("model", ""),
            max_tokens=provider_config.get("max_tokens", 4096),
            temperature=provider_config.get("temperature", 0.7),
            timeout=provider_config.get("timeout", 60),
        )

        return AIChatClient(config)

    @staticmethod
    def create_openai_client(settings: Dict[str, Any]) -> AIChatClient:
        """创建OpenAI客户端"""
        return AIClientFactory.create_client_from_settings("openai", settings)

    @staticmethod
    def create_ollama_client(settings: Dict[str, Any]) -> AIChatClient:
        """创建Ollama客户端"""
        return AIClientFactory.create_client_from_settings("ollama", settings)


# 便捷函数
def create_ai_client(provider: str, settings: Dict[str, Any]) -> AIChatClient:
    """创建AI客户端的便捷函数"""
    return AIClientFactory.create_client_from_settings(provider, settings)


async def generate_content(
    prompt: str,
    provider: str,
    settings: Dict[str, Any],
    system_prompt: str = "",
    stream: bool = False,
    **kwargs,
) -> Union[str, AsyncGenerator[str, None]]:
    """生成内容的便捷函数"""
    client = create_ai_client(provider, settings)
    return await client.generate_content(prompt, system_prompt, stream, **kwargs)


# 使用示例
if __name__ == "__main__":

    async def test_ai_client():
        # 模拟settings.json配置
        settings = {
            "openai": {
                "api_key": "your_openai_key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "max_tokens": 2000,
            },
            "ollama": {
                "api_key": "",  # Ollama通常不需要API key
                "base_url": "http://localhost:11434",
                "model": "qwen3:1.7b",
                "max_tokens": 4096,
            },
        }

        # 创建OpenAI客户端
        openai_client = create_ai_client("openai", settings)
        response = await openai_client.generate_content("你好，请介绍一下自己")
        print(f"OpenAI响应: {response}")

        # 创建Ollama客户端
        ollama_client = create_ai_client("ollama", settings)
        response = await ollama_client.generate_content("写一个Python函数")
        print(f"Ollama响应: {response}")

    # 运行测试
    asyncio.run(test_ai_client())
