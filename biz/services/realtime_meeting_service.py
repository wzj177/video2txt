#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时会议记录服务 - 集成tkinter录制窗口
"""

import asyncio
import logging
import threading
import time
import json
import tempfile
import os
import numpy as np
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from datetime import datetime
import sys

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from .task_service import task_service
from .meeting_recorder_window import show_recorder_window_in_thread
from .notification_service import notification_service
from .voice_analysis_service import voice_analysis_service
from core.audio.audio_capture import AudioCapture, AudioBuffer
from core.asr import initialize_voice_recognition, transcribe_audio
from .video_service import video_service

logger = logging.getLogger(__name__)


class RealtimeMeetingProcessor:
    """实时会议处理器"""

    def __init__(self, task_id: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.config = config
        self.is_running = False
        self.is_paused = False

        # 音频相关
        self.audio_capture = AudioCapture(
            sample_rate=16000, channels=1, chunk_size=1024
        )
        self.audio_buffer = AudioBuffer(max_duration=30.0)

        # 转录相关
        self.last_transcribe_time = 0
        self.transcribe_interval = 5.0  # 每5秒转录一次（增加间隔）
        self.accumulated_audio = []
        self.accumulated_text = []

        # 说话人识别和情感分析
        self.speakers = {}
        self.current_speaker = None
        self.enable_voice_analysis = config.get("enable_speaker_diarization", False)

        # SSE推送回调
        self.sse_callback = None

        # 录制窗口
        self.recorder_window_thread = None

        # 音频文件
        self.audio_file_path = None
        self.temp_dir = None

        # 处理线程
        self.transcribe_thread = None
        self.should_process = True

    def set_sse_callback(self, callback: Callable):
        """设置SSE推送回调"""
        self.sse_callback = callback

    async def start_processing(self):
        """初始化会议处理器（不开始录制）"""
        try:
            if self.is_running:
                logger.warning(f"会议处理器 {self.task_id} 已在运行")
                return False

            # 创建临时目录
            self.temp_dir = tempfile.mkdtemp()
            self.audio_file_path = Path(self.temp_dir) / f"meeting_{self.task_id}.wav"

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "initializing",
                    "progress": 10,
                    "current_step": "初始化语音识别引擎...",
                },
            )

            # 初始化语音识别
            engine = self.config.get("engine", "sensevoice")
            initialize_voice_recognition(engine)

            # 更新状态为等待开始
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "ready",
                    "progress": 30,
                    "current_step": "等待开始录制...",
                },
            )

            # 启动录制窗口（如果未禁用GUI）
            if not self.config.get("disable_gui", False):
                title = self.config.get("title", "会议记录")
                try:
                    self.recorder_window_thread = show_recorder_window_in_thread(
                        task_id=self.task_id,
                        title=title,
                        config=self.config,
                        on_pause=self._on_pause,
                        on_resume=self._on_resume,
                        on_stop=self._on_stop,
                    )

                    if self.recorder_window_thread is not None:
                        logger.info("🖥️ 录制窗口已启动")
                    else:
                        logger.info("🌐 macOS系统：请通过Web界面控制录制")

                except Exception as e:
                    logger.error(f"❌ 启动录制窗口失败: {e}")
                    # 即使GUI启动失败，也继续录制过程
                    self.recorder_window_thread = None
                    logger.info("⚠️ 继续无GUI模式录制")
            else:
                logger.info("🎛️ GUI已禁用，使用外部控制器")
                self.recorder_window_thread = None

            logger.info(f"✅ 会议处理器初始化成功: {self.task_id}")

            # 根据是否有GUI窗口调整提示内容
            import platform

            if platform.system() == "Darwin" and self.recorder_window_thread is None:
                logger.info("🍎 macOS系统：GUI控制器已启动")
                logger.info("💡 请在GUI控制器中点击'开始录制'按钮")
            elif self.recorder_window_thread is not None:
                logger.info("🖥️ 录制窗口已启动")
                logger.info("💡 请在录制窗口中点击'开始录制'按钮")
            else:
                logger.info("⚠️ GUI启动失败，请通过Web界面控制录制")

            # 发送会议初始化通知
            meeting_title = self.config.get("title", "会议记录")
            notification_service.notify_meeting_status(
                meeting_title=meeting_title,
                status="initialized",
                message_extra="会议已创建，等待开始录制",
            )

            return True

        except Exception as e:
            logger.error(f"❌ 启动会议处理器失败: {e}")
            await self._cleanup()
            return False

    async def start_recording(self):
        """开始音频录制和转录"""
        try:
            if self.is_running:
                logger.warning(f"录制已在进行中: {self.task_id}")
                return False

            # 更新状态为启动音频
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "starting_audio",
                    "progress": 40,
                    "current_step": "启动音频捕获...",
                },
            )

            # 启动音频捕获
            if not self.audio_capture.start_capture(callback=self._audio_callback):
                raise RuntimeError("音频捕获启动失败")

            self.is_running = True

            # 启动转录处理线程
            self.transcribe_thread = threading.Thread(
                target=self._transcribe_loop, daemon=True
            )
            self.transcribe_thread.start()

            # 更新状态为录制中
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "recording",
                    "progress": 50,
                    "current_step": "会议记录中...",
                },
            )

            logger.info(f"🎙️ 开始录制: {self.task_id}")
            logger.info("📝 音频捕获和转录已启动")

            # 发送录制开始通知
            meeting_title = self.config.get("title", "会议记录")
            notification_service.notify_meeting_status(
                meeting_title=meeting_title,
                status="started",
                message_extra="录制已开始，正在进行音频捕获和转录",
            )

            return True

        except Exception as e:
            logger.error(f"❌ 开始录制失败: {e}")
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "error",
                    "current_step": f"录制启动失败: {str(e)}",
                },
            )
            return False

    def _audio_callback(self, data_dict):
        """音频回调函数"""
        if self.is_running and not self.is_paused:
            # 从字典中提取音频数据
            audio_data = data_dict.get("audio_data")
            timestamp = data_dict.get("timestamp")

            if audio_data is not None:
                # 添加到缓冲区
                self.audio_buffer.add_audio(audio_data, timestamp)
                # 保存到文件（用于最终处理）
                self.accumulated_audio.append(audio_data)

    def _transcribe_loop(self):
        """转录处理循环"""
        while self.should_process and self.is_running:
            try:
                current_time = time.time()

                # 检查是否需要转录
                if (
                    not self.is_paused
                    and current_time - self.last_transcribe_time
                    >= self.transcribe_interval
                ):

                    # 获取音频数据（增加到10秒，提高识别准确性）
                    audio_data = self.audio_buffer.get_latest_audio(duration=10.0)

                    if audio_data is not None and len(audio_data) > 0:
                        # 执行转录
                        self._perform_transcription(audio_data, current_time)

                    self.last_transcribe_time = current_time

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"转录循环错误: {e}")
                time.sleep(1)

    def _perform_transcription(self, audio_data, timestamp):
        """执行转录和语音分析"""
        try:
            # 转录音频 - 需要先保存为临时文件
            temp_audio_file = self._save_audio_to_temp_file(audio_data)
            if temp_audio_file is None:
                return

            # 使用语音分析服务进行完整分析
            if self.enable_voice_analysis:
                try:
                    # 使用同步版本的语音分析
                    from .voice_analysis_service import analyze_realtime_audio_sync

                    result = analyze_realtime_audio_sync(audio_data)
                except Exception as e:
                    # 如果语音分析失败，回退到基础转录
                    logger.warning(f"语音分析失败，回退到基础转录: {e}")
                    result = self._basic_transcription_sync(temp_audio_file)
            else:
                # 使用基础转录
                result = self._basic_transcription_sync(temp_audio_file)

            if result and not result.get("error"):
                segments = result.get("segments", [])
                if segments:
                    # 处理第一个段落（实时处理通常只有一个段落）
                    segment_data = segments[0]
                    text = segment_data.get("text", "").strip()

                    if text:
                        # 创建转录片段
                        segment = {
                            "id": f"{self.task_id}_{int(timestamp)}",
                            "timestamp": timestamp,
                            "text": text,
                            "confidence": segment_data.get("confidence", 0.8),
                            "language": segment_data.get("language", "zh"),
                            "speaker": segment_data.get("speaker", "Speaker_1"),
                            "emotion": segment_data.get("emotion", {}),
                            "duration": segment_data.get("duration", 3.0),
                        }

                        # 更新说话人信息
                        speaker_id = segment["speaker"]
                        if speaker_id not in self.speakers:
                            self.speakers[speaker_id] = {
                                "name": speaker_id,
                                "total_duration": 0,
                                "segments_count": 0,
                                "emotions": {},
                            }

                        self.speakers[speaker_id]["total_duration"] += segment[
                            "duration"
                        ]
                        self.speakers[speaker_id]["segments_count"] += 1

                        # 统计情感信息
                        emotion = segment.get("emotion", {}).get(
                            "primary_emotion", "neutral"
                        )
                        if emotion not in self.speakers[speaker_id]["emotions"]:
                            self.speakers[speaker_id]["emotions"][emotion] = 0
                        self.speakers[speaker_id]["emotions"][emotion] += 1

                        # 添加到累积文本
                        self.accumulated_text.append(segment)

                        # 推送到前端
                        if self.sse_callback:
                            asyncio.create_task(
                                self.sse_callback(
                                    {"type": "transcription", "data": segment}
                                )
                            )

                        logger.info(
                            f"📝 转录 [{speaker_id}] [{emotion}]: {text[:50]}..."
                        )

        except Exception as e:
            logger.error(f"转录失败: {e}")
        finally:
            # 清理临时文件
            if (
                "temp_audio_file" in locals()
                and temp_audio_file
                and os.path.exists(temp_audio_file)
            ):
                try:
                    os.remove(temp_audio_file)
                except:
                    pass

    def _basic_transcription_sync(self, temp_audio_file: str) -> Dict[str, Any]:
        """基础转录功能（当语音分析不可用时的备用方案）"""
        try:
            from core.asr import get_voice_core

            voice_core = get_voice_core()

            # 确保引擎已初始化
            engine = self.config.get("engine", "sensevoice")
            current_engine_name = voice_core.get_current_engine_name()
            if not voice_core.current_engine or current_engine_name != engine:
                from core.asr import initialize_voice_recognition

                initialize_voice_recognition(engine)
                # 确保引擎已加载
                voice_core._ensure_engine_loaded(engine)

            result = voice_core.recognize_file(temp_audio_file)

            if result and result.get("text", "").strip():
                # 转换为语音分析服务的格式
                return {
                    "segments": [
                        {
                            "text": result["text"].strip(),
                            "confidence": result.get("confidence", 0.8),
                            "language": result.get("language", "zh"),
                            "speaker": "Speaker_1",
                            "emotion": {"primary_emotion": "neutral"},
                            "duration": 3.0,
                            "start": 0.0,
                            "end": 3.0,
                        }
                    ]
                }
            else:
                return {"segments": []}

        except Exception as e:
            logger.error(f"基础转录失败: {e}")
            return {"error": str(e)}

    def _save_audio_to_temp_file(self, audio_data) -> Optional[str]:
        """保存音频数据到临时文件"""
        try:
            import wave
            import tempfile

            # 确保data目录存在
            from pathlib import Path

            data_dir = Path(__file__).parent.parent.parent / "data" / "temp_audio"
            data_dir.mkdir(parents=True, exist_ok=True)

            # 创建临时文件在data目录下
            import time

            timestamp = int(time.time() * 1000)
            temp_path = str(data_dir / f"meeting_{self.task_id}_{timestamp}.wav")

            # 转换音频数据格式
            if isinstance(audio_data, np.ndarray):
                # 转换为16位整数
                audio_int16 = (audio_data * 32767).astype(np.int16)
            else:
                logger.error("不支持的音频数据格式")
                return None

            # 写入WAV文件
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(1)  # 单声道
                wf.setsampwidth(2)  # 16位
                wf.setframerate(16000)  # 16kHz采样率
                wf.writeframes(audio_int16.tobytes())

            return temp_path

        except Exception as e:
            logger.error(f"保存临时音频文件失败: {e}")
            return None

    def _detect_speaker(self, audio_data) -> Optional[str]:
        """检测说话人（简单实现）"""
        # 这里可以集成说话人分离算法
        # 暂时返回简单的说话人标识
        return "Speaker1"  # 简化实现

    async def pause_processing(self):
        """暂停处理"""
        try:
            if not self.is_running or self.is_paused:
                return False

            self.is_paused = True

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                self.task_id,
                {"status": "paused", "current_step": "会议记录已暂停"},
            )

            logger.info(f"⏸️ 会议处理器已暂停: {self.task_id}")

            # 发送暂停通知
            meeting_title = self.config.get("title", "会议记录")
            notification_service.notify_meeting_status(
                meeting_title=meeting_title, status="paused"
            )

            return True

        except Exception as e:
            logger.error(f"暂停会议处理器失败: {e}")
            return False

    async def resume_processing(self):
        """继续处理"""
        try:
            if not self.is_running or not self.is_paused:
                return False

            self.is_paused = False

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                self.task_id,
                {"status": "recording", "current_step": "会议记录中..."},
            )

            logger.info(f"▶️ 会议处理器已继续: {self.task_id}")

            # 发送继续通知
            meeting_title = self.config.get("title", "会议记录")
            notification_service.notify_meeting_status(
                meeting_title=meeting_title, status="resumed"
            )

            return True

        except Exception as e:
            logger.error(f"继续会议处理器失败: {e}")
            return False

    async def stop_processing(self):
        """停止处理"""
        try:
            if not self.is_running:
                return False

            self.is_running = False
            self.should_process = False

            # 更新状态
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "processing",
                    "progress": 70,
                    "current_step": "正在生成会议总结...",
                },
            )

            # 停止音频捕获
            if self.audio_capture:
                self.audio_capture.stop_capture()

            # 等待转录线程结束
            if self.transcribe_thread and self.transcribe_thread.is_alive():
                self.transcribe_thread.join(timeout=5.0)

            # 生成最终结果
            await self._generate_final_results()

            # 清理资源
            await self._cleanup()

            logger.info(f"⏹️ 会议处理器已停止: {self.task_id}")
            return True

        except Exception as e:
            logger.error(f"停止会议处理器失败: {e}")
            return False

    async def _generate_final_results(self):
        """生成最终结果"""
        try:
            # 合并转录文本
            full_transcript = ""
            speakers_info = {}

            for segment in self.accumulated_text:
                text = segment["text"]
                speaker = segment.get("speaker")

                if speaker:
                    full_transcript += f"[{speaker}]: {text}\n"
                    if speaker not in speakers_info:
                        speakers_info[speaker] = {
                            "name": speaker,
                            "segments": 0,
                            "total_words": 0,
                        }
                    speakers_info[speaker]["segments"] += 1
                    speakers_info[speaker]["total_words"] += len(text.split())
                else:
                    full_transcript += f"{text}\n"

            if not full_transcript.strip():
                # 没有转录内容
                await task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "error",
                        "progress": 100,
                        "current_step": "未检测到音频内容",
                        "error": "没有录制到任何音频，无法生成会议记录",
                    },
                )
                return

            # 保存音频文件到项目data目录
            audio_file_path = None
            if self.audio_buffer and self.audio_buffer.get_duration() > 0:
                try:
                    # 确保data目录存在
                    from pathlib import Path

                    data_dir = (
                        Path(__file__).parent.parent.parent / "data" / "temp_audio"
                    )
                    data_dir.mkdir(parents=True, exist_ok=True)

                    # 创建最终音频文件路径
                    final_audio_path = data_dir / f"meeting_{self.task_id}_final.wav"

                    # 保存音频缓冲区到文件
                    if self.audio_buffer.save_to_file(str(final_audio_path)):
                        audio_file_path = str(final_audio_path)
                        logger.info(f"✅ 音频文件已保存: {audio_file_path}")
                    else:
                        logger.error("❌ 音频缓冲区保存失败")

                except Exception as e:
                    logger.error(f"保存音频文件失败: {e}")

            # 使用video_service生成AI内容
            if self.config.get("enable_realtime_summary", False):
                await task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "processing",
                        "progress": 80,
                        "current_step": "正在生成AI内容...",
                    },
                )

                # 生成AI内容
                ai_results = await self._generate_ai_content(
                    full_transcript, audio_file_path
                )
            else:
                ai_results = {}

            # 准备完整的转录文本
            full_transcript = (
                "\n".join(self.accumulated_text) if self.accumulated_text else ""
            )

            # 更新最终结果
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "finished",  # 修改为 finished
                    "progress": 100,
                    "current_step": "会议记录完成",
                    "results": ai_results,
                    "transcript": full_transcript,  # 添加完整转录文本
                    "transcript_segments": len(self.accumulated_text),  # 转录段数
                    "duration": (
                        len(self.accumulated_text) * self.transcribe_interval
                        if self.accumulated_text
                        else 0
                    ),
                },
            )

            logger.info(f"✅ 会议结果生成完成: {self.task_id}")

            # 发送会议完成通知
            meeting_title = self.config.get("title", "会议记录")
            duration_text = None
            if len(self.accumulated_text) > 0:
                total_duration_sec = (
                    len(self.accumulated_text) * self.transcribe_interval
                )
                minutes = int(total_duration_sec // 60)
                seconds = int(total_duration_sec % 60)
                duration_text = f"{minutes}分{seconds}秒"

            notification_service.notify_meeting_status(
                meeting_title=meeting_title,
                status="finished",  # 使用 finished 状态
                duration=duration_text,
                message_extra=f"已生成转录文本和{'AI内容' if self.config.get('enable_realtime_summary') else '基础总结'}",
            )

        except Exception as e:
            logger.error(f"生成最终结果失败: {e}")
            await task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "error",
                    "progress": 100,
                    "current_step": "结果生成失败",
                    "error": str(e),
                },
            )

            # 发送会议错误通知
            meeting_title = self.config.get("title", "会议记录")
            notification_service.notify_meeting_status(
                meeting_title=meeting_title,
                status="error",
                message_extra=f"处理失败: {str(e)[:100]}",
            )

    async def _generate_ai_content(
        self, transcript: str, audio_path: Optional[str] = None
    ):
        """生成AI内容 - 会议专用，传入meeting role"""
        try:
            ai_results = {}

            # 🎯 会议专用：传入meeting role
            meeting_kwargs = {
                "content_role": "meeting",  # 强制指定为会议角色
                "transcript": transcript,
                "audio_path": audio_path,
            }

            # 使用video_service生成内容
            # 内容卡片 (会议纪要)
            content_card_result = await video_service.generate_ai_content(
                "content_card", **meeting_kwargs
            )

            if content_card_result.get("success"):
                ai_results["meeting_notes"] = content_card_result.get("content", "")

            # AI分析
            summary_result = await video_service.generate_ai_content(
                "ai_analysis", **meeting_kwargs
            )

            if summary_result.get("success"):
                ai_results["summary"] = summary_result.get("content", "")

            # 思维导图
            mindmap_result = await video_service.generate_ai_content(
                "mind_map", **meeting_kwargs
            )

            if mindmap_result.get("success"):
                ai_results["mindmap"] = mindmap_result.get("content", "")

            # 学习闪卡 (会议要点)
            flashcards_result = await video_service.generate_ai_content(
                "flashcards", **meeting_kwargs
            )

            if flashcards_result.get("success"):
                ai_results["flashcards"] = flashcards_result.get("content", "")

            logger.info(f"✅ 会议AI内容生成完成，使用meeting角色")
            return ai_results

        except Exception as e:
            logger.error(f"生成AI内容失败: {e}")
            return {}

    async def _cleanup(self):
        """清理资源"""
        try:
            # 清理音频捕获
            if self.audio_capture:
                self.audio_capture.stop_capture()

            # 清理临时文件
            if self.temp_dir:
                import shutil

                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass

        except Exception as e:
            logger.error(f"清理资源失败: {e}")

    def _on_pause(self, task_id: str):
        """录制窗口暂停回调"""
        asyncio.create_task(self.pause_processing())

    def _on_resume(self, task_id: str):
        """录制窗口继续回调"""
        asyncio.create_task(self.resume_processing())

    def _on_stop(self, task_id: str):
        """录制窗口停止回调"""
        asyncio.create_task(self.stop_processing())


class RealtimeMeetingService:
    """实时会议服务"""

    def __init__(self):
        self.processors: Dict[str, RealtimeMeetingProcessor] = {}

    async def create_meeting_processor(
        self, task_id: str, config: Dict[str, Any]
    ) -> bool:
        """创建会议处理器"""
        try:
            if task_id in self.processors:
                logger.warning(f"会议处理器已存在: {task_id}")
                return False

            processor = RealtimeMeetingProcessor(task_id, config)
            success = await processor.start_processing()

            if success:
                self.processors[task_id] = processor
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"创建会议处理器失败: {e}")
            return False

    def get_meeting_processor(self, task_id: str) -> Optional[RealtimeMeetingProcessor]:
        """获取会议处理器"""
        return self.processors.get(task_id)

    async def start_meeting_recording(self, task_id: str) -> bool:
        """开始会议录制"""
        processor = self.processors.get(task_id)
        if processor:
            return await processor.start_recording()
        return False

    async def pause_meeting_processor(self, task_id: str) -> bool:
        """暂停会议处理器"""
        processor = self.processors.get(task_id)
        if processor:
            return await processor.pause_processing()
        return False

    async def resume_meeting_processor(self, task_id: str) -> bool:
        """继续会议处理器"""
        processor = self.processors.get(task_id)
        if processor:
            return await processor.resume_processing()
        return False

    async def stop_meeting_processor(self, task_id: str) -> bool:
        """停止会议处理器"""
        processor = self.processors.get(task_id)
        if processor:
            success = await processor.stop_processing()
            if task_id in self.processors:
                del self.processors[task_id]
            return success
        return False

    async def cleanup_all(self):
        """清理所有处理器"""
        for task_id in list(self.processors.keys()):
            await self.stop_meeting_processor(task_id)


# 全局服务实例
realtime_meeting_service = RealtimeMeetingService()


# 便捷函数
async def create_meeting_processor(task_id: str, config: Dict[str, Any]) -> bool:
    """创建会议处理器"""
    return await realtime_meeting_service.create_meeting_processor(task_id, config)


async def stop_meeting_processor(task_id: str) -> bool:
    """停止会议处理器"""
    return await realtime_meeting_service.stop_meeting_processor(task_id)


def get_meeting_processor(task_id: str) -> Optional[RealtimeMeetingProcessor]:
    """获取会议处理器"""
    return realtime_meeting_service.get_meeting_processor(task_id)
