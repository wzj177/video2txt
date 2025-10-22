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
            logger.error(f"❌ 语音分析服务初始化失败: {e}")
            return False

    async def _initialize_diarization(self):
        """初始化说话人分离模型"""
        try:
            logger.info("📊 初始化PyAnnote说话人分离模型...")

            # 延迟导入以避免初始化时的依赖问题
            try:
                from pyannote.audio import Pipeline
                from pyannote.core import Annotation, Segment
            except ImportError as e:
                logger.error(f"❌ PyAnnote依赖缺失: {e}")
                logger.info("请运行: pip install pyannote.audio")
                raise

            # 使用预训练的说话人分离模型
            model_name = "pyannote/speaker-diarization-3.1"

            # 检查是否需要Hugging Face token
            hf_token = os.getenv("HUGGINGFACE_TOKEN")

            try:
                if hf_token:
                    self.diarization_pipeline = Pipeline.from_pretrained(
                        model_name, use_auth_token=hf_token
                    )
                    logger.info("✅ 使用认证token加载说话人分离模型")
                else:
                    # 尝试无token方式
                    self.diarization_pipeline = Pipeline.from_pretrained(model_name)
                    logger.info("✅ 无需token加载说话人分离模型")

            except Exception as e:
                logger.warning(f"⚠️ 无法加载在线说话人分离模型: {e}")
                logger.info("💡 提示: 设置HUGGINGFACE_TOKEN环境变量可访问更多模型")
                logger.info("📝 将使用简单的时间分割作为备用方案")
                self.diarization_pipeline = None

            if self.diarization_pipeline:
                logger.info("✅ PyAnnote说话人分离模型加载成功")
            else:
                logger.warning("⚠️ 说话人分离模型未加载，将使用简单的时间分割")

        except Exception as e:
            logger.error(f"❌ 初始化说话人分离模型失败: {e}")
            self.diarization_pipeline = None

    async def _initialize_voice_recognition(self):
        """初始化语音识别核心"""
        try:
            logger.info("🎯 初始化SenseVoice语音识别...")

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
            logger.error(f"❌ 初始化语音识别失败: {e}")
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
            logger.error(f"❌ 音频分析失败: {e}")
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
        """改进的时间分割 - 基于音频能量检测多说话人"""
        try:
            import librosa
            import numpy as np
            
            # 加载音频
            y, sr = librosa.load(audio_path, sr=16000)
            duration = len(y) / sr

            # 计算音频能量和静音检测
            frame_length = int(0.025 * sr)  # 25ms帧
            hop_length = int(0.01 * sr)     # 10ms跳跃
            
            # 计算短时能量
            energy = []
            for i in range(0, len(y) - frame_length, hop_length):
                frame = y[i:i + frame_length]
                energy.append(np.sum(frame ** 2))
            
            energy = np.array(energy)
            
            # 动态阈值检测活跃语音段
            energy_threshold = np.percentile(energy, 30)  # 30%分位数作为阈值
            
            # 检测语音活动段
            active_segments = []
            in_speech = False
            start_time = 0
            
            for i, e in enumerate(energy):
                time_pos = i * hop_length / sr
                
                if e > energy_threshold and not in_speech:
                    # 开始语音段
                    start_time = time_pos
                    in_speech = True
                elif e <= energy_threshold and in_speech:
                    # 结束语音段
                    if time_pos - start_time > 0.5:  # 至少0.5秒
                        active_segments.append((start_time, time_pos))
                    in_speech = False
            
            # 如果最后还在语音段中
            if in_speech and duration - start_time > 0.5:
                active_segments.append((start_time, duration))
            
            # 基于语音段长度和间隔推测说话人数量
            if len(active_segments) == 0:
                # 没有检测到明显的语音段，假设一个说话人
                num_speakers = 1
                segments = [{
                    "start": 0.0,
                    "end": duration,
                    "duration": duration,
                    "speaker": "Speaker_1"
                }]
            elif len(active_segments) <= 3:
                # 少量语音段，可能是一个说话人
                num_speakers = 1
                segments = [{
                    "start": seg[0],
                    "end": seg[1], 
                    "duration": seg[1] - seg[0],
                    "speaker": "Speaker_1"
                } for seg in active_segments]
            else:
                # 多个语音段，尝试基于时间间隔推测多说话人
                gaps = []
                for i in range(1, len(active_segments)):
                    gap = active_segments[i][0] - active_segments[i-1][1]
                    gaps.append(gap)
                
                # 如果有较长的间隔，可能是多个说话人轮流说话
                long_gaps = [g for g in gaps if g > 2.0]  # 超过2秒的间隔
                
                if len(long_gaps) >= 2:
                    num_speakers = min(3, len(long_gaps) + 1)  # 最多假设3个说话人
                else:
                    num_speakers = 2  # 默认假设2个说话人
                
                # 交替分配说话人
                segments = []
                for i, (start, end) in enumerate(active_segments):
                    speaker_id = f"Speaker_{(i % num_speakers) + 1}"
                    segments.append({
                        "start": start,
                        "end": end,
                        "duration": end - start,
                        "speaker": speaker_id
                    })

            # 构建说话人信息
            speakers = {}
            for seg in segments:
                speaker_id = seg["speaker"]
                if speaker_id not in speakers:
                    speakers[speaker_id] = {
                        "id": speaker_id,
                        "name": speaker_id,
                        "total_duration": 0.0,
                        "segments_count": 0,
                    }
                speakers[speaker_id]["total_duration"] += seg["duration"]
                speakers[speaker_id]["segments_count"] += 1

            logger.info(f"📊 智能分割检测到 {len(speakers)} 个说话人，{len(segments)} 个语音段")

            return {
                "method": "intelligent_segmentation",
                "speakers": speakers,
                "segments": segments,
                "total_speakers": len(speakers),
            }

        except Exception as e:
            logger.error(f"智能分割失败: {e}")
            # 最后的备用方案
            duration = 30.0  # 默认时长
            try:
                import librosa
                duration = librosa.get_duration(path=audio_path)
            except:
                pass
                
            segments = [{
                "start": 0.0,
                "end": duration,
                "duration": duration,
                "speaker": "Speaker_1"
            }]
            
            speakers = {
                "Speaker_1": {
                    "id": "Speaker_1",
                    "name": "Speaker_1", 
                    "total_duration": duration,
                    "segments_count": 1,
                }
            }
            
            return {
                "method": "fallback_single",
                "speakers": speakers,
                "segments": segments,
                "total_speakers": 1,
            }

            current_time = 0.0
            while current_time < duration:
                end_time = min(current_time + segment_duration, duration)
                segment = {
                    "start": current_time,
                    "end": end_time,
                    "duration": end_time - current_time,
                    "speaker": "Speaker_1",
                }
                segments.append(segment)
                speakers["Speaker_1"]["segments_count"] += 1
                current_time = end_time

            return {
                "method": "simple_time",
                "speakers": speakers,
                "segments": segments,
                "total_speakers": 1,
            }

        except Exception as e:
            logger.error(f"简单时间分割失败: {e}")
            return {
                "method": "fallback",
                "speakers": {},
                "segments": [],
                "total_speakers": 0,
                "error": str(e),
            }

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
                    else {}
                )

                segment_result = {
                    "start": segment["start"],
                    "end": segment["end"],
                    "duration": segment["duration"],
                    "speaker": segment["speaker"],
                    "text": segment_text,
                    "confidence": recognition_result.get("confidence", 0.8),
                    "language": recognition_result.get("language", "zh"),
                    "emotion": emotion_info,
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
            # SenseVoice可能在原始文本中包含情感标记
            raw_text = recognition_result.get("raw_text", text)

            # 简单的情感关键词检测
            emotion_keywords = {
                "happy": ["开心", "高兴", "愉快", "笑", "哈哈"],
                "sad": ["难过", "伤心", "哭", "遗憾", "失望"],
                "angry": ["生气", "愤怒", "气愤", "讨厌"],
                "surprised": ["惊讶", "意外", "没想到", "竟然"],
                "neutral": [],
            }

            detected_emotions = []
            for emotion, keywords in emotion_keywords.items():
                if any(keyword in text for keyword in keywords):
                    detected_emotions.append(emotion)

            if not detected_emotions:
                detected_emotions = ["neutral"]

            return {
                "primary_emotion": detected_emotions[0],
                "all_emotions": detected_emotions,
                "confidence": 0.7,  # 基于关键词的简单检测
                "method": "sensevoice_keyword",
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
