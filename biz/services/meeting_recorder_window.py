#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议录制窗口 - 使用tkinter创建录制界面
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable
import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class MeetingRecorderWindow:
    """会议录制窗口"""

    def __init__(
        self,
        task_id: str,
        title: str,
        config: dict,
        on_pause: Optional[Callable] = None,
        on_resume: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
    ):
        self.task_id = task_id
        self.title = title
        self.config = config
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop

        # 状态
        self.is_recording = True
        self.is_paused = False
        self.start_time = datetime.now()
        self.pause_time = None
        self.total_paused_duration = timedelta()

        # UI组件
        self.window = None
        self.time_label = None
        self.status_label = None
        self.music_label = None
        self.pause_button = None
        self.stop_button = None

        # 定时器
        self.timer_thread = None
        self.should_update = True

        # 音符动画
        self.music_animation_index = 0
        self.music_notes = ["🎵", "🎶", "🎼", "🎤"]

        self.create_window()
        self.start_timer()

    def create_window(self):
        """创建录制窗口"""
        try:
            # 在macOS上设置tkinter的线程安全
            import platform

            if platform.system() == "Darwin":
                # 设置macOS特定的tkinter选项
                import os

                os.environ["TK_SILENCE_DEPRECATION"] = "1"

            self.window = tk.Tk()
            self.window.title("会议录制中")
            self.window.geometry("400x200")
            self.window.resizable(False, False)

            # 设置窗口置顶
            self.window.attributes("-topmost", True)

            # 设置窗口样式
            self.window.configure(bg="#f0f0f0")

            # 创建主框架
            main_frame = ttk.Frame(self.window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)

            # 标题
            title_label = ttk.Label(
                main_frame,
                text=self.title,
                font=("Arial", 14, "bold"),
                foreground="#333333",
            )
            title_label.pack(pady=(0, 10))

            # 状态行
            status_frame = ttk.Frame(main_frame)
            status_frame.pack(fill=tk.X, pady=(0, 15))

            # 音符动画
            self.music_label = ttk.Label(status_frame, text="🎵", font=("Arial", 16))
            self.music_label.pack(side=tk.LEFT)

            # 状态文本
            self.status_label = ttk.Label(
                status_frame,
                text="记录中...",
                font=("Arial", 12, "bold"),
                foreground="#e74c3c",
            )
            self.status_label.pack(side=tk.LEFT, padx=(10, 0))

            # 时间显示
            self.time_label = ttk.Label(
                main_frame,
                text="00:00:00",
                font=("Courier", 18, "bold"),
                foreground="#2c3e50",
            )
            self.time_label.pack(pady=(0, 20))

            # 按钮框架
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            # 暂停/继续按钮
            self.pause_button = ttk.Button(
                button_frame, text="⏸️ 暂停", command=self.toggle_pause, width=12
            )
            self.pause_button.pack(side=tk.LEFT, padx=(0, 10))

            # 完成录制按钮
            self.stop_button = ttk.Button(
                button_frame, text="⏹️ 完成录制", command=self.stop_recording, width=12
            )
            self.stop_button.pack(side=tk.LEFT)

            # 绑定窗口关闭事件
            self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

            logger.info(f"✅ 录制窗口创建成功: {self.title}")

        except Exception as e:
            logger.error(f"创建录制窗口失败: {e}")
            raise

    def start_timer(self):
        """启动计时器线程"""
        self.timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.timer_thread.start()

    def _timer_loop(self):
        """计时器循环"""
        while self.should_update and self.window:
            try:
                if self.window.winfo_exists():
                    self.window.after(0, self.update_display)
                time.sleep(1)
            except tk.TclError:
                break
            except Exception as e:
                logger.error(f"计时器更新失败: {e}")
                break

    def update_display(self):
        """更新显示内容"""
        try:
            if not self.window or not self.window.winfo_exists():
                return

            # 更新时间
            current_time = datetime.now()
            if self.is_paused and self.pause_time:
                # 暂停状态：显示暂停时的时间
                elapsed = (
                    self.pause_time - self.start_time
                ) - self.total_paused_duration
            else:
                # 录制状态：显示当前经过时间
                elapsed = (current_time - self.start_time) - self.total_paused_duration

            # 格式化时间
            total_seconds = int(elapsed.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            self.time_label.config(text=time_str)

            # 更新音符动画（仅在录制时）
            if not self.is_paused:
                self.music_animation_index = (self.music_animation_index + 1) % len(
                    self.music_notes
                )
                self.music_label.config(
                    text=self.music_notes[self.music_animation_index]
                )

        except Exception as e:
            logger.error(f"更新显示失败: {e}")

    def toggle_pause(self):
        """切换暂停/继续状态"""
        try:
            if self.is_paused:
                # 继续录制
                self.resume_recording()
            else:
                # 暂停录制
                self.pause_recording()
        except Exception as e:
            logger.error(f"切换录制状态失败: {e}")
            messagebox.showerror("错误", f"操作失败: {str(e)}")

    def pause_recording(self):
        """暂停录制"""
        try:
            self.is_paused = True
            self.pause_time = datetime.now()

            # 更新UI
            self.status_label.config(text="已暂停", foreground="#f39c12")
            self.music_label.config(text="⏸️")
            self.pause_button.config(text="▶️ 继续")

            # 调用回调
            if self.on_pause:
                self.on_pause(self.task_id)

            logger.info(f"⏸️ 录制已暂停: {self.task_id}")

        except Exception as e:
            logger.error(f"暂停录制失败: {e}")
            raise

    def resume_recording(self):
        """继续录制"""
        try:
            if self.pause_time:
                # 累计暂停时间
                pause_duration = datetime.now() - self.pause_time
                self.total_paused_duration += pause_duration
                self.pause_time = None

            self.is_paused = False

            # 更新UI
            self.status_label.config(text="记录中...", foreground="#e74c3c")
            self.pause_button.config(text="⏸️ 暂停")

            # 调用回调
            if self.on_resume:
                self.on_resume(self.task_id)

            logger.info(f"▶️ 录制已继续: {self.task_id}")

        except Exception as e:
            logger.error(f"继续录制失败: {e}")
            raise

    def stop_recording(self):
        """停止录制"""
        try:
            # 确认对话框
            result = messagebox.askyesno(
                "确认操作",
                "是否要结束会议记录，保存音频并生成说话人日志？",
                icon="question",
            )

            if result:
                # 检查是否录制到声音
                if not self._check_audio_recorded():
                    messagebox.showwarning(
                        "警告",
                        "没有录制到任何音频，无法生成会议记录和说话人日志。\n\n请检查音频设备设置。",
                    )
                    return

                # 更新UI状态
                self.status_label.config(text="正在结束...", foreground="#9b59b6")
                self.music_label.config(text="⏹️")
                self.pause_button.config(state="disabled")
                self.stop_button.config(state="disabled", text="处理中...")

                # 调用停止回调
                if self.on_stop:
                    threading.Thread(
                        target=self._stop_with_callback, daemon=True
                    ).start()
                else:
                    self.close_window()

        except Exception as e:
            logger.error(f"停止录制失败: {e}")
            messagebox.showerror("错误", f"停止录制失败: {str(e)}")

    def _stop_with_callback(self):
        """在线程中执行停止回调"""
        try:
            self.on_stop(self.task_id)
            # 回调执行完成后关闭窗口
            if self.window and self.window.winfo_exists():
                self.window.after(0, self.close_window)
        except Exception as e:
            logger.error(f"停止回调执行失败: {e}")
            if self.window and self.window.winfo_exists():
                self.window.after(
                    0, lambda: messagebox.showerror("错误", f"停止录制失败: {str(e)}")
                )

    def _check_audio_recorded(self) -> bool:
        """检查是否录制到音频（改进实现）"""
        try:
            # 检查是否有音频文件生成
            from pathlib import Path

            data_dir = Path(__file__).parent.parent.parent / "data" / "temp_audio"

            # 检查是否有最近生成的音频文件
            if data_dir.exists():
                audio_files = list(data_dir.glob("*.wav"))
                if audio_files:
                    # 检查最新的音频文件
                    latest_file = max(audio_files, key=lambda f: f.stat().st_mtime)
                    file_size = latest_file.stat().st_size

                    # 如果文件大于100KB，认为有有效录音
                    if file_size > 100 * 1024:  # 100KB
                        logger.info(
                            f"✅ 检测到有效音频文件: {latest_file.name} ({file_size/1024:.1f}KB)"
                        )
                        return True

            # 备用检查：至少录制5秒
            elapsed = datetime.now() - self.start_time
            has_time = elapsed.total_seconds() > 5

            if has_time:
                logger.info(f"✅ 录制时长足够: {elapsed.total_seconds():.1f}秒")
            else:
                logger.warning(f"⚠️ 录制时长不足: {elapsed.total_seconds():.1f}秒")

            return has_time

        except Exception as e:
            logger.error(f"检查音频录制状态失败: {e}")
            # 出错时，如果录制时间超过5秒就认为有效
            elapsed = datetime.now() - self.start_time
            return elapsed.total_seconds() > 5

    def on_window_close(self):
        """窗口关闭事件"""
        try:
            # 确认是否要停止录制
            result = messagebox.askyesno(
                "确认关闭", "关闭窗口将停止会议记录，确定要继续吗？", icon="warning"
            )

            if result:
                self.stop_recording()

        except Exception as e:
            logger.error(f"处理窗口关闭事件失败: {e}")
            self.close_window()

    def close_window(self):
        """关闭窗口"""
        try:
            self.should_update = False

            if self.window and self.window.winfo_exists():
                self.window.quit()
                self.window.destroy()
                self.window = None

            logger.info(f"🔴 录制窗口已关闭: {self.task_id}")

        except Exception as e:
            logger.error(f"关闭窗口失败: {e}")

    def show(self):
        """显示窗口"""
        try:
            if self.window:
                self.window.mainloop()
        except Exception as e:
            logger.error(f"显示窗口失败: {e}")

    def update_status(self, status: str, message: str = ""):
        """更新录制状态"""
        try:
            if not self.window or not self.window.winfo_exists():
                return

            status_text = {
                "recording": "记录中...",
                "paused": "已暂停",
                "processing": "处理中...",
                "completed": "已完成",
                "error": "出错",
            }.get(status, status)

            status_color = {
                "recording": "#e74c3c",
                "paused": "#f39c12",
                "processing": "#9b59b6",
                "completed": "#27ae60",
                "error": "#c0392b",
            }.get(status, "#333333")

            self.window.after(
                0,
                lambda: self.status_label.config(
                    text=status_text, foreground=status_color
                ),
            )

        except Exception as e:
            logger.error(f"更新状态失败: {e}")


def create_recorder_window(
    task_id: str,
    title: str,
    config: dict,
    on_pause: Optional[Callable] = None,
    on_resume: Optional[Callable] = None,
    on_stop: Optional[Callable] = None,
) -> MeetingRecorderWindow:
    """创建录制窗口"""
    try:
        window = MeetingRecorderWindow(
            task_id=task_id,
            title=title,
            config=config,
            on_pause=on_pause,
            on_resume=on_resume,
            on_stop=on_stop,
        )

        return window

    except Exception as e:
        logger.error(f"创建录制窗口失败: {e}")
        raise


def show_recorder_window_in_thread(
    task_id: str,
    title: str,
    config: dict,
    on_pause: Optional[Callable] = None,
    on_resume: Optional[Callable] = None,
    on_stop: Optional[Callable] = None,
):
    """在单独线程中显示录制窗口"""
    import platform
    import subprocess
    import sys

    # macOS系统：使用subprocess启动独立的GUI控制器
    if platform.system() == "Darwin":
        try:
            logger.info(" macOS系统：启动独立GUI控制器...")

            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent
            gui_script_path = project_root / "app/meeting_record_control_ui.py"

            if not gui_script_path.exists():
                logger.error(f" GUI控制器脚本不存在: {gui_script_path}")
                logger.info(" 请确保 meeting_record_control_ui.py 存在于项目根目录")
                return None

            # 使用subprocess启动独立的Python进程，传递taskId参数
            process = subprocess.Popen(
                [sys.executable, str(gui_script_path), "--task-id", task_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(project_root),
            )

            logger.info(f"️ macOS GUI控制器已启动 (PID: {process.pid})")
            logger.info(" 请在GUI控制器中手动开始录制")
            return process

        except Exception as e:
            logger.error(f" macOS GUI启动失败: {e}")
            logger.info(
                "💡 建议：通过Web界面控制录制 (http://127.0.0.1:19080/meeting2txt)"
            )
            logger.info(" 录制功能正常运行，只是没有桌面窗口显示")
            return None

    def run_window():
        try:
            window = create_recorder_window(
                task_id=task_id,
                title=title,
                config=config,
                on_pause=on_pause,
                on_resume=on_resume,
                on_stop=on_stop,
            )

            # 启动窗口事件循环
            window.show()

        except Exception as e:
            logger.error(f"录制窗口线程执行失败: {e}")
            logger.info("💡 建议：通过Web界面控制录制")

    # 非macOS系统在新线程中运行GUI
    thread = threading.Thread(target=run_window, daemon=True)
    thread.start()
    return thread


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def test_pause(task_id):
        print(f"暂停录制: {task_id}")

    def test_resume(task_id):
        print(f"继续录制: {task_id}")

    def test_stop(task_id):
        print(f"停止录制: {task_id}")
        time.sleep(2)  # 模拟处理时间

    # 测试窗口
    window = create_recorder_window(
        task_id="test-123",
        title="测试会议录制",
        config={},
        on_pause=test_pause,
        on_resume=test_resume,
        on_stop=test_stop,
    )

    window.show()
