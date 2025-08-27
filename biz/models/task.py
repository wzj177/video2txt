#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 任务数据模型
"""

from sqlalchemy import Column, String, Integer, Float, Text, JSON, Boolean
from .base import BaseModel


class VideoTask(BaseModel):
    """视频处理任务表"""

    __tablename__ = "video_tasks"

    # 基本信息
    task_type = Column(String(20), nullable=False, default="video")  # video, audio
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    current_step = Column(String(200), default="")

    # 输入信息
    input_type = Column(String(20), nullable=False)  # file, url, local_file
    input_filename = Column(String(500))
    input_size = Column(Integer)
    input_path = Column(Text)
    input_url = Column(Text)

    # 配置信息
    config = Column(JSON)  # 处理配置（语言、模型、输出类型等）

    # 结果信息
    results = Column(JSON)  # 处理结果（转录文本、摘要、文件路径等）
    error_message = Column(Text)

    # 性能指标
    processing_time = Column(Float)  # 处理耗时（秒）
    file_size_mb = Column(Float)  # 文件大小（MB）

    def __repr__(self):
        return f"<VideoTask(id={self.id}, type={self.task_type}, status={self.status})>"


class MeetingTask(BaseModel):
    """会议监控任务表"""

    __tablename__ = "meeting_tasks"

    # 基本信息
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, running, completed, failed, stopped
    progress = Column(Integer, default=0)  # 0-100
    current_step = Column(String(200), default="")

    # 会议配置
    meeting_app = Column(String(50), default="auto")  # auto, zoom, teams, etc.
    source_language = Column(String(10), default="auto")
    target_language = Column(String(10), default="none")
    engine = Column(String(50), default="sensevoice")
    capture_mode = Column(String(20), default="system")  # system, microphone
    realtime = Column(Boolean, default=True)

    # 会议结果
    total_duration = Column(Float)  # 会议总时长（秒）
    total_words = Column(Integer)  # 总词数
    speaker_count = Column(Integer)  # 说话人数量
    transcripts = Column(JSON)  # 转录记录列表
    summary = Column(JSON)  # 会议摘要数据
    keywords = Column(JSON)  # 关键词列表

    # 音频质量指标
    avg_volume = Column(Float)  # 平均音量
    max_volume = Column(Float)  # 最大音量
    silence_ratio = Column(Float)  # 静音比例

    def __repr__(self):
        return f"<MeetingTask(id={self.id}, status={self.status}, duration={self.total_duration})>"


class TaskFile(BaseModel):
    """任务文件关联表"""

    __tablename__ = "task_files"

    task_id = Column(String(36), nullable=False)
    task_type = Column(String(20), nullable=False)  # video, meeting

    file_type = Column(
        String(50), nullable=False
    )  # transcript, summary, subtitle, audio, etc.
    file_name = Column(String(500), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))

    # 文件元数据
    file_metadata = Column(JSON)  # 额外的文件信息

    def __repr__(self):
        return f"<TaskFile(task_id={self.task_id}, type={self.file_type}, name={self.file_name})>"
