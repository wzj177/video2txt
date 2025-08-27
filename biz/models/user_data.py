#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 用户数据模型
"""

from sqlalchemy import Column, String, Integer, Float, Text, JSON, Boolean
from .base import BaseModel


class UserPreference(BaseModel):
    """用户偏好设置表"""

    __tablename__ = "user_preferences"

    # 偏好类型
    category = Column(String(50), nullable=False)  # video, meeting, audio, ui
    key = Column(String(100), nullable=False)
    value = Column(JSON)  # 偏好值（可以是字符串、数字、对象等）

    # 描述信息
    description = Column(String(500))
    is_default = Column(Boolean, default=False)

    def __repr__(self):
        return f"<UserPreference(category={self.category}, key={self.key})>"


class ProcessingHistory(BaseModel):
    """处理历史记录表"""

    __tablename__ = "processing_history"

    # 关联任务
    task_id = Column(String(36), nullable=False)
    task_type = Column(String(20), nullable=False)  # video, meeting

    # 处理信息
    engine_used = Column(String(50))  # 使用的引擎
    model_used = Column(String(100))  # 使用的模型
    language_detected = Column(String(10))  # 检测到的语言

    # 性能指标
    processing_time = Column(Float)  # 处理时间
    accuracy_score = Column(Float)  # 准确率评分（如果有的话）
    file_size_mb = Column(Float)  # 处理的文件大小

    # 用户反馈
    user_rating = Column(Integer)  # 用户评分 1-5
    user_feedback = Column(Text)  # 用户反馈文本

    # 错误信息
    error_type = Column(String(100))  # 错误类型
    error_details = Column(Text)  # 错误详情

    def __repr__(self):
        return f"<ProcessingHistory(task_id={self.task_id}, engine={self.engine_used})>"


class SystemMetrics(BaseModel):
    """系统性能指标表"""

    __tablename__ = "system_metrics"

    # 系统资源使用
    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    disk_usage = Column(Float)
    gpu_usage = Column(Float)

    # 任务统计
    active_tasks = Column(Integer, default=0)
    completed_tasks_today = Column(Integer, default=0)
    failed_tasks_today = Column(Integer, default=0)

    # 性能指标
    avg_processing_time = Column(Float)  # 平均处理时间
    total_processed_mb = Column(Float)  # 今日处理的总数据量

    # 错误统计
    error_count_today = Column(Integer, default=0)
    most_common_error = Column(String(200))

    def __repr__(self):
        return f"<SystemMetrics(cpu={self.cpu_usage}, memory={self.memory_usage})>"
