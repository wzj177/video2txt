#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - FastAPI应用主入口
"""
import asyncio
import sys
import logging
import json
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


def get_project_root() -> Path:
    """
    获取项目根目录，兼容PyInstaller打包

    Returns:
        Path: 项目根目录路径
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller打包后的环境
        # 使用可执行文件的目录作为项目根目录
        return Path(sys.executable).parent
    else:
        # 开发环境
        return Path(__file__).parent.parent


def get_storage_path() -> Path:
    """
    获取存储路径，兼容PyInstaller打包

    Returns:
        Path: 存储目录的绝对路径
    """
    project_root = get_project_root()
    return project_root / "data" / "outputs"


def update_storage_config():
    """
    更新配置文件中的存储路径为绝对路径
    """
    try:
        project_root = get_project_root()
        config_path = project_root / "config" / "settings.json"

        # 确保配置目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有配置
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}

        # 确保system配置存在
        if "system" not in config:
            config["system"] = {}

        # 更新存储路径为绝对路径
        storage_path = get_storage_path()
        config["system"]["storage_path"] = str(storage_path)

        # 确保存储目录存在
        storage_path.mkdir(parents=True, exist_ok=True)

        # 写回配置文件
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"存储路径已更新为: {storage_path}")

    except Exception as e:
        logger.error(f"更新存储配置失败: {e}")


# 获取项目根目录并添加到Python路径
PROJECT_ROOT = get_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

# 确保日志目录存在
# (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
now = datetime.now()
log_dir = PROJECT_ROOT / "logs" / f"{now.strftime('%Y年')}" / f"{now.strftime('%m月')}"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"{now.strftime('%d日')}.log"

# 配置日志

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger(__name__)

# 导入数据库初始化
from biz.database.connection import init_database, close_database

# 全局队列管理器
_queue_manager = None


# Celery相关函数已移除，直接使用SQLite队列系统


async def start_queue_system():
    """启动SQLite队列系统 - 简化版本"""
    global _queue_manager

    logger.info("✅ 使用SQLite队列系统（零依赖，适合个人PC）")
    try:
        # 导入任务以注册到队列
        from biz.tasks import video_tasks
        from biz.queue.task_manager import get_task_manager

        manager = get_task_manager()
        _queue_manager = manager

        # 启动Worker（如果还未启动）
        if not manager.running:
            manager.start_workers(
                worker_count=2,
                queue_names=["video_processing", "meeting_processing", "default"],
            )
            logger.info("✅ SQLite Worker已启动（2个工作进程）")
        else:
            logger.info("✅ SQLite Worker已在运行")

        # 显示队列统计
        stats = manager.get_queue_stats()
        logger.info(f"📊 队列统计: 总任务 {stats.get('total', 0)}")
        logger.info("🚀 系统已启用零依赖异步任务处理")

    except Exception as e:
        logger.error(f"SQLite队列系统启动失败: {e}")
        logger.info("🔄 系统将使用同步处理模式")


async def stop_queue_system():
    """停止队列系统"""
    global _queue_manager
    try:
        if _queue_manager and _queue_manager.running:
            _queue_manager.stop_workers()
            logger.info("✅ SQLite队列系统已停止")
        else:
            logger.info("ℹ️  队列系统已停止或未启动")
    except Exception as e:
        logger.error(f"停止队列系统失败: {e}")


# 导入中间件
from biz.middleware.exception_handler import GlobalExceptionHandler

# 导入路由
from biz.routes.pages import pages_router
from biz.routes.system_api import system_router
from biz.routes.video_api import video_router
from biz.routes.meeting_api import meeting_router
from biz.routes.model_api import model_router
from biz.routes.settings_api import settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时更新存储路径配置
    logger.info("📁 正在更新存储路径配置...")
    try:
        update_storage_config()
        logger.info("✅ 存储路径配置完成")
    except Exception as e:
        logger.error(f"❌ 存储路径配置失败: {e}")
        # 不抛出异常，继续启动

    # 启动时初始化数据库
    logger.info("🗄️  正在初始化数据库...")
    try:
        await init_database()
        logger.info("✅ 数据库初始化完成")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise

    # 智能队列系统启动
    logger.info("🔍 正在启动智能队列系统...")
    await start_queue_system()

    yield

    # 关闭时清理队列系统
    logger.info("🛑 正在关闭队列系统...")
    await stop_queue_system()

    # 关闭时清理数据库连接
    logger.info("🗄️  正在关闭数据库连接...")
    try:
        await close_database()
        logger.info("✅ 数据库连接已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭数据库连接失败: {e}")


# 创建FastAPI应用
app = FastAPI(
    title="听语AI",
    description="智能语音文字转换系统",
    version="3.0.0",
    lifespan=lifespan,
)

# 添加全局异常处理中间件
app.add_middleware(GlobalExceptionHandler, debug=True)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态资源
app.mount(
    "/assets",
    StaticFiles(directory=str(PROJECT_ROOT / "public" / "assets")),
    name="assets",
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(PROJECT_ROOT / "public" / "favicon.ico"))


# 注册路由
app.include_router(pages_router)
app.include_router(system_router)
app.include_router(video_router)
app.include_router(meeting_router)
app.include_router(model_router)
app.include_router(settings_router)


@app.get("/")
async def root():
    """根路径重定向到首页"""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/index")


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time

    # 服务器配置
    host = "127.0.0.1"
    port = 19080
    url = f"http://{host}:{port}"

    def open_browser():
        """延迟1秒后打开浏览器"""
        time.sleep(1)
        print(f"🌐 正在打开浏览器: {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"❌ 无法自动打开浏览器: {e}")
            print(f"📱 请手动访问: {url}")

    # 启动浏览器线程
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    print(f"🚀 听语AI 启动中...")
    print(f"📍 服务地址: {url}")
    print(f"📚 API文档: {url}/docs")

    # 显示使用提示
    print("\n📖 功能说明:")
    print("  🎬 视频转文字：支持MP4、AVI等视频格式")
    print("  🎵 音频转文字：支持MP3、WAV等音频格式")
    print("  🔗 URL处理：支持在线视频链接")
    print("  📝 智能摘要：AI生成内容摘要")
    print("  📄 多格式输出：文本、字幕、记忆卡片等")
    print(f"\n🛑 按 Ctrl+C 停止服务")

    try:
        uvicorn.run(app, host=host, port=port, reload=False)
    except SystemExit as e:
        sys.exit(e.code)
