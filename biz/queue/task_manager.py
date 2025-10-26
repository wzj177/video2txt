#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 任务管理器
管理SQLite队列和Worker
"""

import os
import sys
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Callable, List

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from .sqlite_queue import SQLiteTaskQueue, TaskWorker, get_task_queue

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.queue = get_task_queue()
        self.workers: Dict[str, TaskWorker] = {}
        self.task_handlers: Dict[str, Callable] = {}
        self.running = False

    def register_task(self, task_name: str, handler: Callable):
        """注册任务处理器"""
        self.task_handlers[task_name] = handler
        logger.info(f"注册任务处理器: {task_name}")

    def submit_task(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict = None,
        queue_name: str = "default",
        priority: int = 0,
        max_retries: int = 3,
    ) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())

        if kwargs is None:
            kwargs = {}

        success = self.queue.put_task(
            task_id=task_id,
            queue_name=queue_name,
            task_name=task_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
        )

        if success:
            logger.info(f"任务已提交: {task_id} ({task_name})")
            return task_id
        else:
            raise RuntimeError(f"任务提交失败: {task_name}")

    def start_workers(self, worker_count: int = 2, queue_names: List[str] = None):
        """启动工作器"""
        if self.running:
            logger.warning("Worker已在运行")
            return

        if queue_names is None:
            queue_names = ["default", "video_processing", "meeting_processing"]

        self.running = True

        for i in range(worker_count):
            worker_id = f"worker_{i+1}"
            worker = TaskWorker(
                worker_id=worker_id,
                queue=self.queue,
                queue_names=queue_names,
                task_handlers=self.task_handlers,
            )

            worker.start()
            self.workers[worker_id] = worker

        logger.info(f"已启动 {worker_count} 个Worker")

    def stop_workers(self):
        """停止工作器"""
        if not self.running:
            return

        self.running = False

        for worker_id, worker in self.workers.items():
            worker.stop()

        self.workers.clear()
        logger.info("所有Worker已停止")

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        status = self.queue.get_task_status(task_id)
        if status is None:
            return {"error": "任务不存在"}
        return status

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        return self.queue.cancel_task(task_id)

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        stats = self.queue.get_queue_stats()
        stats["workers"] = len(self.workers)
        stats["running"] = self.running
        return stats

    def cleanup_old_tasks(self, days: int = 7):
        """清理旧任务"""
        self.queue.cleanup_old_tasks(days)


# 全局任务管理器实例
_global_manager = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TaskManager()
    return _global_manager


# 任务处理器装饰器
def task(task_name: str = None, queue_name: str = "default"):
    """
    任务装饰器

    这个装饰器的工作原理是：
        task 是一个高阶函数，接受 task_name 和 queue_name 参数
        它返回一个内部函数 decorator，这是真正的装饰器函数
        当您使用 @task(...) 装饰一个函数时，实际上是调用了这个 decorator 函数
        decorator 函数会：
            获取任务名称（如果未指定则使用函数名）
            获取全局任务管理器实例
        调用 register_task 方法将任务处理函数注册到管理器中
        为被装饰的函数添加一个 delay 方法，用于延迟提交任务
        返回被装饰的函数
所以当您看到这样的代码时
@task("process_video_file", queue_name="video_proc
    """

    def decorator(func: Callable):
        name = task_name or func.__name__
        manager = get_task_manager()
        manager.register_task(name, func)

        # 添加延迟提交方法
        def delay(*args, **kwargs):
            return manager.submit_task(
                task_name=name, args=args, kwargs=kwargs, queue_name=queue_name
            )

        func.delay = delay
        func.task_name = name
        return func

    return decorator
