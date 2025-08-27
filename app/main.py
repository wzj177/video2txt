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

    yield

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

    # 启动浏览器线程
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    print(f"🚀 AI听世界 启动中...")
    print(f"📍 服务地址: {url}")
    print(f"📚 API文档: {url}/docs")
    print(f"🛑 按 Ctrl+C 停止服务")

    # 启动服务器（使用127.0.0.1而不是0.0.0.0以提高安全性）
    uvicorn.run(app, host=host, port=port)
