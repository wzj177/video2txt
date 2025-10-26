#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 下载任务管理器
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DownloadManager:
    """下载任务管理器 - 管理模型下载任务"""

    def __init__(self):
        # 使用内存存储下载任务状态（简单实现）
        self._tasks: Dict[str, Dict[str, Any]] = {}

    def create_task(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建下载任务"""
        try:
            task = {
                "id": task_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                **task_data,
            }

            self._tasks[task_id] = task
            logger.info(f"创建下载任务: {task_id}")
            return task

        except Exception as e:
            logger.error(f"创建下载任务失败: {e}")
            raise

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """更新下载任务"""
        try:
            if task_id not in self._tasks:
                logger.warning(f"任务不存在: {task_id}")
                return False

            self._tasks[task_id].update(updates)
            self._tasks[task_id]["updated_at"] = datetime.now().isoformat()

            logger.debug(f"更新下载任务: {task_id}, 更新内容: {updates}")
            return True

        except Exception as e:
            logger.error(f"更新下载任务失败: {e}")
            return False

    def get_task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务"""
        return self._tasks.copy()

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        try:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"删除下载任务: {task_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除下载任务失败: {e}")
            return False

    def cleanup_completed_tasks(self, max_age_hours: int = 24) -> int:
        """清理已完成的旧任务"""
        try:
            now = datetime.now()
            to_delete = []

            for task_id, task in self._tasks.items():
                if task.get("status") in ["completed", "failed"]:
                    created_at = datetime.fromisoformat(task["created_at"])
                    age_hours = (now - created_at).total_seconds() / 3600

                    if age_hours > max_age_hours:
                        to_delete.append(task_id)

            for task_id in to_delete:
                del self._tasks[task_id]

            logger.info(f"清理了 {len(to_delete)} 个旧的下载任务")
            return len(to_delete)

        except Exception as e:
            logger.error(f"清理下载任务失败: {e}")
            return 0


# 全局下载管理器实例
download_manager = DownloadManager()
