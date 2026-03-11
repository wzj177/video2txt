#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议监控API路由
"""

from fastapi import (
    APIRouter,
    HTTPException,
    BackgroundTasks,
    Query,
    Body,
    UploadFile,
    File,
    Form,
    Depends,
)
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
import json
import asyncio
import uuid
from datetime import datetime
from pydantic import BaseModel
import logging

from ..services.task_service import task_service
from ..services.realtime_meeting_service import realtime_meeting_service
from ..services.meeting_service import meeting_service
from core.audio import AudioPermissionChecker, SystemAudioCapture
from ..middleware.exception_handler import (
    create_success_response,
    create_error_response,
)

# 配置日志
logger = logging.getLogger(__name__)

meeting_router = APIRouter(prefix="/api/tasks/meeting", tags=["meeting"])


async def get_active_meetings():
    """获取活跃的会议（正在进行或准备中的会议）"""
    try:
        # 获取所有会议任务
        tasks = await task_service.get_tasks("meeting", None, 100)

        # 筛选活跃状态的会议
        active_statuses = [
            "ready",
            "recording",
            "paused",
            "starting_audio",
            "initializing",
        ]
        active_meetings = []

        for task in tasks:
            if task.get("status") in active_statuses:
                meeting_info = {
                    "id": task["id"],
                    "title": task.get("config", {}).get("title", "未命名会议"),
                    "status": task.get("status"),
                    "created_at": task.get("created_at"),
                }
                active_meetings.append(meeting_info)

        return active_meetings
    except Exception as e:
        logger.error(f"获取活跃会议失败: {e}")
        return []


def _parse_json_field(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _build_meeting_metadata(task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = task.get("id")
    results = _parse_json_field(task.get("results"))
    config = _parse_json_field(task.get("config"))
    model_name = config.get("model_name") or ""

    speaker_log = results.get("speaker_log") or []
    segments = results.get("segments") or []
    has_speaker_log = len(speaker_log) > 0

    status = task.get("status") or "pending"
    if has_speaker_log:
        diarization_status = "ready"
    elif status in ["processing", "recording", "starting_audio", "monitoring"]:
        diarization_status = "processing"
    elif status in ["stopped", "cancelled"]:
        diarization_status = "stopped"
    elif status in ["finished", "completed"]:
        diarization_status = "not_generated"
    else:
        diarization_status = "pending"

    fallback = results.get("fallback", False)
    if fallback and diarization_status == "ready":
        diarization_status = "fallback_ready"
    elif fallback and diarization_status == "processing":
        diarization_status = "fallback_processing"

    audio_available = bool(config.get("audio_file_path"))
    links = {
        "speakerLog": f"/api/tasks/meeting/{task_id}/speaker-log" if has_speaker_log else None,
        "bundle": f"/api/tasks/meeting/{task_id}/download",
        "audio": f"/api/tasks/meeting/{task_id}/download-audio" if audio_available else None,
        "audioStream": f"/api/tasks/meeting/{task_id}/audio" if audio_available else None,
    }

    return {
        "results": results,
        "config": config,
        "model_name": model_name,
        "hasSpeakerLog": has_speaker_log,
        "diarization": {
            "status": diarization_status,
            "fallback": fallback,
            "segments": len(segments),
        },
        "links": links,
    }


class MeetingCreateRequest(BaseModel):
    title: str
    audioSource: str = "system"
    engine: str = "sensevoice"
    model_name: Optional[str] = None
    language: str = "auto"
    enableSpeakerDiarization: bool = True


class MeetingUploadRequest(BaseModel):
    title: str
    engine: str = "sensevoice"
    model_name: Optional[str] = None
    language: str = "auto"
    enable_speaker_diarization: bool = True


from ..queue.task_manager import get_task_manager


class MeetingTaskManager:
    """会议任务管理器"""

    @staticmethod
    async def _try_queue_processing(
        task_id: str, task_name: str, args: tuple
    ) -> Optional[Dict[str, Any]]:
        """尝试使用队列处理任务"""
        # 尝试SQLite队列
        sqlite_result = await MeetingTaskManager._try_sqlite_processing(
            task_id, task_name, args
        )
        if sqlite_result:
            return sqlite_result

        # 都不可用
        return None

    @staticmethod
    async def _try_sqlite_processing(
        task_id: str, task_name: str, args: tuple
    ) -> Optional[Dict[str, Any]]:
        """尝试使用SQLite队列处理"""
        try:
            manager = get_task_manager()

            # 确保Worker正在运行
            if not manager.running:
                manager.start_workers(worker_count=1)

            # 提交任务到SQLite队列
            queue_task_id = manager.submit_task(
                task_name=task_name, args=args, queue_name="meeting_processing"
            )

            # 更新任务记录
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "queue_task_id": queue_task_id,
                    "status": "queued",
                    "current_step": "任务已提交到SQLite队列...",
                },
            )

            logger.info(f"✅ 任务已提交到SQLite队列: {task_id}")
            return {
                "task_id": task_id,
                "status": "queued",
                "queue_task_id": queue_task_id,
            }

        except Exception as e:
            logger.debug(f"SQLite队列处理失败: {e}")
            return None

    @staticmethod
    async def _process_uploaded_audio_with_error_handling(
        task_id: str, audio_file_path: str
    ):
        """带错误处理的上传音频处理异步任务"""
        try:
            logger.info(f"🚀 开始异步处理上传音频任务: {task_id}")
            result = await meeting_service.process_uploaded_audio(
                task_id, audio_file_path
            )

            if result:
                logger.info(f"✅ 上传音频任务处理完成: {task_id}")
            else:
                logger.error(f"上传音频任务处理失败: {task_id}")

        except Exception as e:
            logger.error(f"异步上传音频任务执行异常: {task_id}, 错误: {e}")
            # 更新任务状态为失败
            try:
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": "error",
                        "current_step": f"异步处理失败: {str(e)}",
                        "error": str(e),
                        "failed_at": datetime.now().isoformat(),
                    },
                )
            except Exception as update_error:
                logger.error(f"更新任务状态失败: {update_error}")


@meeting_router.post("/upload")
async def upload_meeting_recording(
    audio_file: UploadFile = File(...),
    title: str = Form(...),
    engine: str = Form("sensevoice"),
    model_name: Optional[str] = Form(None),
    language: str = Form("auto"),
    enable_speaker_diarization: bool = Form(True),
):
    """上传会议录音文件进行处理"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 保存上传的音频文件
        from pathlib import Path
        import os

        # 确保目录存在
        upload_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件路径
        file_extension = Path(audio_file.filename).suffix
        saved_file_path = upload_dir / f"meeting_{task_id}{file_extension}"

        # 保存文件
        with open(saved_file_path, "wb") as buffer:
            content = await audio_file.read()
            buffer.write(content)

        # 创建任务配置
        config = {
            "title": title,
            "engine": engine,
            "model_name": model_name,
            "language": language,
            "enable_speaker_diarization": enable_speaker_diarization,
            "audio_file_path": str(saved_file_path),  # 保存音频文件路径
            "created_at": datetime.now().isoformat(),
        }

        # 创建任务
        task_data = {
            "status": "uploaded",
            "progress": 0,
            "current_step": "文件上传完成，等待处理...",
            "config": config,
        }

        await task_service.create_task("meeting", task_data, task_id=task_id)

        # 创建文件记录以支持统一的删除和下载功能
        from biz.database.connection import get_database_manager
        from biz.database.repositories import TaskFileRepository

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            file_repo = TaskFileRepository(session)
            await file_repo.create(
                task_id=task_id,
                task_type="meeting",
                file_type="audio",
                file_name=audio_file.filename,
                file_path=str(saved_file_path),
                file_size=len(content),
                mime_type=audio_file.content_type or "audio/mpeg",
            )
            await session.commit()

        # 尝试使用队列处理
        queue_result = await MeetingTaskManager._try_queue_processing(
            task_id, "process_uploaded_audio", (task_id, str(saved_file_path))
        )

        if queue_result:
            return create_success_response(
                {"task_id": task_id}, "会议录音上传成功，开始处理"
            )

        # 队列不可用，回退到异步处理
        logger.warning("队列系统不可用，回退到异步处理")
        # 创建带错误处理的异步任务
        task = asyncio.create_task(
            MeetingTaskManager._process_uploaded_audio_with_error_handling(
                task_id, str(saved_file_path)
            )
        )

        return create_success_response(
            {"task_id": task_id}, "会议录音上传成功，开始处理"
        )

    except Exception as e:
        logger.error(f"上传会议录音失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传会议录音失败: {str(e)}")


@meeting_router.get("/stats")
async def get_meeting_stats() -> Dict[str, Any]:
    """获取会议任务统计"""
    try:
        stats = await task_service.get_task_stats("meeting")
        return create_success_response(stats, "获取会议统计成功")
    except Exception as e:
        return create_error_response(f"获取会议统计失败: {str(e)}", 500)


@meeting_router.get("/active")
async def get_active_meetings_api() -> Dict[str, Any]:
    """获取当前活跃的会议"""
    try:
        active_meetings = await get_active_meetings()
        return create_success_response(
            {
                "meetings": active_meetings,
                "count": len(active_meetings),
                "hasActive": len(active_meetings) > 0,
            },
            "获取活跃会议成功",
        )
    except Exception as e:
        return create_error_response(f"获取活跃会议失败: {str(e)}", 500)


@meeting_router.get("/audio-permissions")
async def check_audio_permissions() -> Dict[str, Any]:
    """检查音频权限状态"""
    try:
        # 获取系统信息
        system_info = AudioPermissionChecker.get_system_info()

        # 检查麦克风权限
        mic_permission = AudioPermissionChecker.check_microphone_permission()

        # 检查系统音频权限
        system_audio_permission = AudioPermissionChecker.check_system_audio_permission()

        data = {
            "system_info": system_info,
            "microphone": mic_permission,
            "system_audio": system_audio_permission,
            "overall_status": (
                mic_permission.get("granted", False)
                or system_audio_permission.get("granted", False)
            ),
        }
        return create_success_response(data, "音频权限检查完成")
    except Exception as e:
        return create_error_response(f"音频权限检查失败: {str(e)}", 500)


@meeting_router.get("/audio-devices")
async def get_audio_devices() -> Dict[str, Any]:
    """获取可用的音频设备列表"""
    try:
        capture = SystemAudioCapture()
        devices = capture.get_audio_devices()

        # 获取系统音频设备
        system_device_id = capture.get_system_audio_device()
        system_device_info = None
        if system_device_id is not None:
            system_device_info = capture.get_device_info(system_device_id)

        data = {
            "input_devices": devices.get("input", []),
            "output_devices": devices.get("output", []),
            "loopback_devices": devices.get("loopback", []),
            "recommended_system_device": {
                "id": system_device_id,
                "info": system_device_info,
            },
            "total_devices": sum(len(devices.get(k, [])) for k in devices.keys()),
        }
        return create_success_response(data, "获取音频设备列表成功")
    except Exception as e:
        return create_error_response(f"获取音频设备列表失败: {str(e)}", 500)


@meeting_router.get("/permission-help")
async def get_permission_help() -> Dict[str, Any]:
    """获取权限设置帮助信息"""
    try:
        help_info = AudioPermissionChecker.get_permission_help()
        return create_success_response(help_info, "获取权限帮助信息成功")
    except Exception as e:
        return create_error_response(f"获取权限帮助信息失败: {str(e)}", 500)


@meeting_router.post("/create")
async def create_meeting_task(
    request: MeetingCreateRequest,
):
    """创建会议监控任务"""
    try:
        # 检查是否已有活跃的会议
        active_meetings = await get_active_meetings()
        if active_meetings:
            active_meeting = active_meetings[0]
            return create_error_response(
                f"已有会议「{active_meeting.get('title', '未命名会议')}」正在进行中，请先结束当前会议再创建新会议",
                400,
                "ActiveMeetingExists",
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 创建任务配置
        config = {
            "title": request.title,
            "audio_source": request.audioSource,
            "engine": request.engine,
            "model_name": request.model_name,
            "language": request.language,
            "enable_speaker_diarization": request.enableSpeakerDiarization,
            "created_at": datetime.now().isoformat(),
        }

        # 创建任务
        await task_service.create_task(
            "meeting",
            {
                "status": "created",
                "progress": 0,
                "current_step": "准备音频捕获...",
                "config": config,
            },
            task_id=task_id,
        )

        # 启动会议处理器
        success = await realtime_meeting_service.create_meeting_processor(
            task_id, config
        )

        if not success:
            raise HTTPException(status_code=500, detail="启动会议处理器失败")

        return create_success_response({"taskId": task_id}, "会议监控任务创建成功")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会议任务失败: {str(e)}")


@meeting_router.get("/{task_id}/stream")
async def stream_meeting_results(task_id: str):
    """实时推送会议转录结果"""

    async def generate():
        """生成SSE数据流"""
        try:
            # 检查任务是否存在
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'})}\n\n"
                return

            # 获取会议处理器
            processor = realtime_meeting_service.get_meeting_processor(task_id)
            if not processor:
                yield f"data: {json.dumps({'type': 'error', 'message': '会议处理器不存在'})}\n\n"
                return

            # 创建消息队列用于SSE推送
            message_queue = asyncio.Queue()

            # 设置SSE回调
            async def sse_callback(data):
                await message_queue.put(data)

            processor.set_sse_callback(sse_callback)

            # 发送连接成功消息
            yield f"data: {json.dumps({'type': 'connected', 'message': '已连接到会议监控'})}\n\n"

            # 持续推送数据
            while True:
                try:
                    # 检查任务状态
                    current_task = await task_service.get_task_by_id("meeting", task_id)
                    if not current_task or current_task.get("status") in [
                        "stopped",
                        "finished",
                        "error",
                    ]:
                        yield f"data: {json.dumps({'type': 'disconnected', 'message': '监控已停止'})}\n\n"
                        break

                    # 等待消息（带超时）
                    try:
                        message = await asyncio.wait_for(
                            message_queue.get(), timeout=1.0
                        )
                        yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        # 超时时发送心跳
                        yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                        continue

                except Exception as e:
                    logger.error(f"SSE推送错误: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    break

        except Exception as e:
            error_data = {"type": "error", "message": f"推送数据时发生错误: {str(e)}"}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@meeting_router.post("/{task_id}/start-recording")
async def start_meeting_recording(task_id: str):
    """开始会议录制"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 开始录制
        success = await realtime_meeting_service.start_meeting_recording(task_id)

        if success:
            return create_success_response(None, "录制已开始")
        else:
            raise HTTPException(status_code=500, detail="开始录制失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"开始录制失败: {str(e)}")


@meeting_router.post("/{task_id}/pause")
async def pause_meeting_task(task_id: str):
    """暂停会议监控任务"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 暂停会议处理器
        success = await realtime_meeting_service.pause_meeting_processor(task_id)

        if success:
            await task_service.update_task("meeting", task_id, {"status": "paused"})
            return create_success_response(None, "会议监控已暂停")
        else:
            raise HTTPException(status_code=500, detail="暂停会议处理器失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"暂停监控失败: {str(e)}")


@meeting_router.post("/{task_id}/resume")
async def resume_meeting_task(task_id: str):
    """继续会议监控任务"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 继续会议处理器
        success = await realtime_meeting_service.resume_meeting_processor(task_id)

        if success:
            await task_service.update_task("meeting", task_id, {"status": "recording"})
            return create_success_response(None, "会议监控已继续")
        else:
            raise HTTPException(status_code=500, detail="继续会议处理器失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"继续监控失败: {str(e)}")


@meeting_router.post("/{task_id}/stop")
async def stop_meeting_task(task_id: str):
    """停止会议监控任务"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 停止会议处理器
        success = await realtime_meeting_service.stop_meeting_processor(task_id)

        if not success:
            logger.warning(f"停止会议处理器失败: {task_id}")

        # 对于上传/离线任务，若没有处理器也要标记为已停止
        if task.get("status") in [
            "uploaded",
            "queued",
            "processing",
            "recording",
            "paused",
            "starting_audio",
            "monitoring",
        ]:
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "stopped",
                    "progress": 100,
                    "current_step": "用户已停止会议处理",
                    "error": "用户手动停止任务",
                },
            )

        return create_success_response(None, "会议监控已停止")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止监控失败: {str(e)}")


@meeting_router.get("/{task_id}/download")
async def download_meeting_task(task_id: str, background_tasks: BackgroundTasks):
    """下载会议记录（转录+说话人日志+音频）"""
    try:
        from fastapi.responses import FileResponse
        import zipfile
        import tempfile
        import os
        from pathlib import Path
        import shutil

        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        results = task.get("results") or {}
        config = task.get("config") or {}

        transcript_content = results.get("transcript") or ""
        segments = results.get("segments") or []
        speakers = results.get("speakers") or {}
        speaker_log = results.get("speaker_log") or []
        audio_file_path = (
            results.get("audio_file")
            or config.get("audio_file_path")
            or config.get("audioFilePath")
        )

        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"meeting_{task_id}.zip")

        with zipfile.ZipFile(zip_path, "w") as zip_file:
            if transcript_content:
                zip_file.writestr("transcript.txt", transcript_content)

            if segments:
                zip_file.writestr(
                    "segments.json",
                    json.dumps(segments, ensure_ascii=False, indent=2),
                )

            if speaker_log:
                zip_file.writestr(
                    "speaker_log.json",
                    json.dumps(speaker_log, ensure_ascii=False, indent=2),
                )

            if speakers:
                zip_file.writestr(
                    "speakers.json",
                    json.dumps(speakers, ensure_ascii=False, indent=2),
                )

            if audio_file_path and Path(audio_file_path).exists():
                audio_path = Path(audio_file_path)
                zip_file.write(audio_file_path, arcname=audio_path.name)

        background_tasks.add_task(shutil.rmtree, temp_dir, ignore_errors=True)

        return FileResponse(
            zip_path, filename=f"meeting_{task_id}.zip", media_type="application/zip"
        )

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@meeting_router.get("/{task_id}/speaker-log")
async def get_meeting_speaker_log(task_id: str):
    """获取会议的说话人日志"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        results = task.get("results") or {}
        speaker_log = results.get("speaker_log") or []

        if not speaker_log:
            raise HTTPException(status_code=404, detail="还没有生成说话人日志")

        return create_success_response(
            {"speaker_log": speaker_log}, "获取说话人日志成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取说话人日志失败: {str(e)}")


@meeting_router.get("/{task_id}/download-audio")
async def download_meeting_audio(task_id: str):
    """下载会议录制音频文件"""
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        from biz.database.connection import get_database_manager
        from biz.database.repositories import TaskFileRepository

        # 首先从 task_files 表中查找音频文件
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            file_repo = TaskFileRepository(session)
            audio_file = await file_repo.get_by_type(task_id, "audio")

            if audio_file and Path(audio_file.file_path).exists():
                return FileResponse(
                    audio_file.file_path,
                    filename=audio_file.file_name,
                    media_type=audio_file.mime_type or "audio/mpeg",
                )

        # 兼容性：如果 task_files 中没有记录，尝试从任务配置中获取
        task = await task_service.get_task("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        config = task.get("config", {})
        audio_file_path = config.get("audio_file_path")

        if audio_file_path and Path(audio_file_path).exists():
            filename = Path(audio_file_path).name
            return FileResponse(
                audio_file_path, filename=filename, media_type="audio/mpeg"
            )

        raise HTTPException(status_code=404, detail="音频文件不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载音频失败: {str(e)}")


@meeting_router.get("/{task_id}/audio")
async def stream_meeting_audio(task_id: str):
    """流式播放会议音频文件"""
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        from biz.database.connection import get_database_manager
        from biz.database.repositories import TaskFileRepository

        # 首先从 task_files 表中查找音频文件
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            file_repo = TaskFileRepository(session)
            audio_file = await file_repo.get_by_type(task_id, "audio")

            if audio_file and Path(audio_file.file_path).exists():
                # 使用 FileResponse 支持范围请求（Range header）用于音频流播放
                return FileResponse(
                    audio_file.file_path,
                    media_type=audio_file.mime_type or "audio/mpeg",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Cache-Control": "public, max-age=3600",
                    },
                )

        # 兼容性：如果 task_files 中没有记录，尝试从任务配置中获取
        task = await task_service.get_task("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        config = task.get("config", {})
        audio_file_path = config.get("audio_file_path")

        if audio_file_path and Path(audio_file_path).exists():
            return FileResponse(
                audio_file_path,
                media_type="audio/mpeg",
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                },
            )

        raise HTTPException(status_code=404, detail="音频文件不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取音频流失败: {str(e)}")

        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 获取音频文件路径
        audio_path = task.get("config", {}).get("audio_path")
        if not audio_path:
            raise HTTPException(status_code=404, detail="音频文件不存在")

        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise HTTPException(status_code=404, detail="音频文件未找到")

        return FileResponse(
            audio_file, filename=f"meeting_{task_id}.wav", media_type="audio/wav"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载音频失败: {str(e)}")


@meeting_router.delete("/{task_id}")
async def delete_meeting_task(task_id: str):
    """删除会议记录"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 如果任务正在运行，先停止
        if task.get("status") in ["recording", "paused"]:
            await realtime_meeting_service.stop_meeting_processor(task_id)

        # 删除任务
        success = await task_service.delete_task("meeting", task_id)

        if success:
            return create_success_response(None, "会议记录已删除")
        else:
            raise HTTPException(status_code=500, detail="删除任务失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@meeting_router.get("/list")
async def get_meeting_list(
    status: Optional[str] = None,
    date: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    """获取会议列表"""
    try:
        # 获取所有会议任务
        tasks = await task_service.get_tasks(
            "meeting", status, 1000
        )  # 先获取足够多的任务进行筛选

        # 筛选
        filtered_tasks = []
        for task in tasks:
            # 状态筛选
            if status and task.get("status") != status:
                continue

            # 日期筛选
            if date:
                task_date = datetime.fromisoformat(task.get("created_at", "")).date()
                filter_date = datetime.fromisoformat(date).date()
                if task_date != filter_date:
                    continue

            # 关键词筛选
            if keyword:
                title = task.get("config", {}).get("title", "")
                if keyword.lower() not in title.lower():
                    continue

            metadata = _build_meeting_metadata(task)
            results = metadata["results"]
            segments = results.get("segments", [])
            speakers = results.get("speakers", {})
            transcript = results.get("transcript", "")
            speaker_log = results.get("speaker_log", [])

            # 计算情感分布
            emotion_stats = {}
            if segments:
                for segment in segments:
                    emotion = segment.get("emotion", "neutral")
                    emotion_stats[emotion] = emotion_stats.get(emotion, 0) + 1

            meeting = {
                "id": task["id"],
                "title": task["name"],
                "startTime": task.get("created_at"),
                "status": task.get("status", "unknown"),
                "duration": task.get("duration"),
                "model_name": metadata.get("model_name", ""),
                "stats": {
                    "transcriptLength": len(transcript),
                    "speakers": len(speakers),
                    "segments": len(segments),
                    "emotions": emotion_stats,
                    "hasAnalysis": bool(segments and len(segments) > 0),
                    "hasSpeakerLog": metadata["hasSpeakerLog"],
                    "diarizationStatus": metadata["diarization"]["status"],
                },
                # 添加预览数据
                "preview": {
                    "firstSegment": (
                        segments[0].get("text", "")[:100] + "..." if segments else ""
                    ),
                    "dominantEmotion": (
                        max(emotion_stats.items(), key=lambda x: x[1])[0]
                        if emotion_stats
                        else "neutral"
                    ),
                    "mainSpeakers": (
                        list(speakers.keys())[:3] if speakers else ["Speaker_1"]
                    ),
                    "speakerLogSample": speaker_log[:3] if speaker_log else [],
                },
                "results": results,
                "config": metadata["config"],
                "hasSpeakerLog": metadata["hasSpeakerLog"],
                "diarization": metadata["diarization"],
                "links": metadata["links"],
            }
            filtered_tasks.append(meeting)

        # 排序（最新的在前）
        filtered_tasks.sort(key=lambda x: x["startTime"], reverse=True)

        # 分页
        total = len(filtered_tasks)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_tasks = filtered_tasks[start:end]

        result_data = {
            "meetings": paginated_tasks,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total,
                "totalPages": (total + page_size - 1) // page_size,
            },
        }
        return create_success_response(result_data, "获取会议列表成功")
    except Exception as e:
        return create_error_response(f"获取会议列表失败: {str(e)}", 500)


@meeting_router.get("/{task_id}")
async def get_meeting_task(task_id: str):
    """获取会议任务状态"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        metadata = _build_meeting_metadata(task)
        enriched_task = dict(task)
        enriched_task.update(
            {
                "results": metadata["results"],
                "config": metadata["config"],
                "model_name": metadata.get("model_name", ""),
                "hasSpeakerLog": metadata["hasSpeakerLog"],
                "diarization": metadata["diarization"],
                "links": metadata["links"],
            }
        )

        return create_success_response(enriched_task, "获取会议任务成功")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务失败: {str(e)}")


@meeting_router.post("/{task_id}/speaker-log")
async def generate_meeting_speaker_log(task_id: str):
    """生成说话人日志"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        results = _parse_json_field(task.get("results"))
        if results.get("speaker_log"):
            return create_success_response(None, "说话人日志已存在")

        queue_result = await MeetingTaskManager._try_queue_processing(
            task_id, "process_meeting_speaker_log", (task_id,)
        )
        if queue_result:
            return create_success_response(None, "已开始生成说话人日志")

        asyncio.create_task(meeting_service.generate_speaker_log(task_id))
        return create_success_response(None, "已开始生成说话人日志")

    except Exception as e:
        return create_error_response(f"生成说话人日志失败: {str(e)}", 500)


@meeting_router.post("/{task_id}/export-transcript-word")
async def export_transcript_to_word(task_id: str):
    """导出会议转录为Word文档"""
    try:
        from pathlib import Path
        import tempfile
        from fastapi.responses import FileResponse

        # 获取会议任务
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 获取转录数据
        results = task.get("results", {})
        segments = results.get("segments", [])
        speakers = results.get("speakers", {})

        if not segments:
            raise HTTPException(status_code=400, detail="暂无转录内容")

        # 构建Markdown内容
        md_content = f"# {task.get('name', '会议记录')}\n\n"
        md_content += "## 会议信息\n\n"
        md_content += f"- **日期**: {task.get('created_at', '')}\n"

        if task.get("total_duration"):
            mins = int(task["total_duration"] // 60)
            secs = int(task["total_duration"] % 60)
            md_content += f"- **时长**: {mins}分{secs}秒\n"

        if task.get("speaker_count"):
            md_content += f"- **说话人数**: {task['speaker_count']}\n"

        md_content += "\n---\n\n## 会议转录\n\n"

        # 添加每条转录
        for segment in segments:
            start_time = segment.get("start", 0)
            mins = int(start_time // 60)
            secs = int(start_time % 60)
            time_str = f"{mins:02d}:{secs:02d}"

            speaker_id = segment.get("speaker", "")
            speaker_name = speaker_id
            if speaker_id and speakers.get(speaker_id):
                speaker_name = speakers[speaker_id].get("name", speaker_id)

            if speaker_name:
                md_content += (
                    f"**[{time_str}] {speaker_name}**: {segment.get('text', '')}\n\n"
                )
            else:
                md_content += f"**[{time_str}]**: {segment.get('text', '')}\n\n"

        # 创建临时Markdown文件
        temp_dir = Path(tempfile.gettempdir())
        md_file = temp_dir / f"meeting_transcript_{task_id}.md"
        docx_file = temp_dir / f"meeting_transcript_{task_id}.docx"

        # 写入Markdown内容
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 检查pandoc是否可用
        try:
            import subprocess

            result = subprocess.run(
                ["pandoc", "--version"], capture_output=True, timeout=5
            )
            pandoc_available = result.returncode == 0
        except:
            pandoc_available = False

        if not pandoc_available:
            # 如果pandoc不可用，返回HTML格式的Word
            # 先转换Markdown内容为HTML
            html_body = (
                md_content.replace("# ", "<h1>")
                .replace("## ", "<h2>")
                .replace("\n\n", "</p><p>")
                .replace("**", "<strong>", 1)
                .replace("**", "</strong>", 1)
            )

            # 构建完整的HTML文档
            html_content = f"""
            <html xmlns:o='urn:schemas-microsoft-com:office:office' 
                  xmlns:w='urn:schemas-microsoft-com:office:word' 
                  xmlns='http://www.w3.org/TR/REC-html40'>
            <head>
                <meta charset='utf-8'>
                <title>会议转录</title>
                <style>
                    body {{ font-family: 'Microsoft YaHei', 'SimSun', sans-serif; line-height: 1.6; }}
                    h1 {{ color: #00B26A; border-bottom: 2px solid #00B26A; padding-bottom: 10px; }}
                    h2 {{ color: #00A1D6; margin-top: 20px; }}
                    .meta {{ color: #666; margin-bottom: 20px; }}
                    .segment {{ margin-bottom: 10px; }}
                    .time {{ color: #00A1D6; font-weight: bold; }}
                    .speaker {{ color: #00B26A; font-weight: bold; }}
                </style>
            </head>
            <body>
                {html_body}
            </body>
            </html>
            """

            with open(docx_file.with_suffix(".doc"), "wb") as f:
                f.write(("\ufeff" + html_content).encode("utf-8"))

            return FileResponse(
                docx_file.with_suffix(".doc"),
                filename=f"会议转录_{task.get('name', task_id)}.doc",
                media_type="application/msword",
            )

        # 使用pandoc转换
        import subprocess
        import asyncio

        process = await asyncio.create_subprocess_exec(
            "pandoc",
            str(md_file),
            "-o",
            str(docx_file),
            "--standalone",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0 or not docx_file.exists():
            raise HTTPException(status_code=500, detail="Word文档生成失败")

        # 返回Word文件
        return FileResponse(
            docx_file,
            filename=f"会议转录_{task.get('name', task_id)}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出会议转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


class UpdateSpeakerRequest(BaseModel):
    update_speaker: Dict[str, Any]


@meeting_router.put("/{task_id}")
async def update_meeting_task(task_id: str, request: UpdateSpeakerRequest):
    """更新会议任务信息（如发言人名称）"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 更新发言人信息
        if "update_speaker" in request.dict():
            speaker_update = request.update_speaker
            speaker_id = speaker_update.get("speaker_id")
            new_name = speaker_update.get("name")

            if not speaker_id or not new_name:
                raise HTTPException(status_code=400, detail="缺少必要参数")

            # 获取当前的 results
            results = task.get("results", {})
            speakers = results.get("speakers", {})

            # 更新发言人名称
            if speaker_id in speakers:
                speakers[speaker_id]["name"] = new_name

                # 更新任务
                await task_service.update_task("meeting", task_id, {"results": results})

                return create_success_response(None, "发言人信息更新成功")
            else:
                raise HTTPException(status_code=404, detail="发言人不存在")

        return create_error_response("未提供更新内容", 400)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")


@meeting_router.post("/api/system/audio/test")
async def test_audio_capture(captureMode: str = "system"):
    """测试音频捕获"""
    try:
        # 导入音频捕获模块
        import sys
        from pathlib import Path

        PROJECT_ROOT = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(PROJECT_ROOT))

        from core.audio.audio_capture import AudioCapture

        # 创建音频捕获器
        audio_capture = AudioCapture()

        # 获取设备列表
        devices_info = audio_capture.list_audio_devices()

        # 执行音频测试
        test_result = audio_capture.test_capture(duration=2.0)

        if test_result["success"]:
            data = {
                "backend": test_result["backend"],
                "device": test_result["device"],
                "sampleRate": f"{test_result['sample_rate']} Hz",
                "avgVolume": test_result.get("avg_volume", 0),
                "maxVolume": test_result.get("max_volume", 0),
                "samples": test_result.get("samples", 0),
                "availableDevices": len(devices_info.get("devices", [])),
            }
            return create_success_response(data, "音频设备测试成功")
        else:
            error_data = {
                "backend": test_result["backend"],
                "error": test_result.get("error", "未知错误"),
            }
            return create_error_response(
                f"音频测试失败: {test_result.get('error', '未知错误')}", 500
            )

    except Exception as e:
        logger.error(f"音频测试异常: {e}")
        return create_error_response(f"音频测试失败: {str(e)}", 500)


@meeting_router.post("/request-permissions")
async def request_audio_permissions() -> Dict[str, Any]:
    """主动触发权限申请"""
    try:
        result = AudioPermissionChecker.request_microphone_permission()

        if result.get("success", False):
            data = {
                "permission_dialog_triggered": result.get(
                    "permission_dialog_triggered", False
                ),
                "error": result.get("error"),
            }
            return create_success_response(
                data, "权限申请已触发，请在系统对话框中允许访问"
            )
        else:
            return create_error_response(result.get("error", "权限申请失败"), 400)
    except Exception as e:
        return create_error_response(f"权限申请失败: {str(e)}", 500)


@meeting_router.post("/test-audio-capture")
async def test_audio_capture_new(
    device_id: Optional[int] = None, duration: float = 2.0
) -> Dict[str, Any]:
    """测试音频捕获功能"""
    try:
        capture = SystemAudioCapture()

        if device_id is None:
            device_id = capture.get_system_audio_device()

        if device_id is None:
            return create_error_response("未找到可用的音频设备", 400)

        # 获取设备信息
        device_info = capture.get_device_info(device_id)

        # 测试音频捕获
        test_result = {
            "success": False,
            "samples_captured": 0,
            "average_volume": 0.0,
            "max_volume": 0.0,
            "error": None,
        }

        import numpy as np
        import threading
        import time

        samples = []
        capture_error = None

        def audio_callback(data):
            nonlocal samples, capture_error
            try:
                samples.append(data.copy())
            except Exception as e:
                capture_error = str(e)

        # 开始短暂的音频捕获测试
        if capture.start_capture(audio_callback, device_id):
            time.sleep(duration)
            capture.stop_capture()

            if capture_error:
                test_result["error"] = capture_error
            elif samples:
                all_samples = np.concatenate(samples)
                test_result["success"] = True
                test_result["samples_captured"] = len(all_samples)
                test_result["average_volume"] = float(np.mean(np.abs(all_samples)))
                test_result["max_volume"] = float(np.max(np.abs(all_samples)))
            else:
                test_result["error"] = "未捕获到音频数据"
        else:
            test_result["error"] = "无法启动音频捕获"

        if test_result["success"]:
            data = {
                "device_id": device_id,
                "device_info": device_info,
                "test_duration": duration,
                "samples_captured": test_result["samples_captured"],
                "average_volume": test_result["average_volume"],
                "max_volume": test_result["max_volume"],
            }
            return create_success_response(data, "音频捕获测试成功")
        else:
            return create_error_response(
                test_result.get("error", "音频捕获测试失败"), 500
            )

    except Exception as e:
        return create_error_response(f"音频捕获测试失败: {str(e)}", 500)
