#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - FastAPI应用主入口
"""

import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 获取项目根目录并添加到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 确保日志目录存在
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "app.log"),
    ],
)

logger = logging.getLogger(__name__)

# 导入数据库初始化
from biz.database.connection import init_database, close_database

# 全局队列管理器
_queue_manager = None


async def detect_queue_system() -> str:
    """检测可用的队列系统"""
    # 1. 检查Redis是否可用（端口6379）
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6379))
        sock.close()

        if result == 0:
            # Redis可用，检查Celery
            try:
                from app.celery_config import celery_app

                inspector = celery_app.control.inspect()
                stats = inspector.stats()
                if stats:
                    return "redis"
                else:
                    logger.warning("⚠️  Redis可用但Celery Worker未启动")
            except Exception as e:
                logger.warning(f"Celery配置错误: {e}")
    except Exception:
        pass

    # 2. 使用SQLite队列
    try:
        from biz.queue.task_manager import get_task_manager

        return "sqlite"
    except Exception as e:
        logger.warning(f"SQLite队列系统不可用: {e}")
        return "none"


async def start_queue_system():
    """启动智能队列系统"""
    global _queue_manager
    queue_type = await detect_queue_system()

    if queue_type == "redis":
        logger.info("✅ 检测到Redis，使用Redis+Celery队列系统")
        try:
            from app.celery_config import celery_app

            inspector = celery_app.control.inspect()
            stats = inspector.stats()
            if stats:
                logger.info("✅ Celery Worker正在运行")
                logger.info("🚀 系统已启用高性能异步任务处理")
            else:
                logger.warning(
                    "⚠️  请启动Celery Worker: celery -A app.celery_config:celery_app worker"
                )
        except Exception as e:
            logger.error(f"Redis队列系统错误: {e}")

    elif queue_type == "sqlite":
        logger.info("✅ 使用SQLite队列系统（推荐，无需Redis）")
        try:
            # 导入任务以注册到队列
            from biz.tasks import video_tasks_sqlite
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
    else:
        logger.warning("⚠️  队列系统不可用，使用同步处理模式")
        logger.info("💡 建议：安装Redis或检查SQLite队列配置")


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
    title="AI听世界",
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

    # 检查队列系统状态
    def check_queue_system():
        """检查队列系统状态"""
        try:
            # 检查Redis
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 6379))
            sock.close()

            if result == 0:
                try:
                    from app.celery_config import celery_app

                    inspector = celery_app.control.inspect()
                    stats = inspector.stats()
                    if stats:
                        print("🔥 Redis+Celery队列系统已启用（高性能模式）")
                        return "redis"
                    else:
                        print("⚠️  Redis可用但Celery Worker未启动")
                except Exception:
                    pass

            # 检查SQLite队列
            try:
                from biz.queue.task_manager import get_task_manager

                manager = get_task_manager()
                if manager.running:
                    print("✅ SQLite队列系统已启用（零依赖模式）")
                    return "sqlite"
                else:
                    print("🟡 SQLite队列系统可用（将在首次任务时启动）")
                    return "sqlite_ready"
            except Exception:
                pass

            print("⚠️  队列系统未配置，使用同步模式")
            return "none"

        except Exception:
            print("⚠️  队列系统检查失败")
            return "none"

    # 启动浏览器线程
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    print(f"🚀 AI听世界 启动中...")
    print(f"📍 服务地址: {url}")
    print(f"📚 API文档: {url}/docs")

    # 检查队列系统状态
    queue_status = check_queue_system()

    # 显示使用提示
    print("\n📖 功能说明:")
    print("  🎬 视频转文字：支持MP4、AVI等视频格式")
    print("  🎵 音频转文字：支持MP3、WAV等音频格式")
    print("  🔗 URL处理：支持在线视频链接")
    print("  📝 智能摘要：AI生成内容摘要")
    print("  📄 多格式输出：文本、字幕、记忆卡片等")

    if queue_status in ["redis", "sqlite", "sqlite_ready"]:
        print("\n🎯 队列特性:")
        print("  ⚡ 真异步处理：上传后立即返回，后台处理")
        print("  📊 实时状态：可查看处理进度和结果")
        print("  🔄 任务管理：支持取消、重试等操作")
        print("  📱 响应迅速：API秒级响应，不会阻塞")

    print(f"\n🛑 按 Ctrl+C 停止服务")

    # 启动服务器（使用127.0.0.1而不是0.0.0.0以提高安全性）
    uvicorn.run(app, host=host, port=port)
