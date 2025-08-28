#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 基于SQLite的轻量级任务队列
适合本地个人使用，无需Redis依赖
"""

import json
import time
import sqlite3
import threading
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SQLiteTaskQueue:
    """基于SQLite的任务队列"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认使用项目数据目录
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "task_queue.db")

        self.db_path = db_path
        self.workers = {}  # worker_id -> WorkerThread
        self.running = False
        self._init_database()

    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_queue (
                    id TEXT PRIMARY KEY,
                    queue_name TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    task_args TEXT NOT NULL,  -- JSON格式
                    task_kwargs TEXT NOT NULL,  -- JSON格式
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    worker_id TEXT NULL,
                    error_message TEXT NULL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3
                )
            """
            )

            # 创建索引
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status_priority ON task_queue(status, priority DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_name ON task_queue(queue_name)"
            )
            conn.commit()

    def put_task(
        self,
        task_id: str,
        queue_name: str,
        task_name: str,
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 0,
        max_retries: int = 3,
    ) -> bool:
        """添加任务到队列"""
        try:
            if kwargs is None:
                kwargs = {}

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO task_queue 
                    (id, queue_name, task_name, task_args, task_kwargs, priority, max_retries)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        task_id,
                        queue_name,
                        task_name,
                        json.dumps(args),
                        json.dumps(kwargs),
                        priority,
                        max_retries,
                    ),
                )
                conn.commit()

            logger.info(f"任务已添加到队列: {task_id} ({task_name})")
            return True

        except Exception as e:
            logger.error(f"添加任务失败: {e}")
            return False

    def get_task(
        self, queue_names: List[str], worker_id: str
    ) -> Optional[Dict[str, Any]]:
        """从队列获取任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 使用事务确保原子性
                conn.execute("BEGIN IMMEDIATE")

                # 查找待处理任务
                placeholders = ",".join("?" * len(queue_names))
                cursor = conn.execute(
                    f"""
                    SELECT id, queue_name, task_name, task_args, task_kwargs, retry_count, max_retries
                    FROM task_queue 
                    WHERE status = 'pending' 
                    AND queue_name IN ({placeholders})
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                """,
                    queue_names,
                )

                row = cursor.fetchone()
                if not row:
                    conn.rollback()
                    return None

                (
                    task_id,
                    queue_name,
                    task_name,
                    task_args,
                    task_kwargs,
                    retry_count,
                    max_retries,
                ) = row

                # 更新任务状态为运行中
                conn.execute(
                    """
                    UPDATE task_queue 
                    SET status = 'running', worker_id = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (worker_id, task_id),
                )

                conn.commit()

                return {
                    "id": task_id,
                    "queue_name": queue_name,
                    "task_name": task_name,
                    "args": json.loads(task_args),
                    "kwargs": json.loads(task_kwargs),
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                }

        except Exception as e:
            logger.error(f"获取任务失败: {e}")
            return None

    def complete_task(self, task_id: str, result: Any = None) -> bool:
        """标记任务为完成"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE task_queue 
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (task_id,),
                )
                conn.commit()

            logger.info(f"任务完成: {task_id}")
            return True

        except Exception as e:
            logger.error(f"标记任务完成失败: {e}")
            return False

    def fail_task(self, task_id: str, error_message: str) -> bool:
        """标记任务为失败，可能重试"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 获取当前重试信息
                cursor = conn.execute(
                    """
                    SELECT retry_count, max_retries FROM task_queue WHERE id = ?
                """,
                    (task_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return False

                retry_count, max_retries = row

                if retry_count < max_retries:
                    # 重试：重置为pending状态
                    conn.execute(
                        """
                        UPDATE task_queue 
                        SET status = 'pending', 
                            retry_count = retry_count + 1,
                            worker_id = NULL,
                            started_at = NULL,
                            error_message = ?
                        WHERE id = ?
                    """,
                        (error_message, task_id),
                    )
                    logger.info(f"任务将重试: {task_id} (第{retry_count + 1}次)")
                else:
                    # 超过重试次数，标记为失败
                    conn.execute(
                        """
                        UPDATE task_queue 
                        SET status = 'failed', 
                            completed_at = CURRENT_TIMESTAMP,
                            error_message = ?
                        WHERE id = ?
                    """,
                        (error_message, task_id),
                    )
                    logger.error(f"任务失败: {task_id} - {error_message}")

                conn.commit()
            return True

        except Exception as e:
            logger.error(f"标记任务失败失败: {e}")
            return False

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE task_queue 
                    SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status IN ('pending', 'running')
                """,
                    (task_id,),
                )

                affected = conn.total_changes
                conn.commit()

            if affected > 0:
                logger.info(f"任务已取消: {task_id}")
                return True
            else:
                logger.warning(f"无法取消任务: {task_id} (可能已完成或不存在)")
                return False

        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT status, created_at, started_at, completed_at, 
                           worker_id, error_message, retry_count
                    FROM task_queue WHERE id = ?
                """,
                    (task_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                (
                    status,
                    created_at,
                    started_at,
                    completed_at,
                    worker_id,
                    error_message,
                    retry_count,
                ) = row

                return {
                    "id": task_id,
                    "status": status,
                    "created_at": created_at,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "worker_id": worker_id,
                    "error_message": error_message,
                    "retry_count": retry_count,
                }

        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
            return None

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM task_queue 
                    GROUP BY status
                """
                )

                stats = {"total": 0}
                for status, count in cursor.fetchall():
                    stats[status] = count
                    stats["total"] += count

                return stats

        except Exception as e:
            logger.error(f"获取队列统计失败: {e}")
            return {"total": 0}

    def cleanup_old_tasks(self, days: int = 7):
        """清理旧任务"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM task_queue 
                    WHERE status IN ('completed', 'failed', 'cancelled')
                    AND created_at < ?
                """,
                    (cutoff_date.isoformat(),),
                )

                deleted_count = cursor.rowcount
                conn.commit()

            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个旧任务")

        except Exception as e:
            logger.error(f"清理旧任务失败: {e}")


class TaskWorker:
    """任务工作线程"""

    def __init__(
        self,
        worker_id: str,
        queue: SQLiteTaskQueue,
        queue_names: List[str],
        task_handlers: Dict[str, Callable],
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.queue_names = queue_names
        self.task_handlers = task_handlers
        self.running = False
        self.thread = None

    def start(self):
        """启动工作线程"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"Worker {self.worker_id} 已启动")

    def stop(self):
        """停止工作线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"Worker {self.worker_id} 已停止")

    def _run(self):
        """工作线程主循环"""
        while self.running:
            try:
                # 获取任务
                task = self.queue.get_task(self.queue_names, self.worker_id)

                if task is None:
                    # 没有任务，短暂休息
                    time.sleep(1)
                    continue

                # 执行任务
                self._execute_task(task)

            except Exception as e:
                logger.error(f"Worker {self.worker_id} 执行异常: {e}")
                time.sleep(1)

    def _execute_task(self, task: Dict[str, Any]):
        """执行单个任务"""
        task_id = task["id"]
        task_name = task["task_name"]

        try:
            logger.info(
                f"Worker {self.worker_id} 开始执行任务: {task_id} ({task_name})"
            )

            # 查找任务处理器
            if task_name not in self.task_handlers:
                raise ValueError(f"未找到任务处理器: {task_name}")

            handler = self.task_handlers[task_name]

            # 执行任务
            result = handler(*task["args"], **task["kwargs"])

            # 标记完成
            self.queue.complete_task(task_id, result)
            logger.info(f"任务执行成功: {task_id}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"任务执行失败: {task_id} - {error_message}")
            self.queue.fail_task(task_id, error_message)


# 全局队列实例
_global_queue = None


def get_task_queue() -> SQLiteTaskQueue:
    """获取全局任务队列实例"""
    global _global_queue
    if _global_queue is None:
        _global_queue = SQLiteTaskQueue()
    return _global_queue
