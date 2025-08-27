#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 数据仓库层
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, desc, asc
from sqlalchemy.orm import selectinload

from ..models.task import VideoTask, MeetingTask, TaskFile
from ..models.user_data import UserPreference, ProcessingHistory, SystemMetrics

logger = logging.getLogger(__name__)


class BaseRepository:
    """基础仓库类"""

    def __init__(self, session: AsyncSession, model_class):
        self.session = session
        self.model_class = model_class

    async def create(self, **kwargs) -> Any:
        """创建记录"""
        instance = self.model_class(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, record_id: str) -> Optional[Any]:
        """根据ID获取记录"""
        result = await self.session.execute(
            select(self.model_class).where(self.model_class.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """获取所有记录"""
        result = await self.session.execute(
            select(self.model_class)
            .order_by(desc(self.model_class.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update(self, record_id: str, **kwargs) -> Optional[Any]:
        """更新记录"""
        instance = await self.get_by_id(record_id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            instance.updated_at = datetime.now()
            await self.session.flush()
            await self.session.refresh(instance)
        return instance

    async def delete(self, record_id: str) -> bool:
        """删除记录"""
        result = await self.session.execute(
            delete(self.model_class).where(self.model_class.id == record_id)
        )
        return result.rowcount > 0

    async def count(self) -> int:
        """获取记录总数"""
        result = await self.session.execute(select(func.count(self.model_class.id)))
        return result.scalar()


class VideoTaskRepository(BaseRepository):
    """视频任务仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VideoTask)

    async def get_by_status(self, status: str, limit: int = 100) -> List[VideoTask]:
        """根据状态获取任务"""
        result = await self.session.execute(
            select(VideoTask)
            .where(VideoTask.status == status)
            .order_by(desc(VideoTask.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_type(self, task_type: str, limit: int = 100) -> List[VideoTask]:
        """根据类型获取任务"""
        result = await self.session.execute(
            select(VideoTask)
            .where(VideoTask.task_type == task_type)
            .order_by(desc(VideoTask.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_stats(self) -> Dict[str, Any]:
        """获取任务统计信息"""
        # 状态统计
        status_result = await self.session.execute(
            select(VideoTask.status, func.count(VideoTask.id)).group_by(
                VideoTask.status
            )
        )
        status_counts = dict(status_result.all())

        # 类型统计
        type_result = await self.session.execute(
            select(VideoTask.task_type, func.count(VideoTask.id)).group_by(
                VideoTask.task_type
            )
        )
        type_counts = dict(type_result.all())

        # 总数
        total = await self.count()

        return {
            "total": total,
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "pending": status_counts.get("pending", 0),
            "audioCount": type_counts.get("audio", 0),
            "videoCount": type_counts.get("video", 0),
        }

    async def get_recent_tasks(self, days: int = 7, limit: int = 50) -> List[VideoTask]:
        """获取最近的任务"""
        since_date = datetime.now() - timedelta(days=days)
        result = await self.session.execute(
            select(VideoTask)
            .where(VideoTask.created_at >= since_date)
            .order_by(desc(VideoTask.created_at))
            .limit(limit)
        )
        return result.scalars().all()


class MeetingTaskRepository(BaseRepository):
    """会议任务仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, MeetingTask)

    async def get_by_status(self, status: str, limit: int = 100) -> List[MeetingTask]:
        """根据状态获取任务"""
        result = await self.session.execute(
            select(MeetingTask)
            .where(MeetingTask.status == status)
            .order_by(desc(MeetingTask.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_active_meetings(self) -> List[MeetingTask]:
        """获取活跃的会议"""
        result = await self.session.execute(
            select(MeetingTask)
            .where(MeetingTask.status.in_(["running", "monitoring"]))
            .order_by(desc(MeetingTask.created_at))
        )
        return result.scalars().all()

    async def get_stats(self) -> Dict[str, Any]:
        """获取会议统计信息"""
        # 状态统计
        status_result = await self.session.execute(
            select(MeetingTask.status, func.count(MeetingTask.id)).group_by(
                MeetingTask.status
            )
        )
        status_counts = dict(status_result.all())

        # 总数和平均时长
        total = await self.count()

        avg_duration_result = await self.session.execute(
            select(func.avg(MeetingTask.total_duration)).where(
                MeetingTask.total_duration.is_not(None)
            )
        )
        avg_duration = avg_duration_result.scalar() or 0

        return {
            "total": total,
            "running": status_counts.get("running", 0)
            + status_counts.get("monitoring", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "pending": status_counts.get("pending", 0),
            "stopped": status_counts.get("stopped", 0),
            "avg_duration": round(avg_duration, 2) if avg_duration else 0,
        }


class TaskFileRepository(BaseRepository):
    """任务文件仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskFile)

    async def get_by_task(self, task_id: str) -> List[TaskFile]:
        """获取任务的所有文件"""
        result = await self.session.execute(
            select(TaskFile)
            .where(TaskFile.task_id == task_id)
            .order_by(TaskFile.created_at)
        )
        return result.scalars().all()

    async def get_by_type(self, task_id: str, file_type: str) -> Optional[TaskFile]:
        """获取任务的特定类型文件"""
        result = await self.session.execute(
            select(TaskFile)
            .where(TaskFile.task_id == task_id, TaskFile.file_type == file_type)
            .limit(1)
        )
        return result.scalar_one_or_none()


class UserPreferenceRepository(BaseRepository):
    """用户偏好仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserPreference)

    async def get_by_category(self, category: str) -> List[UserPreference]:
        """获取分类下的所有偏好"""
        result = await self.session.execute(
            select(UserPreference)
            .where(UserPreference.category == category)
            .order_by(UserPreference.key)
        )
        return result.scalars().all()

    async def get_preference(self, category: str, key: str) -> Optional[UserPreference]:
        """获取特定偏好"""
        result = await self.session.execute(
            select(UserPreference).where(
                UserPreference.category == category, UserPreference.key == key
            )
        )
        return result.scalar_one_or_none()

    async def set_preference(
        self, category: str, key: str, value: Any, description: str = ""
    ) -> UserPreference:
        """设置偏好"""
        existing = await self.get_preference(category, key)
        if existing:
            existing.value = value
            existing.description = description
            existing.updated_at = datetime.now()
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        else:
            return await self.create(
                category=category, key=key, value=value, description=description
            )


class ProcessingHistoryRepository(BaseRepository):
    """处理历史仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ProcessingHistory)

    async def get_by_task(self, task_id: str) -> List[ProcessingHistory]:
        """获取任务的处理历史"""
        result = await self.session.execute(
            select(ProcessingHistory)
            .where(ProcessingHistory.task_id == task_id)
            .order_by(desc(ProcessingHistory.created_at))
        )
        return result.scalars().all()

    async def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取性能统计"""
        since_date = datetime.now() - timedelta(days=days)

        # 平均处理时间
        avg_time_result = await self.session.execute(
            select(func.avg(ProcessingHistory.processing_time))
            .where(ProcessingHistory.created_at >= since_date)
            .where(ProcessingHistory.processing_time.is_not(None))
        )
        avg_processing_time = avg_time_result.scalar() or 0

        # 引擎使用统计
        engine_result = await self.session.execute(
            select(ProcessingHistory.engine_used, func.count(ProcessingHistory.id))
            .where(ProcessingHistory.created_at >= since_date)
            .group_by(ProcessingHistory.engine_used)
        )
        engine_usage = dict(engine_result.all())

        # 错误统计
        error_result = await self.session.execute(
            select(func.count(ProcessingHistory.id))
            .where(ProcessingHistory.created_at >= since_date)
            .where(ProcessingHistory.error_type.is_not(None))
        )
        error_count = error_result.scalar() or 0

        return {
            "avg_processing_time": round(avg_processing_time, 2),
            "engine_usage": engine_usage,
            "error_count": error_count,
            "period_days": days,
        }


class SystemMetricsRepository(BaseRepository):
    """系统指标仓库"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, SystemMetrics)

    async def get_latest(self) -> Optional[SystemMetrics]:
        """获取最新的系统指标"""
        result = await self.session.execute(
            select(SystemMetrics).order_by(desc(SystemMetrics.created_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(self, hours: int = 24) -> List[SystemMetrics]:
        """获取历史指标"""
        since_date = datetime.now() - timedelta(hours=hours)
        result = await self.session.execute(
            select(SystemMetrics)
            .where(SystemMetrics.created_at >= since_date)
            .order_by(desc(SystemMetrics.created_at))
        )
        return result.scalars().all()
