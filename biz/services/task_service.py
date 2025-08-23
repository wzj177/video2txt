#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 任务管理服务
"""

from typing import Dict, List, Any
from datetime import datetime
import asyncio


class TaskService:
    """任务管理服务 - 管理所有类型的任务"""

    def __init__(self):
        self._storage = {"video_tasks": [], "meeting_tasks": []}
        self._init_demo_data()

    def _init_demo_data(self):
        """初始化演示数据"""
        demo_video_tasks = [
            {
                "id": "video_20250821_100000_0",
                "type": "video",
                "status": "completed",
                "progress": 100,
                "created_at": "2025-08-21T10:00:00",
                "updated_at": "2025-08-21T10:15:00",
                "input": {
                    "type": "file",
                    "filename": "demo_video.mp4",
                    "size": 50 * 1024 * 1024,
                },
                "config": {
                    "language": "zh",
                    "model": "whisper",
                    "output_types": ["transcript", "summary"],
                },
                "results": {
                    "transcript": "演示转录内容：这是一个关于AI技术发展的讲座，主要讨论了深度学习和自然语言处理的最新进展...",
                    "summary": "演示摘要内容：讲座重点介绍了AI技术在各个领域的应用，包括语音识别、图像处理等...",
                    "files": [
                        {"name": "transcript.txt", "path": "/demo/transcript.txt"},
                        {"name": "summary.md", "path": "/demo/summary.md"},
                        {"name": "audio.wav", "path": "/demo/audio.wav"},
                    ],
                },
            },
            {
                "id": "video_20250821_110000_1",
                "type": "audio",
                "status": "running",
                "progress": 65,
                "created_at": "2025-08-21T11:00:00",
                "updated_at": "2025-08-21T11:10:00",
                "current_step": "正在进行语音识别...",
                "input": {
                    "type": "file",
                    "filename": "demo_audio.mp3",
                    "size": 25 * 1024 * 1024,
                },
                "config": {
                    "language": "auto",
                    "model": "dolphin",
                    "output_types": ["transcript", "flashcards"],
                },
                "results": {},
                "partial_transcript": "大家好，欢迎来到今天的技术分享会议...",
            },
        ]

        demo_meeting_tasks = [
            {
                "id": "meeting_20250821_090000_0",
                "status": "completed",
                "progress": 100,
                "created_at": "2025-08-21T09:00:00",
                "updated_at": "2025-08-21T09:30:00",
                "config": {"language": "zh", "realtime": True},
                "results": {
                    "transcript": "会议转录内容：今天我们讨论产品迭代计划...",
                    "summary": "会议纪要：确定了下一版本的功能优先级...",
                    "duration": 1800,
                },
            }
        ]

        self._storage["video_tasks"].extend(demo_video_tasks)
        self._storage["meeting_tasks"].extend(demo_meeting_tasks)

    def get_tasks(self, task_type: str) -> List[Dict[str, Any]]:
        """获取任务列表"""
        key = f"{task_type}_tasks"
        if key not in self._storage:
            return []

        # 按创建时间倒序排列
        tasks = sorted(
            self._storage[key],
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )
        return tasks

    def get_task_by_id(self, task_type: str, task_id: str) -> Dict[str, Any]:
        """根据ID获取任务"""
        tasks = self.get_tasks(task_type)
        for task in tasks:
            if task["id"] == task_id:
                return task
        return None

    def get_task_stats(self, task_type: str) -> Dict[str, int]:
        """获取任务统计信息"""
        tasks = self.get_tasks(task_type)

        stats = {
            "total": len(tasks),
            "running": len([t for t in tasks if t.get("status") == "running"]),
            "completed": len([t for t in tasks if t.get("status") == "completed"]),
            "failed": len([t for t in tasks if t.get("status") == "failed"]),
            "pending": len([t for t in tasks if t.get("status") == "pending"]),
        }

        # 视频任务额外统计音频和视频数量
        if task_type == "video":
            stats.update(
                {
                    "audioCount": len([t for t in tasks if t.get("type") == "audio"]),
                    "videoCount": len([t for t in tasks if t.get("type") == "video"]),
                }
            )

        return stats

    def create_task(self, task_type: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新任务"""
        # 生成任务ID
        task_id = f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._storage[f'{task_type}_tasks'])}"

        # 创建任务对象
        task = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            **task_data,
        }

        # 添加到存储
        self._storage[f"{task_type}_tasks"].append(task)

        return task

    def update_task(
        self, task_type: str, task_id: str, updates: Dict[str, Any]
    ) -> bool:
        """更新任务"""
        task = self.get_task_by_id(task_type, task_id)
        if not task:
            return False

        # 更新字段
        task.update(updates)
        task["updated_at"] = datetime.now().isoformat()

        return True


# 全局任务服务实例
task_service = TaskService()
