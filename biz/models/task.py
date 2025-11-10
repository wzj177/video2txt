#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 任务数据模型
"""

from sqlalchemy import Column, String, Integer, Float, Text, JSON, Boolean, DateTime
from .base import BaseModel


class MediaTask(BaseModel):
    """媒体处理任务表（音频/视频）"""

    __tablename__ = "media_tasks"

    # 基本信息
    name = Column(String(500), nullable=False)  # 任务名称
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
    media_duration = Column(Float)  # 媒体时长（秒）- 统一字段，适用于音频和视频
    # 保留旧字段以兼容现有数据
    video_duration = Column(Float)  # 视频时长（秒）- 已弃用，使用media_duration
    audio_duration = Column(Float)  # 音频时长（秒）- 已弃用，使用media_duration

    def __repr__(self):
        return f"<MediaTask(id={self.id}, type={self.task_type}, status={self.status})>"


# 向后兼容别名
VideoTask = MediaTask


class TaskQueue(BaseModel):
    """任务队列表"""

    __tablename__ = "task_queue"

    # 队列信息
    queue_name = Column(String(100), nullable=False)  # 队列名称
    task_name = Column(String(200), nullable=False)  # 任务名称

    # 任务参数（JSON格式）
    task_args = Column(JSON)  # 位置参数
    task_kwargs = Column(JSON)  # 关键字参数


    # 状态信息
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, running, completed, failed
    priority = Column(Integer, default=0)  # 优先级，数字越大优先级越高

    # 执行信息
    worker_id = Column(String(100))  # 执行的Worker ID
    started_at = Column(DateTime)  # 开始执行时间
    completed_at = Column(DateTime)  # 完成时间

    # 结果和错误
    result = Column(JSON)  # 执行结果
    error_message = Column(Text)  # 错误信息
    traceback = Column(Text)  # 错误堆栈

    # 重试信息
    retry_count = Column(Integer, default=0)  # 重试次数
    max_retries = Column(Integer, default=3)  # 最大重试次数

    def __repr__(self):
        return f"<TaskQueue(id={self.id}, queue={self.queue_name}, task={self.task_name}, status={self.status})>"


class MeetingTask(BaseModel):
    """会议监控任务表"""

    __tablename__ = "meeting_tasks"

    # 基本信息
    name = Column(String(500), nullable=False)  # 任务名称
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

    # 配置信息（完整的任务配置，包括所有参数）
    config = Column(JSON)  # 处理配置（语言、引擎、说话人分离、AI分析等）

    # 会议结果 - 统一使用results字段存储所有结果数据
    results = Column(JSON)  # 处理结果（转录、总结、分析等）

    # 会议统计信息（从results中提取的快速查询字段）
    total_duration = Column(Float)  # 会议总时长（秒）
    total_words = Column(Integer)  # 总词数
    speaker_count = Column(Integer)  # 说话人数量
    transcript = Column(Text)  # 完整转录文本（用于快速搜索）

    # 兼容性字段（保留旧字段以支持现有数据）
    transcripts = Column(JSON)  # 转录记录列表（已弃用，使用results.segments）
    summary = Column(JSON)  # 会议摘要数据（已弃用，使用results.summary）
    keywords = Column(JSON)  # 关键词列表（已弃用，使用results.keywords）

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
