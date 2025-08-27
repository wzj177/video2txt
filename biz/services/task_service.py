#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 任务管理服务
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..database.connection import get_database_manager
from ..database.repositories import (
    VideoTaskRepository,
    MeetingTaskRepository,
    TaskFileRepository,
)
from ..models.task import VideoTask, MeetingTask, TaskFile

logger = logging.getLogger(__name__)


class TaskService:
    """任务管理服务 - 管理所有类型的任务（使用SQLite存储）"""

    def __init__(self):
        self.db_manager = get_database_manager()
        self._initialized = False

    async def _ensure_initialized(self):
        """确保数据库已初始化"""
        if not self._initialized:
            await self.db_manager.create_tables()
            self._initialized = True

    async def get_tasks(
        self, task_type: str, status: str = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取任务列表"""
        await self._ensure_initialized()

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                    if status:
                        tasks = await repo.get_by_status(status, limit)
                    else:
                        tasks = await repo.get_all(limit)
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                    if status:
                        tasks = await repo.get_by_status(status, limit)
                    else:
                        tasks = await repo.get_all(limit)
                else:
                    return []

                return [task.to_dict() for task in tasks]
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    async def get_task_by_id(
        self, task_type: str, task_id: str
    ) -> Optional[Dict[str, Any]]:
        """根据ID获取任务"""
        await self._ensure_initialized()

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                else:
                    return None

                task = await repo.get_by_id(task_id)
                return task.to_dict() if task else None
        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None

    async def get_task(self, task_type: str, task_id: str) -> Optional[Dict[str, Any]]:
        """兼容方法：根据ID获取单个任务"""
        return await self.get_task_by_id(task_type, task_id)

    async def get_task_stats(self, task_type: str) -> Dict[str, int]:
        """获取任务统计信息"""
        await self._ensure_initialized()

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                    return await repo.get_stats()
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                    return await repo.get_stats()
                else:
                    return {}
        except Exception as e:
            logger.error(f"获取任务统计失败: {e}")
            return {}

    async def create_task(
        self, task_type: str, task_data: Dict[str, Any], task_id: str = None
    ) -> Dict[str, Any]:
        """创建新任务"""
        await self._ensure_initialized()

        # 如果没有指定ID，生成一个
        if not task_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_id = f"{task_type}_{timestamp}_{hash(str(task_data)) % 1000:03d}"

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                    # 从task_data提取视频任务相关字段
                    input_data = task_data.get("input", {})
                    config_data = task_data.get("config", {})

                    task = await repo.create(
                        id=task_id,
                        task_type=task_data.get("type", "video"),
                        status=task_data.get("status", "pending"),
                        progress=task_data.get("progress", 0),
                        current_step=task_data.get("current_step", ""),
                        input_type=input_data.get("type", "file"),
                        input_filename=input_data.get("filename"),
                        input_size=input_data.get("size"),
                        input_path=input_data.get("file_path"),
                        input_url=input_data.get("url"),
                        config=config_data,
                        results=task_data.get("results", {}),
                    )
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                    config_data = task_data.get("config", {})

                    task = await repo.create(
                        id=task_id,
                        status=task_data.get("status", "pending"),
                        progress=task_data.get("progress", 0),
                        current_step=task_data.get("current_step", ""),
                        meeting_app=config_data.get("meeting_app", "auto"),
                        source_language=config_data.get("source_language", "auto"),
                        target_language=config_data.get("target_language", "none"),
                        engine=config_data.get("engine", "sensevoice"),
                        capture_mode=config_data.get("capture_mode", "system"),
                        realtime=config_data.get("realtime", True),
                    )
                else:
                    raise ValueError(f"不支持的任务类型: {task_type}")

                return task.to_dict()
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            raise

    async def update_task(
        self, task_type: str, task_id: str, updates: Dict[str, Any]
    ) -> bool:
        """更新任务"""
        await self._ensure_initialized()

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                else:
                    return False

                task = await repo.update(task_id, **updates)
                return task is not None
        except Exception as e:
            logger.error(f"更新任务失败: {e}")
            return False

    async def delete_task(self, task_type: str, task_id: str) -> bool:
        """删除任务"""
        await self._ensure_initialized()

        try:
            async with self.db_manager.get_session() as session:
                if task_type == "video":
                    repo = VideoTaskRepository(session)
                elif task_type == "meeting":
                    repo = MeetingTaskRepository(session)
                else:
                    return False

                # 先删除相关文件记录
                file_repo = TaskFileRepository(session)
                task_files = await file_repo.get_by_task(task_id)
                for task_file in task_files:
                    await file_repo.delete(task_file.id)
                    # TODO: 删除实际文件
                    logger.info(f"删除任务文件: {task_file.file_path}")

                # 删除任务
                success = await repo.delete(task_id)
                if success:
                    logger.info(f"任务删除成功: {task_id}")

                return success
        except Exception as e:
            logger.error(f"删除任务失败: {e}")
            return False


# 全局任务服务实例
task_service = TaskService()
