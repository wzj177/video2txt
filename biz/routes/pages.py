#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 页面路由模块
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

# 创建页面路由器
pages_router = APIRouter()

# 获取public目录路径
PUBLIC_DIR = Path(__file__).parent.parent.parent / "public"


@pages_router.get("/", response_class=HTMLResponse)
async def root():
    """根路径重定向到首页"""
    index_file = PUBLIC_DIR / "pages" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 首页文件未找到</h1>", status_code=404)


@pages_router.get("/index", response_class=HTMLResponse)
async def index():
    """首页"""
    index_file = PUBLIC_DIR / "pages" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 首页文件未找到</h1>", status_code=404)


@pages_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """仪表板页面"""
    dashboard_file = PUBLIC_DIR / "pages" / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 仪表板页面未找到</h1>", status_code=404)


@pages_router.get("/video2txt", response_class=HTMLResponse)
async def video2txt():
    """视频转文字页面"""
    video2txt_file = PUBLIC_DIR / "pages" / "video2txt.html"
    if video2txt_file.exists():
        return FileResponse(video2txt_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 视频转文字页面未找到</h1>", status_code=404)


@pages_router.get("/meeting2txt", response_class=HTMLResponse)
async def meeting2txt():
    """会议转文字页面"""
    meeting2txt_file = PUBLIC_DIR / "pages" / "meeting2txt.html"
    if meeting2txt_file.exists():
        return FileResponse(meeting2txt_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 会议转文字页面未找到</h1>", status_code=404)


@pages_router.get("/settings", response_class=HTMLResponse)
async def settings():
    """设置页面"""
    settings_file = PUBLIC_DIR / "pages" / "settings.html"
    if settings_file.exists():
        return FileResponse(settings_file)
    else:
        return HTMLResponse("<h1>AI听世界 - 设置页面未找到</h1>", status_code=404)


# 静态资源路由
@pages_router.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    """提供静态资源文件"""
    asset_file = PUBLIC_DIR / "assets" / file_path
    if asset_file.exists() and asset_file.is_file():
        return FileResponse(asset_file)
    else:
        return HTMLResponse(f"<h1>资源文件未找到: {file_path}</h1>", status_code=404)
