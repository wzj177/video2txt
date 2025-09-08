#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 数据模型包
"""

from .base import Base
from .task import MediaTask, VideoTask, MeetingTask, TaskQueue
from .user_data import UserPreference, ProcessingHistory

__all__ = [
    "Base",
    "MediaTask",
    "VideoTask",  # 向后兼容别名
    "MeetingTask",
    "TaskQueue",
    "UserPreference",
    "ProcessingHistory",
]
