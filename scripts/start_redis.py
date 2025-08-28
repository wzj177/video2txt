#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - Redis启动脚本（开发环境）
"""

import os
import sys
import subprocess
import time
import logging
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_redis_running():
    """检查Redis是否已运行"""
    try:
        result = subprocess.run(
            ["redis-cli", "ping"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == "PONG"
    except:
        return False


def start_redis_server():
    """启动Redis服务器"""
    try:
        logger.info("🔍 检查Redis服务状态...")

        if check_redis_running():
            logger.info("✅ Redis服务已在运行")
            return True

        logger.info("🚀 启动Redis服务器...")

        # 尝试启动Redis服务器
        if sys.platform == "darwin":  # macOS
            # 尝试使用brew启动
            try:
                subprocess.run(["brew", "services", "start", "redis"], check=True)
                logger.info("📦 使用Homebrew启动Redis服务")
            except:
                # 直接启动redis-server
                subprocess.Popen(
                    ["redis-server"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("🔧 直接启动redis-server")

        elif sys.platform.startswith("linux"):  # Linux
            try:
                # 尝试使用systemctl
                subprocess.run(["sudo", "systemctl", "start", "redis"], check=True)
                logger.info("🐧 使用systemctl启动Redis服务")
            except:
                # 直接启动redis-server
                subprocess.Popen(
                    ["redis-server"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("🔧 直接启动redis-server")

        else:  # Windows
            subprocess.Popen(
                ["redis-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info("🪟 在Windows上启动redis-server")

        # 等待Redis启动
        logger.info("⏳ 等待Redis服务启动...")
        for i in range(10):
            if check_redis_running():
                logger.info("✅ Redis服务启动成功")
                return True
            time.sleep(1)

        logger.error("❌ Redis服务启动失败")
        return False

    except Exception as e:
        logger.error(f"❌ 启动Redis失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("🔧 AI听世界 - Redis服务管理")

    if start_redis_server():
        logger.info("🎉 Redis服务已就绪，可以启动Celery Worker")
        logger.info("💡 提示：使用以下命令启动Worker:")
        logger.info("   python scripts/start_worker.py")
    else:
        logger.error("💥 Redis服务启动失败，请手动安装并启动Redis")
        logger.info("📖 安装指南:")
        if sys.platform == "darwin":
            logger.info("   macOS: brew install redis && brew services start redis")
        elif sys.platform.startswith("linux"):
            logger.info("   Ubuntu/Debian: sudo apt install redis-server")
            logger.info("   CentOS/RHEL: sudo yum install redis")
        else:
            logger.info("   Windows: 从 https://redis.io/download 下载安装")

        sys.exit(1)


if __name__ == "__main__":
    main()
