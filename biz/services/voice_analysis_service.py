#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音分析服务 - SenseVoice + PyAnnote方案
实现人声区分、语音转文字和情感分析的完整解决方案
"""

import os
import sys
import logging
import tempfile
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import time
from datetime import datetime
import asyncio

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class VoiceAnalysisService:
    """语音分析服务 - 集成说话人分离、语音识别和情感分析"""

    def __init__(self):
        self.diarization_pipeline = None
        self.voice_core = None
        self.initialized = False
        self.models_cache = {}

    def _get_huggingface_token(self) -> Optional[str]:
        """从配置文件获取 Hugging Face Token"""
        try:
            # 首先尝试从环境变量获取
            env_token = os.getenv("HUGGINGFACE_TOKEN")
            if env_token:
                return env_token

            # 然后从配置文件获取
            config_path = PROJECT_ROOT / "config" / "settings.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    token = config.get("system", {}).get("huggingface", {}).get("token")
                    if token:
                        logger.info("📁 从配置文件加载 Hugging Face Token")
                        return token

            logger.warning("⚠️ 未找到 Hugging Face Token")
            return None

        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return None

    def _should_try_pyannote(self) -> bool:
        """检查是否应该尝试使用 PyAnnote"""
        try:
            config_path = PROJECT_ROOT / "config" / "settings.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return (
                        config.get("system", {})
                        .get("huggingface", {})
                        .get("enable_pyannote", False)
                    )
            return False
        except Exception as e:
            logger.warning(f"读取 PyAnnote 配置失败: {e}")
            return False

    async def initialize(self) -> bool:
        """初始化语音分析服务"""
        try:
            logger.info("🎙️ 初始化语音分析服务...")

            # 1. 初始化说话人分离模型
            await self._initialize_diarization()

            # 2. 初始化语音识别核心
            await self._initialize_voice_recognition()

            self.initialized = True
            logger.info("✅ 语音分析服务初始化完成")
            return True

        except Exception as e:
            logger.error(f"语音分析服务初始化失败: {e}")
            return False

    async def _initialize_diarization(self):
        """初始化说话人分离模型"""
        pass

    async def _initialize_voice_recognition(self):
        """初始化语音识别核心"""
        try:
            logger.info("初始化SenseVoice语音识别...")

            from core.asr import get_voice_core, initialize_voice_recognition

            # 初始化SenseVoice引擎
            success = initialize_voice_recognition("sensevoice", "small")
            if not success:
                raise RuntimeError("SenseVoice初始化失败")

            self.voice_core = get_voice_core()

            # 确保引擎已加载
            if not self.voice_core.current_engine:
                self.voice_core._ensure_engine_loaded("sensevoice")

            logger.info("✅ SenseVoice语音识别初始化成功")

        except Exception as e:
            logger.error(f"初始化语音识别失败: {e}")
            raise

    async def analyze_audio_file(
        self,
        audio_path: str,
        enable_diarization: bool = True,
        enable_emotion: bool = True,
    ) -> Dict[str, Any]:
        """
        分析音频文件 - 完整的语音分析流程

        Args:
            audio_path: 音频文件路径
            enable_diarization: 是否启用说话人分离
            enable_emotion: 是否启用情感分析

        Returns:
            完整的分析结果
        """
        if not self.initialized:
            await self.initialize()

        try:
            logger.info(f"开始分析音频文件: {Path(audio_path).name}")
            start_time = time.time()

            results = {
                "audio_path": audio_path,
                "analysis_time": None,
                "speakers": {},
                "segments": [],
                "full_transcript": "",
                "emotions": {},
                "statistics": {},
            }

            # 步骤1: 说话人分离
            if enable_diarization and self.diarization_pipeline:
                logger.info("👥 执行说话人分离...")
                diarization_result = await self._perform_diarization(audio_path)
                results["diarization"] = diarization_result
            else:
                logger.info("⏭️ 跳过说话人分离，使用简单时间分割")
                diarization_result = await self._simple_time_segmentation(audio_path)
                results["diarization"] = diarization_result

            # 步骤2: 语音转文字 + 情感分析
            logger.info("📝 执行语音识别和情感分析...")
            transcription_result = await self._perform_transcription_with_emotion(
                audio_path, diarization_result, enable_emotion
            )

            results.update(transcription_result)

            # 步骤3: 生成统计信息
            results["statistics"] = self._generate_statistics(results)

            analysis_time = time.time() - start_time
            results["analysis_time"] = analysis_time

            logger.info(f"✅ 音频分析完成，耗时: {analysis_time:.2f}秒")
            return results

        except Exception as e:
            logger.error(f"音频分析失败: {e}")
            return {
                "error": str(e),
                "audio_path": audio_path,
                "analysis_time": (
                    time.time() - start_time if "start_time" in locals() else 0
                ),
            }

    async def _perform_diarization(self, audio_path: str) -> Dict[str, Any]:
        """执行说话人分离"""
        try:
            # 应用说话人分离
            diarization = self.diarization_pipeline(audio_path)

            # 转换结果格式
            speakers = {}
            segments = []

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speaker_id = f"Speaker_{speaker}"

                if speaker_id not in speakers:
                    speakers[speaker_id] = {
                        "id": speaker_id,
                        "name": speaker_id,
                        "total_duration": 0.0,
                        "segments_count": 0,
                    }

                segment = {
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "duration": float(turn.end - turn.start),
                    "speaker": speaker_id,
                }

                segments.append(segment)
                speakers[speaker_id]["total_duration"] += segment["duration"]
                speakers[speaker_id]["segments_count"] += 1

            return {
                "method": "pyannote",
                "speakers": speakers,
                "segments": segments,
                "total_speakers": len(speakers),
            }

        except Exception as e:
            logger.error(f"说话人分离失败: {e}")
            # 回退到简单分割
            return await self._simple_time_segmentation(audio_path)

    async def _simple_time_segmentation(self, audio_path: str) -> Dict[str, Any]:
        pass
    async def _perform_transcription_with_emotion(
        self,
        audio_path: str,
        diarization_result: Dict[str, Any],
        enable_emotion: bool = True,
    ) -> Dict[str, Any]:
        """执行语音识别和情感分析"""
        try:
            # 使用SenseVoice进行完整的语音识别
            recognition_result = self.voice_core.recognize_file(audio_path)

            if not recognition_result or not recognition_result.get("text"):
                # 🔄 第一次识别失败，尝试用不同参数重新识别
                logger.info(f"🔄 首次识别为空，尝试降低VAD敏感度重新识别: {audio_path}")

                try:
                    # 尝试强制使用中文识别，降低VAD敏感度
                    recognition_result = self.voice_core.recognize_file(
                        audio_path, language="zh"
                    )

                    if recognition_result and recognition_result.get("text"):
                        logger.info(
                            f"✅ 重新识别成功: {recognition_result.get('text')[:50]}..."
                        )
                    else:
                        # 最后尝试：使用auto语言检测
                        recognition_result = self.voice_core.recognize_file(
                            audio_path, language="auto"
                        )

                        if recognition_result and recognition_result.get("text"):
                            logger.info(
                                f"✅ 自动语言检测识别成功: {recognition_result.get('text')[:50]}..."
                            )

                except Exception as e:
                    logger.warning(f"重新识别也失败: {e}")

                # 如果重新识别仍然失败
                if not recognition_result or not recognition_result.get("text"):
                    logger.warning(f"音频文件可能为静音或无有效语音内容: {audio_path}")
                    return {
                        "segments": [],
                        "full_transcript": "",
                        "speakers": {},
                        "recognition_info": {
                            "model": "sensevoice",
                            "language": "zh",
                            "processing_time": 0,
                            "confidence": 0.0,
                            "status": "empty_audio",
                        },
                        "warning": "音频内容为空或无法识别",
                    }

            full_transcript = recognition_result["text"]

            # 处理分段信息
            segments = []
            current_segments = diarization_result.get("segments", [])

            if not current_segments:
                # 如果没有分离结果，创建一个完整的段落
                current_segments = [
                    {
                        "start": 0.0,
                        "end": recognition_result.get("duration", 60.0),
                        "duration": recognition_result.get("duration", 60.0),
                        "speaker": "Speaker_1",
                    }
                ]

            # 分配文本到各个时间段
            total_text_length = len(full_transcript)

            for i, segment in enumerate(current_segments):
                # 简单按比例分配文本
                start_ratio = i / len(current_segments)
                end_ratio = (i + 1) / len(current_segments)

                start_pos = int(start_ratio * total_text_length)
                end_pos = int(end_ratio * total_text_length)

                segment_text = full_transcript[start_pos:end_pos].strip()

                if not segment_text and i == len(current_segments) - 1:
                    # 最后一段如果为空，分配剩余文本
                    segment_text = full_transcript[start_pos:].strip()

                # 从SenseVoice结果中提取情感信息
                emotion_info = (
                    self._extract_emotion_from_sensevoice(
                        recognition_result, segment_text
                    )
                    if enable_emotion
                    else "neutral"
                )

                segment_result = {
                    "start": segment["start"],
                    "end": segment["end"],
                    "duration": segment["duration"],
                    "speaker": segment["speaker"],
                    "text": segment_text,
                    "confidence": recognition_result.get("confidence", 0.8),
                    "language": recognition_result.get("language", "zh"),
                    "emotion": (
                        emotion_info.get("primary_emotion", "neutral")
                        if isinstance(emotion_info, dict)
                        else emotion_info
                    ),
                    "timestamp": datetime.now().isoformat(),
                }

                segments.append(segment_result)

            # 更新说话人信息
            speakers = diarization_result.get("speakers", {})
            for segment in segments:
                speaker_id = segment["speaker"]
                if speaker_id in speakers and segment["text"]:
                    if "words" not in speakers[speaker_id]:
                        speakers[speaker_id]["words"] = []
                    speakers[speaker_id]["words"].extend(segment["text"].split())

            return {
                "segments": segments,
                "full_transcript": full_transcript,
                "speakers": speakers,
                "recognition_info": {
                    "model": recognition_result.get("model", "sensevoice"),
                    "language": recognition_result.get("language", "zh"),
                    "processing_time": recognition_result.get("processing_time", 0),
                    "confidence": recognition_result.get("confidence", 0.8),
                },
            }

        except Exception as e:
            logger.error(f"语音识别和情感分析失败: {e}")
            return {
                "segments": [],
                "full_transcript": "",
                "speakers": {},
                "error": str(e),
            }

    def _extract_emotion_from_sensevoice(
        self, recognition_result: Dict[str, Any], text: str
    ) -> Dict[str, Any]:
        """从SenseVoice结果中提取情感信息"""
        try:
            # 1. 首先尝试从SenseVoice原始结果中提取情感标记
            raw_result = recognition_result.get("raw_result", {})
            raw_text = raw_result.get("text", text)

            # SenseVoice的情感标记模式：<|HAPPY|>, <|SAD|>, <|ANGRY|>, <|SURPRISED|>, <|FEARFUL|>, <|DISGUSTED|>, <|NEUTRAL|>
            emotion_patterns = {
                "happy": ["<|HAPPY|>", "<|JOY|>", "开心", "高兴", "愉快", "笑", "哈哈"],
                "sad": ["<|SAD|>", "<|SORROW|>", "难过", "伤心", "哭", "遗憾", "失望"],
                "angry": ["<|ANGRY|>", "<|ANGER|>", "生气", "愤怒", "气愤", "讨厌"],
                "surprised": [
                    "<|SURPRISED|>",
                    "<|SURPRISE|>",
                    "惊讶",
                    "意外",
                    "没想到",
                    "竟然",
                ],
                "fearful": ["<|FEARFUL|>", "<|FEAR|>", "害怕", "恐惧", "担心"],
                "disgusted": ["<|DISGUSTED|>", "<|DISGUST|>", "厌恶", "恶心"],
                "neutral": ["<|NEUTRAL|>", "<|CALM|>"],
            }

            detected_emotions = []
            confidence = 0.5  # 默认置信度
            method = "keyword"

            # 2. 优先检查SenseVoice的情感标记
            for emotion, patterns in emotion_patterns.items():
                for pattern in patterns:
                    if pattern.startswith("<|") and pattern.endswith("|>"):
                        # SenseVoice原生情感标记
                        if pattern in raw_text:
                            detected_emotions.append(emotion)
                            confidence = 0.9  # SenseVoice原生标记置信度高
                            method = "sensevoice_native"
                            break
                    elif pattern in text.lower():
                        # 文本关键词匹配
                        detected_emotions.append(emotion)
                        confidence = max(confidence, 0.7)
                        method = "sensevoice_keyword"

            # 3. 如果没有检测到任何情感，默认为neutral
            if not detected_emotions:
                detected_emotions = ["neutral"]
                confidence = 0.6

            # 4. 基于语音特征的情感推断（简单规则）
            if "！" in text or "!!" in text:
                if "excited" not in detected_emotions:
                    detected_emotions.append("excited")
                confidence = max(confidence, 0.75)

            if "？" in text and len(text) < 20:
                if "surprised" not in detected_emotions:
                    detected_emotions.append("surprised")
                confidence = max(confidence, 0.7)

            # 5. 返回主要情感和所有检测到的情感
            primary_emotion = detected_emotions[0]

            return {
                "primary_emotion": primary_emotion,
                "all_emotions": detected_emotions,
                "confidence": confidence,
                "method": method,
                "raw_text": raw_text,  # 保留原始文本用于调试
                "analysis_details": {
                    "sensevoice_markers": len(
                        [e for e in detected_emotions if method == "sensevoice_native"]
                    ),
                    "keyword_matches": len(
                        [e for e in detected_emotions if method == "sensevoice_keyword"]
                    ),
                    "text_features": {
                        "exclamation_marks": text.count("！") + text.count("!"),
                        "question_marks": text.count("？") + text.count("?"),
                        "text_length": len(text),
                    },
                },
            }

        except Exception as e:
            logger.error(f"情感提取失败: {e}")
            return {
                "primary_emotion": "neutral",
                "all_emotions": ["neutral"],
                "confidence": 0.0,
                "method": "fallback",
                "error": str(e),
            }

    def _generate_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """生成分析统计信息"""
        try:
            segments = results.get("segments", [])
            speakers = results.get("speakers", {})

            stats = {
                "total_duration": sum(s.get("duration", 0) for s in segments),
                "total_speakers": len(speakers),
                "total_segments": len(segments),
                "total_words": len(results.get("full_transcript", "").split()),
                "average_segment_duration": 0,
                "speaker_stats": {},
                "emotion_distribution": {},
            }

            if segments:
                stats["average_segment_duration"] = stats["total_duration"] / len(
                    segments
                )

            # 说话人统计
            for speaker_id, speaker_info in speakers.items():
                stats["speaker_stats"][speaker_id] = {
                    "duration": speaker_info.get("total_duration", 0),
                    "segments": speaker_info.get("segments_count", 0),
                    "words": len(speaker_info.get("words", [])),
                    "percentage": (
                        speaker_info.get("total_duration", 0)
                        / stats["total_duration"]
                        * 100
                        if stats["total_duration"] > 0
                        else 0
                    ),
                }

            # 情感统计
            emotions = {}
            for segment in segments:
                emotion = segment.get("emotion", {}).get("primary_emotion", "neutral")
                emotions[emotion] = emotions.get(emotion, 0) + 1

            total_segments = len(segments)
            for emotion, count in emotions.items():
                stats["emotion_distribution"][emotion] = {
                    "count": count,
                    "percentage": (
                        count / total_segments * 100 if total_segments > 0 else 0
                    ),
                }

            return stats

        except Exception as e:
            logger.error(f"生成统计信息失败: {e}")
            return {"error": str(e)}

    async def analyze_realtime_audio(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> Dict[str, Any]:
        """实时音频分析（简化版）"""
        try:
            if not self.initialized:
                await self.initialize()

            # 确保data目录存在
            from pathlib import Path

            data_dir = Path(__file__).parent.parent.parent / "data" / "temp_audio"
            data_dir.mkdir(parents=True, exist_ok=True)

            # 创建临时文件在data目录下
            import time

            timestamp = int(time.time() * 1000)
            temp_path = str(data_dir / f"voice_analysis_{timestamp}.wav")

            # 保存音频数据
            import soundfile as sf

            sf.write(temp_path, audio_data, sample_rate)

            # 执行快速分析（不进行说话人分离，节省时间）
            result = await self.analyze_audio_file(
                temp_path, enable_diarization=False, enable_emotion=True
            )

            # 清理临时文件
            try:
                os.unlink(temp_path)
            except:
                pass

            return result

        except Exception as e:
            logger.error(f"实时音频分析失败: {e}")
            return {"error": str(e)}


# 全局服务实例
voice_analysis_service = VoiceAnalysisService()


# 便捷函数
async def analyze_audio_file(
    audio_path: str, enable_diarization: bool = True, enable_emotion: bool = True
) -> Dict[str, Any]:
    """分析音频文件的便捷函数"""
    return await voice_analysis_service.analyze_audio_file(
        audio_path, enable_diarization, enable_emotion
    )


async def analyze_realtime_audio(
    audio_data: np.ndarray, sample_rate: int = 16000
) -> Dict[str, Any]:
    """实时音频分析的便捷函数"""
    return await voice_analysis_service.analyze_realtime_audio(audio_data, sample_rate)


def analyze_realtime_audio_sync(
    audio_data: np.ndarray, sample_rate: int = 16000
) -> Dict[str, Any]:
    """实时音频分析的同步便捷函数（用于实时转录线程）"""
    try:
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 在新的事件循环中运行异步分析
            result = loop.run_until_complete(
                voice_analysis_service.analyze_realtime_audio(audio_data, sample_rate)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"同步实时音频分析失败: {e}")
        return {"error": str(e)}


def get_voice_analysis_service() -> VoiceAnalysisService:
    """获取语音分析服务实例"""
    return voice_analysis_service
