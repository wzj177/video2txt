#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - Celery消息队列配置
"""

import os
from pathlib import Path
from celery import Celery

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# Redis配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# 构建Redis URL
if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# 创建Celery应用
try:
    celery_app = Celery(
        "ai_video2text",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=[
            "biz.tasks.video_tasks",
        ],
    )
except Exception as e:
    print(f"Celery初始化失败: {e}")
    # 创建一个基本的Celery应用，避免导入错误
    celery_app = Celery("ai_video2text")

# Celery配置
try:
    celery_app.conf.update(
        # 任务序列化
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        # 任务路由
        task_routes={
            "biz.tasks.video_tasks.*": {"queue": "video_processing"},
        },
        # 任务结果配置
        result_expires=3600,  # 结果保存1小时
        task_track_started=True,
        # Worker配置
        worker_prefetch_multiplier=1,  # 每个worker一次只处理一个任务
        task_acks_late=True,  # 任务完成后才确认
        worker_max_tasks_per_child=50,  # 每个子进程最多处理50个任务后重启
        # 任务时间限制
        task_soft_time_limit=1800,  # 软限制30分钟
        task_time_limit=2100,  # 硬限制35分钟
        # 任务重试配置
        task_default_retry_delay=60,  # 默认重试延迟60秒
        task_max_retries=3,  # 最大重试3次
        # 监控配置
        worker_send_task_events=True,
        task_send_sent_event=True,
    )
except Exception as e:
    print(f"Celery配置失败: {e}")
    # 基本配置，避免应用崩溃
    celery_app.conf.task_serializer = "json"
    celery_app.conf.accept_content = ["json"]

# 队列配置
try:
    from kombu import Queue

    celery_app.conf.task_queues = (
        Queue("video_processing", routing_key="video_processing"),
        Queue("meeting_processing", routing_key="meeting_processing"),
        Queue("default", routing_key="default"),
    )

    # 默认队列
    celery_app.conf.task_default_queue = "default"
    celery_app.conf.task_default_exchange = "default"
    celery_app.conf.task_default_routing_key = "default"
except Exception as e:
    print(f"Celery队列配置失败: {e}")
    # 使用基本配置
    pass
