#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知管理API路由
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
import logging

from ..services.notification_service import notification_service

logger = logging.getLogger(__name__)

notification_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@notification_router.get("/status")
async def get_notification_status() -> Dict[str, Any]:
    """获取通知服务状态"""
    try:
        platform_info = notification_service.get_platform_info()
        return {"success": True, "data": platform_info}
    except Exception as e:
        logger.error(f"获取通知状态失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@notification_router.post("/test")
async def test_notification() -> Dict[str, Any]:
    """测试桌面通知"""
    try:
        success = notification_service.show_notification(
            title="🧪 测试通知",
            message="这是一个测试通知，用于验证桌面通知功能是否正常工作。\n\n如果您看到这个通知，说明功能已正确配置。",
            timeout=8,
        )

        if success:
            return {"success": True, "message": "测试通知已发送"}
        else:
            return {"success": False, "message": "通知发送失败，请检查系统设置"}

    except Exception as e:
        logger.error(f"测试通知失败: {e}")
        raise HTTPException(status_code=500, detail=f"测试通知失败: {str(e)}")


@notification_router.post("/send")
async def send_custom_notification(
    title: str, message: str, timeout: int = 10, event_type: str = "info"
) -> Dict[str, Any]:
    """发送自定义通知"""
    try:
        success = notification_service.notify_system_event(
            event_type=event_type, title=title, message=message, timeout=timeout
        )

        if success:
            return {"success": True, "message": "通知已发送"}
        else:
            return {"success": False, "message": "通知发送失败"}

    except Exception as e:
        logger.error(f"发送自定义通知失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送通知失败: {str(e)}")


@notification_router.get("/history")
async def get_notification_history(limit: int = 50) -> Dict[str, Any]:
    """获取通知历史记录"""
    try:
        history = notification_service.get_notification_history(limit)
        return {
            "success": True,
            "data": {"notifications": history, "total": len(history)},
        }
    except Exception as e:
        logger.error(f"获取通知历史失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@notification_router.delete("/history")
async def clear_notification_history() -> Dict[str, Any]:
    """清空通知历史记录"""
    try:
        success = notification_service.clear_notification_history()

        if success:
            return {"success": True, "message": "通知历史记录已清空"}
        else:
            return {"success": False, "message": "清空失败"}

    except Exception as e:
        logger.error(f"清空通知历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@notification_router.post("/task-completed")
async def send_task_completion_notification(
    task_id: str,
    task_type: str,
    task_name: str,
    duration: Optional[float] = None,
    success: bool = True,
) -> Dict[str, Any]:
    """发送任务完成通知（用于测试）"""
    try:
        result = notification_service.notify_task_completed(
            task_id=task_id,
            task_type=task_type,
            task_name=task_name,
            duration=duration,
            success=success,
        )

        if result:
            return {"success": True, "message": "任务完成通知已发送"}
        else:
            return {"success": False, "message": "通知发送失败"}

    except Exception as e:
        logger.error(f"发送任务完成通知失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送通知失败: {str(e)}")


@notification_router.post("/meeting-status")
async def send_meeting_status_notification(
    meeting_title: str,
    status: str,
    duration: Optional[str] = None,
    message_extra: str = "",
) -> Dict[str, Any]:
    """发送会议状态通知（用于测试）"""
    try:
        result = notification_service.notify_meeting_status(
            meeting_title=meeting_title,
            status=status,
            duration=duration,
            message_extra=message_extra,
        )

        if result:
            return {"success": True, "message": "会议状态通知已发送"}
        else:
            return {"success": False, "message": "通知发送失败"}

    except Exception as e:
        logger.error(f"发送会议状态通知失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送通知失败: {str(e)}")

