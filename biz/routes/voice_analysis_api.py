#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音分析API路由 - 支持人声区分和情感分析
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import json
import tempfile
import os
from pathlib import Path
from pydantic import BaseModel

from ..services.voice_analysis_service import voice_analysis_service
from ..services.task_service import task_service

voice_analysis_router = APIRouter(prefix="/api/voice-analysis", tags=["voice-analysis"])


class VoiceAnalysisRequest(BaseModel):
    task_id: str
    enable_diarization: bool = True
    enable_emotion: bool = True


@voice_analysis_router.post("/analyze-file")
async def analyze_audio_file(
    audio_file: UploadFile = File(...),
    enable_diarization: bool = Form(True),
    enable_emotion: bool = Form(True),
) -> Dict[str, Any]:
    """分析上传的音频文件"""
    try:
        # 验证文件类型
        if not audio_file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="只支持音频文件")

        # 创建临时文件
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, audio_file.filename)

        # 保存上传的文件
        with open(temp_path, "wb") as buffer:
            content = await audio_file.read()
            buffer.write(content)

        # 执行语音分析
        result = await voice_analysis_service.analyze_audio_file(
            temp_path,
            enable_diarization=enable_diarization,
            enable_emotion=enable_emotion,
        )

        # 清理临时文件
        try:
            os.remove(temp_path)
            os.rmdir(temp_dir)
        except:
            pass

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {"success": True, "data": result, "message": "语音分析完成"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音分析失败: {str(e)}")


@voice_analysis_router.post("/analyze-task/{task_id}")
async def analyze_task_audio(
    task_id: str,
    enable_diarization: bool = Form(True),
    enable_emotion: bool = Form(True),
) -> Dict[str, Any]:
    """分析现有任务的音频文件"""
    try:
        # 获取任务信息
        task = await task_service.get_task_by_id("video", task_id)
        if not task:
            # 尝试获取会议任务
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")

        # 获取音频文件路径
        audio_path = task.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="任务音频文件不存在")

        # 执行语音分析
        result = await voice_analysis_service.analyze_audio_file(
            audio_path,
            enable_diarization=enable_diarization,
            enable_emotion=enable_emotion,
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存分析结果到任务中
        analysis_results = task.get("results", {})
        analysis_results["voice_analysis"] = result

        await task_service.update_task(
            task.get("task_type", "video"), task_id, {"results": analysis_results}
        )

        return {
            "success": True,
            "data": result,
            "message": "语音分析完成并已保存到任务",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务语音分析失败: {str(e)}")


@voice_analysis_router.get("/task/{task_id}/voice-analysis")
async def get_task_voice_analysis(task_id: str) -> Dict[str, Any]:
    """获取任务的语音分析结果"""
    try:
        # 获取任务信息
        task = await task_service.get_task_by_id("video", task_id)
        if not task:
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")

        # 获取语音分析结果
        voice_analysis = task.get("results", {}).get("voice_analysis")

        if not voice_analysis:
            return {"success": True, "data": None, "message": "该任务尚未进行语音分析"}

        return {
            "success": True,
            "data": voice_analysis,
            "message": "获取语音分析结果成功",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取语音分析结果失败: {str(e)}")


@voice_analysis_router.get("/speakers/{task_id}")
async def get_task_speakers(task_id: str) -> Dict[str, Any]:
    """获取任务的说话人信息"""
    try:
        # 获取任务信息
        task = await task_service.get_task_by_id("video", task_id)
        if not task:
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")

        # 获取语音分析结果
        voice_analysis = task.get("results", {}).get("voice_analysis", {})
        speakers = voice_analysis.get("speakers", {})
        statistics = voice_analysis.get("statistics", {}).get("speaker_stats", {})

        # 组合说话人信息
        speaker_info = {}
        for speaker_id, speaker_data in speakers.items():
            stats = statistics.get(speaker_id, {})
            speaker_info[speaker_id] = {**speaker_data, "statistics": stats}

        return {
            "success": True,
            "data": {
                "speakers": speaker_info,
                "total_speakers": len(speaker_info),
                "analysis_available": bool(voice_analysis),
            },
            "message": "获取说话人信息成功",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取说话人信息失败: {str(e)}")


@voice_analysis_router.get("/emotions/{task_id}")
async def get_task_emotions(task_id: str) -> Dict[str, Any]:
    """获取任务的情感分析结果"""
    try:
        # 获取任务信息
        task = await task_service.get_task_by_id("video", task_id)
        if not task:
            task = await task_service.get_task_by_id("meeting", task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")

        # 获取语音分析结果
        voice_analysis = task.get("results", {}).get("voice_analysis", {})
        segments = voice_analysis.get("segments", [])
        statistics = voice_analysis.get("statistics", {})

        # 提取情感信息
        emotions_timeline = []
        for segment in segments:
            emotion_data = segment.get("emotion", {})
            if emotion_data:
                emotions_timeline.append(
                    {
                        "start": segment.get("start", 0),
                        "end": segment.get("end", 0),
                        "speaker": segment.get("speaker", "Unknown"),
                        "text": segment.get("text", ""),
                        "emotion": emotion_data.get("primary_emotion", "neutral"),
                        "confidence": emotion_data.get("confidence", 0),
                        "all_emotions": emotion_data.get("all_emotions", []),
                    }
                )

        return {
            "success": True,
            "data": {
                "emotions_timeline": emotions_timeline,
                "emotion_distribution": statistics.get("emotion_distribution", {}),
                "analysis_available": bool(voice_analysis),
            },
            "message": "获取情感分析结果成功",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取情感分析结果失败: {str(e)}")


@voice_analysis_router.get("/service/status")
async def get_service_status() -> Dict[str, Any]:
    """获取语音分析服务状态"""
    try:
        return {
            "success": True,
            "data": {
                "initialized": voice_analysis_service.initialized,
                "diarization_available": voice_analysis_service.diarization_pipeline
                is not None,
                "voice_recognition_available": voice_analysis_service.voice_core
                is not None,
                "models_cache": list(voice_analysis_service.models_cache.keys()),
            },
            "message": "语音分析服务状态获取成功",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": {
                "initialized": False,
                "diarization_available": False,
                "voice_recognition_available": False,
            },
        }


@voice_analysis_router.post("/service/initialize")
async def initialize_service() -> Dict[str, Any]:
    """初始化语音分析服务"""
    try:
        success = await voice_analysis_service.initialize()

        if success:
            return {"success": True, "message": "语音分析服务初始化成功"}
        else:
            raise HTTPException(status_code=500, detail="语音分析服务初始化失败")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化服务失败: {str(e)}")


@voice_analysis_router.get("/supported-features")
async def get_supported_features() -> Dict[str, Any]:
    """获取支持的功能特性"""
    return {
        "success": True,
        "data": {
            "features": {
                "speaker_diarization": {
                    "name": "说话人分离",
                    "description": "识别音频中不同的说话人",
                    "available": True,
                    "models": ["pyannote/speaker-diarization-3.1"],
                },
                "emotion_analysis": {
                    "name": "情感分析",
                    "description": "分析语音中的情感表达",
                    "available": True,
                    "methods": ["sensevoice_keyword", "text_analysis"],
                },
                "voice_recognition": {
                    "name": "语音识别",
                    "description": "将语音转换为文字",
                    "available": True,
                    "engines": ["sensevoice", "whisper"],
                },
            },
            "supported_formats": [".wav", ".mp3", ".m4a", ".flac"],
            "max_file_size": "100MB",
            "languages": ["zh", "en", "ja", "ko"],
        },
        "message": "功能特性获取成功",
    }
