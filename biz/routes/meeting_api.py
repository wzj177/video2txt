#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议监控API路由
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional
import json
import asyncio
import uuid
from datetime import datetime

from ..services.task_service import task_service
from ..services.meeting_service import meeting_service
from core.audio import AudioPermissionChecker, SystemAudioCapture

meeting_router = APIRouter(prefix="/api/tasks/meeting", tags=["meeting"])


@meeting_router.get("/stats")
async def get_meeting_stats() -> Dict[str, Any]:
    """获取会议任务统计"""
    try:
        stats = await task_service.get_task_stats("meeting")
        return {"success": True, "data": stats}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


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

        return {
            "success": True,
            "data": {
                "system_info": system_info,
                "microphone": mic_permission,
                "system_audio": system_audio_permission,
                "overall_status": (
                    mic_permission.get("granted", False)
                    or system_audio_permission.get("granted", False)
                ),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


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

        return {
            "success": True,
            "data": {
                "input_devices": devices.get("input", []),
                "output_devices": devices.get("output", []),
                "loopback_devices": devices.get("loopback", []),
                "recommended_system_device": {
                    "id": system_device_id,
                    "info": system_device_info,
                },
                "total_devices": sum(len(devices.get(k, [])) for k in devices.keys()),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@meeting_router.get("/permission-help")
async def get_permission_help() -> Dict[str, Any]:
    """获取权限设置帮助信息"""
    try:
        help_info = AudioPermissionChecker.get_permission_help()

        return {"success": True, "data": help_info}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@meeting_router.post("")
async def create_meeting_task(
    background_tasks: BackgroundTasks,
    meetingApp: str = "auto",
    sourceLanguage: str = "auto",
    targetLanguage: str = "none",
    engine: str = "sensevoice",
    captureMode: str = "system",
    realtime: bool = True,
):
    """创建会议监控任务"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 创建任务配置
        config = {
            "meeting_app": meetingApp,
            "source_language": sourceLanguage,
            "target_language": targetLanguage,
            "engine": engine,
            "capture_mode": captureMode,
            "realtime": realtime,
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
        success = await meeting_service.create_meeting_processor(task_id, config)

        if not success:
            raise HTTPException(status_code=500, detail="启动会议处理器失败")

        return {"success": True, "task_id": task_id, "message": "会议监控任务创建成功"}

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
            processor = meeting_service.get_meeting_processor(task_id)
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
                        "completed",
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


@meeting_router.post("/{task_id}/stop")
async def stop_meeting_task(task_id: str):
    """停止会议监控任务"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 停止会议处理器
        success = await meeting_service.stop_meeting_processor(task_id)

        if not success:
            logger.warning(f"停止会议处理器失败: {task_id}")

        return {"success": True, "message": "会议监控已停止"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止监控失败: {str(e)}")


@meeting_router.get("/{task_id}")
async def get_meeting_task(task_id: str):
    """获取会议任务状态"""
    try:
        task = await task_service.get_task_by_id("meeting", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        return {"success": True, "task": task}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务失败: {str(e)}")


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
            return {
                "success": True,
                "backend": test_result["backend"],
                "device": test_result["device"],
                "sampleRate": f"{test_result['sample_rate']} Hz",
                "avgVolume": test_result.get("avg_volume", 0),
                "maxVolume": test_result.get("max_volume", 0),
                "samples": test_result.get("samples", 0),
                "availableDevices": len(devices_info.get("devices", [])),
                "message": "音频设备测试成功",
            }
        else:
            return {
                "success": False,
                "backend": test_result["backend"],
                "error": test_result.get("error", "未知错误"),
                "message": f"音频测试失败: {test_result.get('error', '未知错误')}",
            }

    except Exception as e:
        logger.error(f"音频测试异常: {e}")
        return {"success": False, "message": f"音频测试失败: {str(e)}"}


@meeting_router.post("/request-permissions")
async def request_audio_permissions() -> Dict[str, Any]:
    """主动触发权限申请"""
    try:
        result = AudioPermissionChecker.request_microphone_permission()

        return {
            "success": result.get("success", False),
            "data": {
                "permission_dialog_triggered": result.get(
                    "permission_dialog_triggered", False
                ),
                "error": result.get("error"),
                "message": (
                    "权限申请已触发，请在系统对话框中允许访问"
                    if result.get("success")
                    else result.get("error", "权限申请失败")
                ),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


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
            return {"success": False, "error": "未找到可用的音频设备", "data": {}}

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

        return {
            "success": test_result["success"],
            "data": {
                "device_id": device_id,
                "device_info": device_info,
                "test_duration": duration,
                "samples_captured": test_result["samples_captured"],
                "average_volume": test_result["average_volume"],
                "max_volume": test_result["max_volume"],
                "error": test_result["error"],
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}
