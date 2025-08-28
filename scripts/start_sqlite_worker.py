#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - SQLite队列Worker启动脚本
无需Redis依赖，适合本地个人使用
"""

import os
import sys
import signal
import logging
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "sqlite_worker.log"),
    ],
)

logger = logging.getLogger(__name__)


def start_sqlite_worker():
    """启动SQLite队列Worker"""
    try:
        logger.info("🚀 启动AI听世界 SQLite Worker...")

        # 确保日志目录存在
        (PROJECT_ROOT / "logs").mkdir(exist_ok=True)

        # 导入任务管理器和任务
        from biz.queue.task_manager import get_task_manager
        from biz.tasks import video_tasks_sqlite  # 导入以注册任务

        manager = get_task_manager()

        # 启动Worker
        manager.start_workers(
            worker_count=2,  # 启动2个Worker
            queue_names=["video_processing", "meeting_processing", "default"],
        )

        logger.info("✅ SQLite Worker启动成功")
        logger.info("📊 队列统计:")
        stats = manager.get_queue_stats()
        for key, value in stats.items():
            logger.info(f"   {key}: {value}")

        logger.info("🛑 按 Ctrl+C 停止Worker")

        # 等待中断信号
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 收到停止信号...")

        # 停止Worker
        manager.stop_workers()
        logger.info("✅ SQLite Worker已停止")

    except Exception as e:
        logger.error(f"❌ Worker启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_sqlite_worker()
