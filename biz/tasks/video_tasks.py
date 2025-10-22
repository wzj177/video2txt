#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 视频处理队列任务 - 统一版本
支持Celery和SQLite队列
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any
import logging

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 使用标准日志记录器（Celery任务会使用Celery专用日志）
logger = logging.getLogger(__name__)

from ..services.video_processor import video_processor


def sync_process_video_file(
    task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    同步方式执行视频文件处理任务 - 队列任务统一入口

    Args:
        task_id: 任务ID
        file_data: 文件数据
        config: 处理配置

    Returns:
        处理结果
    """
    try:
        logger.info(f"🚀 开始处理视频文件任务: {task_id}")

        # 运行异步处理函数
        result = _run_async_task(
            video_processor.process_file_complete(task_id, file_data, config)
        )

        logger.info(f"✅ 视频文件任务完成: {task_id}")
        return result

    except Exception as e:
        logger.error(f"视频文件任务失败: {task_id}, 错误: {e}")
        return {"success": False, "error": str(e)}


def sync_process_video_url(
    task_id: str, url: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    同步方式执行视频URL处理任务 - 队列任务统一入口

    Args:
        task_id: 任务ID
        url: 视频URL
        config: 处理配置

    Returns:
        处理结果
    """
    try:
        logger.info(f"🚀 开始处理视频URL任务: {task_id}")

        # 运行异步处理函数
        result = _run_async_task(
            video_processor.process_url_complete(task_id, url, config)
        )

        logger.info(f"✅ 视频URL任务完成: {task_id}")
        return result

    except Exception as e:
        logger.error(f"视频URL任务失败: {task_id}, 错误: {e}")
        return {"success": False, "error": str(e)}


def _run_async_task(coro):
    """
    在同步环境中运行异步任务

    Args:
        coro: 异步协程对象

    Returns:
        协程执行结果
    """
    try:
        # 尝试获取当前事件循环
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，创建新的事件循环
            import threading
            import concurrent.futures

            def run_in_new_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_new_loop)
                return future.result(timeout=3600)  # 1小时超时
        else:
            # 直接运行异步任务
            return loop.run_until_complete(coro)

    except RuntimeError:
        # 没有事件循环，创建新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# =============================================================================
# Celery支持已移除，专注使用SQLite队列系统
# =============================================================================
logger.info("ℹ️ 使用SQLite队列系统，无需Celery")


# =============================================================================
# SQLite队列任务装饰器版本（如果SQLite队列可用）
# =============================================================================
try:
    from ..queue.task_manager import task

    @task("process_video_file", queue_name="video_processing")
    def process_video_file_sqlite_task(
        task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
    ):
        """SQLite队列版本的视频文件处理任务"""
        return sync_process_video_file(task_id, file_data, config)

    @task("process_video_url", queue_name="video_processing")
    def process_video_url_sqlite_task(task_id: str, url: str, config: Dict[str, Any]):
        """SQLite队列版本的视频URL处理任务"""
        return sync_process_video_url(task_id, url, config)

    logger.info("✅ SQLite队列任务已注册")

except ImportError:
    logger.info("ℹ️ SQLite队列不可用，跳过SQLite队列任务注册")
