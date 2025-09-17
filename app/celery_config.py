#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - Celery消息队列配置
"""

import os
import logging
from pathlib import Path
from celery import Celery
from celery.utils.log import get_task_logger

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


# 配置Celery日志
def setup_celery_logging():
    """配置Celery专用日志"""
    try:
        from datetime import datetime
        from logging.handlers import TimedRotatingFileHandler

        # 创建日志目录
        now = datetime.now()
        log_dir = (
            PROJECT_ROOT
            / "logs"
            / f"{now.strftime('%Y年')}"
            / f"{now.strftime('%m月')}"
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        celery_log_file = log_dir / f"celery_{now.strftime('%d日')}.log"

        # 配置Celery任务日志
        task_logger = get_task_logger(__name__)
        task_logger.setLevel(logging.INFO)

        # 创建文件处理器
        file_handler = TimedRotatingFileHandler(
            celery_log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - CELERY - %(levelname)s - %(message)s")
        )

        # 添加处理器
        task_logger.addHandler(file_handler)
        task_logger.addHandler(console_handler)

        # 配置根日志记录器
        celery_logger = logging.getLogger("celery")
        celery_logger.setLevel(logging.INFO)
        celery_logger.addHandler(file_handler)
        celery_logger.addHandler(console_handler)

        print(f"✅ Celery日志配置完成: {celery_log_file}")
        return task_logger

    except Exception as e:
        print(f"❌ Celery日志配置失败: {e}")
        return get_task_logger(__name__)


# 设置Celery日志
celery_task_logger = setup_celery_logging()

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
        # 日志配置
        worker_log_format="%(asctime)s - CELERY-WORKER - %(levelname)s - %(message)s",
        worker_task_log_format="%(asctime)s - CELERY-TASK - %(levelname)s - %(message)s",
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
