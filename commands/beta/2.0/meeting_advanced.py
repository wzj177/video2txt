#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时会议记录系统 - 高级功能模块
包括说话人分离、Ollama集成、智能总结等
"""

import os
import json
import time
import requests
import threading
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import torch

# 说话人分离
try:
    from pyannote.audio import Pipeline
    import torchaudio

    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False


@dataclass
class SpeakerSegment:
    """说话人片段"""

    start_time: float
    end_time: float
    speaker_id: str
    confidence: float = 0.0


class SpeakerDiarizer:
    """说话人分离模块"""

    def __init__(self):
        self.pipeline = None
        self.speaker_embeddings = {}
        self.speaker_names = {}
        self.speaker_counter = 0

    def initialize(self) -> bool:
        """初始化说话人分离模型"""
        if not HAS_PYANNOTE:
            print("⚠️ 说话人分离功能需要安装: pip install pyannote.audio")
            return False

        try:
            print("🔄 加载说话人分离模型...")
            # 使用预训练的说话人分离模型
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=None,  # 如果需要HuggingFace token
            )
            print("✅ 说话人分离模型加载完成")
            return True

        except Exception as e:
            print(f"⚠️ 说话人分离模型加载失败: {e}")
            print("💡 提示: 可能需要HuggingFace访问权限")
            return False

    def process_audio_chunk(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> List[SpeakerSegment]:
        """处理音频块，返回说话人片段"""
        if not self.pipeline:
            return []

        try:
            # 转换为torch tensor
            audio_tensor = torch.from_numpy(audio_data).float()
            if len(audio_tensor.shape) == 1:
                audio_tensor = audio_tensor.unsqueeze(0)  # 添加batch维度

            # 创建临时音频对象用于分离
            waveform = {"waveform": audio_tensor, "sample_rate": sample_rate}

            # 执行说话人分离
            diarization = self.pipeline(waveform)

            # 转换结果
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = SpeakerSegment(
                    start_time=turn.start,
                    end_time=turn.end,
                    speaker_id=speaker,
                    confidence=1.0,  # pyannote不直接提供置信度
                )
                segments.append(segment)

            return segments

        except Exception as e:
            print(f"⚠️ 说话人分离处理失败: {e}")
            return []

    def assign_speaker_name(self, speaker_id: str, name: str):
        """为说话人分配名称"""
        self.speaker_names[speaker_id] = name

    def get_speaker_name(self, speaker_id: str) -> str:
        """获取说话人名称"""
        return self.speaker_names.get(speaker_id, f"说话人{speaker_id}")


class MeetingAnalyzer:
    """会议分析器"""

    def __init__(self):
        self.speaker_diarizer = SpeakerDiarizer()
        self.ollama = OllamaIntegration()

    def initialize(self) -> bool:
        """初始化分析器"""
        success = True

        # 初始化说话人分离（可选）
        if not self.speaker_diarizer.initialize():
            print("⚠️ 说话人分离功能不可用")
            success = False

        # 初始化Ollama（可选）
        if not self.ollama.initialize():
            print("⚠️ AI总结功能不可用")
            success = False

        return success

    def analyze_meeting_file(self, transcription_file: str) -> Dict:
        """分析会议文件"""
        try:
            # 读取转录文件
            transcriptions = []
            with open(transcription_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        transcriptions.append(json.loads(line))

            # 基础统计
            analysis = self._basic_analysis(transcriptions)

            # AI总结
            if self.ollama.available:
                analysis["ai_summary"] = {
                    "general": self.ollama.generate_summary(transcriptions, "general"),
                    "by_speaker": self.ollama.generate_summary(
                        transcriptions, "by_speaker"
                    ),
                    "by_topic": self.ollama.generate_summary(
                        transcriptions, "by_topic"
                    ),
                }

            return analysis

        except Exception as e:
            print(f"❌ 会议分析失败: {e}")
            return {}

    def _basic_analysis(self, transcriptions: List[Dict]) -> Dict:
        """基础分析"""
        if not transcriptions:
            return {}

        # 时间统计
        start_time = transcriptions[0].get("start_time", 0)
        end_time = transcriptions[-1].get("end_time", 0)
        duration = end_time - start_time

        # 语言统计
        languages = {}
        for trans in transcriptions:
            lang = trans.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1

        # 说话人统计
        speakers = {}
        for trans in transcriptions:
            speaker = trans.get("speaker_id", "unknown")
            speakers[speaker] = speakers.get(speaker, 0) + 1

        # 字数统计
        total_words = sum(len(trans.get("text", "")) for trans in transcriptions)

        return {
            "duration_minutes": duration / 60,
            "total_segments": len(transcriptions),
            "total_words": total_words,
            "languages": languages,
            "speakers": speakers,
            "start_time": start_time,
            "end_time": end_time,
        }


def analyze_meeting_command(transcription_file: str):
    """命令行工具：分析会议文件"""
    print(f"分析会议文件: {transcription_file}")

    analyzer = MeetingAnalyzer()
    analyzer.initialize()

    analysis = analyzer.analyze_meeting_file(transcription_file)

    if analysis:
        print("\n📊 会议分析结果:")
        print(f"会议时长: {analysis.get('duration_minutes', 0):.1f} 分钟")
        print(f"转录片段: {analysis.get('total_segments', 0)} 段")
        print(f"总字数: {analysis.get('total_words', 0)} 字")

        # 语言分布
        languages = analysis.get("languages", {})
        if languages:
            print(
                f"语言分布: {', '.join([f'{lang}({count})' for lang, count in languages.items()])}"
            )

        # 说话人分布
        speakers = analysis.get("speakers", {})
        if speakers:
            print(
                f"发言人: {', '.join([f'{speaker}({count})' for speaker, count in speakers.items()])}"
            )

        # AI总结
        ai_summary = analysis.get("ai_summary", {})
        if ai_summary:
            print("\n🤖 AI智能总结:")

            general = ai_summary.get("general")
            if general:
                print("\n### 会议总览")
                print(general)

            by_speaker = ai_summary.get("by_speaker")
            if by_speaker:
                print("\n### 按发言人总结")
                print(by_speaker)

            by_topic = ai_summary.get("by_topic")
            if by_topic:
                print("\n### 按主题总结")
                print(by_topic)

    else:
        print("❌ 分析失败")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        analyze_meeting_command(sys.argv[1])
    else:
        print("用法: python meeting_advanced.py <transcription_file>")
        print(
            "示例: python meeting_advanced.py meeting_records/20240115_143022/transcriptions.jsonl"
        )
