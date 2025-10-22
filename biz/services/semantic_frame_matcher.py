#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语义帧匹配器 - 基于语义相似度而非时间进行帧匹配
通过AI分析帧内容和转录文本的语义关联度，提升匹配精度
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FrameMatchResult:
    """帧匹配结果"""

    frame_filename: str
    frame_timestamp: float
    matched_text_segment: str
    semantic_score: float
    match_reason: str
    confidence: float


class SemanticFrameMatcher:
    """语义帧匹配器 - 基于语义相似度进行智能匹配"""

    def __init__(self, ai_client):
        self.ai_client = ai_client
        logger.info("语义帧匹配器初始化完成")

    async def match_frames_to_content(
        self,
        frames: List[Tuple[str, float]],
        transcript: str,
        subtitles: List[Dict[str, Any]] = None,
        content_domain: str = "general",
        **kwargs,
    ) -> List[FrameMatchResult]:
        """
        基于语义相似度匹配帧与内容

        Args:
            frames: 帧列表 [(filename, timestamp), ...]
            transcript: 完整转录文本
            subtitles: SRT字幕列表（可选）
            content_domain: 内容领域

        Returns:
            List[FrameMatchResult]: 匹配结果列表
        """
        try:
            if not frames or not transcript.strip():
                return []

            # 1. 分析转录内容，提取语义段落
            semantic_segments = await self._extract_semantic_segments(
                transcript, content_domain
            )

            # 2. 为每个帧生成语义描述
            frame_descriptions = await self._generate_frame_descriptions(
                frames, content_domain
            )

            # 3. 执行语义匹配
            matches = await self._perform_semantic_matching(
                frame_descriptions, semantic_segments, subtitles
            )

            # 4. 优化匹配结果
            optimized_matches = self._optimize_matches(matches)

            logger.info(f"语义匹配完成: {len(optimized_matches)} 个高质量匹配")
            return optimized_matches

        except Exception as e:
            logger.error(f"语义帧匹配失败: {e}")
            return []

    async def _extract_semantic_segments(
        self, transcript: str, content_domain: str
    ) -> List[Dict[str, Any]]:
        """提取转录内容的语义段落"""

        domain_context = {
            "education": "教学内容，关注知识点、概念、步骤",
            "cooking": "烹饪内容，关注食材、步骤、技巧",
            "travel": "旅游内容，关注景点、体验、攻略",
            "technology": "科技内容，关注功能、操作、特性",
            "lifestyle": "生活内容，关注日常、体验、感受",
        }.get(content_domain, "通用内容")

        system_prompt = f"""你是一个专业的内容分析专家，擅长将文本内容分割为语义相关的段落。

# 任务说明
分析以下{content_domain}领域的转录内容，将其分割为3-8个语义相关的段落。每个段落应该：
1. 包含一个明确的主题或概念
2. 长度适中（50-200字）
3. 具有视觉表现潜力（可能对应视频画面）
4. 在{domain_context}的背景下有意义

# 输出格式
请以JSON数组格式返回，每个段落包含：
{{
    "segment_id": "段落编号",
    "content": "段落文字内容",
    "main_topic": "主要话题",
    "visual_keywords": ["可能的视觉关键词1", "关键词2"],
    "importance": "high/medium/low"
}}

请确保返回有效的JSON格式。"""

        user_prompt = f"请分析以下转录内容并分割为语义段落：\n\n{transcript[:2500]}"

        try:
            response = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=1000,
                temperature=0.3,
            )

            # 解析JSON响应
            segments = json.loads(response.strip())

            if not isinstance(segments, list):
                segments = []

            logger.info(f"📝 提取了 {len(segments)} 个语义段落")
            return segments

        except json.JSONDecodeError:
            logger.warning("⚠️ 语义段落提取返回无效JSON，使用简单分割")
            return self._simple_segment_extraction(transcript)
        except Exception as e:
            logger.error(f"语义段落提取失败: {e}")
            return self._simple_segment_extraction(transcript)

    def _simple_segment_extraction(self, transcript: str) -> List[Dict[str, Any]]:
        """简单的段落分割（备选方案）"""
        # 按句号和换行符分割
        sentences = [
            s.strip() for s in transcript.replace("\n", "。").split("。") if s.strip()
        ]

        # 合并短句，创建段落
        segments = []
        current_segment = ""
        segment_id = 1

        for sentence in sentences:
            if len(current_segment) + len(sentence) < 150:
                current_segment += sentence + "。"
            else:
                if current_segment:
                    segments.append(
                        {
                            "segment_id": f"seg_{segment_id}",
                            "content": current_segment.strip(),
                            "main_topic": sentence[:20] + "...",
                            "visual_keywords": [],
                            "importance": "medium",
                        }
                    )
                    segment_id += 1
                current_segment = sentence + "。"

        # 添加最后一个段落
        if current_segment:
            segments.append(
                {
                    "segment_id": f"seg_{segment_id}",
                    "content": current_segment.strip(),
                    "main_topic": current_segment[:20] + "...",
                    "visual_keywords": [],
                    "importance": "medium",
                }
            )

        return segments

    async def _generate_frame_descriptions(
        self, frames: List[Tuple[str, float]], content_domain: str
    ) -> List[Dict[str, Any]]:
        """为帧生成语义描述（模拟，实际项目中可能需要图像识别API）"""

        frame_descriptions = []

        for filename, timestamp in frames:
            # 基于时间戳和文件名生成模拟描述
            # 实际项目中应该使用图像识别API（如OpenAI Vision、Google Vision等）
            # timestamp 非 number
            description = await self._simulate_frame_description(
                filename, timestamp, content_domain
            )

            frame_descriptions.append(
                {
                    "filename": filename,
                    "timestamp": timestamp,
                    "description": description,
                    "visual_elements": description.get("visual_elements", []),
                    "scene_type": description.get("scene_type", "unknown"),
                }
            )

        return frame_descriptions

    async def _simulate_frame_description(
        self, filename: str, timestamp: float, content_domain: str
    ) -> Dict[str, Any]:
        """模拟帧描述生成（实际项目中应该使用图像识别）"""

        # 处理 timestamp 可能是 datetime.timedelta 类型的情况
        if hasattr(timestamp, 'total_seconds'):
            timestamp = timestamp.total_seconds()
        
        # 基于时间戳模拟不同类型的场景
        minute = int(timestamp // 60)
        second = int(timestamp % 60)

        # 根据领域生成不同类型的场景描述
        domain_scenes = {
            "cooking": [
                {
                    "scene_type": "ingredient_prep",
                    "visual_elements": ["食材", "切菜", "准备"],
                    "description": "食材准备场景",
                },
                {
                    "scene_type": "cooking_process",
                    "visual_elements": ["炒锅", "烹饪", "火候"],
                    "description": "烹饪过程场景",
                },
                {
                    "scene_type": "final_dish",
                    "visual_elements": ["成品", "装盘", "美食"],
                    "description": "成品展示场景",
                },
            ],
            "education": [
                {
                    "scene_type": "explanation",
                    "visual_elements": ["讲解", "图表", "演示"],
                    "description": "概念讲解场景",
                },
                {
                    "scene_type": "demonstration",
                    "visual_elements": ["操作", "步骤", "实践"],
                    "description": "操作演示场景",
                },
                {
                    "scene_type": "summary",
                    "visual_elements": ["总结", "要点", "结论"],
                    "description": "总结归纳场景",
                },
            ],
            "travel": [
                {
                    "scene_type": "landscape",
                    "visual_elements": ["风景", "景点", "自然"],
                    "description": "风景展示场景",
                },
                {
                    "scene_type": "activity",
                    "visual_elements": ["活动", "体验", "互动"],
                    "description": "活动体验场景",
                },
                {
                    "scene_type": "culture",
                    "visual_elements": ["文化", "建筑", "历史"],
                    "description": "文化介绍场景",
                },
            ],
        }

        scenes = domain_scenes.get(content_domain, domain_scenes["education"])
        scene_index = (minute + second) % len(scenes)
        selected_scene = scenes[scene_index]

        return {
            "scene_type": selected_scene["scene_type"],
            "visual_elements": selected_scene["visual_elements"],
            "description": f"{selected_scene['description']} (时间: {minute:02d}:{second:02d})",
            "confidence": 0.7,  # 模拟置信度
        }

    async def _perform_semantic_matching(
        self,
        frame_descriptions: List[Dict[str, Any]],
        semantic_segments: List[Dict[str, Any]],
        subtitles: List[Dict[str, Any]] = None,
    ) -> List[FrameMatchResult]:
        """执行语义匹配"""

        matches = []

        for frame_desc in frame_descriptions:
            best_match = None
            best_score = 0.0

            for segment in semantic_segments:
                # 计算语义相似度
                similarity_score = await self._calculate_semantic_similarity(
                    frame_desc, segment, subtitles
                )

                if similarity_score > best_score:
                    best_score = similarity_score
                    best_match = segment

            # 只保留高质量匹配
            if best_match and best_score > 0.3:
                match_result = FrameMatchResult(
                    frame_filename=frame_desc["filename"],
                    frame_timestamp=frame_desc["timestamp"],
                    matched_text_segment=best_match["content"],
                    semantic_score=best_score,
                    match_reason=f"语义相似度: {best_score:.2f}, 主题: {best_match['main_topic']}",
                    confidence=best_score,
                )
                matches.append(match_result)

        return matches

    async def _calculate_semantic_similarity(
        self,
        frame_desc: Dict[str, Any],
        text_segment: Dict[str, Any],
        subtitles: List[Dict[str, Any]] = None,
    ) -> float:
        """计算帧描述与文本段落的语义相似度"""

        # 简化的相似度计算（实际项目中可以使用更复杂的NLP模型）
        frame_keywords = set(frame_desc.get("visual_elements", []))
        text_keywords = set(text_segment.get("visual_keywords", []))

        # 关键词重叠度
        keyword_overlap = len(frame_keywords & text_keywords) / max(
            len(frame_keywords | text_keywords), 1
        )

        # 时间相关性（如果有SRT）
        time_relevance = 0.5  # 默认中等相关性
        if subtitles:
            frame_time = frame_desc["timestamp"]
            # 查找时间最接近的字幕
            closest_subtitle = min(
                subtitles,
                key=lambda s: abs(self._parse_time(s.get("start", 0)) - frame_time),
            )
            if (
                abs(self._parse_time(closest_subtitle.get("start", 0)) - frame_time)
                < 5.0
            ):  # 5秒内
                time_relevance = 0.8

        # 重要性权重
        importance_weight = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(
            text_segment.get("importance", "medium"), 0.7
        )

        # 综合相似度计算
        similarity = (
            keyword_overlap * 0.4 + time_relevance * 0.3 + importance_weight * 0.3
        )

        return min(similarity, 1.0)

    def _parse_time(self, time_value) -> float:
        """解析时间值为秒数"""
        if isinstance(time_value, (int, float)):
            return float(time_value)
        elif hasattr(time_value, "total_seconds"):
            return time_value.total_seconds()
        else:
            return 0.0

    def _optimize_matches(
        self, matches: List[FrameMatchResult]
    ) -> List[FrameMatchResult]:
        """优化匹配结果"""

        # 按语义分数排序
        sorted_matches = sorted(matches, key=lambda m: m.semantic_score, reverse=True)

        # 去重：避免多个帧匹配到相同的文本段落
        unique_matches = []
        used_segments = set()

        for match in sorted_matches:
            segment_key = match.matched_text_segment[:50]  # 使用前50个字符作为唯一标识
            if segment_key not in used_segments:
                unique_matches.append(match)
                used_segments.add(segment_key)

        # 限制数量，保留最佳匹配
        return unique_matches[:10]

    def generate_matching_strategy_prompt(
        self, matches: List[FrameMatchResult], keyframes_path: str
    ) -> str:
        """基于语义匹配结果生成图像策略提示词"""

        if not matches:
            return "## 📌 无图像匹配\n暂无可用的图像帧匹配结果。"

        strategy_prompt = f"""## 📌 语义智能匹配策略
- 🧠 **智能匹配**: 基于语义相似度进行帧内容匹配
- 📊 **匹配统计**: 共 {len(matches)} 个高质量语义匹配
- **匹配精度**: 平均语义分数 {sum(m.semantic_score for m in matches) / len(matches):.2f}
- 📁 **图片路径**: ![图片名](file://{keyframes_path}/图片名)

### 语义匹配映射：
"""

        for i, match in enumerate(matches, 1):
            minutes, seconds = divmod(int(match.frame_timestamp), 60)
            content_preview = (
                match.matched_text_segment[:60] + "..."
                if len(match.matched_text_segment) > 60
                else match.matched_text_segment
            )

            strategy_prompt += f"""• **{match.frame_filename}** ({minutes:02d}:{seconds:02d})
  - 匹配内容: "{content_preview}"
  - 语义分数: {match.semantic_score:.2f}
  - 匹配原因: {match.match_reason}
"""

        strategy_prompt += """
### 📋 智能使用规则：
1. **语义优先**: 根据内容语义选择最匹配的帧
2. **精准对应**: 图片与文字在语义上高度相关
3. **质量保证**: 只使用高置信度的匹配结果
4. **强制图文混排**: 图片必须插入到对应的内容段落中

**⚠️ 严禁使用未列出的图片文件名！**
"""

        return strategy_prompt


# 便捷函数
async def semantic_match_frames(
    ai_client,
    frames: List[Tuple[str, float]],
    transcript: str,
    subtitles: List[Dict[str, Any]] = None,
    content_domain: str = "general",
) -> List[FrameMatchResult]:
    """语义匹配帧的便捷函数"""
    matcher = SemanticFrameMatcher(ai_client)
    return await matcher.match_frames_to_content(
        frames, transcript, subtitles, content_domain
    )
