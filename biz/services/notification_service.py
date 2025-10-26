#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面通知服务 - 基于plyer库实现跨平台桌面通知
"""

import logging
import sys
import os
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

try:
    from plyer import notification

    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False
    print("⚠️ plyer库未安装，桌面通知功能不可用")

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class NotificationService:
    """桌面通知服务"""

    def __init__(self):
        self.enabled = HAS_PLYER
        self.app_name = "听语AI"
        self.app_icon = self._get_app_icon()

        # 通知历史记录
        self.notification_history = []

        if not self.enabled:
            logger.warning("plyer库不可用，桌面通知功能已禁用")
        else:
            logger.info("✅ 桌面通知服务已初始化")

    def _get_app_icon(self) -> Optional[str]:
        """获取应用图标路径"""
        try:
            # 查找可能的图标文件
            icon_paths = [
                PROJECT_ROOT / "public" / "favicon.ico",
                PROJECT_ROOT / "public" / "assets" / "images" / "logo.png",
                PROJECT_ROOT / "public" / "assets" / "images" / "icon.png",
            ]

            for icon_path in icon_paths:
                if icon_path.exists():
                    return str(icon_path)

            return None
        except Exception as e:
            logger.warning(f"获取应用图标失败: {e}")
            return None

    def show_notification(
        self,
        title: str,
        message: str,
        timeout: int = 10,
        app_icon: Optional[str] = None,
        ticker: Optional[str] = None,
        toast: bool = False,
    ) -> bool:
        """
        显示桌面通知

        Args:
            title: 通知标题
            message: 通知内容
            timeout: 显示时长（秒）
            app_icon: 自定义图标路径
            ticker: Android平台的ticker文本
            toast: 是否使用toast样式（Android）

        Returns:
            bool: 通知是否成功发送
        """
        if not self.enabled:
            logger.warning("桌面通知功能不可用")
            return False

        try:
            # 使用自定义图标或默认图标
            icon = app_icon or self.app_icon

            # 记录通知历史
            notification_record = {
                "timestamp": datetime.now().isoformat(),
                "title": title,
                "message": message,
                "timeout": timeout,
                "success": False,
            }

            # 发送通知
            notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                app_icon=icon,
                timeout=timeout,
                ticker=ticker,
                toast=toast,
            )

            notification_record["success"] = True
            self.notification_history.append(notification_record)

            logger.info(f"✅ 桌面通知已发送: {title}")
            return True

        except Exception as e:
            logger.error(f"发送桌面通知失败: {e}")
            notification_record["error"] = str(e)
            self.notification_history.append(notification_record)
            return False

    def notify_task_completed(
        self,
        task_id: str,
        task_type: str,
        task_name: str,
        duration: Optional[float] = None,
        success: bool = True,
    ) -> bool:
        """
        任务完成通知

        Args:
            task_id: 任务ID
            task_type: 任务类型 (video, audio, meeting)
            task_name: 任务名称
            duration: 处理时长（秒）
            success: 是否成功完成

        Returns:
            bool: 通知是否成功发送
        """
        if success:
            title = f"🎉 {self._get_task_type_name(task_type)}任务完成"

            duration_text = ""
            if duration:
                if duration < 60:
                    duration_text = f"，耗时 {duration:.1f} 秒"
                else:
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    duration_text = f"，耗时 {minutes} 分 {seconds} 秒"

            message = f"任务 「{task_name}」 已成功完成{duration_text}。\n\n点击查看详细结果。"
        else:
            title = f"{self._get_task_type_name(task_type)}任务失败"
            message = f"任务 「{task_name}」 处理失败。\n\n请检查任务详情或重新尝试。"

        return self.show_notification(
            title=title, message=message, timeout=15  # 任务完成通知显示15秒
        )

    def notify_meeting_status(
        self,
        meeting_title: str,
        status: str,
        duration: Optional[str] = None,
        message_extra: str = "",
    ) -> bool:
        """
        会议状态通知

        Args:
            meeting_title: 会议标题
            status: 状态 (started, paused, resumed, completed, error)
            duration: 会议时长
            message_extra: 额外信息

        Returns:
            bool: 通知是否成功发送
        """
        status_map = {
            "started": {"title": "🎤 会议记录开始", "emoji": "▶️"},
            "paused": {"title": "⏸️ 会议记录暂停", "emoji": "⏸️"},
            "resumed": {"title": "▶️ 会议记录继续", "emoji": "▶️"},
            "completed": {"title": "✅ 会议记录完成", "emoji": "🎉"},
            "finished": {
                "title": "🎉 会议记录任务完成",
                "emoji": "✅",
            },  # 添加 finished 状态
            "error": {"title": "会议记录出错", "emoji": "⚠️"},
        }

        status_info = status_map.get(
            status, {"title": f"📢 会议状态更新", "emoji": "📢"}
        )

        duration_text = f" ({duration})" if duration else ""
        message = f"会议 「{meeting_title}」{duration_text}"

        if message_extra:
            message += f"\n\n{message_extra}"

        timeout = 15 if status in ["completed", "finished", "error"] else 8

        return self.show_notification(
            title=status_info["title"], message=message, timeout=timeout
        )

    def notify_system_event(
        self, event_type: str, title: str, message: str, timeout: int = 10
    ) -> bool:
        """
        系统事件通知

        Args:
            event_type: 事件类型 (info, warning, error, success)
            title: 通知标题
            message: 通知内容
            timeout: 显示时长

        Returns:
            bool: 通知是否成功发送
        """
        emoji_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}

        emoji = emoji_map.get(event_type, "📢")
        formatted_title = f"{emoji} {title}"

        return self.show_notification(
            title=formatted_title, message=message, timeout=timeout
        )

    def _get_task_type_name(self, task_type: str) -> str:
        """获取任务类型的中文名称"""
        type_map = {"video": "视频处理", "audio": "音频处理", "meeting": "会议记录"}
        return type_map.get(task_type, "任务")

    def get_notification_history(self, limit: int = 50) -> list:
        """
        获取通知历史记录

        Args:
            limit: 返回记录数量限制

        Returns:
            list: 通知历史记录
        """
        return self.notification_history[-limit:]

    def clear_notification_history(self) -> bool:
        """清空通知历史记录"""
        try:
            self.notification_history.clear()
            logger.info("通知历史记录已清空")
            return True
        except Exception as e:
            logger.error(f"清空通知历史记录失败: {e}")
            return False

    def is_enabled(self) -> bool:
        """检查通知服务是否可用"""
        return self.enabled

    def get_platform_info(self) -> Dict[str, Any]:
        """获取平台信息"""
        platform_info = {
            "enabled": self.enabled,
            "app_name": self.app_name,
            "app_icon": self.app_icon,
            "platform": sys.platform,
            "has_plyer": HAS_PLYER,
        }

        if HAS_PLYER:
            try:
                # 尝试获取更多平台信息
                platform_info["notification_available"] = True
            except Exception as e:
                platform_info["notification_available"] = False
                platform_info["error"] = str(e)

        return platform_info


# 全局通知服务实例
notification_service = NotificationService()


# 便捷函数
def notify_task_completed(
    task_id: str,
    task_type: str,
    task_name: str,
    duration: Optional[float] = None,
    success: bool = True,
) -> bool:
    """任务完成通知便捷函数"""
    return notification_service.notify_task_completed(
        task_id, task_type, task_name, duration, success
    )


def notify_meeting_status(
    meeting_title: str,
    status: str,
    duration: Optional[str] = None,
    message_extra: str = "",
) -> bool:
    """会议状态通知便捷函数"""
    return notification_service.notify_meeting_status(
        meeting_title, status, duration, message_extra
    )


def notify_system_event(
    event_type: str, title: str, message: str, timeout: int = 10
) -> bool:
    """系统事件通知便捷函数"""
    return notification_service.notify_system_event(event_type, title, message, timeout)


def show_notification(title: str, message: str, timeout: int = 10) -> bool:
    """显示通知便捷函数"""
    return notification_service.show_notification(title, message, timeout)


# 测试代码
if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO)

    # 测试基本通知
    print("测试基本通知...")
    notification_service.show_notification(
        title="测试通知",
        message="这是一个测试通知，用于验证桌面通知功能是否正常工作。",
        timeout=5,
    )

    time.sleep(2)

    # 测试任务完成通知
    print("测试任务完成通知...")
    notification_service.notify_task_completed(
        task_id="test-123",
        task_type="video",
        task_name="测试视频.mp4",
        duration=125.5,
        success=True,
    )

    time.sleep(2)

    # 测试会议通知
    print("测试会议通知...")
    notification_service.notify_meeting_status(
        meeting_title="团队例会",
        status="completed",
        duration="45分30秒",
        message_extra="已生成会议纪要和AI总结",
    )

    time.sleep(2)

    # 测试系统事件通知
    print("测试系统事件通知...")
    notification_service.notify_system_event(
        event_type="success",
        title="系统更新",
        message="AI模型已成功更新到最新版本",
        timeout=8,
    )

    # 显示平台信息
    print("\n平台信息:")
    import json

    print(
        json.dumps(
            notification_service.get_platform_info(), indent=2, ensure_ascii=False
        )
    )

    # 显示通知历史
    print("\n通知历史:")
    history = notification_service.get_notification_history()
    for record in history:
        print(f"- {record['timestamp']}: {record['title']}")
