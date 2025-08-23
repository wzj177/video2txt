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

from ..services.task_service import task_service
from ..services.video_service import video_service

# 创建视频API路由器
video_router = APIRouter(prefix="/api/tasks/video", tags=["video"])


@video_router.get("")
async def get_video_tasks() -> Dict[str, Any]:
    """获取视频任务列表"""
    try:
        tasks = task_service.get_tasks("video")
        return {"success": True, "data": tasks}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@video_router.get("/{task_id}")
async def get_video_task(task_id: str) -> Dict[str, Any]:
    """获取单个视频任务"""
    try:
        task = task_service.get_task_by_id("video", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务未找到")

        return {"success": True, "data": task}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@video_router.get("/stats")
async def get_video_stats() -> Dict[str, Any]:
    """获取视频任务统计"""
    try:
        stats = task_service.get_task_stats("video")
        return {"success": True, "data": stats}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@video_router.post("")
async def create_video_task(
    file: UploadFile = File(None),
    url: str = Form(None),
    language: str = Form("zh"),
    model: str = Form("whisper"),
    output_types: str = Form("transcript,summary"),
) -> Dict[str, Any]:
    """创建视频处理任务"""
    try:
        # 验证输入参数
        if not file and not url:
            raise HTTPException(status_code=400, detail="必须提供文件或URL")

        if file and url:
            raise HTTPException(status_code=400, detail="不能同时提供文件和URL")

        # 解析输出类型
        output_type_list = [t.strip() for t in output_types.split(",") if t.strip()]

        # 构建配置
        config = {
            "language": language,
            "model": model,
            "output_types": output_type_list,
        }

        # 处理文件或URL
        if file:
            # 验证文件类型
            if not file.filename:
                raise HTTPException(status_code=400, detail="文件名不能为空")

            # 构建文件数据
            file_data = {
                "filename": file.filename,
                "size": file.size or 0,
                "content_type": file.content_type,
                "type": "file",
            }

            # 处理文件
            result = await video_service.process_file(file_data, config)
        else:
            # 处理URL
            result = await video_service.process_url(url, config)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {"success": True, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@video_router.get("/{task_id}/stream")
async def get_task_progress_stream(task_id: str):
    """获取任务进度流 (SSE)"""

    async def generate_progress():
        """生成进度数据流"""
        while True:
            try:
                # 获取任务当前状态
                task = task_service.get_task_by_id("video", task_id)
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
    try:
        task = task_service.get_task_by_id("video", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务未找到")

        # 这里应该实现实际的删除逻辑
        # 包括删除任务记录和相关文件

        return {"success": True, "message": "任务删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}
