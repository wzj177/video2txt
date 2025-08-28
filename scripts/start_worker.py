#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - Celery Worker启动脚本
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置环境变量
os.environ.setdefault("CELERY_APP", "app.celery_config:celery_app")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "celery_worker.log"),
    ],
)

logger = logging.getLogger(__name__)


def start_worker():
    """启动Celery Worker"""
    try:
        logger.info("🚀 启动AI听世界 Celery Worker...")

        # 确保日志目录存在
        (PROJECT_ROOT / "logs").mkdir(exist_ok=True)

        # 导入Celery应用
        from app.celery_config import celery_app

        # 启动worker
        celery_app.worker_main(
            [
                "worker",
                "--loglevel=info",
                "--concurrency=2",  # 并发数
                "--queues=video_processing,meeting_processing,default",
                "--hostname=worker@%h",
                "--logfile=" + str(PROJECT_ROOT / "logs" / "celery_worker.log"),
                "--pidfile=" + str(PROJECT_ROOT / "logs" / "celery_worker.pid"),
            ]
        )

    except Exception as e:
        logger.error(f"❌ Worker启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_worker()
