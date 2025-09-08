#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 视频/音频处理服务 - 简化版本
"""

import os
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

from ..services.task_service import task_service
from ..services.video_processor import video_processor


class VideoService:
    """视频/音频处理服务 - 使用统一的处理器"""

    def __init__(self):
        self.work_dir = Path(__file__).parent.parent.parent / "data" / "outputs"
        self.uploads_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    async def process_file(
        self, file_data: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理上传的文件（兼容同步和异步模式）"""
        try:
            # 创建任务
            task_data = {
                "name": config.get("name", file_data["filename"]),
                "type": self._detect_file_type(file_data["filename"]),
                "input": file_data,
                "config": config,
                "current_step": "准备处理...",
            }

            task = await task_service.create_task("av", task_data)
            task_id = task["id"]

            # 检查是否强制同步处理
            force_sync = config.get("force_sync", False)

            if force_sync:
                # 同步处理：等待任务完成
                logger.info("执行同步处理模式")
                result = await video_processor.process_file_complete(
                    task_id, file_data, config
                )

                if result.get("success"):
                    return {
                        "task_id": task_id,
                        "status": "completed",
                        "results": result.get("results", {}),
                    }
                else:
                    return {"error": result.get("error", "处理失败")}
            else:
                # 尝试使用队列处理
                queue_result = await self._try_queue_processing(
                    task_id, "process_video_file", (task_id, file_data, config)
                )

                if queue_result:
                    return queue_result

                # 队列不可用，回退到异步处理
                logger.warning("队列系统不可用，回退到异步处理")
                asyncio.create_task(
                    video_processor.process_file_complete(task_id, file_data, config)
                )
                return {"task_id": task_id, "status": "created"}

        except Exception as e:
            return {"error": str(e)}

    async def process_url(self, url: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """处理URL链接（兼容同步和异步模式）"""
        try:
            # 创建任务
            task_data = {
                "name": config.get("name", url),
                "type": "video",  # URL通常是视频
                "input": {"type": "url", "url": url},
                "config": config,
                "current_step": "准备下载...",
            }

            task = await task_service.create_task("av", task_data)
            task_id = task["id"]

            # 检查是否强制同步处理
            force_sync = config.get("force_sync", False)

            if force_sync:
                # 同步处理：等待任务完成
                logger.info("执行同步处理模式")
                result = await video_processor.process_url_complete(
                    task_id, url, config
                )

                if result.get("success"):
                    return {
                        "task_id": task_id,
                        "status": "completed",
                        "results": result.get("results", {}),
                    }
                else:
                    return {"error": result.get("error", "处理失败")}
            else:
                # 尝试使用队列处理
                queue_result = await self._try_queue_processing(
                    task_id, "process_video_url", (task_id, url, config)
                )

                if queue_result:
                    return queue_result

                # 队列不可用，回退到异步处理
                logger.warning("队列系统不可用，回退到异步处理")
                asyncio.create_task(
                    video_processor.process_url_complete(task_id, url, config)
                )
                return {"task_id": task_id, "status": "created"}

        except Exception as e:
            return {"error": str(e)}

    def _detect_file_type(self, filename: str) -> str:
        """检测文件类型"""
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
        audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}

        ext = Path(filename).suffix.lower()
        if ext in video_extensions:
            return "video"
        elif ext in audio_extensions:
            return "audio"
        else:
            return "unknown"

    async def _try_queue_processing(
        self, task_id: str, task_name: str, args: tuple
    ) -> Optional[Dict[str, Any]]:
        """尝试使用队列处理任务"""
        # 1. 尝试Celery队列
        celery_result = await self._try_celery_processing(task_id, task_name, args)
        if celery_result:
            return celery_result

        # 2. 尝试SQLite队列
        sqlite_result = await self._try_sqlite_processing(task_id, task_name, args)
        if sqlite_result:
            return sqlite_result

        # 都不可用
        return None

    async def _try_celery_processing(
        self, task_id: str, task_name: str, args: tuple
    ) -> Optional[Dict[str, Any]]:
        """尝试使用Celery处理"""
        try:
            # 检查Redis连接
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 6379))
            sock.close()

            if result != 0:
                return None  # Redis不可用

            # 导入Celery任务
            if task_name == "process_video_file":
                from ..tasks.video_tasks import process_video_file_task

                celery_task = process_video_file_task.delay(*args)
            else:
                from ..tasks.video_tasks import process_video_url_task

                celery_task = process_video_url_task.delay(*args)

            # 更新任务记录，保存Celery任务ID
            await task_service.update_task(
                "av",
                task_id,
                {
                    "celery_task_id": celery_task.id,
                    "status": "queued",
                    "current_step": "任务已提交到Celery队列...",
                },
            )

            logger.info(f"✅ 任务已提交到Celery队列: {task_id}")
            return {
                "task_id": task_id,
                "status": "queued",
                "celery_task_id": celery_task.id,
            }

        except Exception as e:
            logger.debug(f"Celery处理失败: {e}")
            return None

    async def _try_sqlite_processing(
        self, task_id: str, task_name: str, args: tuple
    ) -> Optional[Dict[str, Any]]:
        """尝试使用SQLite队列处理"""
        try:
            from ..queue.task_manager import get_task_manager

            manager = get_task_manager()

            # 确保Worker正在运行
            if not manager.running:
                manager.start_workers(worker_count=1)

            # 提交任务到SQLite队列
            queue_task_id = manager.submit_task(
                task_name=task_name, args=args, queue_name="video_processing"
            )

            # 更新任务记录
            await task_service.update_task(
                "av",
                task_id,
                {
                    "queue_task_id": queue_task_id,
                    "status": "queued",
                    "current_step": "任务已提交到SQLite队列...",
                },
            )

            logger.info(f"✅ 任务已提交到SQLite队列: {task_id}")
            return {
                "task_id": task_id,
                "status": "queued",
                "queue_task_id": queue_task_id,
            }

        except Exception as e:
            logger.debug(f"SQLite队列处理失败: {e}")
            return None


# 全局视频服务实例
video_service = VideoService()
