#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 视频处理异步任务
"""

import os
import sys
import json
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.celery_config import celery_app
from biz.services.task_service import task_service

# 导入ASR模块
from core.asr import voice_core, initialize_voice_recognition, transcribe_audio

import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_video_file")
def process_video_file_task(
    self, task_id: str, file_data: Dict[str, Any], config: Dict[str, Any]
):
    """
    异步处理视频文件任务

    Args:
        task_id: 任务ID
        file_data: 文件数据
        config: 处理配置
    """
    try:
        # 更新任务状态为处理中
        update_task_status(
            task_id,
            {
                "status": "running",
                "progress": 5,
                "current_step": "开始处理...",
                "celery_task_id": self.request.id,
            },
        )

        # 初始化ASR模块
        logger.info("🔧 初始化ASR语音识别模块...")
        if not initialize_voice_recognition("auto"):
            raise Exception("ASR模块初始化失败")

        # 步骤1: 文件预处理
        update_task_status(task_id, {"progress": 15, "current_step": "文件预处理..."})

        # 验证文件存在性
        file_path = file_data.get("file_path", "")
        if not file_path or not Path(file_path).exists():
            raise Exception(f"文件不存在: {file_path}")

        # 步骤2: 音频提取
        update_task_status(task_id, {"progress": 30, "current_step": "音频提取..."})

        audio_path = extract_audio_from_video(file_path, task_id, file_data)

        # 步骤3: 语音识别
        update_task_status(task_id, {"progress": 50, "current_step": "语音识别中..."})

        transcript = run_speech_recognition(audio_path, config)

        # 步骤4: 生成摘要
        update_task_status(task_id, {"progress": 75, "current_step": "生成摘要..."})

        transcript_text = (
            transcript.get("text", "")
            if isinstance(transcript, dict)
            else str(transcript)
        )
        summary = generate_summary(transcript_text, config)

        # 步骤5: 生成输出文件
        update_task_status(task_id, {"progress": 90, "current_step": "生成输出文件..."})

        output_files = generate_output_files(task_id, transcript, summary, config)

        # 完成任务
        update_task_status(
            task_id,
            {
                "status": "completed",
                "progress": 100,
                "current_step": "处理完成",
                "results": {
                    "transcript": transcript_text,
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

        logger.info(f"✅ 任务 {task_id} 处理完成")
        return {"status": "success", "task_id": task_id}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 任务 {task_id} 处理失败: {error_msg}")

        # 更新任务状态为失败
        update_task_status(
            task_id,
            {
                "status": "failed",
                "error": error_msg,
                "current_step": f"处理失败: {error_msg}",
            },
        )

        # 重新抛出异常，让Celery记录
        raise


@celery_app.task(bind=True, name="process_video_url")
def process_video_url_task(self, task_id: str, url: str, config: Dict[str, Any]):
    """
    异步处理视频URL任务

    Args:
        task_id: 任务ID
        url: 视频URL
        config: 处理配置
    """
    try:
        # 更新任务状态
        update_task_status(
            task_id,
            {
                "status": "running",
                "progress": 5,
                "current_step": "开始下载视频...",
                "celery_task_id": self.request.id,
            },
        )

        # 模拟下载过程（实际项目中可以使用youtube-dl或yt-dlp）
        for progress in range(5, 40, 5):
            update_task_status(
                task_id,
                {"progress": progress, "current_step": f"下载中... {progress}%"},
            )
            # 模拟下载延迟
            import time

            time.sleep(1)

        # 创建模拟的文件数据
        file_data = {
            "filename": "downloaded_video.mp4",
            "size": 100 * 1024 * 1024,  # 100MB
            "type": "url",
            "file_path": "/tmp/downloaded_video.mp4",  # 实际应该是下载后的路径
        }

        # 继续按文件处理流程
        return process_video_file_task(self, task_id, file_data, config)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ URL任务 {task_id} 处理失败: {error_msg}")

        update_task_status(
            task_id,
            {
                "status": "failed",
                "error": error_msg,
                "current_step": f"下载失败: {error_msg}",
            },
        )

        raise


def update_task_status(task_id: str, update_data: Dict[str, Any]):
    """更新任务状态（同步版本，用于Celery任务中）"""
    try:
        # 使用asyncio运行异步任务更新
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # 如果事件循环正在运行，创建新的事件循环
            import threading
            import concurrent.futures

            def run_async_update():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        task_service.update_task("video", task_id, update_data)
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_update)
                future.result(timeout=10)  # 10秒超时
        else:
            # 直接运行异步更新
            loop.run_until_complete(
                task_service.update_task("video", task_id, update_data)
            )

    except Exception as e:
        logger.error(f"更新任务状态失败: {e}")


def extract_audio_from_video(
    video_path: str, task_id: str, file_data: Dict[str, Any]
) -> str:
    """从视频中提取音频"""
    try:
        logger.info(f"🎬 从视频提取音频: {Path(video_path).name}")

        # 如果是音频文件，直接返回路径
        if file_data.get("type") == "audio":
            return video_path

        # 检查视频文件是否存在
        if not Path(video_path).exists():
            raise Exception(f"视频文件不存在: {video_path}")

        # 创建输出目录
        work_dir = PROJECT_ROOT / "data" / "outputs" / task_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # 音频输出路径
        audio_filename = f"{task_id}_audio.wav"
        audio_path = work_dir / audio_filename

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
            logger.info(f"✅ 音频提取成功: {audio_path}")
            return str(audio_path)
        else:
            error_msg = result.stderr if result.stderr else "未知错误"
            raise Exception(f"音频提取失败: {error_msg}")

    except Exception as e:
        logger.error(f"❌ 音频提取失败: {e}")
        raise


def run_speech_recognition(audio_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """运行语音识别"""
    try:
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
            if result.get("error"):
                error_msg = result.get("error", "未知错误")
                logger.error(f"❌ 语音识别失败: {error_msg}")
                raise Exception(f"语音识别失败: {error_msg}")

            text_content = result.get("text", "").strip()
            if text_content:
                logger.info(f"✅ 识别成功 - 文本长度: {len(text_content)}")
                return result
            else:
                raise Exception("语音识别返回空文本内容")
        else:
            raise Exception("语音识别返回空结果")

    except Exception as e:
        logger.error(f"❌ 语音识别失败: {e}")
        raise


def generate_summary(transcript_text: str, config: Dict[str, Any]) -> str:
    """生成摘要"""
    try:
        output_types = config.get("output_types", [])

        if "summary" in output_types and transcript_text:
            # 这里应该调用AI摘要生成模块
            # 目前返回简单摘要
            return f"基于转录内容生成的智能摘要：{transcript_text[:200]}..."
        else:
            return ""

    except Exception as e:
        logger.error(f"摘要生成失败: {e}")
        return f"摘要生成失败: {str(e)}"


def generate_output_files(
    task_id: str,
    transcript: Dict[str, Any],
    summary: str,
    config: Dict[str, Any],
) -> List[Dict[str, str]]:
    """生成输出文件"""
    try:
        # 创建任务输出目录
        output_dir = PROJECT_ROOT / "data" / "outputs" / task_id
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
            subtitle_content = generate_subtitle(transcript_text)
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
            flashcards = generate_flashcards(transcript_text)
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
        logger.error(f"文件生成失败: {e}")
        raise Exception(f"文件生成失败: {str(e)}")


def generate_subtitle(transcript: str) -> str:
    """生成字幕文件"""
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


def generate_flashcards(transcript: str) -> List[Dict[str, str]]:
    """生成记忆卡片"""
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
