#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 异步任务模块
"""

# 导入所有任务模块以确保任务处理器被正确注册
from . import video_tasks, meeting_tasks

__all__ = ["video_tasks", "meeting_tasks"]