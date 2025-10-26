#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI会议分析服务 - 提供完整的会议分析功能
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class AIMeetingAnalyzer:
    """AI会议分析器 - 提供智能会议分析功能"""

    def __init__(self):
        self.initialized = False

    async def analyze_meeting(
        self,
        transcript_text: str,
        segments: List[Dict[str, Any]],
        speakers: Dict[str, Any],
        config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """兼容原有调用的会议分析方法"""
        meeting_title = config.get("title", "会议记录") if config else "会议记录"
        return await self.analyze_meeting_content(
            segments=segments,
            full_transcript=transcript_text,
            speakers=speakers,
            meeting_title=meeting_title,
        )

    async def analyze_meeting_content(
        self,
        segments: List[Dict[str, Any]],
        full_transcript: str,
        speakers: Dict[str, Any],
        meeting_title: str = "会议记录",
    ) -> Dict[str, Any]:
        """完整的会议内容分析

        Args:
            segments: 分段转录结果
            full_transcript: 完整转录文本
            speakers: 说话人信息
            meeting_title: 会议标题

        Returns:
            完整的会议分析结果
        """
        try:
            logger.info("🤖 开始AI会议分析...")

            # 1. 智能速览分析
            overview = await self._generate_smart_overview(
                segments, full_transcript, speakers, meeting_title
            )

            # 2. 章节速览分析
            chapters = await self._generate_chapter_overview(segments, full_transcript)

            # 3. 发言人总结分析
            speaker_summaries = await self._generate_speaker_summaries(
                segments, speakers
            )

            # 4. 问答回顾分析
            qa_review = await self._generate_qa_review(segments, full_transcript)

            # 5. 情感和主题分析
            sentiment_analysis = await self._analyze_sentiment_and_topics(
                segments, full_transcript
            )

            result = {
                "success": True,  # 添加success字段
                "smart_overview": overview,
                "chapters": chapters,
                "speaker_summaries": speaker_summaries,
                "qa_review": qa_review,
                "sentiment_analysis": sentiment_analysis,
                # 兼容原有字段名
                "summary": overview.get("summary", ""),
                "keywords": overview.get("keywords", []),
                "key_points": overview.get("key_topics", []),
                "qa_analysis": qa_review,
                "speaker_analysis": speaker_summaries,
                "meeting_overview": overview,
                "action_items": [],  # 可以后续扩展
                "decisions": [],  # 可以后续扩展
                "analysis_metadata": {
                    "analyzed_at": datetime.now().isoformat(),
                    "total_segments": len(segments),
                    "total_speakers": len(speakers),
                    "total_words": len(full_transcript.split()),
                    "analyzer_version": "1.0.0",
                },
            }

            logger.info("✅ AI会议分析完成")
            return result

        except Exception as e:
            logger.error(f"AI会议分析失败: {e}")
            return {
                "success": False,  # 添加success字段
                "error": str(e),
                "analysis_metadata": {
                    "analyzed_at": datetime.now().isoformat(),
                    "status": "failed",
                },
            }

    async def _generate_smart_overview(
        self,
        segments: List[Dict[str, Any]],
        full_transcript: str,
        speakers: Dict[str, Any],
        meeting_title: str,
    ) -> Dict[str, Any]:
        """生成智能速览"""
        try:
            # 提取关键词
            keywords = await self._extract_keywords(full_transcript)

            # 生成会议总结
            summary = await self._generate_meeting_summary(
                full_transcript, segments, meeting_title
            )

            return {
                "keywords": keywords,
                "summary": summary,
                "meeting_title": meeting_title,
                "participants_count": len(speakers),
                "key_topics": await self._extract_key_topics(full_transcript),
            }

        except Exception as e:
            logger.error(f"智能速览生成失败: {e}")
            return {"keywords": [], "summary": "分析失败，请重试", "error": str(e)}

    async def _generate_chapter_overview(
        self, segments: List[Dict[str, Any]], full_transcript: str
    ) -> List[Dict[str, Any]]:
        """生成章节速览"""
        try:
            chapters = []

            # 按时间段分组（每3-5分钟一个章节）
            chapter_duration = 180  # 3分钟
            current_chapter = []
            chapter_start_time = 0

            for segment in segments:
                segment_start = segment.get("start", 0)

                # 如果超过章节时长，创建新章节
                if (
                    segment_start - chapter_start_time > chapter_duration
                    and current_chapter
                ):
                    chapter = await self._create_chapter_from_segments(
                        current_chapter, chapter_start_time
                    )
                    chapters.append(chapter)

                    current_chapter = [segment]
                    chapter_start_time = segment_start
                else:
                    current_chapter.append(segment)

            # 处理最后一个章节
            if current_chapter:
                chapter = await self._create_chapter_from_segments(
                    current_chapter, chapter_start_time
                )
                chapters.append(chapter)

            return chapters

        except Exception as e:
            logger.error(f"章节速览生成失败: {e}")
            return []

    async def _create_chapter_from_segments(
        self, segments: List[Dict[str, Any]], start_time: float
    ) -> Dict[str, Any]:
        """从分段创建章节"""
        try:
            # 合并所有文本
            chapter_text = " ".join([seg.get("text", "") for seg in segments])

            # 生成章节标题
            title = await self._generate_chapter_title(chapter_text)

            # 生成章节描述
            description = await self._generate_chapter_description(chapter_text)

            # 格式化时间
            time_formatted = self._format_timestamp(start_time)

            return {
                "time": time_formatted,
                "start_seconds": start_time,
                "title": title,
                "description": description,
                "segment_count": len(segments),
                "word_count": len(chapter_text.split()),
            }

        except Exception as e:
            logger.error(f"章节创建失败: {e}")
            return {
                "time": self._format_timestamp(start_time),
                "title": "未知章节",
                "description": "分析失败",
                "error": str(e),
            }

    async def _generate_speaker_summaries(
        self, segments: List[Dict[str, Any]], speakers: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """生成发言人总结"""
        try:
            summaries = []

            for speaker_id, speaker_info in speakers.items():
                # 收集该说话人的所有发言
                speaker_segments = [
                    seg for seg in segments if seg.get("speaker") == speaker_id
                ]

                if not speaker_segments:
                    continue

                # 合并发言内容
                speaker_text = " ".join(
                    [seg.get("text", "") for seg in speaker_segments]
                )

                if len(speaker_text.strip()) < 10:
                    summary_content = "发言内容太少，无总结内容哦"
                else:
                    # 生成发言人总结
                    summary_content = await self._generate_individual_speaker_summary(
                        speaker_text, speaker_segments
                    )

                summaries.append(
                    {
                        "speaker_id": speaker_id,
                        "speaker_name": f"发言人 {speaker_id.replace('Speaker_', '')}",
                        "avatar": self._get_speaker_avatar(speaker_id),
                        "summary": summary_content,
                        "segments_count": len(speaker_segments),
                        "word_count": len(speaker_text.split()),
                        "speaking_duration": sum(
                            [seg.get("duration", 0) for seg in speaker_segments]
                        ),
                    }
                )

            return summaries

        except Exception as e:
            logger.error(f"发言人总结生成失败: {e}")
            return []

    async def _generate_qa_review(
        self, segments: List[Dict[str, Any]], full_transcript: str
    ) -> List[Dict[str, Any]]:
        """生成问答回顾"""
        try:
            qa_pairs = []

            # 简单的问答识别逻辑
            question_indicators = ["什么", "为什么", "怎么", "如何", "吗", "呢", "？"]

            current_question = None
            for i, segment in enumerate(segments):
                text = segment.get("text", "").strip()
                if not text:
                    continue

                # 检查是否是问题
                is_question = (
                    any(indicator in text for indicator in question_indicators)
                    or text.endswith("？")
                    or text.endswith("?")
                )

                if is_question:
                    current_question = {
                        "question": text,
                        "timestamp": segment.get("start", 0),
                        "speaker": segment.get("speaker", "Unknown"),
                    }
                elif current_question and i < len(segments) - 1:
                    # 寻找后续的回答
                    answer_segments = segments[i : i + 3]  # 查看后续3个分段
                    answer_text = " ".join(
                        [
                            seg.get("text", "")
                            for seg in answer_segments
                            if seg.get("speaker")
                            != current_question["speaker"]  # 不同说话人的回答
                        ]
                    )

                    if answer_text.strip():
                        qa_pairs.append(
                            {
                                "question": f"问：{current_question['question']}",
                                "answer": f"答：{answer_text.strip()}",
                                "timestamp": current_question["timestamp"],
                                "question_speaker": current_question["speaker"],
                            }
                        )
                        current_question = None

            # 如果没有找到明显的问答，生成一些基于内容的问答
            if len(qa_pairs) < 3:
                synthetic_qa = await self._generate_synthetic_qa(full_transcript)
                qa_pairs.extend(synthetic_qa)

            return qa_pairs[:10]  # 最多返回10个问答

        except Exception as e:
            logger.error(f"问答回顾生成失败: {e}")
            return []

    async def _analyze_sentiment_and_topics(
        self, segments: List[Dict[str, Any]], full_transcript: str
    ) -> Dict[str, Any]:
        """分析情感和主题"""
        try:
            # 情感分析
            emotions = {}
            for segment in segments:
                emotion = segment.get("emotion", "neutral")
                emotions[emotion] = emotions.get(emotion, 0) + 1

            # 主题提取
            topics = await self._extract_key_topics(full_transcript)

            # 整体情感倾向
            total_segments = len(segments)
            sentiment_distribution = (
                {emotion: count / total_segments for emotion, count in emotions.items()}
                if total_segments > 0
                else {}
            )

            return {
                "emotion_distribution": emotions,
                "sentiment_distribution": sentiment_distribution,
                "dominant_emotion": (
                    max(emotions.items(), key=lambda x: x[1])[0]
                    if emotions
                    else "neutral"
                ),
                "key_topics": topics,
                "overall_tone": self._determine_overall_tone(sentiment_distribution),
            }

        except Exception as e:
            logger.error(f"情感和主题分析失败: {e}")
            return {
                "emotion_distribution": {},
                "sentiment_distribution": {},
                "dominant_emotion": "neutral",
                "key_topics": [],
                "overall_tone": "neutral",
            }

    # 辅助方法

    async def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取（基于词频）
        words = text.split()
        word_freq = {}

        # 停用词
        stop_words = {
            "的",
            "了",
            "是",
            "在",
            "我",
            "你",
            "他",
            "她",
            "和",
            "与",
            "或",
            "但",
            "然后",
            "这",
            "那",
            "这个",
            "那个",
        }

        for word in words:
            if len(word) > 1 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # 返回频次最高的关键词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:20] if freq > 1]

    async def _extract_key_topics(self, text: str) -> List[str]:
        """提取关键主题"""
        keywords = await self._extract_keywords(text)
        # 简单分组相关词汇作为主题
        return keywords[:10]  # 前10个关键词作为主题

    async def _generate_meeting_summary(
        self, full_transcript: str, segments: List[Dict[str, Any]], meeting_title: str
    ) -> str:
        """生成会议总结"""
        # 这里应该调用大语言模型，现在先用简单逻辑
        keywords = await self._extract_keywords(full_transcript)
        speakers_count = len(set([seg.get("speaker") for seg in segments]))

        summary = f"本次{meeting_title}共有{speakers_count}位参与者进行讨论。"

        if keywords:
            top_keywords = keywords[:5]
            summary += f"主要讨论了{', '.join(top_keywords)}等话题。"

        # 分析会议氛围
        emotions = [seg.get("emotion", "neutral") for seg in segments]
        positive_ratio = emotions.count("happy") / len(emotions) if emotions else 0

        if positive_ratio > 0.3:
            summary += "整体氛围较为积极正面。"
        elif positive_ratio < 0.1:
            summary += "讨论过程较为严肃。"
        else:
            summary += "会议氛围平和。"

        return summary

    async def _generate_chapter_title(self, text: str) -> str:
        """生成章节标题"""
        # 简单的标题生成逻辑
        keywords = await self._extract_keywords(text)
        if keywords:
            return f"{keywords[0]}相关讨论"
        return "会议讨论"

    async def _generate_chapter_description(self, text: str) -> str:
        """生成章节描述"""
        # 简单截取前100字作为描述
        return text[:100] + "..." if len(text) > 100 else text

    async def _generate_individual_speaker_summary(
        self, speaker_text: str, speaker_segments: List[Dict[str, Any]]
    ) -> str:
        """生成个人发言总结"""
        # 分析发言特点
        keywords = await self._extract_keywords(speaker_text)
        emotions = [seg.get("emotion", "neutral") for seg in speaker_segments]

        summary_parts = []

        # 发言内容特点
        if keywords:
            summary_parts.append(f"主要讨论了{', '.join(keywords[:3])}等内容")

        # 情感特点
        emotion_counts = {}
        for emotion in emotions:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

        dominant_emotion = (
            max(emotion_counts.items(), key=lambda x: x[1])[0]
            if emotion_counts
            else "neutral"
        )

        if dominant_emotion == "happy":
            summary_parts.append("表现出积极乐观的态度")
        elif dominant_emotion == "sad":
            summary_parts.append("表达出一些担忧或不满")
        elif dominant_emotion == "angry":
            summary_parts.append("语气较为激动")
        else:
            summary_parts.append("保持相对平和的语调")

        # 发言量特点
        if len(speaker_segments) > 10:
            summary_parts.append("发言较为活跃")
        elif len(speaker_segments) < 3:
            summary_parts.append("发言相对较少")

        return "，".join(summary_parts) + "。"

    async def _generate_synthetic_qa(self, text: str) -> List[Dict[str, Any]]:
        """生成合成的问答对"""
        # 基于内容生成一些通用问答
        keywords = await self._extract_keywords(text)

        synthetic_qa = []

        if "项目" in text or "工作" in text:
            synthetic_qa.append(
                {
                    "question": "问：这次讨论的主要项目是什么？",
                    "answer": f"答：主要讨论了{', '.join(keywords[:3])}相关的项目内容。",
                    "timestamp": 0,
                    "question_speaker": "System",
                }
            )

        if "时间" in text or "计划" in text:
            synthetic_qa.append(
                {
                    "question": "问：有提到具体的时间安排吗？",
                    "answer": "答：会议中提到了相关的时间安排和计划事项。",
                    "timestamp": 0,
                    "question_speaker": "System",
                }
            )

        return synthetic_qa

    def _get_speaker_avatar(self, speaker_id: str) -> str:
        """获取说话人头像"""
        avatars = ["👤", "👩", "👨", "🐦", "👦", "👧"]
        # 根据speaker_id生成一致的头像
        index = hash(speaker_id) % len(avatars)
        return avatars[index]

    def _format_timestamp(self, seconds: float) -> str:
        """格式化时间戳"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _determine_overall_tone(self, sentiment_distribution: Dict[str, float]) -> str:
        """确定整体语调"""
        if not sentiment_distribution:
            return "neutral"

        positive_emotions = ["happy", "excited", "positive"]
        negative_emotions = ["sad", "angry", "negative"]

        positive_score = sum(
            [sentiment_distribution.get(emotion, 0) for emotion in positive_emotions]
        )
        negative_score = sum(
            [sentiment_distribution.get(emotion, 0) for emotion in negative_emotions]
        )

        if positive_score > negative_score + 0.2:
            return "positive"
        elif negative_score > positive_score + 0.2:
            return "negative"
        else:
            return "neutral"


# 全局实例
ai_meeting_analyzer = AIMeetingAnalyzer()
