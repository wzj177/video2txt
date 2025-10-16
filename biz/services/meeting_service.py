#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议处理服务 - 实时音频捕获、转录、分析
"""

import os
import sys
import logging
import asyncio
import threading
import time
import json
import tempfile
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from datetime import datetime
import numpy as np

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.audio.audio_capture import AudioCapture, AudioBuffer
from core.asr import initialize_voice_recognition, transcribe_audio
from .task_service import task_service
from core.asr.voice_recognition_core import get_voice_core

logger = logging.getLogger(__name__)


class MeetingProcessor:
    """会议处理器"""

    def __init__(self, task_id: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.config = config
        self.is_running = False

        # 音频相关
        self.audio_capture = AudioCapture(
            sample_rate=16000, channels=1, chunk_size=1024
        )
        self.audio_buffer = AudioBuffer(max_duration=30.0)

        # 转录相关
        self.last_transcribe_time = 0
        self.transcribe_interval = 3.0  # 每3秒转录一次
        self.accumulated_text = []

        # 说话人识别
        self.speakers = {}
        self.current_speaker = None

        # SSE推送回调
        self.sse_callback = None

        # 分析结果
        self.meeting_summary = {
            "transcripts": [],
            "speakers": {},
            "keywords": [],
            "key_points": [],
            "start_time": datetime.now().isoformat(),
        }

    def set_sse_callback(self, callback: Callable):
        """设置SSE推送回调"""
        self.sse_callback = callback

    async def start_processing(self):
        """开始会议处理"""
        if self.is_running:
            logger.warning(f"会议处理器 {self.task_id} 已在运行")
            return False

        try:
            self.is_running = True

            # 更新任务状态
            await asyncio.create_task(
                task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "initializing",
                        "progress": 10,
                        "current_step": "初始化语音识别引擎...",
                    },
                )
            )

            # 初始化语音识别（延迟加载）
            engine = self.config.get("engine", "sensevoice")
            initialize_voice_recognition(engine)  # 现在只是准备，不会实际加载引擎

            # 更新状态
            await asyncio.create_task(
                task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "starting_audio",
                        "progress": 30,
                        "current_step": "启动音频捕获...",
                    },
                )
            )

            # 启动音频捕获
            if not self.audio_capture.start_capture(callback=self._audio_callback):
                raise RuntimeError("音频捕获启动失败")

            # 启动转录处理线程
            self.transcribe_thread = threading.Thread(
                target=self._transcribe_loop, daemon=True
            )
            self.transcribe_thread.start()

            # 更新状态为监控中
            await asyncio.create_task(
                task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "monitoring",
                        "progress": 50,
                        "current_step": "正在监控会议音频...",
                    },
                )
            )

            # 推送连接成功消息
            if self.sse_callback:
                await self.sse_callback(
                    {
                        "type": "connected",
                        "message": "会议监控已启动",
                        "config": self.config,
                    }
                )

            logger.info(f"会议处理器 {self.task_id} 启动成功")
            return True

        except Exception as e:
            logger.error(f"会议处理器启动失败: {e}")
            await self.stop_processing()

            # 更新任务状态为错误
            await asyncio.create_task(
                task_service.update_task(
                    "meeting",
                    self.task_id,
                    {
                        "status": "error",
                        "progress": 0,
                        "current_step": f"启动失败: {str(e)}",
                        "error": str(e),
                    },
                )
            )

            return False

    async def stop_processing(self):
        """停止会议处理"""
        if not self.is_running:
            return

        logger.info(f"正在停止会议处理器 {self.task_id}")
        self.is_running = False

        # 停止音频捕获
        self.audio_capture.stop_capture()

        # 等待转录线程结束
        if hasattr(self, "transcribe_thread") and self.transcribe_thread.is_alive():
            self.transcribe_thread.join(timeout=3)

        # 生成最终摘要
        await self._generate_final_summary()

        # 更新任务状态
        await asyncio.create_task(
            task_service.update_task(
                "meeting",
                self.task_id,
                {
                    "status": "completed",
                    "progress": 100,
                    "current_step": "会议监控已停止",
                    "end_time": datetime.now().isoformat(),
                    "summary": self.meeting_summary,
                },
            )
        )

        # 推送停止消息
        if self.sse_callback:
            await self.sse_callback(
                {
                    "type": "disconnected",
                    "message": "会议监控已停止",
                    "summary": self.meeting_summary,
                }
            )

        logger.info(f"会议处理器 {self.task_id} 已停止")

    def _audio_callback(self, audio_data: Dict[str, Any]):
        """音频数据回调"""
        if not self.is_running:
            return

        # 添加音频到缓冲区
        self.audio_buffer.add_audio(audio_data["audio_data"])

        # 推送音量数据
        if self.sse_callback:
            asyncio.create_task(
                self.sse_callback(
                    {
                        "type": "volume",
                        "level": audio_data["volume_level"],
                        "timestamp": audio_data["timestamp"],
                    }
                )
            )

    def _transcribe_loop(self):
        """转录处理循环"""
        logger.info(f"转录处理线程已启动 (任务: {self.task_id})")

        while self.is_running:
            try:
                current_time = time.time()

                # 检查是否到了转录时间
                if current_time - self.last_transcribe_time >= self.transcribe_interval:
                    self._process_transcription()
                    self.last_transcribe_time = current_time

                time.sleep(0.5)  # 避免过度消耗CPU

            except Exception as e:
                logger.error(f"转录处理循环错误: {e}")
                if self.is_running:
                    time.sleep(1)  # 错误后等待1秒再继续

        logger.info(f"转录处理线程已结束 (任务: {self.task_id})")

    def _process_transcription(self):
        """处理音频转录"""
        try:
            # 获取最近的音频数据
            audio_data = self.audio_buffer.get_audio(duration=5.0)  # 最近5秒

            if len(audio_data) < 16000:  # 少于1秒的音频不处理
                return

            # 检查音频是否有足够的能量（避免处理静音）
            energy = np.sqrt(np.mean(audio_data**2))
            if energy < 0.01:  # 能量阈值
                return

            # 保存音频到临时文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name

            # 保存音频
            if not self.audio_buffer.save_to_file(temp_path, duration=5.0):
                logger.warning("保存临时音频文件失败")
                return

            try:
                # 进行语音识别
                language = self.config.get("source_language", "auto")
                result = transcribe_audio(temp_path, language=language)

                if result and result.get("text", "").strip():
                    transcript_text = result["text"].strip()

                    # 说话人识别 (简单实现)
                    speaker = self._identify_speaker(audio_data)

                    # 创建转录记录
                    transcript = {
                        "text": transcript_text,
                        "speaker": speaker,
                        "timestamp": datetime.now().isoformat(),
                        "confidence": result.get("confidence", 0.9),
                        "language": result.get("language", language),
                    }

                    # 添加到累积文本
                    self.accumulated_text.append(transcript)
                    self.meeting_summary["transcripts"].append(transcript)

                    # 更新说话人统计
                    if speaker not in self.meeting_summary["speakers"]:
                        self.meeting_summary["speakers"][speaker] = {
                            "name": speaker,
                            "word_count": 0,
                            "speaking_time": 0,
                        }

                    self.meeting_summary["speakers"][speaker]["word_count"] += len(
                        transcript_text.split()
                    )

                    # 推送转录结果
                    if self.sse_callback:
                        asyncio.create_task(
                            self.sse_callback(
                                {"type": "transcript", "content": transcript}
                            )
                        )

                    # 如果需要翻译
                    if self.config.get("target_language", "none") != "none":
                        translation = self._translate_text(
                            transcript_text, self.config["target_language"]
                        )

                        if translation:
                            if self.sse_callback:
                                asyncio.create_task(
                                    self.sse_callback(
                                        {
                                            "type": "translation",
                                            "content": {
                                                "translation": translation,
                                                "target_language": self.config[
                                                    "target_language"
                                                ],
                                            },
                                        }
                                    )
                                )

                    # 定期进行关键词提取和分析
                    if len(self.accumulated_text) % 5 == 0:  # 每5句话分析一次
                        self._analyze_content()

            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"转录处理失败: {e}")

    def _identify_speaker(self, audio_data: np.ndarray) -> str:
        """简单的说话人识别"""
        # 这里实现简单的说话人识别逻辑
        # 实际应用中可以使用更复杂的声纹识别算法

        # 计算音频特征
        energy = np.sqrt(np.mean(audio_data**2))
        pitch_estimate = self._estimate_pitch(audio_data)

        # 基于特征匹配说话人
        speaker_key = f"pitch_{int(pitch_estimate/50)*50}_energy_{int(energy*1000)}"

        if speaker_key not in self.speakers:
            speaker_count = len(self.speakers) + 1
            speaker_name = f"参与者{speaker_count}"
            self.speakers[speaker_key] = speaker_name

        return self.speakers[speaker_key]

    def _estimate_pitch(self, audio_data: np.ndarray) -> float:
        """估算基频（简单实现）"""
        try:
            # 使用自相关法估算基频
            correlation = np.correlate(audio_data, audio_data, mode="full")
            correlation = correlation[len(correlation) // 2 :]

            # 找到第一个峰值
            for i in range(50, min(400, len(correlation))):
                if correlation[i] > 0.3 * np.max(correlation):
                    return 16000 / i  # 转换为频率

            return 150.0  # 默认值
        except:
            return 150.0

    def _translate_text(self, text: str, target_language: str) -> Optional[str]:
        """翻译文本（简单实现）"""
        # 这里可以集成翻译API或本地翻译模型
        # 目前返回模拟翻译结果

        translation_map = {
            "en": f"[EN] {text}",
            "ja": f"[JA] {text}",
            "ko": f"[KO] {text}",
        }

        return translation_map.get(
            target_language, f"[{target_language.upper()}] {text}"
        )

    def _analyze_content(self):
        """分析会议内容"""
        try:
            # 合并最近的文本
            recent_texts = [t["text"] for t in self.accumulated_text[-10:]]
            combined_text = " ".join(recent_texts)

            if not combined_text.strip():
                return

            # 简单的关键词提取
            keywords = self._extract_keywords(combined_text)

            # 更新关键词（去重）
            for keyword in keywords:
                if keyword not in self.meeting_summary["keywords"]:
                    self.meeting_summary["keywords"].append(keyword)

            # 生成要点
            key_point = self._generate_key_point(combined_text)
            if key_point:
                self.meeting_summary["key_points"].append(
                    {"content": key_point, "timestamp": datetime.now().isoformat()}
                )

            # 推送分析结果
            if self.sse_callback:
                asyncio.create_task(
                    self.sse_callback(
                        {
                            "type": "analysis",
                            "content": {"keywords": keywords, "key_point": key_point},
                        }
                    )
                )

        except Exception as e:
            logger.error(f"内容分析失败: {e}")

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简单实现）"""
        # 简单的关键词提取逻辑
        import re

        # 移除标点符号，分词
        words = re.findall(r"\b\w+\b", text.lower())

        # 过滤停用词
        stop_words = {
            "的",
            "是",
            "在",
            "有",
            "和",
            "了",
            "我",
            "你",
            "他",
            "她",
            "它",
            "the",
            "is",
            "at",
            "which",
            "on",
            "and",
            "a",
            "an",
            "as",
            "are",
        }

        keywords = [word for word in words if len(word) > 2 and word not in stop_words]

        # 统计词频，返回高频词
        from collections import Counter

        word_counts = Counter(keywords)

        return [word for word, count in word_counts.most_common(5)]

    def _generate_key_point(self, text: str) -> Optional[str]:
        """生成要点（简单实现）"""
        # 简单的要点生成逻辑
        sentences = text.split("。")

        # 选择最长的句子作为要点
        if sentences:
            longest_sentence = max(sentences, key=len).strip()
            if len(longest_sentence) > 10:
                return longest_sentence + "。"

        return None

    async def _generate_final_summary(self):
        """生成最终会议摘要"""
        try:
            if not self.meeting_summary["transcripts"]:
                return

            # 统计信息
            total_words = sum(
                len(t["text"].split()) for t in self.meeting_summary["transcripts"]
            )
            duration = (
                datetime.now()
                - datetime.fromisoformat(self.meeting_summary["start_time"])
            ).total_seconds()

            # 生成摘要
            summary_text = self._generate_summary_text()

            self.meeting_summary.update(
                {
                    "total_words": total_words,
                    "duration_seconds": duration,
                    "summary_text": summary_text,
                    "end_time": datetime.now().isoformat(),
                }
            )

            logger.info(f"会议摘要已生成 (任务: {self.task_id})")

        except Exception as e:
            logger.error(f"生成最终摘要失败: {e}")

    def _generate_summary_text(self) -> str:
        """生成摘要文本"""
        if not self.meeting_summary["transcripts"]:
            return "本次会议没有有效的转录内容。"

        # 简单的摘要生成
        key_points = [kp["content"] for kp in self.meeting_summary["key_points"]]
        keywords = ", ".join(self.meeting_summary["keywords"][:10])

        summary_parts = []

        if key_points:
            summary_parts.append(f"会议要点：{'; '.join(key_points[:3])}")

        if keywords:
            summary_parts.append(f"关键词：{keywords}")

        speaker_count = len(self.meeting_summary["speakers"])
        summary_parts.append(f"参与人数：{speaker_count}人")

        return " | ".join(summary_parts)


class MeetingService:
    """会议服务管理器"""

    def __init__(self):
        self.processors = {}  # task_id -> MeetingProcessor

    async def create_meeting_processor(
        self, task_id: str, config: Dict[str, Any]
    ) -> bool:
        """创建会议处理器"""
        if task_id in self.processors:
            logger.warning(f"会议处理器 {task_id} 已存在")
            return False

        try:
            processor = MeetingProcessor(task_id, config)
            self.processors[task_id] = processor

            # 启动处理器
            success = await processor.start_processing()

            if not success:
                del self.processors[task_id]
                return False

            return True

        except Exception as e:
            logger.error(f"创建会议处理器失败: {e}")
            return False

    async def process_uploaded_audio(self, task_id: str, audio_file_path: str):
        """处理上传的音频文件"""
        try:
            # 获取任务信息
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False

            config = task.get("config", {})

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "processing",
                    "progress": 10,
                    "current_step": "开始处理上传的音频文件...",
                },
            )

            # 初始化语音识别引擎
            engine = config.get("engine", "sensevoice")
            voice_core = get_voice_core()
            voice_core.initialize(engine)  # 修复：将 initialize_engine 改为 initialize

            # 更新任务状态
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "processing",
                    "progress": 30,
                    "current_step": "正在进行语音识别...",
                },
            )

            # 执行语音识别
            result = voice_core.recognize_file(
                audio_file_path, language=config.get("language", "auto")
            )

            if not result or not result.get("text", "").strip():
                # 没有识别到内容
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": "error",
                        "progress": 100,
                        "current_step": "未识别到有效音频内容",
                        "error": "音频文件中未检测到有效的语音内容",
                    },
                )
                return False

            # 处理识别结果
            transcript_text = result.get("text", "").strip()
            segments = []
            speakers_info = {}

            # 如果启用了说话人分离和情感分析，则进行高级处理
            if config.get("enable_speaker_diarization", False) or config.get(
                "enable_ai_analysis", False
            ):
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": "processing",
                        "progress": 50,
                        "current_step": "正在进行说话人分离和情感分析...",
                    },
                )

                try:
                    # 使用语音分析服务进行说话人分离和情感分析
                    from biz.services.voice_analysis_service import (
                        voice_analysis_service,
                    )
                    from biz.services.ai_meeting_analyzer import ai_meeting_analyzer

                    # 执行完整的语音分析
                    analysis_result = await voice_analysis_service.analyze_audio_file(
                        audio_file_path,
                        enable_diarization=config.get(
                            "enable_speaker_diarization", True
                        ),
                        enable_emotion=config.get("enable_ai_analysis", True),
                    )

                    if not analysis_result.get("error") and analysis_result.get(
                        "segments"
                    ):
                        # 使用分析结果
                        segments = analysis_result["segments"]
                        speakers_info = analysis_result.get("diarization", {}).get(
                            "speakers", {}
                        )
                        transcript_text = analysis_result.get(
                            "full_transcript", transcript_text
                        )

                        # 确保segments格式正确
                        formatted_segments = []
                        for seg in segments:
                            # 处理emotion字段 - 确保格式一致
                            emotion_value = seg.get("emotion", "neutral")
                            if isinstance(emotion_value, dict):
                                # 如果emotion是dict，提取主要情感
                                emotion_value = emotion_value.get("primary", "neutral")
                            elif not isinstance(emotion_value, str):
                                emotion_value = "neutral"

                            formatted_seg = {
                                "text": seg.get("text", ""),
                                "confidence": seg.get("confidence", 0.8),
                                "language": seg.get("language", "zh"),
                                "speaker": seg.get("speaker", "Speaker_1"),
                                "emotion": emotion_value,  # 统一为字符串格式
                                "start": seg.get("start", 0),
                                "end": seg.get("end", 0),
                                "duration": seg.get("duration", 0),
                                "timestamp": seg.get(
                                    "timestamp", datetime.now().isoformat()
                                ),
                            }
                            formatted_segments.append(formatted_seg)

                        segments = formatted_segments
                        logger.info(
                            f"✅ 语音分析完成: {len(segments)} 个分段, {len(speakers_info)} 个说话人"
                        )
                    else:
                        logger.warning(
                            f"语音分析失败: {analysis_result.get('error', '未知错误')}，使用基础识别结果"
                        )
                        raise Exception("语音分析失败")

                except Exception as e:
                    logger.warning(f"高级语音分析失败: {e}，使用基础处理")
                    # 回退到基础处理
                    segment = {
                        "text": transcript_text,
                        "confidence": result.get("confidence", 0.8),
                        "language": result.get("language", "zh"),
                        "speaker": "Speaker_1",
                        "emotion": "neutral",
                        "start": 0,
                        "end": len(transcript_text) / 20.0,
                        "duration": len(transcript_text) / 20.0,
                        "timestamp": datetime.now().isoformat(),
                    }
                    segments.append(segment)
                    speakers_info = {"Speaker_1": {"name": "Speaker_1", "segments": 1}}
            else:
                # 基础处理 - 不进行说话人分离
                segment = {
                    "text": transcript_text,
                    "confidence": result.get("confidence", 0.8),
                    "language": result.get("language", "zh"),
                    "speaker": "Speaker_1",
                    "emotion": "neutral",
                    "start": 0,
                    "end": len(transcript_text) / 20.0,
                    "duration": len(transcript_text) / 20.0,
                    "timestamp": datetime.now().isoformat(),
                }
                segments.append(segment)
                speakers_info = {"Speaker_1": {"name": "Speaker_1", "segments": 1}}

            # 准备结果数据结构
            results = {
                "transcript": transcript_text,  # 完整转录文本
                "segments": segments,  # 分段转录数据
                "speakers": speakers_info,  # 说话人信息
            }

            # 统计信息
            total_words = len(transcript_text.split())
            speaker_count = len(speakers_info)
            total_duration = (
                max(seg.get("end", 0) for seg in segments)
                if segments
                else len(transcript_text) / 20.0
            )

            # 如果启用了AI分析，则进行处理
            if config.get("enable_ai_analysis", False):
                await task_service.update_task(
                    "meeting",
                    task_id,
                    {
                        "status": "processing",
                        "progress": 70,
                        "current_step": "正在进行AI分析...",
                    },
                )

                # 使用AI会议分析器进行全面分析
                try:
                    ai_analysis = await ai_meeting_analyzer.analyze_meeting(
                        transcript_text=transcript_text,
                        segments=segments,
                        speakers=speakers_info,
                        config=config,
                    )

                    if ai_analysis and ai_analysis.get("success"):
                        # 合并AI分析结果
                        results.update(
                            {
                                "summary": ai_analysis.get("summary"),
                                "key_points": ai_analysis.get("key_points", []),
                                "keywords": ai_analysis.get("keywords", []),
                                "chapters": ai_analysis.get("chapters", []),
                                "qa_analysis": ai_analysis.get("qa_analysis", []),
                                "speaker_analysis": ai_analysis.get(
                                    "speaker_analysis", {}
                                ),
                                "meeting_overview": ai_analysis.get("meeting_overview"),
                                "action_items": ai_analysis.get("action_items", []),
                                "decisions": ai_analysis.get("decisions", []),
                            }
                        )
                        logger.info(f"✅ AI会议分析完成")
                    else:
                        raise Exception(
                            f"AI分析失败: {ai_analysis.get('error', '未知错误')}"
                        )

                except Exception as e:
                    logger.warning(f"AI分析处理失败: {e}")
                    # 回退到基础分析
                    results["summary"] = {
                        "content": f"会议内容摘要：{transcript_text[:200]}...",
                        "generated_at": datetime.now().isoformat(),
                    }
                    results["key_points"] = ["完成了语音识别转录", "建议进一步人工审核"]
                    results["keywords"] = []

            # 完成处理 - 同时保存到新旧两种数据结构中以确保兼容性
            update_data = {
                "status": "finished",  # 修复：将 completed 改为 finished 以匹配前端期望
                "progress": 100,
                "current_step": "处理完成",
                "results": results,  # 新的结构化数据
                "transcript": transcript_text,  # 纯文本转录
                "total_words": total_words,
                "speaker_count": speaker_count,
                "total_duration": total_duration,
                "engine": engine,
            }

            # 同时保存到旧的字段结构中以保持兼容性
            update_data["transcripts"] = segments  # 分段转录数据
            if results.get("summary"):
                update_data["summary"] = results["summary"]  # 摘要数据
            if results.get("keywords"):
                update_data["keywords"] = results["keywords"]  # 关键词数据

            await task_service.update_task("meeting", task_id, update_data)

            logger.info(f"✅ 音频文件处理完成: {task_id}")
            return True

        except Exception as e:
            logger.error(f"处理上传音频文件失败: {e}")
            await task_service.update_task(
                "meeting",
                task_id,
                {
                    "status": "error",
                    "progress": 100,
                    "current_step": "处理失败",
                    "error": str(e),
                },
            )
            return False

    async def stop_meeting_processor(self, task_id: str) -> bool:
        """停止会议处理器"""
        if task_id not in self.processors:
            logger.warning(f"会议处理器 {task_id} 不存在")
            return False

        try:
            processor = self.processors[task_id]
            await processor.stop_processing()
            del self.processors[task_id]
            return True

        except Exception as e:
            logger.error(f"停止会议处理器失败: {e}")
            return False

    def get_meeting_processor(self, task_id: str) -> Optional[MeetingProcessor]:
        """获取会议处理器"""
        return self.processors.get(task_id)

    def set_sse_callback(self, task_id: str, callback: Callable):
        """设置SSE回调"""
        processor = self.processors.get(task_id)
        if processor:
            processor.set_sse_callback(callback)


# 全局会议服务实例
meeting_service = MeetingService()
