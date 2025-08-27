#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 视频/音频处理服务
"""

import os
import tempfile
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import asyncio
import json
import subprocess
import shutil
import sys

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ..services.task_service import task_service

# 导入ASR模块
from core.asr import voice_core, initialize_voice_recognition, transcribe_audio


class VideoService:
    """视频/音频处理服务 - 实际调用核心处理模块"""

    def __init__(self):
        self.work_dir = Path(__file__).parent.parent.parent / "data" / "outputs"
        self.uploads_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        # 初始化ASR模块
        self._initialize_asr()

    async def process_file(
        self, file_data: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理上传的文件"""
        try:
            # 创建任务
            task_data = {
                "type": self._detect_file_type(file_data["filename"]),
                "input": file_data,
                "config": config,
                "current_step": "准备处理...",
            }

            task = await task_service.create_task("video", task_data)
            task_id = task["id"]

            # 异步处理文件
            asyncio.create_task(self._process_file_async(task_id, file_data, config))

            return {"task_id": task_id, "status": "created"}

        except Exception as e:
            return {"error": str(e)}

    async def process_url(self, url: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """处理URL链接"""
        try:
            # 创建任务
            task_data = {
                "type": "video",  # URL通常是视频
                "input": {"type": "url", "url": url},
                "config": config,
                "current_step": "准备下载...",
            }

            task = await task_service.create_task("video", task_data)
            task_id = task["id"]

            # 异步处理URL
            asyncio.create_task(self._process_url_async(task_id, url, config))

            return {"task_id": task_id, "status": "created"}

        except Exception as e:
            return {"error": str(e)}

    def _detect_file_type(self, filename: str) -> str:
        """检测文件类型"""
        ext = Path(filename).suffix.lower()
        video_exts = [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"]
        audio_exts = [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"]

        if ext in video_exts:
            return "video"
        elif ext in audio_exts:
            return "audio"
        else:
            return "unknown"

    async def _process_file_async(
        self, task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
    ):
        """异步处理文件"""
        temp_audio_path = None
        try:
            # 文件已经在API层验证过，直接开始处理
            await task_service.update_task(
                "video",
                task_id,
                {"status": "running", "progress": 10, "current_step": "文件预处理..."},
            )

            # 步骤1: 文件预处理 - 提取音频
            await task_service.update_task(
                "video", task_id, {"progress": 25, "current_step": "音频提取..."}
            )

            # 如果是视频文件，需要提取音频
            if file_data.get("type") == "video":
                temp_audio_path = await self._extract_audio_from_video(
                    file_data.get("file_path", ""), task_id
                )
            else:
                # 音频文件直接使用
                temp_audio_path = file_data.get("file_path", "")

            if not temp_audio_path or not os.path.exists(temp_audio_path):
                raise Exception("音频文件处理失败")

            # 步骤2: 语音识别
            await task_service.update_task(
                "video", task_id, {"progress": 50, "current_step": "语音识别中..."}
            )

            # 调用实际的ASR语音识别模块
            transcript = await self._run_speech_recognition_with_asr(
                temp_audio_path, config
            )

            await asyncio.sleep(2)

            # 步骤3: 生成摘要和其他内容
            await task_service.update_task(
                "video", task_id, {"progress": 75, "current_step": "生成摘要..."}
            )

            # 提取文本用于生成摘要
            transcript_text_for_summary = (
                transcript.get("text", "")
                if isinstance(transcript, dict)
                else str(transcript)
            )
            summary = await self._generate_summary(transcript_text_for_summary, config)

            await asyncio.sleep(1)

            # 步骤4: 生成输出文件
            await task_service.update_task(
                "video", task_id, {"progress": 90, "current_step": "生成输出文件..."}
            )

            output_files = await self._generate_output_files(
                task_id, transcript, summary, config
            )

            # 完成任务
            await task_service.update_task(
                "video",
                task_id,
                {
                    "status": "completed",
                    "progress": 100,
                    "current_step": "处理完成",
                    "results": {
                        "transcript": (
                            transcript.get("text", "")
                            if isinstance(transcript, dict)
                            else str(transcript)
                        ),
                        "transcript_data": (
                            transcript if isinstance(transcript, dict) else {}
                        ),
                        "summary": summary,
                        "files": output_files,
                        "engine_info": {
                            "model": (
                                transcript.get("model", "unknown")
                                if isinstance(transcript, dict)
                                else "unknown"
                            ),
                            "language": (
                                transcript.get("language", "auto")
                                if isinstance(transcript, dict)
                                else "auto"
                            ),
                            "processing_time": (
                                transcript.get("processing_time", 0)
                                if isinstance(transcript, dict)
                                else 0
                            ),
                        },
                    },
                },
            )

        except Exception as e:
            # 任务失败
            await task_service.update_task(
                "video",
                task_id,
                {
                    "status": "failed",
                    "error": str(e),
                    "current_step": f"处理失败: {str(e)}",
                },
            )

    async def _process_url_async(self, task_id: str, url: str, config: Dict[str, Any]):
        """异步处理URL"""
        try:
            # 更新任务状态
            await task_service.update_task(
                "video",
                task_id,
                {"status": "running", "progress": 5, "current_step": "下载视频..."},
            )

            # 模拟下载过程
            for progress in range(5, 40, 5):
                await asyncio.sleep(1)
                await task_service.update_task(
                    "video",
                    task_id,
                    {"progress": progress, "current_step": f"下载中... {progress}%"},
                )

            # 模拟下载的文件数据
            file_data = {
                "filename": "downloaded_video.mp4",
                "size": 100 * 1024 * 1024,  # 100MB
                "type": "url",
            }

            # 继续按文件处理流程
            await self._process_file_async(task_id, file_data, config)

        except Exception as e:
            await task_service.update_task(
                "video",
                task_id,
                {
                    "status": "failed",
                    "error": str(e),
                    "current_step": f"下载失败: {str(e)}",
                },
            )

    async def _run_speech_recognition(
        self, file_data: Dict[str, Any], config: Dict[str, Any]
    ) -> str:
        """运行语音识别 - 调用实际的处理模块"""
        try:
            # 这里应该调用 core/ 目录下的实际语音识别模块
            # 为了演示，先返回模拟结果

            language = config.get("language", "zh")
            model = config.get("model", "whisper")

            # 根据配置调用不同的模型
            if model == "whisper":
                return await self._call_whisper_model(file_data, language)
            elif model == "dolphin":
                return await self._call_dolphin_model(file_data, language)
            else:
                return "使用默认模型进行语音识别的结果文本内容..."

        except Exception as e:
            raise Exception(f"语音识别失败: {str(e)}")

    async def _call_whisper_model(
        self, file_data: Dict[str, Any], language: str
    ) -> str:
        """调用Whisper模型"""
        # 这里应该调用 core/asr_provider.py 等模块
        # 目前返回模拟结果
        return f"使用Whisper模型({language})识别的文本内容：这是一段关于AI技术发展的讲座内容，主要讨论了深度学习、自然语言处理等前沿技术..."

    async def _call_dolphin_model(
        self, file_data: Dict[str, Any], language: str
    ) -> str:
        """调用Dolphin模型"""
        # 这里应该调用相关的模块
        return f"使用Dolphin模型({language})识别的文本内容：这是经过高精度语音识别处理的结果文本..."

    async def _generate_summary(self, transcript: str, config: Dict[str, Any]) -> str:
        """生成摘要"""
        try:
            # 这里应该调用 core/summarizer.py 等模块
            # 目前返回模拟结果
            output_types = config.get("output_types", [])

            if "summary" in output_types:
                return "基于转录内容生成的智能摘要：本次讲座重点介绍了AI技术的最新发展趋势，包括深度学习算法优化、自然语言处理应用等核心内容..."
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
    ) -> List[Dict[str, str]]:
        """生成输出文件"""
        try:
            # 创建任务输出目录
            output_dir = self.work_dir / task_id
            output_dir.mkdir(parents=True, exist_ok=True)

            files = []
            output_types = config.get("output_types", ["transcript"])

            # 提取文本内容
            transcript_text = (
                transcript.get("text", "")
                if isinstance(transcript, dict)
                else str(transcript)
            )

            # 生成转录文件
            if "transcript" in output_types:
                transcript_file = output_dir / "transcript.txt"
                transcript_file.write_text(transcript_text, encoding="utf-8")
                files.append(
                    {
                        "name": "transcript.txt",
                        "path": str(transcript_file),
                        "type": "transcript",
                    }
                )

            # 生成摘要文件
            if "summary" in output_types and summary:
                summary_file = output_dir / "summary.md"
                summary_file.write_text(summary, encoding="utf-8")
                files.append(
                    {"name": "summary.md", "path": str(summary_file), "type": "summary"}
                )

            # 生成字幕文件
            if "subtitle" in output_types:
                subtitle_file = output_dir / "subtitle.srt"
                subtitle_content = self._generate_subtitle(transcript_text)
                subtitle_file.write_text(subtitle_content, encoding="utf-8")
                files.append(
                    {
                        "name": "subtitle.srt",
                        "path": str(subtitle_file),
                        "type": "subtitle",
                    }
                )

            # 生成记忆卡片
            if "flashcards" in output_types:
                flashcards_file = output_dir / "flashcards.json"
                flashcards = self._generate_flashcards(transcript_text)
                flashcards_file.write_text(
                    json.dumps(flashcards, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                files.append(
                    {
                        "name": "flashcards.json",
                        "path": str(flashcards_file),
                        "type": "flashcards",
                    }
                )

            return files

        except Exception as e:
            raise Exception(f"文件生成失败: {str(e)}")

    def _generate_subtitle(self, transcript: str) -> str:
        """生成字幕文件"""
        # 简单的字幕生成逻辑
        lines = transcript.split("。")
        subtitle_content = ""

        for i, line in enumerate(lines):
            if line.strip():
                start_time = f"00:00:{i*3:02d},000"
                end_time = f"00:00:{(i+1)*3:02d},000"
                subtitle_content += (
                    f"{i+1}\n{start_time} --> {end_time}\n{line.strip()}。\n\n"
                )

        return subtitle_content

    def _generate_flashcards(self, transcript: str) -> List[Dict[str, str]]:
        """生成记忆卡片"""
        # 简单的卡片生成逻辑
        sentences = [s.strip() for s in transcript.split("。") if s.strip()]
        flashcards = []

        for i, sentence in enumerate(sentences[:5]):  # 最多生成5张卡片
            flashcards.append(
                {
                    "id": f"card_{i+1}",
                    "question": f"关于第{i+1}个要点的问题",
                    "answer": sentence,
                    "category": "主要内容",
                }
            )

        return flashcards

    def _initialize_asr(self):
        """初始化ASR语音识别模块"""
        try:
            import logging

            logger = logging.getLogger(__name__)

            logger.info("🔧 初始化ASR语音识别模块...")

            # 初始化语音识别核心，使用auto模式自动选择最佳引擎
            if initialize_voice_recognition("auto"):
                logger.info("✅ ASR模块初始化成功")
                # 获取当前引擎信息
                engine_info = voice_core.get_engine_info()
                logger.info(f"🎤 当前引擎: {engine_info.get('engine', 'unknown')}")
            else:
                logger.error("❌ ASR模块初始化失败")

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"❌ ASR初始化异常: {e}")

    async def _run_speech_recognition_with_asr(
        self, audio_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用ASR模块进行语音识别"""
        try:
            import logging

            logger = logging.getLogger(__name__)

            language = config.get("language", "auto")
            model = config.get("model", "auto")

            logger.info(f"🎤 开始语音识别: {Path(audio_path).name}")
            logger.info(f"   语言: {language}, 模型: {model}")

            # 如果指定了特定模型，尝试切换引擎
            if model != "auto":
                engine_map = {
                    "whisper": "whisper",
                    "faster_whisper": "faster_whisper",
                    "sensevoice": "sensevoice",
                    "dolphin": "dolphin",
                }

                if model in engine_map:
                    voice_core.switch_engine(engine_map[model])
                    logger.info(f"🔄 切换到指定引擎: {model}")

            # 执行语音识别
            result = voice_core.recognize_file(audio_path, language)

            if result:
                # 检查是否有错误信息
                if result.get("error"):
                    error_msg = result.get("error", "未知错误")
                    suggestions = result.get("suggestions", [])
                    logger.error(f"❌ 语音识别失败: {error_msg}")
                    if suggestions:
                        logger.info("💡 解决方案建议:")
                        for suggestion in suggestions:
                            logger.info(f"  - {suggestion}")
                    raise Exception(f"语音识别失败: {error_msg}")

                # 检查是否有有效的文本内容
                text_content = result.get("text", "").strip()
                if text_content:
                    logger.info(f"✅ 识别成功 - 文本长度: {len(text_content)}")
                    logger.info(
                        f"   处理时间: {result.get('processing_time', 0):.2f}秒"
                    )
                    return result
                else:
                    logger.warning(
                        "⚠️ 语音识别返回空文本，可能是音频质量问题或模型加载失败"
                    )
                    raise Exception("语音识别返回空文本内容")
            else:
                raise Exception("语音识别返回空结果")

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"❌ 语音识别失败: {e}")
            raise

    async def _extract_audio_from_video(self, video_path: str, task_id: str) -> str:
        """从视频中提取音频"""
        try:
            import logging
            import subprocess

            logger = logging.getLogger(__name__)

            logger.info(f"🎬 从视频提取音频: {Path(video_path).name}")

            # 首先检查视频文件是否存在
            if not Path(video_path).exists():
                raise Exception(f"视频文件不存在: {video_path}")

            # 检查视频是否包含音频流
            audio_stream_info = await self._check_audio_stream(video_path)
            if not audio_stream_info["has_audio"]:
                raise Exception(
                    f"视频文件不包含音频流，无法进行语音识别。"
                    f"视频信息: {audio_stream_info['info']}"
                )

            # 创建音频输出路径
            audio_filename = f"{task_id}_audio.wav"
            audio_path = self.work_dir / task_id / audio_filename
            audio_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用ffmpeg提取音频
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",  # 不处理视频
                "-acodec",
                "pcm_s16le",  # 音频编码
                "-ar",
                "16000",  # 采样率
                "-ac",
                "1",  # 单声道
                "-y",  # 覆盖输出文件
                "-loglevel",
                "error",  # 减少日志输出
                str(audio_path),
            ]

            logger.info(f"🔧 执行FFmpeg命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if (
                result.returncode == 0
                and audio_path.exists()
                and audio_path.stat().st_size > 0
            ):
                logger.info(
                    f"✅ 音频提取成功: {audio_path} (大小: {audio_path.stat().st_size} bytes)"
                )
                return str(audio_path)
            else:
                error_msg = result.stderr if result.stderr else "未知错误"
                logger.error(
                    f"❌ FFmpeg错误 (返回码: {result.returncode}): {error_msg}"
                )

                # 检查是否是权限问题
                if "Permission denied" in error_msg:
                    raise Exception(f"权限不足，无法写入音频文件: {audio_path}")

                # 检查是否是磁盘空间问题
                if "No space left on device" in error_msg:
                    raise Exception("磁盘空间不足，无法保存音频文件")

                raise Exception(f"音频提取失败: {error_msg}")

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"❌ 音频提取失败: {e}")
            raise

    async def _check_audio_stream(self, video_path: str) -> dict:
        """检查视频文件是否包含音频流"""
        try:
            import subprocess
            import json

            # 使用ffprobe检查音频流
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "a",  # 只选择音频流
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                try:
                    probe_data = json.loads(result.stdout)
                    audio_streams = probe_data.get("streams", [])

                    if audio_streams:
                        # 有音频流
                        stream_info = audio_streams[0]  # 取第一个音频流
                        return {
                            "has_audio": True,
                            "info": {
                                "codec": stream_info.get("codec_name", "unknown"),
                                "duration": stream_info.get("duration", "unknown"),
                                "sample_rate": stream_info.get(
                                    "sample_rate", "unknown"
                                ),
                                "channels": stream_info.get("channels", "unknown"),
                            },
                        }
                    else:
                        # 没有音频流，获取视频基本信息
                        return await self._get_video_basic_info(video_path)

                except json.JSONDecodeError:
                    return {"has_audio": False, "info": "无法解析视频文件信息"}
            else:
                return {"has_audio": False, "info": f"ffprobe检查失败: {result.stderr}"}

        except Exception as e:
            return {"has_audio": False, "info": f"检查音频流时发生错误: {str(e)}"}

    async def _get_video_basic_info(self, video_path: str) -> dict:
        """获取视频基本信息（当没有音频流时）"""
        try:
            import subprocess
            import json

            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                video_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                try:
                    probe_data = json.loads(result.stdout)
                    format_info = probe_data.get("format", {})
                    streams = probe_data.get("streams", [])

                    video_streams = [
                        s for s in streams if s.get("codec_type") == "video"
                    ]

                    return {
                        "has_audio": False,
                        "info": {
                            "format": format_info.get("format_name", "unknown"),
                            "duration": format_info.get("duration", "unknown"),
                            "video_streams": len(video_streams),
                            "audio_streams": 0,
                            "message": "此视频文件仅包含视频流，没有音频内容",
                        },
                    }
                except json.JSONDecodeError:
                    pass

        except Exception:
            pass

        return {"has_audio": False, "info": "此视频文件没有音频内容"}


# 全局视频服务实例
video_service = VideoService()
