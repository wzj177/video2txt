#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 视频处理API路由
"""
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import StreamingResponse, FileResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import asyncio
import time
from pathlib import Path
import weakref
from collections import defaultdict
from datetime import datetime

from ..services.task_service import task_service
from ..services.video_service import video_service
from ..middleware.exception_handler import (
    create_success_response,
    create_error_response,
)

# 配置日志
logger = logging.getLogger(__name__)
# 创建视频API路由器
video_router = APIRouter(prefix="/api/tasks/video", tags=["video"])

# 全局流式事件存储
_streaming_events = defaultdict(list)


class TranscriptUpdateRequest(BaseModel):
    """转录文本更新请求模型"""

    transcript: str


class SegmentationRequest(BaseModel):
    """文本分段请求模型"""

    text: str
    method: str = "auto"  # auto, basic, ai, hybrid


async def push_streaming_event(task_id: str, event_type: str, data: dict):
    """推送流式事件到指定任务"""
    event = {"event": event_type, "data": data, "timestamp": time.time()}
    _streaming_events[task_id].append(event)

    # 限制事件数量，避免内存泄漏
    if len(_streaming_events[task_id]) > 100:
        _streaming_events[task_id] = _streaming_events[task_id][-50:]


@video_router.get("")
async def get_video_tasks(status: str = None) -> Dict[str, Any]:
    """获取视频任务列表"""
    # 传递状态参数给服务层
    filter_status = status if status and status != "all" else None
    tasks = await task_service.get_tasks("av", status=filter_status)
    return create_success_response(tasks)


@video_router.get("/stats")
async def get_video_stats() -> Dict[str, Any]:
    """获取视频任务统计"""
    stats = await task_service.get_task_stats("av")
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
    task = await task_service.get_task_by_id("av", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    return create_success_response(task)


@video_router.put("/{task_id}/transcript")
async def update_transcript(
        task_id: str, request: TranscriptUpdateRequest
) -> Dict[str, Any]:
    """更新任务的转录文本"""
    try:
        # 获取任务
        task = await task_service.get_task_by_id("av", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务未找到")

        # 获取新的转录文本
        new_transcript = request.transcript
        if not new_transcript.strip():
            raise HTTPException(status_code=400, detail="转录文本不能为空")

        # 更新任务结果
        results = task.get("results", {})
        results["transcript"] = new_transcript.strip()

        # 保存到数据库
        await task_service.update_task(
            "av",
            task_id,
            {"results": results, "updated_at": datetime.now().isoformat()},
        )

        return create_success_response(
            {"message": "转录文本更新成功", "transcript": new_transcript.strip()}
        )

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"更新转录文本失败: {e}")
        return create_error_response(f"更新失败: {str(e)}")


@video_router.post("/segment-text")
async def segment_text(request: SegmentationRequest) -> Dict[str, Any]:
    """对文本进行智能分段"""
    try:
        from ..services.text_segmentation import segment_transcript
        import json

        # 加载settings.json
        settings_path = Path(__file__).parent.parent.parent / "config" / "settings.json"
        settings = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"加载settings.json失败: {e}")

        # 进行文本分段
        from ..services.text_segmentation import get_segmentation_service

        service = get_segmentation_service(settings)
        segments = service.segment_text(request.text, request.method)

        # 转换为字典格式
        segments_dict = [
            {
                "text": seg.text,
                "start_index": seg.start_index,
                "end_index": seg.end_index,
                "segment_type": seg.segment_type,
                "confidence": seg.confidence,
                "length": len(seg.text),
                "metadata": seg.metadata or {},
            }
            for seg in segments
        ]

        return create_success_response(
            {
                "segments": segments_dict,
                "total_segments": len(segments_dict),
                "method_used": request.method,
                "total_length": len(request.text),
            }
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"文本分段失败: {e}")
        return create_error_response(f"分段失败: {str(e)}")


@video_router.get("/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """SSE实时进度流"""
    # 验证任务存在
    task = await task_service.get_task_by_id("av", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    async def event_generator():
        """SSE事件生成器"""
        last_status = None
        last_progress = None

        while True:
            try:
                # 获取最新任务状态
                current_task = await task_service.get_task_by_id("av", task_id)
                if not current_task:
                    break

                # 检查状态变化
                if (
                        current_task.get("status") != last_status
                        or current_task.get("progress") != last_progress
                ):
                    # 发送进度更新事件
                    progress_data = {
                        "progress": current_task.get("progress", 0),
                        "status": current_task.get("status", "pending"),
                        "current_step": current_task.get("current_step", "准备中..."),
                    }
                    yield {
                        "event": "progress",
                        "data": json.dumps(progress_data, ensure_ascii=False),
                    }

                    last_status = current_task.get("status")
                    last_progress = current_task.get("progress")

                # 如果任务完成，发送完成事件并退出
                if current_task.get("status") in ["completed", "failed"]:
                    if current_task.get("status") == "completed":
                        complete_data = {
                            "results": current_task.get("results", {}),
                            "output_files": current_task.get("output_files", []),
                        }
                        yield {
                            "event": "complete",
                            "data": json.dumps(complete_data, ensure_ascii=False),
                        }
                    else:
                        error_data = {
                            "error": current_task.get("error", "处理失败"),
                            "current_step": current_task.get(
                                "current_step", "处理失败"
                            ),
                        }
                        yield {
                            "event": "error",
                            "data": json.dumps(error_data, ensure_ascii=False),
                        }
                    break

                # 等待1秒后继续检查
                await asyncio.sleep(1)

            except Exception as e:
                # 发送错误事件
                error_data = {"error": f"获取任务状态失败: {str(e)}"}
                yield {
                    "event": "error",
                    "data": json.dumps(error_data, ensure_ascii=False),
                }
                break

    return EventSourceResponse(event_generator())


@video_router.post("")
async def create_video_task(
        file: UploadFile = File(None),
        url: str = Form(None),
        name: str = Form(None),
        language: str = Form("zh"),
        model: str = Form("whisper"),
        model_size: str = Form("small"),
        output_types: str = Form("transcript,summary"),
        ai_output_types: str = Form(""),
        force_sync: bool = Form(False),
        ai_correction: bool = Form(False),
        content_role: str = Form("auto"),
        ai_enhancement: bool = Form(False),
) -> Dict[str, Any]:
    """创建视频处理任务"""
    # 验证输入参数
    if not file and not url:
        raise HTTPException(status_code=400, detail="必须提供文件或URL")

    if file and url:
        raise HTTPException(status_code=400, detail="不能同时提供文件和URL")

    # 解析输出类型
    output_type_list = [t.strip() for t in output_types.split(",") if t.strip()]

    # 解析AI输出类型
    ai_output_type_list = []
    if ai_output_types:
        ai_output_type_list = [
            t.strip() for t in ai_output_types.split(",") if t.strip()
        ]

    # 检查模型可用性
    from core.asr import get_available_engines

    available_engines = get_available_engines()

    # 智能模型选择逻辑
    if model == "auto":
        if not available_engines:
            raise HTTPException(status_code=400, detail="没有可用的语音识别引擎")

        # 基于语言智能推荐最佳模型
        model = _select_best_model_for_language(language, available_engines)

    elif model not in available_engines:
        raise HTTPException(status_code=400, detail=f"语音识别引擎 {model} 不可用")

    # 构建配置
    config = {
        "name": name,
        "language": language,
        "model": model,
        "model_size": model_size,
        "output_types": output_type_list,
        "ai_output_types": ai_output_type_list,
        "force_sync": force_sync,
        "ai_correction": ai_correction,
        "content_role": content_role,
        "ai_enhancement": ai_enhancement,
    }

    # debug config to log
    logger.debug(f"视频处理配置: {config}")

    # 处理文件或URL
    if file:
        # 验证文件类型
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        # 保存上传的文件到项目uploads目录
        import shutil
        from pathlib import Path

        # 获取项目根目录
        PROJECT_ROOT = Path(__file__).parent.parent.parent
        uploads_dir = PROJECT_ROOT / "data" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        file_extension = Path(file.filename).suffix
        upload_file_path = uploads_dir / f"upload_{int(time.time())}{file_extension}"

        # 流式保存文件（支持大文件）
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        with open(upload_file_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)

        # 步骤1: 基本验证（快速）
        await validate_media_file_basic(str(upload_file_path), file.filename)

        # 步骤2: 完整验证（必要，确保文件可用）
        validation_result = await validate_media_file_full(
            str(upload_file_path), file.filename
        )
        if not validation_result["valid"]:
            # 验证失败，删除上传文件并返回错误
            upload_file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=validation_result["error"])

        # 构建文件数据
        file_data = {
            "filename": file.filename,
            "size": file_size,
            "content_type": file.content_type,
            "type": "file",
            "file_path": str(upload_file_path),
            "validation_info": validation_result["info"],  # 传递验证信息，避免重复验证
        }

        # 处理文件（自动选择异步或同步模式）
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

            # 步骤1: 基本验证：文件大小和类型
            await validate_media_file_basic(str(file_path), file_path.name)

            # 步骤2: 完整验证（必要，确保文件可用）：音视频ffprobe
            validation_result = await validate_media_file_full(
                str(file_path), file_path.name
            )
            if not validation_result["valid"]:
                raise HTTPException(status_code=400, detail=validation_result["error"])

            # 构建文件数据
            file_data = {
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "content_type": "application/octet-stream",
                "type": "local_file",
                "file_path": str(file_path.absolute()),
                "validation_info": validation_result[
                    "info"
                ],  # 传递验证信息，避免重复验证
            }

            # 处理本地文件（自动选择异步或同步模式）
            result = await video_service.process_file(file_data, config)
        else:
            # 网络URL - 自动选择异步或同步模式
            result = await video_service.process_url(url, config)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return create_success_response(result)


@video_router.get("/{task_id}/stream")
async def get_task_progress_stream(task_id: str):
    """获取任务进度流 (SSE)"""

    async def generate_progress():
        """生成进度数据流"""
        last_event_count = 0

        while True:
            try:
                # 获取任务当前状态
                task = await task_service.get_task_by_id("av", task_id)
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

                yield f"event: progress\ndata: {json.dumps(progress_data)}\n\n"

                # 发送AI流式事件
                task_events = _streaming_events.get(task_id, [])
                if len(task_events) > last_event_count:
                    # 发送新的AI事件
                    for event in task_events[last_event_count:]:
                        yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                    last_event_count = len(task_events)

                # 如果任务完成或失败，发送完成事件并结束流
                if task.get("status") in ["completed", "failed"]:
                    completion_data = {
                        "task_id": task_id,
                        "status": task.get("status"),
                        "results": task.get("results", {}),
                        "output_files": task.get("results", {}).get("files", []),
                    }
                    yield f"event: complete\ndata: {json.dumps(completion_data)}\n\n"

                    # 清理该任务的事件
                    if task_id in _streaming_events:
                        del _streaming_events[task_id]
                    break

                # 等待一段时间再次检查
                await asyncio.sleep(1)

            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
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
    task = await task_service.get_task_by_id("av", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    # 如果任务正在运行，尝试取消任务
    if task.get("status") in ["queued", "running"]:
        try:
            # 尝试取消Celery任务
            if task.get("celery_task_id"):
                from app.celery_config import celery_app

                celery_app.control.revoke(task["celery_task_id"], terminate=True)

            # 尝试取消SQLite队列任务
            if task.get("queue_task_id"):
                from ..queue.task_manager import get_task_manager

                manager = get_task_manager()
                manager.cancel_task(task["queue_task_id"])

        except Exception as e:
            # 取消失败不影响删除操作
            logger.warning(f"取消任务失败: {e}")
            pass

    # 删除任务和相关资源
    success = await task_service.delete_task("av", task_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除任务失败")

    return create_success_response(None, "任务删除成功")


@video_router.post("/{task_id}/cancel")
async def cancel_video_task(task_id: str) -> Dict[str, Any]:
    """取消视频任务"""
    task = await task_service.get_task_by_id("av", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    # 只有排队中或运行中的任务可以取消
    if task.get("status") not in ["queued", "running"]:
        raise HTTPException(status_code=400, detail="任务不能取消")

    # 取消队列任务
    cancelled = False
    cancel_error = None

    try:
        # 尝试取消Celery任务
        if task.get("celery_task_id"):
            from app.celery_config import celery_app

            celery_app.control.revoke(task["celery_task_id"], terminate=True)
            cancelled = True

        # 尝试取消SQLite队列任务
        elif task.get("queue_task_id"):
            from ..queue.task_manager import get_task_manager

            manager = get_task_manager()
            manager.cancel_task(task["queue_task_id"])
            cancelled = True

        if cancelled:
            # 更新任务状态
            await task_service.update_task(
                "av",
                task_id,
                {
                    "status": "cancelled",
                    "current_step": "任务已取消",
                    "error": "用户取消了任务",
                },
            )

            return create_success_response(None, "任务已取消")
        else:
            raise HTTPException(status_code=400, detail="无法取消任务：任务不在队列中")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")


async def validate_media_file_basic(file_path: str, filename: str) -> None:
    """基本文件验证（快速，同步执行）"""
    from pathlib import Path

    # 检查文件是否存在
    if not Path(file_path).exists():
        raise HTTPException(status_code=400, detail=f"文件不存在: {filename}")

    # 检查文件大小
    file_size = Path(file_path).stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=400, detail=f"文件为空: {filename}")

    # 检查文件大小限制（例如500MB）
    max_size = 500 * 1024 * 1024  # 500MB
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大: {filename} ({file_size / 1024 / 1024:.1f}MB)。最大支持 {max_size / 1024 / 1024}MB",
        )

    # 检查文件扩展名
    file_extension = Path(filename).suffix.lower()
    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
    audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}

    if (
            file_extension not in video_extensions
            and file_extension not in audio_extensions
    ):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_extension}。支持的格式: {', '.join(video_extensions | audio_extensions)}",
        )


async def validate_media_file_full(file_path: str, filename: str) -> dict:
    """完整的媒体文件验证（耗时，异步执行）- 返回验证结果而不抛出异常"""
    from pathlib import Path
    import subprocess
    import json

    try:
        # 使用ffprobe验证文件格式和内容
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {
                "valid": False,
                "error": f"文件格式无效或损坏: {filename}。FFprobe错误: {result.stderr}",
            }

        # 解析文件信息
        try:
            probe_data = json.loads(result.stdout)
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])

            if not streams:
                return {"valid": False, "error": f"文件不包含有效的媒体流: {filename}"}

            # 检查是否有音频流（用于语音识别）
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
            video_streams = [s for s in streams if s.get("codec_type") == "video"]

            if not audio_streams:
                if video_streams:
                    return {
                        "valid": False,
                        "error": f"视频文件 '{filename}' 不包含音频流，无法进行语音识别。请上传包含音频的视频文件或音频文件。",
                    }
                else:
                    return {
                        "valid": False,
                        "error": f"文件 '{filename}' 不包含音频内容，无法进行语音识别。",
                    }

            # 检查音频流质量
            if audio_streams:
                audio_info = audio_streams[0]
                duration = float(format_info.get("duration", 0))

                if duration > 0 and duration < 0.1:  # 少于0.1秒
                    return {
                        "valid": False,
                        "error": f"音频文件太短 (时长: {duration:.2f}秒)，无法进行有效的语音识别。",
                    }

                # 检查采样率
                sample_rate = audio_info.get("sample_rate")
                if sample_rate and int(sample_rate) < 8000:
                    return {
                        "valid": False,
                        "error": f"音频采样率过低 ({sample_rate}Hz)，建议使用8kHz以上的音频文件。",
                    }

            # 验证通过，返回文件信息
            return {
                "valid": True,
                "info": {
                    "duration": format_info.get("duration", "unknown"),
                    "format": format_info.get("format_name", "unknown"),
                    "audio_streams": len(audio_streams),
                    "video_streams": len(video_streams),
                    "audio_info": audio_streams[0] if audio_streams else None,
                },
            }

        except json.JSONDecodeError:
            return {"valid": False, "error": f"无法解析文件信息: {filename}"}

    except subprocess.TimeoutExpired:
        return {
            "valid": False,
            "error": f"文件验证超时: {filename}。文件可能过大或损坏。",
        }
    except Exception as e:
        return {"valid": False, "error": f"文件验证失败: {str(e)}"}


def _select_best_model_for_language(language: str, available_engines: List[str]) -> str:
    """
    基于语言智能推荐最佳模型

    Args:
        language: 语言代码 ('zh', 'en', 'auto', 'dialect')
        available_engines: 可用的引擎列表

    Returns:
        推荐的模型名称
    """
    # 定义语言到模型的优先级映射 (与前端保持一致)
    language_model_priority = {
        "zh": ["sensevoice", "whisper", "faster_whisper"],  # 中文优先SenseVoice
        "en": [
            "faster_whisper",
            "whisper",
            "sensevoice",
        ],  # 英文优先Faster-Whisper (速度快)
        "dialect": ["dolphin", "sensevoice", "whisper"],  # 方言优先Dolphin
        "auto": [
            "sensevoice",
            "faster_whisper",
            "whisper",
            "dolphin",
        ],  # 自动检测的通用优先级
    }

    # 获取该语言的优先级列表
    priority_list = language_model_priority.get(
        language, language_model_priority["auto"]
    )

    # 按优先级查找第一个可用的模型
    for model in priority_list:
        if model in available_engines:
            return model

    # 如果没有找到优先推荐的模型，返回第一个可用的
    if available_engines:
        return available_engines[0]

    # 理论上不应该到达这里，因为上层已经检查了available_engines非空
    raise HTTPException(status_code=400, detail="没有可用的语音识别引擎")


@video_router.get("/{task_id}/files/{file_name:path}")
async def download_output_file(task_id: str, file_name: str):
    """下载任务输出文件"""
    try:
        # 获取项目根目录
        PROJECT_ROOT = Path(__file__).parent.parent.parent

        # 构建文件路径
        file_path = PROJECT_ROOT / "data" / "outputs" / task_id / file_name

        # 检查文件是否存在
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_name}")

        # 检查文件是否在允许的目录内（安全检查）
        outputs_dir = PROJECT_ROOT / "data" / "outputs"
        try:
            file_path.resolve().relative_to(outputs_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="访问被拒绝")

        # 返回文件
        return FileResponse(
            path=str(file_path),
            filename=file_name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")


@video_router.get("/{task_id}/images/{image_path:path}")
async def serve_task_image(task_id: str, image_path: str):
    """为任务提供图片流服务"""
    try:
        # 获取项目根目录
        PROJECT_ROOT = Path(__file__).parent.parent.parent

        # 构建图片文件路径
        image_file_path = PROJECT_ROOT / "data" / "outputs" / task_id / image_path

        # 检查文件是否存在
        if not image_file_path.exists():
            raise HTTPException(status_code=404, detail=f"图片不存在: {image_path}")

        # 检查文件是否在允许的目录内（安全检查）
        outputs_dir = PROJECT_ROOT / "data" / "outputs"
        try:
            image_file_path.resolve().relative_to(outputs_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="访问被拒绝")

        # 确定媒体类型
        media_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            media_type = "image/png"
        elif image_path.lower().endswith(".gif"):
            media_type = "image/gif"
        elif image_path.lower().endswith(".webp"):
            media_type = "image/webp"

        # 返回图片文件流
        return FileResponse(
            path=str(image_file_path),
            media_type=media_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载图片失败: {str(e)}")


@video_router.get("/{task_id}/outputs")
async def list_output_files(task_id: str):
    """列出任务的输出文件"""
    try:
        # 获取项目根目录
        PROJECT_ROOT = Path(__file__).parent.parent.parent

        # 构建输出目录路径
        output_dir = PROJECT_ROOT / "data" / "outputs" / task_id

        # 检查目录是否存在
        if not output_dir.exists():
            raise HTTPException(
                status_code=404, detail=f"任务输出目录不存在: {task_id}"
            )

        # 列出所有文件（包括子目录中的文件）
        files = []

        def scan_directory(directory, prefix=""):
            for file_path in directory.iterdir():
                if file_path.is_file():
                    name = f"{prefix}{file_path.name}" if prefix else file_path.name
                    files.append(
                        {
                            "name": name,
                            "size": file_path.stat().st_size,
                            "modified": file_path.stat().st_mtime,
                            "download_url": f"/api/tasks/video/{task_id}/files/{name}",
                        }
                    )
                elif file_path.is_dir():
                    # 递归扫描子目录
                    scan_directory(file_path, f"{prefix}{file_path.name}/")

        scan_directory(output_dir)

        return create_success_response(data=files)

    except HTTPException:
        raise
    except Exception as e:
        return create_error_response(f"获取文件列表失败: {str(e)}")


@video_router.post("/{task_id}/export-word")
async def export_md_to_word(
        task_id: str, file_name: str = Body(..., embed=True)
) -> Dict[str, Any]:
    """导出MD文件为word"""
    try:
        # 检查任务是否存在
        task = await task_service.get_task_by_id("av", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务未找到")

        # 导入word导出服务
        from ..services.doc_export_service import word_export_service

        # 执行word导出
        result = await word_export_service.export_md_to_word(task_id, file_name)

        if result["success"]:
            return create_success_response(result["data"], "word导出成功")
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"word导出失败: {e}")
        return create_error_response(f"word导出失败: {str(e)}")


@video_router.get("/{task_id}/status")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """获取任务状态（用于调试）"""
    try:
        task = await task_service.get_task_by_id("av", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务未找到")

        # 检查Celery任务状态（如果有）
        celery_status = None
        if task.get("celery_task_id"):
            try:
                from app.celery_config import celery_app

                celery_task = celery_app.AsyncResult(task["celery_task_id"])
                celery_status = {
                    "task_id": task["celery_task_id"],
                    "status": celery_task.status,
                    "result": celery_task.result,
                    "traceback": celery_task.traceback,
                }
            except Exception as e:
                celery_status = {"error": f"获取Celery状态失败: {e}"}

        # 检查SQLite队列状态（如果有）
        sqlite_status = None
        if task.get("queue_task_id"):
            try:
                from ..queue.task_manager import TaskManager

                manager = TaskManager()
                queue_task = manager.get_task_status(task["queue_task_id"])
                sqlite_status = {
                    "task_id": task["queue_task_id"],
                    "status": queue_task.get("status") if queue_task else "not_found",
                    "details": queue_task,
                }
            except Exception as e:
                sqlite_status = {"error": f"获取SQLite队列状态失败: {e}"}

        return {
            "success": True,
            "data": {
                "task": task,
                "celery_status": celery_status,
                "sqlite_status": sqlite_status,
                "monitoring_url": f"/api/tasks/video/{task_id}/stream",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        return create_error_response(f"获取任务状态失败: {str(e)}")
