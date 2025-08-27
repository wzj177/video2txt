#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 视频处理API路由
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
import json
import asyncio
import time

from ..services.task_service import task_service
from ..services.video_service import video_service
from ..middleware.exception_handler import (
    create_success_response,
    create_error_response,
)

# 创建视频API路由器
video_router = APIRouter(prefix="/api/tasks/video", tags=["video"])


@video_router.get("")
async def get_video_tasks(status: str = None) -> Dict[str, Any]:
    """获取视频任务列表"""
    # 传递状态参数给服务层
    filter_status = status if status and status != "all" else None
    tasks = await task_service.get_tasks("video", status=filter_status)
    return create_success_response(tasks)


@video_router.get("/stats")
async def get_video_stats() -> Dict[str, Any]:
    """获取视频任务统计"""
    stats = await task_service.get_task_stats("video")
    return create_success_response(stats)


@video_router.get("/browse")
async def browse_local_files(
    path: str = "/", file_types: str = "video,audio"
) -> Dict[str, Any]:
    """浏览本地文件系统（仅限音视频文件）"""
    try:
        from pathlib import Path
        import os

        # 安全检查：限制访问范围
        base_path = Path(path).resolve()

        # 定义允许的文件扩展名
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
        audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}

        allowed_extensions = set()
        if "video" in file_types:
            allowed_extensions.update(video_extensions)
        if "audio" in file_types:
            allowed_extensions.update(audio_extensions)

        if not base_path.exists():
            raise HTTPException(status_code=404, detail="路径不存在")

        if not base_path.is_dir():
            raise HTTPException(status_code=400, detail="路径不是目录")

        items = []

        # 添加上级目录
        if base_path.parent != base_path:
            items.append(
                {
                    "name": "..",
                    "type": "directory",
                    "path": str(base_path.parent),
                    "size": 0,
                    "is_parent": True,
                }
            )

        # 遍历目录
        try:
            for item in sorted(
                base_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
            ):
                try:
                    if item.is_dir():
                        items.append(
                            {
                                "name": item.name,
                                "type": "directory",
                                "path": str(item),
                                "size": 0,
                                "is_parent": False,
                            }
                        )
                    elif item.is_file() and item.suffix.lower() in allowed_extensions:
                        stat_info = item.stat()
                        items.append(
                            {
                                "name": item.name,
                                "type": "file",
                                "path": str(item),
                                "size": stat_info.st_size,
                                "extension": item.suffix.lower(),
                                "modified": stat_info.st_mtime,
                                "is_parent": False,
                            }
                        )
                except (PermissionError, OSError):
                    # 跳过无权限访问的文件/目录
                    continue

        except (PermissionError, OSError) as e:
            raise HTTPException(status_code=403, detail=f"无权限访问目录: {str(e)}")

        return create_success_response(
            {
                "current_path": str(base_path),
                "items": items,
                "total": len(items),
            }
        )

    except HTTPException:
        raise


@video_router.get("/engines")
async def get_available_engines() -> Dict[str, Any]:
    """获取可用的语音识别引擎"""
    from core.asr import get_available_engines

    engines = get_available_engines()

    # 获取引擎详细信息
    engine_info = {}
    for engine_name in engines:
        try:
            if engine_name == "whisper":
                from core.asr.engines.whisper_engine import WhisperEngine

                engine = WhisperEngine({})
            elif engine_name == "faster_whisper":
                from core.asr.engines.faster_whisper_engine import (
                    FasterWhisperEngine,
                )

                engine = FasterWhisperEngine({})
            elif engine_name == "sensevoice":
                from core.asr.engines.sensevoice_engine import SenseVoiceEngine

                engine = SenseVoiceEngine({})
            elif engine_name == "dolphin":
                from core.asr.engines.dolphin_engine import DolphinEngine

                engine = DolphinEngine({})
            else:
                continue

            engine_info[engine_name] = engine.get_engine_info()
            engine_info[engine_name]["available"] = True

        except Exception as e:
            engine_info[engine_name] = {
                "name": engine_name,
                "available": False,
                "error": str(e),
            }

    return create_success_response(engine_info)


@video_router.get("/{task_id}")
async def get_video_task(task_id: str) -> Dict[str, Any]:
    """获取单个视频任务"""
    task = await task_service.get_task_by_id("video", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    return create_success_response(task)


@video_router.post("")
async def create_video_task(
    file: UploadFile = File(None),
    url: str = Form(None),
    language: str = Form("zh"),
    model: str = Form("whisper"),
    model_size: str = Form("small"),
    output_types: str = Form("transcript,summary"),
) -> Dict[str, Any]:
    """创建视频处理任务"""
    # 验证输入参数
    if not file and not url:
        raise HTTPException(status_code=400, detail="必须提供文件或URL")

    if file and url:
        raise HTTPException(status_code=400, detail="不能同时提供文件和URL")

    # 解析输出类型
    output_type_list = [t.strip() for t in output_types.split(",") if t.strip()]

    # 检查模型可用性
    from core.asr import get_available_engines

    available_engines = get_available_engines()

    # 如果指定的是 "auto"，检查是否有任何可用引擎
    if model == "auto":
        if not available_engines:
            raise HTTPException(status_code=400, detail="没有可用的语音识别引擎")
    elif model not in available_engines:
        raise HTTPException(status_code=400, detail=f"语音识别引擎 {model} 不可用")

    # 构建配置
    config = {
        "language": language,
        "model": model,
        "model_size": model_size,
        "output_types": output_type_list,
    }

    # 处理文件或URL
    if file:
        # 验证文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        # 保存上传的文件
        import tempfile
        import shutil
        from pathlib import Path

        # 创建临时文件
        temp_dir = Path(tempfile.gettempdir()) / "ai-video2text"
        temp_dir.mkdir(exist_ok=True)

        file_extension = Path(file.filename).suffix
        temp_file_path = temp_dir / f"upload_{int(time.time())}{file_extension}"

        # 流式保存文件（支持大文件）
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        with open(temp_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)

        # 构建文件数据
        file_data = {
            "filename": file.filename,
            "size": file_size,
            "content_type": file.content_type,
            "type": "file",
            "file_path": str(temp_file_path),
        }

        # 处理文件
        result = await video_service.process_file(file_data, config)
    else:
        # 处理URL或本地文件路径
        from pathlib import Path
        import os

        # 检查是否为本地文件路径
        if os.path.exists(url) or Path(url).exists():
            # 本地文件路径
            file_path = Path(url)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail=f"文件不存在: {url}")

            if not file_path.is_file():
                raise HTTPException(status_code=400, detail=f"路径不是文件: {url}")

            # 验证文件类型
            allowed_extensions = {
                ".mp4",
                ".avi",
                ".mov",
                ".mkv",
                ".mp3",
                ".wav",
                ".m4a",
                ".flac",
            }
            file_extension = file_path.suffix.lower()
            if file_extension not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的文件类型: {file_extension}。支持的类型: {', '.join(allowed_extensions)}",
                )

            # 构建文件数据
            file_data = {
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "content_type": "application/octet-stream",
                "type": "local_file",
                "file_path": str(file_path.absolute()),
            }

            # 处理本地文件
            result = await video_service.process_file(file_data, config)
        else:
            # 网络URL
            result = await video_service.process_url(url, config)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return create_success_response(result)


@video_router.get("/{task_id}/stream")
async def get_task_progress_stream(task_id: str):
    """获取任务进度流 (SSE)"""

    async def generate_progress():
        """生成进度数据流"""
        while True:
            try:
                # 获取任务当前状态
                task = await task_service.get_task_by_id("video", task_id)
                if not task:
                    yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                    break

                # 发送当前进度
                progress_data = {
                    "task_id": task_id,
                    "status": task.get("status", "unknown"),
                    "progress": task.get("progress", 0),
                    "current_step": task.get("current_step", ""),
                    "updated_at": task.get("updated_at", ""),
                }

                yield f"data: {json.dumps(progress_data)}\n\n"

                # 如果任务完成或失败，结束流
                if task.get("status") in ["completed", "failed"]:
                    break

                # 等待一段时间再次检查
                await asyncio.sleep(1)

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@video_router.delete("/{task_id}")
async def delete_video_task(task_id: str) -> Dict[str, Any]:
    """删除视频任务"""
    task = await task_service.get_task_by_id("video", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    # 删除任务和相关资源
    success = await task_service.delete_task("video", task_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除任务失败")

    return create_success_response(None, "任务删除成功")
