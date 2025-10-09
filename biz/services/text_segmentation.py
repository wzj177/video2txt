#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能文本分段处理服务
支持基础分段和AI增强分段
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import sys

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ai.ai_chat_client import create_ai_client

logger = logging.getLogger(__name__)


@dataclass
class TextSegment:
    """文本段落数据结构"""

    text: str
    start_index: int
    end_index: int
    segment_type: str = "paragraph"  # paragraph, sentence, topic
    confidence: float = 1.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TextSegmentationService:
    """文本分段处理服务"""

    def __init__(self, settings: Dict[str, Any] = None):
        self.settings = settings or {}
        self.ai_client = None

        # 尝试初始化AI客户端（用于智能分段）
        try:
            if self.settings:
                self.ai_client = create_ai_client("openai", self.settings)
        except Exception as e:
            logger.warning(f"AI客户端初始化失败，将使用基础分段: {e}")

    def segment_text(self, text: str, method: str = "auto") -> List[TextSegment]:
        """
        智能文本分段

        Args:
            text: 要分段的文本
            method: 分段方法 ("auto", "basic", "ai", "hybrid")

        Returns:
            分段结果列表
        """
        if not text or not text.strip():
            return []

        # 根据方法选择分段策略
        if method == "basic":
            return self._basic_segmentation(text)
        elif method == "ai" and self.ai_client:
            # AI分段需要异步处理，这里先回退到基础分段
            return self._basic_segmentation(text)
        elif method == "hybrid" and self.ai_client:
            # 混合分段需要异步处理，这里先回退到高级基础分段
            return self._advanced_basic_segmentation(text)
        else:
            # auto模式：根据文本长度和AI可用性自动选择
            return self._auto_segmentation(text)

    def _auto_segmentation(self, text: str) -> List[TextSegment]:
        """自动选择最佳分段方法"""
        text_length = len(text)

        # 短文本直接使用基础分段
        if text_length < 500:
            return self._basic_segmentation(text)

        # 中等长度文本，如果有AI则使用混合模式
        if text_length < 2000 and self.ai_client:
            # 暂时回退到高级基础分段，避免异步问题
            return self._advanced_basic_segmentation(text)

        # 长文本，优先使用AI分段，否则使用高级基础分段
        if self.ai_client:
            # 暂时回退到高级基础分段，避免异步问题
            return self._advanced_basic_segmentation(text)
        else:
            return self._advanced_basic_segmentation(text)

    def _basic_segmentation(self, text: str) -> List[TextSegment]:
        """基础分段：按换行符和长度分段"""
        segments = []
        current_start = 0

        # 按换行符分割
        lines = text.split("\n")
        current_segment = ""

        for line in lines:
            line = line.strip()
            if not line:
                # 空行，结束当前段落
                if current_segment.strip():
                    segments.append(
                        TextSegment(
                            text=current_segment.strip(),
                            start_index=current_start,
                            end_index=current_start + len(current_segment),
                            segment_type="paragraph",
                        )
                    )
                    current_start += len(current_segment) + 1
                    current_segment = ""
                continue

            # 添加到当前段落
            if current_segment:
                current_segment += "\n" + line
            else:
                current_segment = line

            # 如果段落太长，尝试分段
            if len(current_segment) > 800:
                split_segments = self._split_long_paragraph(
                    current_segment, current_start
                )
                segments.extend(split_segments)
                current_start += len(current_segment) + 1
                current_segment = ""

        # 添加最后一个段落
        if current_segment.strip():
            segments.append(
                TextSegment(
                    text=current_segment.strip(),
                    start_index=current_start,
                    end_index=current_start + len(current_segment),
                    segment_type="paragraph",
                )
            )

        return segments

    def _advanced_basic_segmentation(self, text: str) -> List[TextSegment]:
        """高级基础分段：结合语义和结构"""
        segments = []

        # 首先按明显的段落标志分段
        paragraph_patterns = [
            r"\n\s*\n",  # 双换行
            r"\n\s*[0-9]+\.",  # 编号段落
            r"\n\s*[一二三四五六七八九十]+[、.]",  # 中文编号
            r"\n\s*[（(][0-9]+[）)]",  # 括号编号
        ]

        # 合并所有模式
        combined_pattern = "|".join(paragraph_patterns)
        parts = re.split(f"({combined_pattern})", text)

        current_start = 0
        current_segment = ""

        for part in parts:
            if not part.strip():
                continue

            # 如果是分隔符，结束当前段落
            if re.match(combined_pattern, part):
                if current_segment.strip():
                    segments.append(
                        TextSegment(
                            text=current_segment.strip(),
                            start_index=current_start,
                            end_index=current_start + len(current_segment),
                            segment_type="paragraph",
                        )
                    )
                    current_start += len(current_segment)
                    current_segment = ""
                continue

            current_segment += part

            # 检查是否需要进一步分割
            if len(current_segment) > 600:
                split_segments = self._split_by_sentences(
                    current_segment, current_start
                )
                segments.extend(split_segments)
                current_start += len(current_segment)
                current_segment = ""

        # 添加最后一个段落
        if current_segment.strip():
            segments.append(
                TextSegment(
                    text=current_segment.strip(),
                    start_index=current_start,
                    end_index=current_start + len(current_segment),
                    segment_type="paragraph",
                )
            )

        return segments

    def _split_long_paragraph(self, text: str, start_index: int) -> List[TextSegment]:
        """分割过长的段落"""
        segments = []

        # 尝试按句号分割
        sentences = re.split(r"[。！？.!?]", text)
        current_segment = ""
        current_start = start_index

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 添加标点符号
            if current_segment:
                test_segment = current_segment + "。" + sentence
            else:
                test_segment = sentence

            # 如果加上这个句子会太长，先保存当前段落
            if len(test_segment) > 400 and current_segment:
                segments.append(
                    TextSegment(
                        text=current_segment + "。",
                        start_index=current_start,
                        end_index=current_start + len(current_segment) + 1,
                        segment_type="paragraph",
                    )
                )
                current_start += len(current_segment) + 1
                current_segment = sentence
            else:
                current_segment = test_segment

        # 添加最后一个段落
        if current_segment:
            segments.append(
                TextSegment(
                    text=current_segment,
                    start_index=current_start,
                    end_index=current_start + len(current_segment),
                    segment_type="paragraph",
                )
            )

        return segments

    def _split_by_sentences(self, text: str, start_index: int) -> List[TextSegment]:
        """按句子分割文本"""
        segments = []

        # 中英文句子分割模式
        sentence_pattern = r"[。！？.!?]+\s*"
        sentences = re.split(sentence_pattern, text)

        current_start = start_index
        current_segment = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 尝试添加到当前段落
            if current_segment:
                test_segment = current_segment + "。" + sentence
            else:
                test_segment = sentence

            # 如果段落合适长度，继续添加
            if len(test_segment) <= 300:
                current_segment = test_segment
            else:
                # 保存当前段落，开始新段落
                if current_segment:
                    segments.append(
                        TextSegment(
                            text=current_segment + "。",
                            start_index=current_start,
                            end_index=current_start + len(current_segment) + 1,
                            segment_type="sentence_group",
                        )
                    )
                    current_start += len(current_segment) + 1

                current_segment = sentence

        # 添加最后一个段落
        if current_segment:
            segments.append(
                TextSegment(
                    text=current_segment,
                    start_index=current_start,
                    end_index=current_start + len(current_segment),
                    segment_type="sentence_group",
                )
            )

        return segments

    async def _ai_segmentation(self, text: str) -> List[TextSegment]:
        """AI智能分段"""
        try:
            prompt = f"""请对以下转录文本进行智能分段，按照语义和逻辑结构划分段落。

要求：
1. 每个段落应该有完整的语义
2. 段落长度适中（100-500字符）
3. 保持原文内容不变
4. 按主题或逻辑分组

请返回JSON格式：
{{
    "segments": [
        {{"text": "段落1内容", "type": "paragraph", "topic": "主题描述"}},
        {{"text": "段落2内容", "type": "paragraph", "topic": "主题描述"}}
    ]
}}

原文：
{text}"""

            response = await self.ai_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.3,
            )

            # 解析AI响应
            import json

            result = json.loads(response)
            segments = []
            current_start = 0

            for seg_data in result.get("segments", []):
                segment_text = seg_data.get("text", "").strip()
                if segment_text:
                    segments.append(
                        TextSegment(
                            text=segment_text,
                            start_index=current_start,
                            end_index=current_start + len(segment_text),
                            segment_type=seg_data.get("type", "paragraph"),
                            confidence=0.9,
                            metadata={"topic": seg_data.get("topic", "")},
                        )
                    )
                    current_start += len(segment_text) + 1

            return segments

        except Exception as e:
            logger.error(f"AI分段失败: {e}")
            # 回退到基础分段
            return self._basic_segmentation(text)

    def _hybrid_segmentation(self, text: str) -> List[TextSegment]:
        """混合分段：基础分段 + AI优化"""
        # 首先进行基础分段
        basic_segments = self._advanced_basic_segmentation(text)

        # 如果段落数量合适，直接返回
        if len(basic_segments) <= 8:
            return basic_segments

        # 否则尝试AI优化
        try:
            # 将基础分段结果发送给AI进行优化
            segment_texts = [seg.text for seg in basic_segments]
            optimized_segments = self._ai_optimize_segments(segment_texts)
            return optimized_segments
        except Exception as e:
            logger.error(f"混合分段AI优化失败: {e}")
            return basic_segments

    async def _ai_optimize_segments(self, segments: List[str]) -> List[TextSegment]:
        """AI优化分段结果"""
        try:
            segments_text = "\n\n".join(
                [f"段落{i+1}: {seg}" for i, seg in enumerate(segments)]
            )

            prompt = f"""以下是初步分段的文本，请优化分段结果：

要求：
1. 合并语义相关的短段落
2. 分割过长的段落
3. 确保每个段落有完整的语义
4. 段落数量控制在3-8个之间

请返回优化后的分段JSON：
{{
    "segments": [
        {{"text": "优化后段落1", "reason": "合并原因或分割原因"}},
        {{"text": "优化后段落2", "reason": "合并原因或分割原因"}}
    ]
}}

原始分段：
{segments_text}"""

            response = await self.ai_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.2,
            )

            import json

            result = json.loads(response)
            optimized_segments = []
            current_start = 0

            for seg_data in result.get("segments", []):
                segment_text = seg_data.get("text", "").strip()
                if segment_text:
                    optimized_segments.append(
                        TextSegment(
                            text=segment_text,
                            start_index=current_start,
                            end_index=current_start + len(segment_text),
                            segment_type="ai_optimized",
                            confidence=0.95,
                            metadata={
                                "optimization_reason": seg_data.get("reason", "")
                            },
                        )
                    )
                    current_start += len(segment_text) + 1

            return optimized_segments

        except Exception as e:
            logger.error(f"AI分段优化失败: {e}")
            # 回退到原始分段
            result_segments = []
            current_start = 0
            for text in segments:
                result_segments.append(
                    TextSegment(
                        text=text,
                        start_index=current_start,
                        end_index=current_start + len(text),
                        segment_type="paragraph",
                    )
                )
                current_start += len(text) + 1
            return result_segments


# 全局服务实例
_segmentation_service = None


def get_segmentation_service(
    settings: Dict[str, Any] = None,
) -> TextSegmentationService:
    """获取全局文本分段服务实例"""
    global _segmentation_service
    if _segmentation_service is None:
        _segmentation_service = TextSegmentationService(settings)
    return _segmentation_service


async def segment_transcript(
    text: str, method: str = "auto", settings: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    便捷函数：对转录文本进行分段

    Args:
        text: 转录文本
        method: 分段方法
        settings: AI设置

    Returns:
        分段结果（字典格式）
    """
    service = get_segmentation_service(settings)
    segments = service.segment_text(text, method)

    # 转换为字典格式
    return [
        {
            "text": seg.text,
            "start_index": seg.start_index,
            "end_index": seg.end_index,
            "segment_type": seg.segment_type,
            "confidence": seg.confidence,
            "length": len(seg.text),
            "metadata": seg.metadata or {},
        }
        for seg in segments
    ]
