#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音识别引擎基类
定义统一的语音识别接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseVoiceEngine(ABC):
    """语音识别引擎基类"""

    def __init__(self, config):
        self.config = config
        self.model = None
        self.initialized = False

    @abstractmethod
    def initialize(self) -> bool:
        """初始化引擎"""
        pass

    @abstractmethod
    def recognize_file(
        self, audio_path: str, language: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """识别音频文件"""
        pass

    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "engine": self.__class__.__name__,
            "initialized": self.initialized,
            "config": vars(self.config) if self.config else {},
        }

    def cleanup(self):
        """清理资源"""
        self.model = None
        self.initialized = False
