#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 会议处理队列任务
支持SQLite队列
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

# 使用标准日志记录器
logger = logging.getLogger(__name__)

from ..services.meeting_service import meeting_service


def sync_process_uploaded_audio(
    task_id: str, audio_file_path: str
) -> Dict[str, Any]:
    """
    同步方式执行上传音频处理任务 - 队列任务统一入口

    Args:
        task_id: 任务ID
        audio_file_path: 音频文件路径

    Returns:
        处理结果
    """
    try:
        logger.info(f"🚀 开始处理上传音频任务: {task_id}")

        # 运行异步处理函数
        result = _run_async_task(
            meeting_service.process_uploaded_audio(task_id, audio_file_path)
        )

        logger.info(f"✅ 上传音频任务完成: {task_id}")
        return result

    except Exception as e:
        logger.error(f"上传音频任务失败: {task_id}, 错误: {e}")
        return {"success": False, "error": str(e)}


def sync_process_speaker_log(task_id: str) -> Dict[str, Any]:
    """同步方式执行说话人日志生成任务"""
    try:
        logger.info(f"🚀 开始生成说话人日志任务: {task_id}")
        result = _run_async_task(meeting_service.generate_speaker_log(task_id))
        if result:
            logger.info(f"✅ 说话人日志生成完成: {task_id}")
        else:
            logger.warning(f"⚠️ 说话人日志生成失败: {task_id}")
        return result
    except Exception as e:
        logger.error(f"说话人日志生成失败: {task_id}, 错误: {e}")
        return {"success": False, "error": str(e)}


def _run_async_task(coro):
    """
    在同步环境中运行异步任务

    Args:
        coro: 异步协程对象

    Returns:
        协程执行结果
    """
    def _run_in_loop(target_loop):
        asyncio.set_event_loop(target_loop)
        try:
            result = target_loop.run_until_complete(coro)
            pending = [t for t in asyncio.all_tasks(target_loop) if not t.done()]
            if pending:
                for task in pending:
                    task.cancel()
                target_loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            target_loop.run_until_complete(target_loop.shutdown_asyncgens())
            return result
        finally:
            target_loop.close()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_in_loop, asyncio.new_event_loop())
                return future.result(timeout=3600)
        return _run_in_loop(loop)

    except RuntimeError:
        return _run_in_loop(asyncio.new_event_loop())


# =============================================================================
# SQLite队列任务装饰器版本（如果SQLite队列可用）
# =============================================================================
try:
    from ..queue.task_manager import task

    @task("process_uploaded_audio", queue_name="meeting_processing")
    def process_uploaded_audio_sqlite_task(
        task_id: str, audio_file_path: str
    ):
        """SQLite队列版本的上传音频处理任务"""
        return sync_process_uploaded_audio(task_id, audio_file_path)

    @task("process_meeting_speaker_log", queue_name="meeting_processing")
    def process_meeting_speaker_log_task(task_id: str):
        """SQLite队列版本的说话人日志生成任务"""
        return sync_process_speaker_log(task_id)

    logger.info("✅ SQLite队列任务已注册")

except ImportError:
    logger.info("ℹ️ SQLite队列不可用，跳过SQLite队列任务注册")
