#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的会议录制控制GUI
基于tkinter实现，跨平台兼容，包括macOS
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import json
import threading
import time
import asyncio
from datetime import datetime
from pathlib import Path
import logging


def get_project_root() -> Path:
    """
    获取项目根目录，兼容PyInstaller打包

    Returns:
        Path: 项目根目录路径
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller打包后的环境
        # 使用可执行文件的目录作为项目根目录
        return Path(sys.executable).parent
    else:
        # 开发环境
        return Path(__file__).parent.parent


# 添加项目根目录到Python路径
PROJECT_ROOT = get_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
now = datetime.now()
log_dir = PROJECT_ROOT / "logs" / f"{now.strftime('%Y年')}" / f"{now.strftime('%m月')}"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"gui_log_{now.strftime('%d日')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=log_file,
)
logger = logging.getLogger(__name__)

# 导入服务模块
try:
    from biz.services.realtime_meeting_service import realtime_meeting_service
    from biz.services.task_service import task_service
    from biz.services.notification_service import notification_service

    HAS_SERVICES = True
except ImportError as e:
    logger.warning(f"无法导入服务模块: {e}")
    HAS_SERVICES = False


class MeetingControlGUI:
    def __init__(self, task_id=None):
        self.root = tk.Tk()
        self.root.title("AI会议记录控制器")
        self.root.geometry("720x540")
        self.root.resizable(True, True)

        # API配置
        self.api_base = "http://127.0.0.1:19080"

        # 会议状态
        self.current_meeting = None
        self.is_recording = False
        self.start_time = None
        self.existing_task_id = task_id  # 从外部传入的任务ID

        # 定时器
        self.update_timer = None

        # 事件循环
        self.loop = None
        self.loop_thread = None

        # SSE消息队列
        self.message_queue = None

        # 音频检测
        self.audio_detection_enabled = True
        self.audio_detection_timer = None
        self.last_audio_check_time = None
        self.no_audio_warning_shown = False

        self.setup_ui()
        self.check_server_status()
        self.start_async_loop()

        # 如果有现有任务ID，加载任务信息
        if self.existing_task_id:
            self.load_existing_task_info()

    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # 标题
        title_label = ttk.Label(
            main_frame, text="🎙️ AI会议记录控制器", font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))

        # 服务器状态
        self.status_frame = ttk.LabelFrame(main_frame, text="服务器状态", padding="10")
        self.status_frame.grid(
            row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10)
        )

        self.status_label = ttk.Label(
            self.status_frame, text="检查中...", foreground="orange"
        )
        self.status_label.grid(row=0, column=0, sticky=tk.W)

        self.refresh_button = ttk.Button(
            self.status_frame, text="刷新状态", command=self.check_server_status
        )
        self.refresh_button.grid(row=0, column=1, sticky=tk.E)

        self.status_frame.columnconfigure(0, weight=1)

        # 快速配置
        config_frame = ttk.LabelFrame(main_frame, text="快速配置", padding="10")
        config_frame.grid(
            row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10)
        )
        config_frame.columnconfigure(1, weight=1)

        # 会议标题显示（只读）
        ttk.Label(config_frame, text="会议标题:").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 5)
        )
        self.title_var = tk.StringVar(value="加载中...")
        title_label = ttk.Label(
            config_frame, textvariable=self.title_var, foreground="blue"
        )
        title_label.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 5))

        # 使用默认配置提示
        default_config_label = ttk.Label(
            config_frame,
            text="🔧 其他配置将使用Web页面的默认设置",
            foreground="gray",
            font=("Arial", 9),
        )
        default_config_label.grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0)
        )

        # 控制按钮
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=10)

        self.start_button = ttk.Button(
            control_frame,
            text="🎙️ 开始录制",
            command=self.start_recording,
            style="Accent.TButton",
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.pause_button = ttk.Button(
            control_frame,
            text="⏸️ 暂停",
            command=self.pause_recording,
            state=tk.DISABLED,
        )
        self.pause_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_button = ttk.Button(
            control_frame, text="⏹️ 停止", command=self.stop_recording, state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT)

        # 当前会议状态
        self.meeting_frame = ttk.LabelFrame(main_frame, text="当前会议", padding="10")
        self.meeting_frame.grid(
            row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10)
        )
        self.meeting_frame.columnconfigure(0, weight=1)

        self.meeting_info = ttk.Label(
            self.meeting_frame, text="无活动会议", foreground="gray"
        )
        self.meeting_info.grid(row=0, column=0, sticky=tk.W)

        self.duration_label = ttk.Label(self.meeting_frame, text="", foreground="blue")
        self.duration_label.grid(row=1, column=0, sticky=tk.W)

        # 提示信息
        info_frame = ttk.LabelFrame(main_frame, text="使用说明", padding="10")
        info_frame.grid(
            row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10)
        )

        info_text = (
            "💡 实时转录内容将显示在Web界面中\n"
            "📱 点击「查看实时转录」按钮打开对应的会议页面\n"
            "🎙️ 此控制器专注于录制控制，简洁高效"
        )

        info_label = ttk.Label(info_frame, text=info_text, foreground="gray")
        info_label.grid(row=0, column=0, sticky=tk.W)

        # 底部工具栏
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.grid(
            row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0)
        )
        toolbar_frame.columnconfigure(0, weight=1)

        # self.view_meeting_button = ttk.Button(
        #     toolbar_frame, text="📱 查看实时转录", command=self.view_current_meeting
        # )
        # self.view_meeting_button.pack(side=tk.LEFT)

        self.history_button = ttk.Button(
            toolbar_frame, text="📋 会议历史", command=self.view_history
        )
        self.history_button.pack(side=tk.LEFT, padx=(10, 0))

        self.settings_button = ttk.Button(
            toolbar_frame, text="⚙️ 设置", command=self.open_settings
        )
        self.settings_button.pack(side=tk.RIGHT)

        # 为所有按钮添加鼠标悬停效果（在所有按钮创建完成后）
        self._add_hover_effect(self.refresh_button)
        self._add_hover_effect(self.start_button)
        self._add_hover_effect(self.pause_button)
        self._add_hover_effect(self.stop_button)
        # self._add_hover_effect(self.view_meeting_button)
        self._add_hover_effect(self.history_button)
        self._add_hover_effect(self.settings_button)

    def _add_hover_effect(self, button):
        """为按钮添加鼠标悬停效果"""

        def on_enter(event):
            """鼠标进入时改变光标为pointer"""
            button.config(cursor="hand2")  # hand2在所有平台上都显示为pointer

        def on_leave(event):
            """鼠标离开时恢复默认光标"""
            button.config(cursor="")

        # 绑定鼠标进入和离开事件
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    def load_existing_task_info(self):
        """加载现有任务信息"""

        def load():
            try:
                response = requests.get(
                    f"{self.api_base}/api/tasks/meeting/{self.existing_task_id}",
                    timeout=5,
                )
                if response.status_code == 200:
                    task_data = response.json()
                    if task_data.get("success"):
                        task_info = task_data.get("data", {})
                        # 更新UI显示任务标题
                        title = task_info.get("name", "未知会议")
                        self.root.after(0, lambda: self.title_var.set(title))
                        logger.info(f"已加载任务信息: {title}")
                    else:
                        self.root.after(0, lambda: self.title_var.set("加载失败"))
                        logger.error(
                            f"加载任务失败: {task_data.get('message', '未知错误')}"
                        )
                else:
                    self.root.after(0, lambda: self.title_var.set("任务不存在"))
                    logger.error(f"任务不存在: {self.existing_task_id}")
            except Exception as e:
                logger.error(f"加载任务信息失败: {e}")
                self.root.after(0, lambda: self.title_var.set("加载失败"))

        threading.Thread(target=load, daemon=True).start()

    async def _start_recording_via_api(self, task_id: str) -> bool:
        """通过HTTP API开始录制"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/tasks/meeting/{task_id}/start-recording",
                    timeout=10,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("success", False)
                    return False
        except Exception as e:
            logger.error(f"HTTP API开始录制失败: {e}")
            return False

    async def _get_task_info_via_api(self, task_id: str) -> dict:
        """通过HTTP API获取任务信息"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base}/api/tasks/meeting/{task_id}", timeout=5
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success"):
                            return result.get("data", {})
                    return {}
        except Exception as e:
            logger.error(f"HTTP API获取任务信息失败: {e}")
            return {}

    async def _pause_recording_via_api(self) -> bool:
        """通过HTTP API暂停录制"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/tasks/meeting/{self.current_meeting['id']}/pause",
                    timeout=10,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success"):
                            self.current_meeting["status"] = "paused"
                            self.root.after(0, self.update_recording_ui)
                            return True
                    return False
        except Exception as e:
            logger.error(f"HTTP API暂停录制失败: {e}")
            return False

    async def _resume_recording_via_api(self) -> bool:
        """通过HTTP API继续录制"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/tasks/meeting/{self.current_meeting['id']}/resume",
                    timeout=10,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success"):
                            self.current_meeting["status"] = "recording"
                            self.root.after(0, self.update_recording_ui)
                            return True
                    return False
        except Exception as e:
            logger.error(f"HTTP API继续录制失败: {e}")
            return False

    async def _stop_recording_via_api(self) -> bool:
        """通过HTTP API停止录制"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/tasks/meeting/{self.current_meeting['id']}/stop",
                    timeout=15,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("success", False)
                    return False
        except Exception as e:
            logger.error(f"HTTP API停止录制失败: {e}")
            return False

    def start_async_loop(self):
        """启动异步事件循环"""
        if not HAS_SERVICES:
            logger.warning("服务模块不可用，跳过异步循环启动")
            return

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_forever()
            except Exception as e:
                logger.error(f"异步事件循环错误: {e}")
            finally:
                self.loop.close()

        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        logger.info("异步事件循环已启动")

    def run_async_task(self, coro):
        """在异步循环中运行任务"""
        if self.loop and not self.loop.is_closed():
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            logger.error("异步事件循环不可用")
            return None

    def check_server_status(self):
        """检查服务器状态"""

        def check():
            try:
                response = requests.get(f"{self.api_base}/api/system/health", timeout=5)
                if response.status_code == 200:
                    self.root.after(
                        0, lambda: self.update_status("✅ 服务器运行正常", "green")
                    )
                    self.root.after(0, self.enable_controls)
                else:
                    self.root.after(
                        0, lambda: self.update_status("❌ 服务器响应异常", "red")
                    )
                    self.root.after(0, self.disable_controls)
            except Exception as e:
                self.root.after(
                    0, lambda: self.update_status("❌ 服务器连接失败", "red")
                )
                self.root.after(0, self.disable_controls)

        threading.Thread(target=check, daemon=True).start()

    def update_status(self, text, color):
        """更新状态显示"""
        self.status_label.config(text=text, foreground=color)

    def enable_controls(self):
        """启用控制按钮"""
        if not self.is_recording:
            self.start_button.config(state=tk.NORMAL)

    def disable_controls(self):
        """禁用控制按钮"""
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

    def start_recording(self):
        """开始录制"""
        # 检查是否有有效的任务标题
        current_title = self.title_var.get().strip()
        if not current_title or current_title in [
            "加载中...",
            "加载失败",
            "任务不存在",
        ]:
            messagebox.showwarning("警告", "会议信息未正确加载，请稍后重试")
            return

        if not HAS_SERVICES:
            messagebox.showerror("错误", "服务模块不可用，无法启动录制")
            return

        # 检查macOS音频权限
        if self._check_macos_audio_permission():

            def start():
                try:
                    # 使用异步方式调用服务
                    future = self.run_async_task(self._start_recording_async())
                    if future:
                        result = future.result(timeout=30)  # 30秒超时
                        if result:
                            self.root.after(
                                0,
                                lambda: messagebox.showinfo("成功", "会议录制已开始！"),
                            )
                        else:
                            self.root.after(
                                0, lambda: messagebox.showerror("错误", "启动录制失败")
                            )
                    else:
                        self.root.after(
                            0, lambda: messagebox.showerror("错误", "异步任务启动失败")
                        )

                except Exception as e:
                    logger.error(f"启动录制失败: {e}")
                    self.root.after(
                        0, lambda: messagebox.showerror("错误", f"启动失败: {str(e)}")
                    )

            threading.Thread(target=start, daemon=True).start()

    def _check_macos_audio_permission(self) -> bool:
        """检查macOS音频权限"""
        import platform

        if platform.system() != "Darwin":  # 非macOS系统
            return True

        try:
            # 检查麦克风权限
            result = messagebox.askyesno(
                "音频权限确认",
                "🎙️ 即将开始录制会议音频\n\n"
                "请确认以下设置：\n"
                "• 已授予应用麦克风权限\n"
                "• 音频输入设备工作正常\n"
                "• 环境中有可录制的声音\n\n"
                "💡 提示：首次使用可能需要在系统设置中授权麦克风权限\n\n"
                "是否继续开始录制？",
            )

            if not result:
                # 用户选择取消，提供帮助信息
                messagebox.showinfo(
                    "设置帮助",
                    "🔧 如需配置音频权限：\n\n"
                    "1. 打开「系统设置」\n"
                    "2. 选择「隐私与安全性」\n"
                    "3. 点击「麦克风」\n"
                    "4. 确保本应用已被授权\n\n"
                    "配置完成后请重新开始录制。",
                )
                return False

            return True

        except Exception as e:
            logger.error(f"音频权限检查失败: {e}")
            return True  # 出错时允许继续，让用户自己判断

    async def _start_recording_async(self):
        """异步开始录制"""
        try:
            # 如果有现有的任务ID，使用它；否则创建新的
            if self.existing_task_id:
                task_id = self.existing_task_id
                logger.info(f"使用现有任务ID: {task_id}")

                # 通过HTTP API开始录制现有任务
                recording_success = await self._start_recording_via_api(task_id)
                if recording_success:
                    # 获取任务信息
                    task_info = await self._get_task_info_via_api(task_id)
                    if task_info:
                        task_title = task_info.get("name", self.title_var.get())

                        # 更新UI状态
                        self.current_meeting = {
                            "id": task_id,
                            "title": task_title,
                            "status": "recording",
                        }
                        self.start_time = datetime.now()
                        self.is_recording = True

                        # 在主线程中更新UI
                        self.root.after(0, self.update_recording_ui)
                        self.root.after(0, self.start_update_timer)
                        self.root.after(0, self.start_audio_detection)

                        logger.info(f"✅ 现有会议录制已开始: {task_id}")
                        return True
                    else:
                        logger.error(f"无法找到任务: {task_id}")
                        return False
                else:
                    logger.error("开始录制现有任务失败")
                    return False
            else:
                # 创建新任务
                import uuid

                task_id = str(uuid.uuid4())

                # 创建任务配置
                config = {
                    "title": self.title_var.get(),
                    "audio_source": "system",
                    "engine": "sensevoice",
                    "language": "auto",
                    "enable_speaker_diarization": True,
                    "enable_realtime_summary": False,
                    "created_at": datetime.now().isoformat(),
                    "disable_gui": True,  # 禁用GUI启动
                }

                # 创建任务记录
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

                # 创建会议处理器
                success = await realtime_meeting_service.create_meeting_processor(
                    task_id, config
                )
                if success:
                    # 开始录制
                    recording_success = (
                        await realtime_meeting_service.start_meeting_recording(task_id)
                    )
                    if recording_success:
                        # 更新UI状态
                        self.current_meeting = {
                            "id": task_id,
                            "title": self.title_var.get(),
                            "status": "recording",
                        }
                        self.start_time = datetime.now()
                        self.is_recording = True

                        # 在主线程中更新UI
                        self.root.after(0, self.update_recording_ui)
                        self.root.after(0, self.start_update_timer)
                        self.root.after(0, self.start_audio_detection)

                        # 发送通知
                        notification_service.notify_meeting_status(
                            meeting_title=self.title_var.get(),
                            status="started",
                            message_extra="录制已开始，正在进行音频捕获和转录",
                        )

                        logger.info(f"✅ 新会议录制已开始: {task_id}")
                        return True
                    else:
                        logger.error("开始录制失败")
                        return False
                else:
                    logger.error("创建会议处理器失败")
                    return False

        except Exception as e:
            logger.error(f"异步开始录制失败: {e}")
            return False

    def pause_recording(self):
        """暂停录制"""
        if not self.current_meeting:
            return

        if not HAS_SERVICES:
            messagebox.showerror("错误", "服务模块不可用，无法暂停录制")
            return

        def pause():
            try:
                # 根据当前状态决定是暂停还是继续
                if self.current_meeting["status"] == "recording":
                    future = self.run_async_task(self._pause_recording_via_api())
                    action = "暂停"
                else:
                    future = self.run_async_task(self._resume_recording_via_api())
                    action = "继续"

                if future:
                    result = future.result(timeout=10)
                    if result:
                        self.root.after(
                            0, lambda: messagebox.showinfo("成功", f"会议已{action}")
                        )
                    else:
                        self.root.after(
                            0, lambda: messagebox.showerror("错误", f"{action}失败")
                        )
                else:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "错误", f"异步{action}任务启动失败"
                        ),
                    )

            except Exception as e:
                logger.error(f"{action}录制失败: {e}")
                self.root.after(
                    0, lambda: messagebox.showerror("错误", f"{action}失败: {str(e)}")
                )

        threading.Thread(target=pause, daemon=True).start()

    async def _pause_recording_async(self):
        """异步暂停录制"""
        try:
            task_id = self.current_meeting["id"]
            success = await realtime_meeting_service.pause_meeting_processor(task_id)

            if success:
                # 更新任务状态
                await task_service.update_task("meeting", task_id, {"status": "paused"})

                # 更新UI状态
                self.current_meeting["status"] = "paused"
                self.root.after(0, self.update_recording_ui)

                # 发送状态同步到Web页面
                self.root.after(0, lambda: self.sync_status_to_web("paused"))

                # 发送通知
                notification_service.notify_meeting_status(
                    meeting_title=self.current_meeting["title"],
                    status="paused",
                    message_extra="录制已暂停",
                )

                logger.info(f"✅ 会议录制已暂停: {task_id}")
                return True
            else:
                logger.error("暂停录制失败")
                return False

        except Exception as e:
            logger.error(f"异步暂停录制失败: {e}")
            return False

    async def _resume_recording_async(self):
        """异步继续录制"""
        try:
            task_id = self.current_meeting["id"]
            success = await realtime_meeting_service.resume_meeting_processor(task_id)

            if success:
                # 更新任务状态
                await task_service.update_task(
                    "meeting", task_id, {"status": "recording"}
                )

                # 更新UI状态
                self.current_meeting["status"] = "recording"
                self.root.after(0, self.update_recording_ui)

                # 发送状态同步到Web页面
                self.root.after(0, lambda: self.sync_status_to_web("recording"))

                # 发送通知
                notification_service.notify_meeting_status(
                    meeting_title=self.current_meeting["title"],
                    status="resumed",
                    message_extra="录制已继续",
                )

                logger.info(f"✅ 会议录制已继续: {task_id}")
                return True
            else:
                logger.error("继续录制失败")
                return False

        except Exception as e:
            logger.error(f"异步继续录制失败: {e}")
            return False

    def stop_recording(self):
        """停止录制"""
        if not self.current_meeting:
            return

        if not HAS_SERVICES:
            messagebox.showerror("错误", "服务模块不可用，无法停止录制")
            return

        result = messagebox.askyesno(
            "确认停止录制",
            f"是否要结束会议「{self.current_meeting['title']}」的录制？\n\n"
            "停止后将:\n"
            "• 完成音频转录和分析\n"
            "• 生成会议总结和纪要\n"
            "• 关闭录制控制窗口\n\n"
            "确定要停止吗？",
        )
        if not result:
            return

        # 立即停止倒计时和音频检测
        self.stop_update_timer()
        self.stop_audio_detection()

        # 立即更新UI状态
        self.is_recording = False
        self.update_status("🛑 正在停止录制...", "orange")
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)

        def stop():
            try:
                future = self.run_async_task(self._stop_recording_via_api())
                if future:
                    result = future.result(timeout=15)  # 减少超时时间到15秒
                    if result:
                        # 成功停止，关闭GUI窗口
                        self.root.after(0, self._close_after_stop_success)
                    else:
                        self.root.after(
                            0, lambda: messagebox.showerror("错误", "停止录制失败")
                        )
                        # 恢复UI状态
                        self.root.after(0, self._restore_ui_after_stop_failure)
                else:
                    self.root.after(
                        0, lambda: messagebox.showerror("错误", "异步停止任务启动失败")
                    )
                    # 恢复UI状态
                    self.root.after(0, self._restore_ui_after_stop_failure)

            except Exception as e:
                logger.error(f"停止录制失败: {e}")
                self.root.after(
                    0, lambda: messagebox.showerror("错误", f"停止失败: {str(e)}")
                )
                # 恢复UI状态
                self.root.after(0, self._restore_ui_after_stop_failure)

        threading.Thread(target=stop, daemon=True).start()

    def _close_after_stop_success(self):
        """停止成功后关闭窗口"""
        # 检查是否录制到了声音（简单检查录制时长）
        recording_duration = 0
        if self.start_time:
            recording_duration = (datetime.now() - self.start_time).total_seconds()

        # 如果录制时长很短，提示可能没有录制到声音
        if recording_duration < 10:  # 少于10秒
            messagebox.showwarning(
                "录制时长较短",
                f"会议「{self.current_meeting['title']}」录制时长仅 {int(recording_duration)} 秒。\n\n"
                "⚠️ 可能的问题：\n"
                "• 未检测到有效音频输入\n"
                "• 麦克风权限未授予\n"
                "• 音频设备配置问题\n\n"
                "建议检查音频设置后重新录制。",
            )

        # 显示成功消息
        messagebox.showinfo(
            "录制完成",
            f"会议「{self.current_meeting['title']}」录制已完成！\n\n"
            "• 转录和分析正在后台进行\n"
            "• 完成后将收到桌面通知\n"
            "• 可在会议历史中查看结果\n\n"
            "录制控制窗口即将关闭",
        )

        # 清理状态
        self.current_meeting = None
        self.is_recording = False
        self.start_time = None
        self.stop_update_timer()
        self.stop_audio_detection()

        # 关闭窗口
        self.root.after(1000, self.root.destroy)  # 1秒后关闭窗口

    def _restore_ui_after_stop_failure(self):
        """停止失败后恢复UI状态"""
        if self.current_meeting:
            self.is_recording = True
            self.update_recording_ui()
            self.start_update_timer()
            self.start_audio_detection()
            self.update_status("✅ 服务器运行正常", "green")

    def update_recording_ui(self):
        """更新录制界面"""
        if self.is_recording and self.current_meeting:
            # 更新按钮状态
            self.start_button.config(state=tk.DISABLED)

            if self.current_meeting["status"] == "recording":
                self.pause_button.config(state=tk.NORMAL, text="⏸️ 暂停")
                self.stop_button.config(state=tk.NORMAL)
            elif self.current_meeting["status"] == "paused":
                self.pause_button.config(state=tk.NORMAL, text="▶️ 继续")
                self.stop_button.config(state=tk.NORMAL)

            # 更新会议信息
            self.meeting_info.config(
                text=f"📹 {self.current_meeting['title']}", foreground="green"
            )
        else:
            # 重置界面
            self.start_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED, text="⏸️ 暂停")
            self.stop_button.config(state=tk.DISABLED)
            self.meeting_info.config(text="无活动会议", foreground="gray")
            self.duration_label.config(text="")

    def start_update_timer(self):
        """启动更新定时器"""
        self.update_duration()

    def stop_update_timer(self):
        """停止更新定时器"""
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None

    def update_duration(self):
        """更新录制时长"""
        if self.is_recording and self.start_time:
            duration = datetime.now() - self.start_time
            hours, remainder = divmod(int(duration.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)

            duration_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.duration_label.config(text=duration_text)

            # 1秒后再次更新
            self.update_timer = self.root.after(1000, self.update_duration)

    def start_audio_detection(self):
        """开始音频检测"""
        if self.audio_detection_enabled and self.is_recording:
            self.last_audio_check_time = datetime.now()
            self.no_audio_warning_shown = False
            self.check_audio_activity()

    def stop_audio_detection(self):
        """停止音频检测"""
        if self.audio_detection_timer:
            self.root.after_cancel(self.audio_detection_timer)
            self.audio_detection_timer = None

    def check_audio_activity(self):
        """检查音频活动"""
        if not self.is_recording or not self.current_meeting:
            return

        try:
            # 检查是否有转录内容更新（简单的音频活动检测）
            current_time = datetime.now()
            if self.last_audio_check_time:
                time_diff = (current_time - self.last_audio_check_time).total_seconds()

                # 如果超过30秒没有音频活动，显示警告
                if time_diff > 30 and not self.no_audio_warning_shown:
                    self.show_no_audio_warning()
                    self.no_audio_warning_shown = True
                    # 更新最后检查时间，避免连续警告
                    self.last_audio_check_time = current_time
                elif time_diff <= 30:
                    self.no_audio_warning_shown = False
                    # 如果在30秒内检测到音频活动，更新检查时间
                    if time_diff > 0:  # 确保有时间差才更新
                        self.last_audio_check_time = current_time

            # 30秒后再次检查
            self.audio_detection_timer = self.root.after(
                30000, self.check_audio_activity
            )

        except Exception as e:
            logger.error(f"音频检测失败: {e}")

    def show_no_audio_warning(self):
        """显示无音频警告"""
        if self.is_recording and self.current_meeting:
            result = messagebox.askyesno(
                "音频检测",
                f"会议「{self.current_meeting['title']}」已录制超过30秒，但未检测到明显的音频活动。\n\n"
                "可能的原因：\n"
                "• 麦克风权限未授予\n"
                "• 音频输入设备未正确配置\n"
                "• 环境过于安静\n\n"
                "是否要检查音频设置？",
            )
            if result:
                self.open_audio_settings()

    def open_audio_settings(self):
        """打开音频设置"""
        try:
            import webbrowser

            # 打开系统音频设置页面
            import platform

            system = platform.system()

            if system == "Darwin":  # macOS
                import subprocess

                subprocess.run(
                    ["open", "/System/Library/PreferencePanes/Sound.prefPane"]
                )
            elif system == "Windows":
                import subprocess

                subprocess.run(["ms-settings:sound"], shell=True)
            else:  # Linux
                messagebox.showinfo(
                    "音频设置", "请打开系统设置 > 声音，检查音频输入设备配置"
                )
        except Exception as e:
            logger.error(f"打开音频设置失败: {e}")
            messagebox.showinfo(
                "音频设置", "无法自动打开音频设置，请手动检查系统音频输入配置"
            )

    def sync_status_to_web(self, status):
        """同步状态到Web页面"""
        if not self.current_meeting:
            return

        def sync():
            try:
                # 通过HTTP请求触发SSE推送，确保Web页面能收到状态更新
                data = {
                    "type": "status_update",
                    "task_id": self.current_meeting["id"],
                    "status": status,
                    "timestamp": datetime.now().isoformat(),
                    "source": "gui_controller",
                }

                # 发送到SSE推送端点
                response = requests.post(
                    f"{self.api_base}/api/tasks/meeting/{self.current_meeting['id']}/sync-status",
                    json=data,
                    timeout=5,
                )

                if response.status_code == 200:
                    logger.info(f"状态已同步到Web页面: {status}")
                else:
                    logger.warning(f"⚠状态同步失败: {response.status_code}")

            except Exception as e:
                logger.error(f"状态同步失败: {e}")

        # 在后台线程中执行，避免阻塞UI
        threading.Thread(target=sync, daemon=True).start()

    def view_current_meeting(self):
        """查看当前会议的实时转录"""
        if self.current_meeting:
            import webbrowser

            meeting_url = (
                f"{self.api_base}/meeting_create?taskId={self.current_meeting['id']}"
            )
            webbrowser.open(meeting_url)
        else:
            messagebox.showinfo("提示", "当前没有活动的会议")

    def view_history(self):
        """查看历史记录"""
        import webbrowser

        webbrowser.open(f"{self.api_base}/meeting2txt")

    def open_settings(self):
        """打开设置"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("设置")
        settings_window.geometry("400x300")
        settings_window.resizable(False, False)

        # 设置为模态对话框
        settings_window.transient(self.root)
        settings_window.grab_set()

        frame = ttk.Frame(settings_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="API服务器地址:", font=("Arial", 10, "bold")).pack(
            anchor=tk.W, pady=(0, 5)
        )

        api_var = tk.StringVar(value=self.api_base)
        api_entry = ttk.Entry(frame, textvariable=api_var, width=50)
        api_entry.pack(fill=tk.X, pady=(0, 10))

        def save_settings():
            self.api_base = api_var.get().rstrip("/")
            messagebox.showinfo("成功", "设置已保存")
            settings_window.destroy()
            self.check_server_status()

        save_button = ttk.Button(frame, text="保存", command=save_settings)
        save_button.pack(pady=10)
        self._add_hover_effect(save_button)

        # 居中显示
        settings_window.geometry(
            "+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50)
        )

    def on_closing(self):
        """程序关闭时的处理"""
        if self.is_recording:
            result = messagebox.askyesnocancel(
                "确认退出",
                f"会议「{self.current_meeting['title']}」正在录制中，是否要停止录制并退出？\n\n"
                "选择'是'：停止录制并退出\n"
                "选择'否'：保持录制在后台继续，退出GUI程序\n"
                "选择'取消'：不退出程序",
                icon="warning",
            )
            # 自定义按钮文本为中文
            self.root.tk.call("wm", "attributes", ".", "-topmost", "1")
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    widget.focus_set()
                    widget.grab_set()
                    # 修改 messagebox 按钮文本
                    try:
                        self.root.tk.call(
                            "tk_dialog",
                            ".!toplevel",
                            "确认退出",
                            f"会议「{self.current_meeting['title']}」正在录制中，是否要停止录制并退出？\n\n"
                            "选择'是'：停止录制并退出\n"
                            "选择'否'：保持录制在后台继续，退出GUI程序\n"
                            "选择'取消'：不退出程序",
                            "warning",
                            3,
                            "是",
                            "否",
                            "取消",
                        )
                    except:
                        pass
            if result is None:  # 取消
                return
            elif result:  # 是，停止录制
                # 直接调用停止录制，它会自动关闭窗口
                self.stop_recording()
                return
            else:  # 否，保持录制继续
                messagebox.showinfo(
                    "后台运行",
                    f"会议「{self.current_meeting['title']}」将在后台继续录制。\n\n"
                    "• 录制会自动完成并生成总结\n"
                    "• 完成后会收到桌面通知\n"
                    "• 可通过Web界面查看进度和结果",
                )

        # 清理资源
        self.stop_update_timer()
        self._cleanup_async_loop()
        self.root.destroy()

    def _cleanup_async_loop(self):
        """清理异步事件循环"""
        try:
            if self.loop and not self.loop.is_closed():
                # 停止事件循环
                self.loop.call_soon_threadsafe(self.loop.stop)

                # 等待线程结束
                if self.loop_thread and self.loop_thread.is_alive():
                    self.loop_thread.join(timeout=2)

                logger.info("异步事件循环已清理")
        except Exception as e:
            logger.error(f"清理异步事件循环失败: {e}")

    def run(self):
        """运行GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # macOS特殊设置
        import platform

        if platform.system() == "Darwin":
            # 设置macOS应用名称
            self.root.createcommand("tk::mac::ReopenApplication", self.root.deiconify)

        print("AI会议记录控制器已启动")
        print(f"API服务器: {self.api_base}")
        print("提示: 确保AI服务器正在运行在 http://127.0.0.1:19080")

        self.root.mainloop()


def main():
    """主函数"""
    try:
        # 检查命令行参数
        task_id = None
        if len(sys.argv) > 1:
            # 支持 --task-id=xxx 或 --task-id xxx 格式
            for arg in sys.argv[1:]:
                if arg.startswith("--task-id="):
                    task_id = arg.split("=", 1)[1]
                    break
                elif arg == "--task-id" and len(sys.argv) > sys.argv.index(arg) + 1:
                    task_id = sys.argv[sys.argv.index(arg) + 1]
                    break

        if task_id:
            print(f"使用现有任务ID: {task_id}")
            logger.info(f"使用现有任务ID: {task_id}")
        else:
            print("将创建新的会议任务")
            logger.info("将创建新的会议任务")

        # 创建并运行GUI
        app = MeetingControlGUI(task_id=task_id)
        app.run()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
