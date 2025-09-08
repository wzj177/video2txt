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


async def start_celery_worker() -> bool:
    """尝试自动启动Celery Worker"""
    try:
        import subprocess
        import sys
        import os

        # 获取当前Python解释器路径
        python_path = sys.executable

        # 构建Celery Worker启动命令
        cmd = [
            python_path,
            "-m",
            "celery",
            "-A",
            "app.celery_config:celery_app",
            "worker",
            "--loglevel=info",
            "--concurrency=2",  # 限制并发数
            "--max-tasks-per-child=50",  # 每个子进程最多处理50个任务
        ]

        # 尝试使用detach选项，如果失败则使用常规方式
        use_detach = True

        logger.info(f"启动命令: {' '.join(cmd)}")

        # 启动Worker进程（后台方式）
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,  # 忽略输出，让Worker在后台运行
            stderr=asyncio.subprocess.DEVNULL,
            cwd=PROJECT_ROOT,
            start_new_session=True,  # 在新的会话中启动，避免与主进程关联
        )

        # 不等待进程完成，直接让它在后台运行
        logger.info("Worker进程已启动，等待初始化...")

        # 等待8秒让Worker完全启动和注册
        await asyncio.sleep(8)

        # 验证Worker是否真正运行（多次尝试）
        from app.celery_config import celery_app

        for attempt in range(5):  # 增加到5次尝试
            try:
                inspector = celery_app.control.inspect()
                stats = inspector.stats()
                active = inspector.active()

                logger.info(
                    f"第 {attempt + 1} 次检测: stats={bool(stats)}, active={bool(active)}"
                )

                if stats and len(stats) > 0:
                    logger.info(f"检测到 {len(stats)} 个活跃Worker")
                    return True
                elif active is not None and len(active) > 0:
                    logger.info("检测到Worker活动，验证成功")
                    return True
                else:
                    logger.info(
                        f"第 {attempt + 1} 次检测未发现活跃Worker，等待3秒后重试..."
                    )
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"第 {attempt + 1} 次检测失败: {e}")
                await asyncio.sleep(3)

        logger.warning("Worker启动但未能检测到活跃状态")
        return False

    except ImportError:
        logger.warning("Celery未安装，无法自动启动Worker")
        return False
    except Exception as e:
        logger.error(f"启动Celery Worker时出错: {e}")
        return False


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

                # 检查celery_app是否正确初始化
                if hasattr(celery_app, "control") and celery_app.control:
                    return "redis"
                    # try:
                    #     inspector = celery_app.control.inspect()
                    #     stats = inspector.stats()
                    #     if stats:
                    #         return "redis"
                    #     else:
                    #         logger.warning("⚠️  Redis可用但Celery Worker未启动")
                    # except Exception as inspect_error:
                    #     logger.warning(f"Celery检查失败: {inspect_error}")
                else:
                    logger.warning("⚠️  Celery应用未正确初始化")
            except ImportError as e:
                logger.warning(f"Celery导入失败: {e}")
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

            # 检查celery_app是否正确初始化
            if hasattr(celery_app, "control") and celery_app.control:
                try:
                    inspector = celery_app.control.inspect()
                    stats = inspector.stats()
                    if stats:
                        logger.info("✅ Celery Worker正在运行")
                        logger.info("🚀 系统已启用高性能异步任务处理")
                    else:
                        logger.info("🚀 检测到Redis可用，尝试自动启动Celery Worker...")
                        worker_started = await start_celery_worker()
                        if worker_started:
                            logger.info("✅ Celery Worker已自动启动")
                            logger.info("🚀 系统已启用高性能异步任务处理")
                        else:
                            logger.warning("❌ 自动启动Celery Worker失败")
                            logger.warning(
                                "⚠️  请手动启动: celery -A app.celery_config:celery_app worker --loglevel=info"
                            )
                            logger.info("🔄 回退到SQLite队列系统")
                            queue_type = "sqlite"
                except Exception as inspect_error:
                    logger.warning(f"Celery Worker检查失败: {inspect_error}")
                    logger.info("🔄 回退到SQLite队列系统")
                    # 重新检测队列系统，这次应该会选择SQLite
                    queue_type = "sqlite"
            else:
                logger.warning("⚠️  Celery应用未正确初始化，回退到SQLite队列")
                # 回退到SQLite队列
                queue_type = "sqlite"
        except Exception as e:
            logger.error(f"Redis队列系统错误: {e}")
            logger.info("🔄 回退到SQLite队列系统")

    elif queue_type == "sqlite":
        logger.info("✅ 使用SQLite队列系统（推荐，无需Redis）")
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
