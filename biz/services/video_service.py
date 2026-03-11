#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 视频/音频处理服务 - 简化版本
"""

import os
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
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
                # 创建带错误处理的异步任务
                task = asyncio.create_task(
                    self._process_file_with_error_handling(task_id, file_data, config)
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
                # 创建带错误处理的异步任务
                task = asyncio.create_task(
                    self._process_url_with_error_handling(task_id, url, config)
                )
                return {"task_id": task_id, "status": "created"}

        except Exception as e:
            return {"error": str(e)}

    async def _process_file_with_error_handling(
        self, task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
    ):
        """带错误处理的文件处理异步任务"""
        try:
            logger.info(f"🚀 开始异步处理文件任务: {task_id}")
            result = await video_processor.process_file_complete(
                task_id, file_data, config
            )

            if result.get("success"):
                logger.info(f"✅ 文件任务处理完成: {task_id}")
            else:
                logger.error(
                    f"文件任务处理失败: {task_id}, 错误: {result.get('error')}"
                )

        except Exception as e:
            logger.error(f"异步文件任务执行异常: {task_id}, 错误: {e}")
            # 更新任务状态为失败
            try:
                await task_service.update_task(
                    "av",
                    task_id,
                    {
                        "status": "failed",
                        "current_step": f"异步处理失败: {str(e)}",
                        "error": str(e),
                        "failed_at": datetime.now().isoformat(),
                    },
                )
            except Exception as update_error:
                logger.error(f"更新任务状态失败: {update_error}")

    async def _process_url_with_error_handling(
        self, task_id: str, url: str, config: Dict[str, Any]
    ):
        """带错误处理的URL处理异步任务"""
        try:
            logger.info(f"🚀 开始异步处理URL任务: {task_id}")
            result = await video_processor.process_url_complete(task_id, url, config)

            if result.get("success"):
                logger.info(f"✅ URL任务处理完成: {task_id}")
            else:
                logger.error(
                    f"URL任务处理失败: {task_id}, 错误: {result.get('error')}"
                )

        except Exception as e:
            logger.error(f"异步URL任务执行异常: {task_id}, 错误: {e}")
            # 更新任务状态为失败
            try:
                await task_service.update_task(
                    "av",
                    task_id,
                    {
                        "status": "failed",
                        "current_step": f"异步处理失败: {str(e)}",
                        "error": str(e),
                        "failed_at": datetime.now().isoformat(),
                    },
                )
            except Exception as update_error:
                logger.error(f"更新任务状态失败: {update_error}")

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
        # 尝试SQLite队列
        sqlite_result = await self._try_sqlite_processing(task_id, task_name, args)
        if sqlite_result:
            return sqlite_result

        # 都不可用
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

    async def generate_ai_content(
        self,
        output_type: str,
        transcript: str = "",
        video_path: str = "",
        audio_path: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """生成AI内容 - 支持content_role参数"""
        try:
            from .ai_content_generator import create_ai_factory
            import json

            # 加载settings.json
            settings_path = (
                Path(__file__).parent.parent.parent / "config" / "settings.json"
            )
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            else:
                settings = {}

            # 创建AI工厂
            factory = await create_ai_factory(settings)

            # 传递内容角色（不启用智能识别）
            kwargs["content_role"] = kwargs.get("content_role") or "general"

            # 调用AI工厂生成内容
            result = await factory.generate(
                output_type=output_type,
                transcript=transcript,
                video_path=video_path,
                audio_path=audio_path,
                **kwargs,
            )

            return result

        except Exception as e:
            logger.error(f"生成AI内容失败: {e}")
            return {"error": str(e), "success": False}


# 全局视频服务实例
video_service = VideoService()
