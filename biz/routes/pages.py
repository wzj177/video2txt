#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 页面路由模块
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
        return HTMLResponse("<h1>听语AI - 首页文件未找到</h1>", status_code=404)


@pages_router.get("/index", response_class=HTMLResponse)
async def index():
    """首页"""
    index_file = PUBLIC_DIR / "pages" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    else:
        return HTMLResponse("<h1>听语AI - 首页文件未找到</h1>", status_code=404)


@pages_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """仪表板页面"""
    dashboard_file = PUBLIC_DIR / "pages" / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    else:
        return HTMLResponse("<h1>听语AI - 仪表板页面未找到</h1>", status_code=404)


@pages_router.get("/video2txt", response_class=HTMLResponse)
async def video2txt():
    """视频转文字页面"""
    video2txt_file = PUBLIC_DIR / "pages" / "video2txt.html"
    if video2txt_file.exists():
        return FileResponse(video2txt_file)
    else:
        return HTMLResponse("<h1>听语AI - 视频转文字页面未找到</h1>", status_code=404)

@pages_router.get("/mindmap", response_class=HTMLResponse)
async def mindmap():
    """思维导图页面"""
    mindmap_file = PUBLIC_DIR / "pages" / "mindmap.html"
    if mindmap_file.exists():
        return FileResponse(mindmap_file)
    else:
        return HTMLResponse("<h1>听语AI - 思维导图页面未找到</h1>", status_code=404)

@pages_router.get("/task_create", response_class=HTMLResponse)
async def task_create():
    """创建任务页面"""
    task_create_file = PUBLIC_DIR / "pages" / "task_create.html"
    if task_create_file.exists():
        return FileResponse(task_create_file)
    else:
        return HTMLResponse("<h1>听语AI - 创建任务页面未找到</h1>", status_code=404)


@pages_router.get("/task_detail", response_class=HTMLResponse)
async def task_detail(task_id: str):
    """任务详情页面"""
    task_detail_file = PUBLIC_DIR / "pages" / "task_detail.html"
    if task_detail_file.exists():
        return FileResponse(task_detail_file)
    else:
        return HTMLResponse("<h1>听语AI - 任务详情页面未找到</h1>", status_code=404)


@pages_router.get("/meeting2txt", response_class=HTMLResponse)
async def meeting2txt():
    """会议转文字页面"""
    meeting2txt_file = PUBLIC_DIR / "pages" / "meeting2txt.html"
    if meeting2txt_file.exists():
        return FileResponse(meeting2txt_file)
    else:
        return HTMLResponse("<h1>听语AI - 会议转文字页面未找到</h1>", status_code=404)


@pages_router.get("/meeting_create", response_class=HTMLResponse)
async def meeting_create():
    """创建会议页面"""
    meeting_create_file = PUBLIC_DIR / "pages" / "meeting_create.html"
    if meeting_create_file.exists():
        return FileResponse(meeting_create_file)
    else:
        return HTMLResponse("<h1>听语AI - 创建会议页面未找到</h1>", status_code=404)


@pages_router.get("/meeting_detail", response_class=HTMLResponse)
async def meeting_detail():
    """会议详情页面"""
    meeting_detail_file = PUBLIC_DIR / "pages" / "meeting_detail.html"
    if meeting_detail_file.exists():
        return FileResponse(meeting_detail_file)
    else:
        return HTMLResponse("<h1>听语AI - 会议详情页面未找到</h1>", status_code=404)


@pages_router.get("/meeting_upload", response_class=HTMLResponse)
async def meeting_upload():
    """上传会议录音页面"""
    meeting_upload_file = PUBLIC_DIR / "pages" / "meeting_upload.html"
    if meeting_upload_file.exists():
        return FileResponse(meeting_upload_file)
    else:
        return HTMLResponse("<h1>听语AI - 上传会议录音页面未找到</h1>", status_code=404)


@pages_router.get("/settings", response_class=HTMLResponse)
async def settings():
    """设置页面"""
    settings_file = PUBLIC_DIR / "pages" / "settings.html"
    if settings_file.exists():
        return FileResponse(settings_file)
    else:
        return HTMLResponse("<h1>听语AI - 设置页面未找到</h1>", status_code=404)


# 静态资源路由
@pages_router.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    """提供静态资源文件"""
    asset_file = PUBLIC_DIR / "assets" / file_path
    if asset_file.exists() and asset_file.is_file():
        return FileResponse(asset_file)
    else:
        return HTMLResponse(f"<h1>资源文件未找到: {file_path}</h1>", status_code=404)
