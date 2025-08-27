#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI分析模块
包含内容分析、思维导图生成、闪卡生成等AI功能
"""

from .clients.ai_client_openai import OpenAIClient
from .clients.ai_client_ollama import OllamaClient

__all__ = ["OpenAIClient", "OllamaClient"]
