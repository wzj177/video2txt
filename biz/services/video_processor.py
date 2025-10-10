#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 视频处理核心模块
统一的处理函数，供同步和异步调用
"""

import os
import sys
import json
import asyncio
import tempfile
import subprocess
import shutil
import time
import srt
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging

logger = logging.getLogger(__name__)

from ..services.task_service import task_service

# 导入ASR模块
from core.asr import voice_core, initialize_voice_recognition, transcribe_audio

# 导入AI内容生成工厂和帧提取器
from ..services.ai_content_generator import create_ai_factory
from core.media.frame_extractor import create_frame_extractor


class VideoProcessor:
    """视频处理核心类 - 统一的处理逻辑"""

    def __init__(self):
        self.work_dir = Path(__file__).parent.parent.parent / "data" / "outputs"
        self.uploads_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        # 初始化AI内容生成工厂和帧提取器
        self._ai_factory = None
        self._frame_extractor = None

    async def _get_ai_factory(self):
        """获取AI内容生成工厂实例"""
        if self._ai_factory is None:
            # 加载settings.json
            settings_path = Path("config/settings.json")
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            else:
                settings = {}

            self._ai_factory = await create_ai_factory(settings)

        return self._ai_factory

    def _get_frame_extractor(self):
        """获取帧提取器实例"""
        if self._frame_extractor is None:
            self._frame_extractor = create_frame_extractor()

        return self._frame_extractor

    async def process_file_complete(
        self, task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        完整的文件处理流程 - 统一函数

        Args:
            task_id: 任务ID
            file_data: 文件数据
            config: 处理配置

        Returns:
            处理结果
        """
        try:
            # 更新任务状态
            await task_service.update_task(
                "av",
                task_id,
                {"status": "running", "current_step": "开始处理文件...", "progress": 0},
            )

            # 获取文件路径
            file_path = file_data["file_path"]
            filename = file_data["filename"]

            # 检测文件类型
            file_type = self._detect_file_type(filename)
            await task_service.update_task(
                "av",
                task_id,
                {"current_step": f"检测到文件类型: {file_type}", "progress": 5},
            )

            # 获取媒体时长
            media_duration = await self._get_media_duration(file_path)
            await task_service.update_task(
                "av", task_id, {"media_duration": media_duration, "progress": 10}
            )

            # 提取音频（如果是视频文件） (10-30%)
            audio_path = None
            embedded_subtitle_path = None
            embedded_subtitle_content = None

            if file_type == "video":
                await task_service.update_task(
                    "av", task_id, {"current_step": "提取音频流...", "progress": 15}
                )
                audio_path = await self._extract_audio(file_path, task_id)

                # 获取音频时长
                if audio_path:
                    audio_duration = await self._get_media_duration(audio_path)
                    await task_service.update_task(
                        "av",
                        task_id,
                        {"audio_duration": audio_duration, "progress": 20},
                    )

                # 尝试提取内嵌字幕 (20-25%)
                await task_service.update_task(
                    "av",
                    task_id,
                    {"current_step": "检测内嵌字幕...", "progress": 25},
                )
                embedded_subtitle_path = await self._extract_embedded_subtitles(
                    file_path, task_id
                )

                if embedded_subtitle_path:
                    try:
                        with open(embedded_subtitle_path, "r", encoding="utf-8") as f:
                            embedded_subtitle_content = f.read()
                        logger.info(
                            f"成功读取内嵌字幕，长度: {len(embedded_subtitle_content)} 字符"
                        )
                    except Exception as e:
                        logger.warning(f"读取内嵌字幕失败: {e}")
                        embedded_subtitle_content = None

            # 语音识别 (25-50%)
            await task_service.update_task(
                "av",
                task_id,
                {"current_step": "开始语音识别...", "progress": 30},
            )

            if audio_path:
                transcript = await self._transcribe_audio(audio_path, config)
            else:
                # 直接处理音频文件
                transcript = await self._transcribe_audio(file_path, config)

            # 智能纠错处理 (50-60%)
            await task_service.update_task(
                "av", task_id, {"current_step": "智能纠错处理...", "progress": 50}
            )

            # 第一步：规则纠错
            original_text = (
                transcript.get("text", "")
                if isinstance(transcript, dict)
                else str(transcript)
            )
            corrected_text, rule_corrections = self._correct_whisper_errors(
                original_text
            )

            if rule_corrections:
                logger.info(f"规则纠错完成，修正了 {len(rule_corrections)} 处错误")

            # 第二步：AI纠错（如果配置了AI）
            ai_corrections = []
            if isinstance(transcript, dict) and transcript.get("segments"):
                # 将segments转换为SRT格式进行AI纠错
                srt_subtitles = []
                for i, segment in enumerate(transcript["segments"]):
                    start_time = timedelta(seconds=segment["start"])
                    end_time = timedelta(seconds=segment["end"])
                    content = segment["text"].strip()

                    # 应用规则纠错到每个segment
                    corrected_content, _ = self._correct_whisper_errors(content)

                    srt_subtitles.append(
                        srt.Subtitle(
                            index=i + 1,
                            start=start_time,
                            end=end_time,
                            content=corrected_content,
                        )
                    )

                # 检查是否启用AI纠错
                enable_ai_correction = config.get("ai_correction", False)
                if enable_ai_correction:
                    try:
                        from core.ai.ai_chat_client import create_ai_client

                        # 读取AI配置
                        settings_path = PROJECT_ROOT / "config" / "settings.json"
                        with open(settings_path, "r", encoding="utf-8") as f:
                            settings = json.load(f)

                        ai_client = create_ai_client("openai", settings)
                        ai_model = config.get("ai_model", "qwen-plus")

                        corrected_subtitles, ai_corrections = (
                            await self._ai_correct_subtitles(
                                srt_subtitles,
                                embedded_subtitle_content,
                                ai_client,
                                ai_model,
                                rounds=config.get("ai_correction_rounds", 2),
                            )
                        )

                        # 更新transcript
                        corrected_segments = []
                        corrected_full_text = ""

                        for subtitle in corrected_subtitles:
                            segment = {
                                "start": subtitle.start.total_seconds(),
                                "end": subtitle.end.total_seconds(),
                                "text": subtitle.content,
                            }
                            corrected_segments.append(segment)
                            corrected_full_text += subtitle.content + " "

                        transcript["segments"] = corrected_segments
                        transcript["text"] = corrected_full_text.strip()

                        if ai_corrections:
                            logger.info(
                                f"AI纠错完成，修正了 {len(ai_corrections)} 处错误"
                            )

                    except Exception as e:
                        logger.warning(f"AI纠错失败，跳过: {e}")

            else:
                # 对于纯文本transcript，只应用规则纠错
                transcript = (
                    corrected_text if isinstance(transcript, str) else transcript
                )

            # 生成摘要 (60-70%)
            await task_service.update_task(
                "av", task_id, {"current_step": "生成内容摘要...", "progress": 60}
            )
            summary = await self._generate_summary(transcript, config)

            # 生成输出文件 (70-100%)
            await task_service.update_task(
                "av", task_id, {"current_step": "生成输出文件...", "progress": 70}
            )
            output_files = await self._generate_output_files(
                task_id, transcript, summary, config, file_path, audio_path, file_type
            )

            # 构建结果对象
            results = {
                "transcript": (
                    transcript.get("text", "")
                    if isinstance(transcript, dict)
                    else str(transcript)
                ),
                "summary": summary,
                "files": output_files,
            }

            # 更新任务状态为完成
            await task_service.update_task(
                "av",
                task_id,
                {
                    "status": "completed",
                    "current_step": "处理完成",
                    "progress": 100,
                    "results": results,
                    "output_files": output_files,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            return {"success": True, "task_id": task_id, "results": results}

        except Exception as e:
            # 更新任务状态为失败
            await task_service.update_task(
                "av",
                task_id,
                {
                    "status": "failed",
                    "current_step": f"处理失败: {str(e)}",
                    "error": str(e),
                    "failed_at": datetime.now().isoformat(),
                },
            )

            return {"success": False, "error": str(e)}

    async def process_url_complete(
        self, task_id: str, url: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        完整的URL处理流程 - 统一函数

        Args:
            task_id: 任务ID
            url: 视频URL
            config: 处理配置

        Returns:
            处理结果
        """
        try:
            # 更新任务状态 (0-20%)
            await task_service.update_task(
                "av",
                task_id,
                {"status": "running", "current_step": "开始下载文件...", "progress": 0},
            )

            # 下载文件
            file_path = await self._download_file(url, task_id)
            if not file_path:
                raise Exception("文件下载失败")

            # 构建文件数据
            file_data = {
                "filename": Path(url).name or "downloaded_file",
                "file_path": str(file_path),
                "type": "url",
            }

            # 调用文件处理方法
            return await self.process_file_complete(task_id, file_data, config)

        except Exception as e:
            # 更新任务状态为失败
            await task_service.update_task(
                "av",
                task_id,
                {
                    "status": "failed",
                    "current_step": f"处理失败: {str(e)}",
                    "error": str(e),
                    "failed_at": datetime.now().isoformat(),
                },
            )

            return {"success": False, "error": str(e)}

    def _detect_file_type(self, filename: str) -> str:
        """检测文件类型"""
        video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
        audio_extensions = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}

        ext = Path(filename).suffix.lower()
        if ext in video_extensions:
            return "video"
        elif ext in audio_extensions:
            return "audio"
        else:
            return "unknown"

    async def _get_media_duration(self, media_path: str) -> float:
        """获取媒体文件时长"""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                media_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                import json

                info = json.loads(stdout.decode())
                duration = float(info["format"]["duration"])
                return duration
            else:
                return 0.0

        except Exception as e:
            logger.warning(f"获取媒体时长失败: {e}")
            return 0.0

    async def _extract_audio(self, video_path: str, task_id: str) -> Optional[str]:
        """从视频中提取音频"""
        try:
            # 创建音频输出目录
            audio_dir = self.work_dir / task_id
            audio_dir.mkdir(parents=True, exist_ok=True)

            # 生成音频文件名
            audio_filename = f"{Path(video_path).stem}_audio.wav"
            audio_path_output = audio_dir / audio_filename

            # 使用ffmpeg提取音频
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",  # 不包含视频
                "-acodec",
                "pcm_s16le",  # 16位PCM编码
                "-ar",
                "16000",  # 16kHz采样率
                "-ac",
                "1",  # 单声道
                "-y",  # 覆盖输出文件
                str(audio_path_output),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return str(audio_path_output)
            else:
                raise Exception(f"音频提取失败: {stderr.decode()}")

        except Exception as e:
            raise Exception(f"音频提取失败: {str(e)}")

    async def _extract_embedded_subtitles(
        self, video_path: str, task_id: str
    ) -> Optional[str]:
        """从视频中提取内嵌字幕"""
        try:
            # 创建字幕输出目录
            subtitle_dir = self.work_dir / task_id
            subtitle_dir.mkdir(parents=True, exist_ok=True)

            # 生成字幕文件名
            subtitle_filename = f"{Path(video_path).stem}_embedded.srt"
            subtitle_path = subtitle_dir / subtitle_filename

            # 首先检查视频是否包含字幕流
            probe_cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "s",
                video_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                import json

                probe_data = json.loads(stdout.decode())
                subtitle_streams = probe_data.get("streams", [])

                if not subtitle_streams:
                    logger.info(f"视频 {video_path} 不包含内嵌字幕")
                    return None

                logger.info(f"发现 {len(subtitle_streams)} 个字幕流")

                # 提取第一个字幕流（通常是主要字幕）
                extract_cmd = [
                    "ffmpeg",
                    "-i",
                    video_path,
                    "-map",
                    "0:s:0",  # 选择第一个字幕流
                    "-c:s",
                    "srt",  # 转换为SRT格式
                    "-y",  # 覆盖输出文件
                    str(subtitle_path),
                ]

                process = await asyncio.create_subprocess_exec(
                    *extract_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0 and subtitle_path.exists():
                    logger.info(f"成功提取内嵌字幕: {subtitle_path}")
                    return str(subtitle_path)
                else:
                    logger.warning(f"提取内嵌字幕失败: {stderr.decode()}")
                    return None
            else:
                logger.info(f"检测字幕流失败: {stderr.decode()}")
                return None

        except Exception as e:
            logger.warning(f"提取内嵌字幕时发生错误: {e}")
            return None

    async def _transcribe_audio(
        self, audio_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转录音频文件"""
        try:
            # 获取配置
            language = config.get("language", "zh")
            model = config.get("model", "whisper")
            model_size = config.get("model_size", "small")

            # 处理新的模型格式
            if "-" in model and model != "auto":
                # 新格式：已经包含引擎和大小信息
                model_id = model
                logger.info(f"🎯 使用模型: {model_id}")
            else:
                # 传统格式：组合引擎和大小
                model_id = f"{model}-{model_size}" if model != "auto" else model
                logger.info(
                    f"🎯 组合模型: 引擎={model}, 大小={model_size} -> {model_id}"
                )

            # 初始化语音识别（支持新格式）
            initialize_voice_recognition(model=model, model_size=model_size)

            # 调用ASR核心进行转录
            result = voice_core.recognize_file(audio_path, language=language)

            if result and result.get("text"):
                # 清理转录文本，去除语音识别标记
                cleaned_text = self._clean_transcript_text(result.get("text", ""))
                # 转换繁体字为简体字
                simplified_text = self._convert_traditional_to_simplified(cleaned_text)
                result["text"] = simplified_text

                # 如果有segments，也需要清理和转换
                if "segments" in result and isinstance(result["segments"], list):
                    for segment in result["segments"]:
                        if "text" in segment:
                            cleaned_segment_text = self._clean_transcript_text(
                                segment["text"]
                            )
                            simplified_segment_text = (
                                self._convert_traditional_to_simplified(
                                    cleaned_segment_text
                                )
                            )
                            segment["text"] = simplified_segment_text

            return result

        except Exception as e:
            raise Exception(f"语音识别失败: {str(e)}")

    def _clean_transcript_text(self, text: str) -> str:
        """清理转录文本，去除语音识别标记符号"""
        import re

        if not text:
            return ""

        # 去除语音识别引擎的标记符号
        # 如: <|zh|><|NEUTRAL|><|Speech|><|withitn|>
        text = re.sub(r"<\|[^|]*\|>", "", text)

        # 去除多余的空格和换行
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text

    def _convert_traditional_to_simplified(self, text: str) -> str:
        """将繁体中文转换为简体中文"""
        if not text:
            return ""

        try:
            # 尝试使用opencc进行繁简转换
            try:
                import opencc

                cc = opencc.OpenCC("t2s")  # 繁体转简体
                return cc.convert(text)
            except ImportError:
                # 如果没有opencc，使用内置的简单映射
                return self._simple_traditional_to_simplified(text)
        except Exception as e:
            # 转换失败时返回原文
            logger.warning(f"繁体转简体失败: {e}")
            return text

    def _simple_traditional_to_simplified(self, text: str) -> str:
        """简单的繁体转简体映射（常用字）"""
        # 常用繁体字到简体字的映射
        mapping = {
            "會": "会",
            "為": "为",
            "個": "个",
            "應": "应",
            "該": "该",
            "時": "时",
            "間": "间",
            "長": "长",
            "過": "过",
            "來": "来",
            "對": "对",
            "於": "于",
            "從": "从",
            "開": "开",
            "關": "关",
            # ... 更多映射可以根据需要添加
        }

        result = text
        for traditional, simplified in mapping.items():
            result = result.replace(traditional, simplified)

        return result

    def _correct_whisper_errors(
        self, text: str, domain_keywords: List[str] = None
    ) -> tuple[str, List[str]]:
        """智能修正Whisper语音识别错误"""
        # 通用纠错词典
        universal_corrections = {
            # 常见同音字错误
            "的话": "的话",
            "德话": "的话",
            "地话": "的话",
            "这样": "这样",
            "这养": "这样",
            "怎样": "怎样",
            "怎养": "怎样",
            "可以": "可以",
            "克以": "可以",
            "能够": "能够",
            "能狗": "能够",
            "应该": "应该",
            "英该": "应该",
            "因为": "因为",
            "音为": "因为",
            "所以": "所以",
            "索以": "所以",
            "然后": "然后",
            "燃后": "然后",
            # ... 更多纠错规则
        }

        corrected_text = text
        corrections_made = []

        # 按照长度降序排序，优先替换长短语
        sorted_corrections = sorted(
            universal_corrections.items(), key=lambda x: len(x[0]), reverse=True
        )

        for wrong, correct in sorted_corrections:
            if wrong in corrected_text:
                count = corrected_text.count(wrong)
                corrected_text = corrected_text.replace(wrong, correct)
                if count > 0:
                    corrections_made.append(f"{wrong} → {correct} ({count}次)")

        return corrected_text, corrections_made

    async def _ai_correct_subtitles(
        self,
        subtitles: List[Any],
        embedded_subtitle_content: str = None,
        ai_client=None,
        model: str = None,
        rounds: int = 2,
    ) -> tuple[List[Any], List[str]]:
        """使用AI进行字幕纠错"""
        if not ai_client or not model:
            logger.warning("AI客户端或模型未配置，跳过AI纠错")
            return subtitles, []

        logger.info(f"开始AI智能纠错（{rounds}轮）...")

        corrected_subtitles = subtitles.copy()
        all_corrections = []

        # 构建参考内容
        reference_context = ""
        if embedded_subtitle_content:
            reference_context = f"\n\n**参考字幕内容**（来自视频内嵌字幕，可作为纠错参考）：\n{embedded_subtitle_content[:1000]}..."

        for round_num in range(1, rounds + 1):
            logger.info(f"执行第 {round_num} 轮AI纠错...")

            round_corrections = []
            batch_size = 8  # 每次处理8条字幕

            for i in range(0, len(corrected_subtitles), batch_size):
                batch = corrected_subtitles[i : i + batch_size]

                # 构建批处理文本
                batch_text = ""
                for j, subtitle in enumerate(batch):
                    batch_text += f"{i+j+1}. [{subtitle.start}] {subtitle.content}\n"

                # 构建纠错提示词
                correction_prompt = f"""# 任务
你是一位专业的中文语音识别纠错专家，请仔细检查以下字幕文本中的错别字、同音字错误、语法错误，并进行修正。

# 纠错原则
1. **保持原意**：只修正明显的错误，不改变原始语义
2. **同音字纠错**：修正语音识别导致的同音字错误
3. **语法纠错**：修正明显的语法错误
4. **专业术语**：确保专业术语的准确性
5. **上下文一致**：保持前后语境的一致性{reference_context}

# 输出格式
请按照以下格式输出，对于每一条字幕：
- 如果有错误：`序号. [时间戳] 修正后的内容 | 修改说明: 原词→正词`
- 如果无错误：`序号. [时间戳] 原内容`

# 待纠错字幕（第{round_num}轮）
{batch_text}

请逐条检查并修正："""

                try:
                    # 调用AI进行纠错
                    corrected_response = await ai_client.chat_completion(
                        messages=[{"role": "user", "content": correction_prompt}],
                        temperature=0.2,
                        max_tokens=2048,
                    )

                    if corrected_response:
                        # 解析AI返回的纠错结果
                        corrected_lines = corrected_response.strip().split("\n")

                        for line_idx, line in enumerate(corrected_lines):
                            if line.strip() and f"{i+line_idx+1}." in line:
                                try:
                                    # 解析格式: "序号. [时间戳] 内容 | 修改说明"
                                    parts = line.split("] ", 1)
                                    if len(parts) >= 2:
                                        content_part = parts[1]

                                        if " | 修改说明:" in content_part:
                                            # 有修改
                                            new_content, change_desc = (
                                                content_part.split(" | 修改说明:", 1)
                                            )
                                            new_content = new_content.strip()

                                            # 更新字幕内容
                                            original_idx = i + line_idx
                                            if original_idx < len(corrected_subtitles):
                                                old_content = corrected_subtitles[
                                                    original_idx
                                                ].content
                                                if new_content != old_content:
                                                    corrected_subtitles[
                                                        original_idx
                                                    ] = srt.Subtitle(
                                                        index=corrected_subtitles[
                                                            original_idx
                                                        ].index,
                                                        start=corrected_subtitles[
                                                            original_idx
                                                        ].start,
                                                        end=corrected_subtitles[
                                                            original_idx
                                                        ].end,
                                                        content=new_content,
                                                    )
                                                    round_corrections.append(
                                                        f"第{round_num}轮: {change_desc.strip()}"
                                                    )
                                except Exception as e:
                                    logger.warning(f"解析纠错结果失败: {e}")
                                    continue

                except Exception as e:
                    logger.warning(f"AI纠错失败: {e}")
                    continue

            all_corrections.extend(round_corrections)
            logger.info(f"第 {round_num} 轮完成，修正 {len(round_corrections)} 处")

        logger.info(f"AI纠错完成，共 {rounds} 轮，总计修正 {len(all_corrections)} 处")
        return corrected_subtitles, all_corrections

    async def _generate_summary(
        self, transcript: Dict[str, Any], config: Dict[str, Any]
    ) -> str:
        """生成内容摘要"""
        try:
            output_types = config.get("output_types", ["transcript"])

            if "summary" in output_types:
                # 使用AI内容生成工厂生成摘要
                ai_factory = await self._get_ai_factory()

                transcript_text = (
                    transcript.get("text", "")
                    if isinstance(transcript, dict)
                    else str(transcript)
                )

                # 生成内容卡片作为摘要
                result = await ai_factory.generate(
                    "content_card",
                    transcript_text,
                    language=config.get("language", "zh"),
                )

                if result.get("success"):
                    return result["content"]
                else:
                    return f"摘要生成失败: {result.get('error', '未知错误')}"
            else:
                return ""

        except Exception as e:
            return f"摘要生成失败: {str(e)}"

    async def _generate_output_files(
        self,
        task_id: str,
        transcript: Dict[str, Any],
        summary: str,
        config: Dict[str, Any],
        video_path: str = None,
        audio_path: str = None,
        file_type: str = "video",
    ) -> List[Dict[str, str]]:
        """生成输出文件"""
        try:
            # 创建任务输出目录
            output_dir = self.work_dir / task_id
            output_dir.mkdir(parents=True, exist_ok=True)

            files = []
            output_types = config.get("output_types", ["transcript"])
            ai_output_types = config.get("ai_output_types", [])

            # 提取文本内容
            transcript_text = (
                transcript.get("text", "")
                if isinstance(transcript, dict)
                else str(transcript)
            )

            # 获取字幕信息（用于帧提取）
            subtitles = transcript.get("segments", [])

            # 第1步：处理帧提取 (70-75%) - 仅对视频文件
            frame_info = {
                "frames": [],
                "cover_frame": None,
                "has_frames": False,
                "type": file_type,
            }

            if file_type == "video":
                await task_service.update_task(
                    "av", task_id, {"current_step": "正在提取关键帧...", "progress": 75}
                )
                frame_info = await self._process_frames(
                    video_path, audio_path, subtitles, output_dir, task_id
                )
            else:
                # 音频文件跳过帧提取
                await task_service.update_task(
                    "av",
                    task_id,
                    {"current_step": "跳过帧提取（音频文件）...", "progress": 75},
                )
                logger.info(f"音频文件 {audio_path or video_path} 跳过帧提取步骤")

            # 第2步：生成基础文件 (75-85%)
            await task_service.update_task(
                "av",
                task_id,
                {"current_step": "正在生成基础文件...", "progress": 80},
            )
            files.extend(
                await self._generate_basic_files(
                    output_dir, transcript_text, summary, subtitles
                )
            )

            # 第3步：生成AI内容文件 (85-95%)
            if ai_output_types:
                await task_service.update_task(
                    "av",
                    task_id,
                    {"current_step": "正在生成AI分析内容...", "progress": 85},
                )

                # 确保frame_info不为None，并有必要的字段
                safe_frame_info = frame_info or {
                    "frames": [],
                    "cover_frame": None,
                    "has_frames": False,
                    "type": "unknown",
                }

                # 确保frame_info包含所有必要字段
                if not isinstance(safe_frame_info, dict):
                    safe_frame_info = {
                        "frames": [],
                        "cover_frame": None,
                        "has_frames": False,
                        "type": "unknown",
                    }

                ai_files = await self._generate_ai_content_files(
                    output_dir,
                    transcript_text,
                    safe_frame_info,
                    ai_output_types,
                    config,
                    task_id,
                    subtitles,
                )
                files.extend(ai_files)

            # 完成文件生成
            await task_service.update_task(
                "av", task_id, {"current_step": "文件生成完成", "progress": 95}
            )

            return files

        except Exception as e:
            raise Exception(f"文件生成失败: {str(e)}")

    async def _process_frames(
        self,
        video_path: str,
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        output_dir: Path,
        task_id: str,
    ) -> Dict[str, Any]:
        """处理帧提取"""
        frame_info = {
            "frames": [],
            "cover_frame": None,
            "frame_dir": "",
            "has_frames": False,
        }

        try:
            frame_extractor = self._get_frame_extractor()

            if video_path and subtitles:
                # 视频帧提取 - 需要转换subtitles格式
                frame_dir = output_dir / "keyframes"
                frame_dir.mkdir(parents=True, exist_ok=True)

                # 转换subtitles格式为帧提取器需要的格式
                formatted_subtitles = self._format_subtitles_for_frames(subtitles)

                if formatted_subtitles:
                    # 🎯 使用新的固定间隔提取方法（2秒一帧）
                    frames, cover_frame = frame_extractor.extract_frames_by_interval(
                        video_path,
                        formatted_subtitles,
                        str(frame_dir),
                        interval=2.0,
                        verbose=True,
                    )

                    frame_info.update(
                        {
                            "frames": frames,
                            "cover_frame": cover_frame,
                            "frame_dir": str(frame_dir),
                            "has_frames": len(frames) > 0,
                            "type": "video",
                        }
                    )

                    # 记录帧信息到任务
                    await task_service.update_task(
                        "av", task_id, {"frame_info": frame_info}
                    )

            elif audio_path:
                # 音频可视化生成
                frame_dir = output_dir / "audio_visuals"
                frame_dir.mkdir(parents=True, exist_ok=True)

                frames, cover_frame = frame_extractor.generate_audio_visualizations(
                    audio_path, str(frame_dir), verbose=True
                )

                frame_info.update(
                    {
                        "frames": frames,
                        "cover_frame": cover_frame,
                        "frame_dir": str(frame_dir),
                        "has_frames": len(frames) > 0,
                        "type": "audio",
                    }
                )

                # 记录帧信息到任务
                await task_service.update_task(
                    "av", task_id, {"frame_info": frame_info}
                )

        except Exception as e:
            logger.error(f"帧处理失败: {e}")
            # 确保在异常情况下也返回正确的格式
            frame_info = {
                "frames": [],
                "cover_frame": None,
                "frame_dir": "",
                "has_frames": False,
                "type": "error",
                "error": str(e),
            }

        return frame_info

    def _format_subtitles_for_frames(
        self, segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """将segments格式转换为帧提取器需要的格式"""
        formatted_subtitles = []

        if not segments:
            return formatted_subtitles

        for i, segment in enumerate(segments):
            # 处理时间戳 - 从秒转换为timedelta对象
            start_time = segment.get("start", i * 3)
            end_time = segment.get("end", (i + 1) * 3)

            # 如果是数字，转换为timedelta
            if isinstance(start_time, (int, float)):
                start_time = timedelta(seconds=start_time)
            if isinstance(end_time, (int, float)):
                end_time = timedelta(seconds=end_time)

            formatted_subtitles.append(
                {
                    "start": start_time,
                    "end": end_time,
                    "content": segment.get("text", "").strip(),
                }
            )

        return formatted_subtitles

    async def _generate_basic_files(
        self,
        output_dir: Path,
        transcript_text: str,
        summary: str,
        subtitles: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """生成基础文件"""
        files = []

        # 生成原始转录.txt文件
        transcript_txt_file = output_dir / "原始转录.txt"
        transcript_txt_file.write_text(transcript_text, encoding="utf-8")
        files.append(
            {
                "name": "原始转录.txt",
                "path": str(transcript_txt_file),
                "type": "transcript_txt",
            }
        )

        # 生成原始转录.json文件
        transcript_json_file = output_dir / "原始转录.json"
        transcript_json_data = {
            "text": transcript_text,
            "segments": subtitles if subtitles else [],
            "language": "zh",
            "processing_time": 0.0,
            "model": "SenseVoice",
            "device": "cpu",
        }
        transcript_json_file.write_text(
            json.dumps(transcript_json_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files.append(
            {
                "name": "原始转录.json",
                "path": str(transcript_json_file),
                "type": "transcript_json",
            }
        )

        # 生成字幕文件.srt
        subtitle_file = output_dir / "字幕文件.srt"
        subtitle_content = self._generate_subtitle_from_segments(
            subtitles, transcript_text
        )
        subtitle_file.write_text(subtitle_content, encoding="utf-8")
        files.append(
            {"name": "字幕文件.srt", "path": str(subtitle_file), "type": "subtitle"}
        )

        # 生成处理报告.md
        report_file = output_dir / "处理报告.md"
        report_content = self._generate_processing_report(transcript_text, subtitles)
        report_file.write_text(report_content, encoding="utf-8")
        files.append(
            {"name": "处理报告.md", "path": str(report_file), "type": "report"}
        )

        return files

    async def _generate_ai_content_files(
        self,
        output_dir: Path,
        transcript_text: str,
        frame_info: Dict[str, Any],
        ai_output_types: List[str],
        config: Dict[str, Any],
        task_id: str,
        subtitles: List[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """生成AI内容文件"""
        files = []

        try:
            ai_factory = await self._get_ai_factory()

            # 处理视频/音频路径
            video_path = ""
            audio_path = ""
            # 使用传递的字幕信息，如果没有则使用空列表
            if subtitles is None:
                subtitles = []

            total_types = len(ai_output_types)
            for i, output_type in enumerate(ai_output_types):
                try:
                    # 更新进度
                    progress = 85 + int((i / total_types) * 10)  # 85-95%
                    type_names = {
                        "content_card": "内容卡片",
                        "mind_map": "思维导图",
                        "flashcards": "学习闪卡",
                        "ai_analysis": "AI分析",
                    }
                    current_type_name = type_names.get(output_type, output_type)

                    await task_service.update_task(
                        "av",
                        task_id,
                        {
                            "current_step": f"正在生成{current_type_name}...",
                            "progress": progress,
                        },
                    )

                    # 🎯 传递content_role参数
                    generate_kwargs = {
                        "video_path": video_path,
                        "audio_path": audio_path,
                        "subtitles": subtitles,
                        "frame_info": frame_info,
                        "language": config.get("language", "zh"),
                        "task_id": task_id,
                    }

                    # 如果配置中有content_role，传递给AI生成器
                    if "content_role" in config:
                        generate_kwargs["force_domain"] = config["content_role"]
                        logger.info(f"🎯 使用指定内容角色: {config['content_role']}")

                    result = await ai_factory.generate(
                        output_type, transcript_text, **generate_kwargs
                    )

                    if result.get("success"):
                        # 根据输出类型生成文件
                        file_info = await self._save_ai_content(
                            output_dir, output_type, result, frame_info
                        )
                        if file_info:
                            files.append(file_info)

                except Exception as e:
                    logger.error(f"生成{output_type}失败: {e}")
                    continue

        except Exception as e:
            logger.error(f"AI内容生成失败: {e}")

        return files

    async def _save_ai_content(
        self,
        output_dir: Path,
        output_type: str,
        result: Dict[str, Any],
        frame_info: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """保存AI生成的内容到文件"""
        try:
            content = result.get("content", "")
            if not content:
                return None

            # 根据输出类型确定文件名和格式
            if output_type == "content_card":
                filename = "内容卡片.md"
                file_path = output_dir / filename
                file_path.write_text(content, encoding="utf-8")

            elif output_type == "mind_map":
                filename = "思维导图.md"
                file_path = output_dir / filename
                file_path.write_text(content, encoding="utf-8")

                # 同时生成FreeMind格式
                mm_filename = "思维导图.mm"
                mm_file_path = output_dir / mm_filename
                mm_content = self._convert_to_freemind(content)
                mm_file_path.write_text(mm_content, encoding="utf-8")

                return {
                    "name": filename,
                    "path": str(file_path),
                    "type": "mind_map",
                    "additional_files": [
                        {
                            "name": mm_filename,
                            "path": str(mm_file_path),
                            "type": "freemind",
                        }
                    ],
                }

            elif output_type == "flashcards":
                # 生成学习闪卡.md文件
                filename = "学习闪卡.md"
                file_path = output_dir / filename
                file_path.write_text(content, encoding="utf-8")

                # 同时生成Anki格式
                anki_filename = "学习闪卡-Anki格式.csv"
                anki_file_path = output_dir / anki_filename
                anki_content = self._convert_to_anki(content)
                anki_file_path.write_text(anki_content, encoding="utf-8")

                # 生成JSON格式的闪卡文件
                json_filename = "flashcards.json"
                json_file_path = output_dir / json_filename
                json_content = self._convert_to_flashcard_json(content)
                json_file_path.write_text(json_content, encoding="utf-8")

                return {
                    "name": filename,
                    "path": str(file_path),
                    "type": "flashcards",
                    "additional_files": [
                        {
                            "name": anki_filename,
                            "path": str(anki_file_path),
                            "type": "anki",
                        },
                        {
                            "name": json_filename,
                            "path": str(json_file_path),
                            "type": "flashcards_json",
                        },
                    ],
                }

            elif output_type == "ai_analysis":
                filename = "AI分析结果.json"
                file_path = output_dir / filename
                # 清理JSON内容中的markdown标记
                cleaned_content = self._clean_json_content(content)
                file_path.write_text(cleaned_content, encoding="utf-8")
                return {"name": filename, "path": str(file_path), "type": output_type}

            else:
                return None

        except Exception as e:
            logger.error(f"保存AI内容失败: {e}")
            return None

    def _clean_json_content(self, content: str) -> str:
        """清理JSON内容中的markdown标记"""
        if not content:
            return content

        import re

        # 去除markdown代码块标记
        content = re.sub(r"^```json\s*\n?", "", content, flags=re.MULTILINE)
        content = re.sub(r"\n?```\s*$", "", content, flags=re.MULTILINE)

        # 去除其他可能的markdown标记
        content = re.sub(r"^```\s*\n?", "", content, flags=re.MULTILINE)

        # 清理多余的空白字符
        content = content.strip()

        return content

    def _convert_to_freemind(self, markdown_content: str) -> str:
        """将Markdown内容转换为FreeMind格式"""
        # 简单的FreeMind格式转换
        lines = markdown_content.split("\n")
        freemind_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
        freemind_content += '<map version="1.0.1">\n'
        freemind_content += '  <node ID="root" TEXT="思维导图">\n'

        current_level = 0
        for line in lines:
            line = line.strip()
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                text = line.lstrip("#").strip()
                if text:
                    freemind_content += (
                        "    " * (level + 1) + f'<node TEXT="{text}"/>\n'
                    )

        freemind_content += "  </node>\n"
        freemind_content += "</map>"

        return freemind_content

    def _convert_to_anki(self, markdown_content: str) -> str:
        """将Markdown内容转换为Anki格式"""
        # 简单的Anki CSV格式转换
        lines = markdown_content.split("\n")
        anki_content = "Question,Answer\n"

        current_question = ""
        current_answer = ""

        for line in lines:
            line = line.strip()
            if line.startswith("Q:"):
                if current_question and current_answer:
                    anki_content += f'"{current_question}","{current_answer}"\n'
                current_question = line[2:].strip()
                current_answer = ""
            elif line.startswith("A:"):
                current_answer = line[2:].strip()
            elif line.startswith("---"):
                if current_question and current_answer:
                    anki_content += f'"{current_question}","{current_answer}"\n'
                current_question = ""
                current_answer = ""

        # 处理最后一个卡片
        if current_question and current_answer:
            anki_content += f'"{current_question}","{current_answer}"\n'

        return anki_content

    def _convert_to_flashcard_json(self, markdown_content: str) -> str:
        """将Markdown内容转换为JSON格式的闪卡"""
        lines = markdown_content.split("\n")
        flashcards = []
        current_question = ""
        current_answer = ""
        card_id = 1

        for line in lines:
            line = line.strip()
            if line.startswith("Q:"):
                if current_question and current_answer:
                    flashcards.append(
                        {
                            "id": f"card_{card_id}",
                            "question": current_question,
                            "answer": current_answer,
                            "category": "主要内容",
                        }
                    )
                    card_id += 1
                current_question = line[2:].strip()
                current_answer = ""
            elif line.startswith("A:"):
                current_answer = line[2:].strip()
            elif line.startswith("---"):
                if current_question and current_answer:
                    flashcards.append(
                        {
                            "id": f"card_{card_id}",
                            "question": current_question,
                            "answer": current_answer,
                            "category": "主要内容",
                        }
                    )
                    card_id += 1
                current_question = ""
                current_answer = ""

        # 处理最后一个卡片
        if current_question and current_answer:
            flashcards.append(
                {
                    "id": f"card_{card_id}",
                    "question": current_question,
                    "answer": current_answer,
                    "category": "主要内容",
                }
            )

        # 如果没有找到Q:A:格式，生成默认的闪卡
        if not flashcards:
            # 基于内容生成简单的问答卡片
            content_lines = [
                line.strip()
                for line in lines
                if line.strip() and not line.startswith("#")
            ]
            if content_lines:
                for i, line in enumerate(content_lines[:5]):  # 最多5张卡片
                    flashcards.append(
                        {
                            "id": f"card_{i+1}",
                            "question": f"关于第{i+1}个要点的问题",
                            "answer": line,
                            "category": "主要内容",
                        }
                    )

        return json.dumps(flashcards, ensure_ascii=False, indent=2)

    def _generate_subtitle_from_segments(
        self, segments: List[Dict[str, Any]], transcript_text: str
    ) -> str:
        """从segments生成字幕文件"""
        if not segments or len(segments) == 0:
            # 如果没有segments，使用简单的文本分割
            return self._generate_subtitle_from_text(transcript_text)

        subtitle_content = ""
        for i, segment in enumerate(segments):
            start_time = self._format_timestamp(segment.get("start", i * 3))
            end_time = self._format_timestamp(segment.get("end", (i + 1) * 3))
            text = segment.get("text", "").strip()

            if text:
                subtitle_content += f"{i+1}\n{start_time} --> {end_time}\n{text}\n\n"

        return subtitle_content

    def _generate_subtitle_from_text(self, transcript: str) -> str:
        """从纯文本生成字幕文件"""
        lines = transcript.split("。")
        subtitle_content = ""

        for i, line in enumerate(lines):
            if line.strip():
                start_time = f"00:00:{i*3:02d},000"
                end_time = f"00:00:{(i+1)*3:02d},000"
                subtitle_content += (
                    f"{i+1}\n{start_time} --> {end_time}\n{line.strip()}\n\n"
                )

        return subtitle_content

    def _format_timestamp(self, seconds: float) -> str:
        """格式化时间戳为SRT格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds - int(seconds)) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    def _generate_processing_report(
        self, transcript_text: str, segments: List[Dict[str, Any]]
    ) -> str:
        """生成处理报告"""
        word_count = len(transcript_text) if transcript_text else 0
        segment_count = len(segments) if segments else 0

        report = f"""# 视频处理报告

## 基本信息
- 处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 转录字数: {word_count} 字
- 字幕段数: {segment_count} 段

## 处理状态
- ✅ 音频提取: 完成
- ✅ 语音识别: 完成
- ✅ 字幕生成: 完成
- ✅ 文件输出: 完成

## 输出文件
- 原始转录.txt - 纯文本转录内容
- 原始转录.json - 结构化转录数据
- 字幕文件.srt - 标准字幕格式
- AI分析结果.json - 智能分析报告
- 内容卡片.md - 结构化内容总结
- 学习闪卡.md - 学习卡片
- 思维导图.md - 思维导图

## 技术参数
- 语音识别引擎: SenseVoice
- 处理设备: CPU
- 语言: 中文 (zh)
"""
        return report

    async def _download_file(self, url: str, task_id: str) -> Optional[str]:
        """下载文件"""
        try:
            # 创建下载目录
            download_dir = self.work_dir / task_id
            download_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            filename = Path(url).name or f"downloaded_{int(time.time())}"
            file_path = download_dir / filename

            # 使用wget或curl下载文件
            if shutil.which("wget"):
                cmd = ["wget", "-O", str(file_path), url]
            elif shutil.which("curl"):
                cmd = ["curl", "-L", "-o", str(file_path), url]
            else:
                raise Exception("没有可用的下载工具")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0 and file_path.exists():
                return str(file_path)
            else:
                raise Exception(f"下载失败: {stderr.decode()}")

        except Exception as e:
            raise Exception(f"文件下载失败: {str(e)}")


# 全局处理器实例
video_processor = VideoProcessor()
