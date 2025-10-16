#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI内容生成工厂
支持内容卡片、思维导图、闪卡、AI分析等生成
集成智能帧提取功能
"""

import logging
import json
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import datetime
from biz.services.contents import ContentCardGenerator

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入AI客户端和帧提取器
from core.ai.ai_chat_client import create_ai_client
from core.media.frame_extractor import create_frame_extractor

# 导入新的内容分析器
from .ai_content_analyzer import AIContentAnalyzer, analyze_and_generate_prompt

# 导入设置API中的角色映射函数和提示词模板函数
from biz.routes.settings_api import get_role_name, get_prompt_template

logger = logging.getLogger(__name__)


class OutputType(Enum):
    """AI输出类型枚举"""

    CONTENT_CARD = "content_card"
    MIND_MAP = "mind_map"
    FLASHCARDS = "flashcards"
    AI_ANALYSIS = "ai_analysis"


@dataclass
class GenerationConfig:
    """生成配置"""

    output_type: OutputType
    language: str = "zh"
    model: str = "default"
    max_tokens: int = 2000
    temperature: float = 0.7


class AIContentFactory:
    """AI内容生成工厂"""

    def __init__(self, settings: Dict[str, Any], provider: str = "openai"):
        self.settings = settings
        self.provider = provider
        self.ai_client = create_ai_client(provider, settings)
        self.frame_extractor = create_frame_extractor()
        #  移除frame_selector，直接使用frame_extractor的固定间隔提取
        self.output_dir = Path("data/outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.content_card_generator = ContentCardGenerator(
            ai_client=self.ai_client, storage_path=self._get_storage_path()
        )
        #  新增：智能内容分析器
        self.content_analyzer = AIContentAnalyzer(self.ai_client)

    def _get_storage_path(self) -> Path:
        """
        获取存储路径，从配置中读取

        Returns:
            Path: 存储目录的绝对路径
        """
        try:
            # 从settings中获取存储路径
            storage_path = self.settings.get("system", {}).get("storage_path")
            if storage_path:
                return Path(storage_path)
            else:
                # 回退到默认路径
                return Path("data/outputs").resolve()
        except Exception:
            # 异常情况下使用默认路径
            return Path("data/outputs").resolve()

    async def generate(
        self,
        output_type: str,
        transcript: str = "",
        video_path: str = "",
        audio_path: str = "",
        subtitles: List[Dict[str, Any]] = None,
        frame_info: Dict[str, Any] = None,  # 关键修复：接收帧信息
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        生成指定类型的内容 - 集成智能分析

        Args:
            output_type: 输出类型 (content_card, mind_map, flashcards, ai_analysis)
            transcript: 转录文本内容
            video_path: 视频文件路径（可选）
            audio_path: 音频文件路径（可选）
            subtitles: 字幕列表（可选）
            **kwargs: 其他参数

        Returns:
            生成结果
        """
        try:
            # 验证输出类型
            if output_type not in [t.value for t in OutputType]:
                raise ValueError(f"不支持的输出类型: {output_type}")

            #  第一步：智能内容分析
            if stream_callback:
                await stream_callback(
                    "content_analyzing",
                    {"type": output_type, "message": " 正在分析内容特征和领域..."},
                )

            # 进行内容分析和动态提示词生成
            analysis_result, dynamic_prompts = await analyze_and_generate_prompt(
                self.ai_client,
                transcript,
                output_type,
                frame_info=frame_info,
                subtitles=subtitles,
                **kwargs,
            )

            logger.info(
                f" 内容分析完成: {analysis_result.primary_domain.value}领域, 置信度: {analysis_result.confidence:.2f}"
            )

            # 获取配置
            config = GenerationConfig(
                output_type=OutputType(output_type),
                language=kwargs.get("language", "zh"),
                model=kwargs.get("model", "default"),
                max_tokens=kwargs.get("max_tokens", 2000),
                temperature=kwargs.get("temperature", 0.7),
            )

            #  关键修复：使用传入的帧信息，而不是重新处理
            if frame_info is None:
                # 如果没有传入帧信息，则进行处理（向后兼容）
                frame_info = await self._process_frames(
                    video_path, audio_path, subtitles, **kwargs
                )

            #  第二步：使用动态提示词生成内容
            kwargs.update(
                {"analysis_result": analysis_result, "dynamic_prompts": dynamic_prompts}
            )

            # 根据类型生成内容
            if output_type == OutputType.CONTENT_CARD.value:
                return await self._generate_content_card_smart(
                    config, transcript, frame_info, stream_callback, **kwargs
                )
            elif output_type == OutputType.MIND_MAP.value:
                return await self._generate_mind_map_smart(
                    config, transcript, frame_info, stream_callback, **kwargs
                )
            elif output_type == OutputType.FLASHCARDS.value:
                return await self._generate_flashcards_smart(
                    config, transcript, frame_info, stream_callback, **kwargs
                )
            elif output_type == OutputType.AI_ANALYSIS.value:
                return await self._generate_ai_analysis_smart(
                    config, transcript, frame_info, stream_callback, **kwargs
                )
            else:
                raise ValueError(f"未实现的输出类型: {output_type}")

        except Exception as e:
            logger.error(f"生成内容失败: {e}")
            return {"error": str(e), "success": False}

    async def generate_all(
        self,
        transcript: str = "",
        video_path: str = "",
        audio_path: str = "",
        subtitles: List[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        生成所有类型的内容

        Args:
            transcript: 转录文本内容
            video_path: 视频文件路径（可选）
            audio_path: 音频文件路径（可选）
            subtitles: 字幕列表（可选）
            **kwargs: 生成参数

        Returns:
            所有生成结果
        """
        try:
            results = {}

            # 生成所有类型
            for output_type in OutputType:
                result = await self.generate(
                    output_type.value,
                    transcript,
                    video_path,
                    audio_path,
                    subtitles,
                    **kwargs,
                )
                results[output_type.value] = result

            return {"success": True, "results": results, "message": "所有内容生成完成"}

        except Exception as e:
            logger.error(f"批量生成失败: {e}")
            return {"error": str(e), "success": False}

    async def _process_frames(
        self,
        video_path: str,
        audio_path: str,
        subtitles: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """处理帧提取，返回帧信息 - 向后兼容方法"""
        logger.warning(
            "⚠️ 使用了向后兼容的帧处理方法，建议从video_service传递frame_info"
        )

        frame_info = {
            "frames": [],
            "cover_frame": None,
            "frame_dir": "",
            "has_frames": False,
        }

        try:
            if video_path and subtitles:
                # 🎯 使用固定间隔提取（2秒一帧）
                frame_dir = str(
                    Path(video_path).parent / "keyframes"
                )  # 改为keyframes目录
                frames, cover_frame = self.frame_extractor.extract_frames_by_interval(
                    video_path,
                    subtitles,
                    frame_dir,
                    interval=2.0,  # 固定2秒间隔
                    verbose=kwargs.get("verbose", False),
                )

                frame_info.update(
                    {
                        "frames": frames,
                        "cover_frame": cover_frame,
                        "frame_dir": frame_dir,
                        "has_frames": True,
                        "type": "video",
                    }
                )

                logger.info(f"✅ 固定间隔提取了 {len(frames)} 个视频关键帧（2秒间隔）")

            elif audio_path:
                # 音频可视化生成
                frame_dir = str(Path(audio_path).parent / "frames")
                frames, cover_frame = (
                    self.frame_extractor.generate_audio_visualizations(
                        audio_path, frame_dir, verbose=kwargs.get("verbose", False)
                    )
                )

                frame_info.update(
                    {
                        "frames": frames,
                        "cover_frame": cover_frame,
                        "frame_dir": frame_dir,
                        "has_frames": True,
                        "type": "audio",
                    }
                )

                logger.info(f"✅ 生成了 {len(frames)} 个音频可视化图像")

        except Exception as e:
            logger.error(f"帧处理失败: {e}")

        return frame_info

    async def _generate_content_card(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容卡片"""
        return await self.content_card_generator.generate_content_card(
            config=config,
            transcript=transcript,
            frame_info=frame_info,
            stream_callback=stream_callback,
            **kwargs,
        )

    def _match_srt_to_frames(
        self, subtitles: List[Dict[str, Any]], frame_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """核心方法：将SRT时间段与帧进行精确匹配"""
        matches = []

        for i, subtitle in enumerate(subtitles):
            # 解析SRT时间
            start_time = self._parse_time(subtitle.get("start", 0))
            end_time = self._parse_time(subtitle.get("end", start_time + 5))
            content = subtitle.get("text") or subtitle.get("content", "")

            if not content.strip():
                continue

            # 在SRT时间段内找最佳帧
            best_frame = None
            min_distance = float("inf")
            srt_center = (start_time + end_time) / 2

            for frame in frame_list:
                frame_time = frame["timestamp"]

                # 检查帧是否在SRT时间范围内（允许1秒容差）
                if start_time - 1.0 <= frame_time <= end_time + 1.0:
                    distance = abs(frame_time - srt_center)
                    if distance < min_distance:
                        min_distance = distance
                        best_frame = frame

            # 记录匹配结果
            if best_frame:
                match_quality = "精确匹配" if min_distance < 1.0 else "近似匹配"
                matches.append(
                    {
                        "srt_index": i,
                        "start_time": start_time,
                        "end_time": end_time,
                        "content": content.strip(),
                        "frame": best_frame,
                        "match_quality": match_quality,
                    }
                )

        logger.info(f"🎯 SRT匹配完成: {len(matches)} 个精确匹配")
        return matches

    def _parse_time(self, time_value) -> float:
        """解析时间值为秒数"""
        if isinstance(time_value, (int, float)):
            return float(time_value)
        elif hasattr(time_value, "total_seconds"):
            return time_value.total_seconds()
        else:
            return 0.0

    def _build_srt_matching_strategy(
        self,
        matches: List[Dict[str, Any]],
        frame_list: List[Dict[str, Any]],
        cover_frame: str,
        keyframes_path,
    ) -> str:
        """构建SRT匹配策略的提示词"""
        frame_names = [f["filename"] for f in frame_list]
        frames_list = ", ".join(frame_names)

        # 生成匹配映射信息
        mapping_info = "\n### 🎯 SRT内容与关键帧精确匹配：\n"
        for match in matches:
            start_min, start_sec = divmod(int(match["start_time"]), 60)
            end_min, end_sec = divmod(int(match["end_time"]), 60)
            content_preview = (
                match["content"][:40] + "..."
                if len(match["content"]) > 40
                else match["content"]
            )
            mapping_info += f'• {start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d} "{content_preview}" → **{match["frame"]["filename"]}** ({match["match_quality"]})\n'

        # 找出未匹配的帧
        matched_filenames = {match["frame"]["filename"] for match in matches}
        unmatched_frames = [
            f for f in frame_list if f["filename"] not in matched_filenames
        ]

        if unmatched_frames:
            mapping_info += "\n**未匹配帧（可用于过渡内容）**：\n"
            for frame in unmatched_frames:
                minutes, seconds = divmod(int(frame["timestamp"]), 60)
                mapping_info += f'• {minutes:02d}:{seconds:02d} → **{frame["filename"]}** (过渡帧)\n'

        return f"""
## 📌 SRT时间段精确匹配策略
- 🎯 **智能匹配**: 每个SRT时间段都已匹配到最佳帧
- 📊 **匹配统计**: {len(matches)} 个精确匹配，{len(unmatched_frames)} 个过渡帧
- 🖼️ **可用图片**: {frames_list}
- 🏠 **封面帧**: {cover_frame or "自动选择"}
- 📁 **图片路径**: ![图片名]({keyframes_path}/图片名)

{mapping_info}

### 📋 使用规则：
1. **优先使用精确匹配帧**：描述特定内容时，使用对应的匹配帧
2. **语义对应原则**：图片与文字内容必须在时间和语义上对应
3. **过渡帧补充**：章节过渡、总结等使用未匹配帧
4. **强制图文混排**：图片必须插入到相关段落中，不能集中在文末

**⚠️ 严禁使用未列出的图片文件名！**
"""

    def _build_simple_frame_strategy(
        self, frame_list: List[Dict[str, Any]], cover_frame: str, keyframes_path
    ) -> str:
        """构建简单帧策略（无SRT时）"""
        frame_names = [f["filename"] for f in frame_list]
        frames_list = ", ".join(frame_names)

        time_mapping = "\n### 🎯 时间轴帧映射：\n"
        for frame in frame_list:
            minutes, seconds = divmod(int(frame["timestamp"]), 60)
            time_mapping += f'• {minutes:02d}:{seconds:02d} → **{frame["filename"]}**\n'

        return f"""
## 📌 固定间隔帧提取策略
- 🎯 **2秒间隔**: 每2秒提取一帧，从第2秒开始
- 📊 **帧数量**: 共 {len(frame_list)} 帧
- 🖼️ **可用图片**: {frames_list}
- 🏠 **封面帧**: {cover_frame or "自动选择"}

{time_mapping}

### 📋 使用规则：
1. **时间对应**：根据内容时间点选择最接近的帧
2. **均匀分布**：合理分配图片，确保视觉连贯
3. **图文混排**：图片插入到相关段落中

**⚠️ 严禁使用未列出的图片文件名！**
"""

    def _build_system_prompt(self, image_strategy: str, keyframes_path) -> str:
        """构建系统提示词"""
        return f"""# 角色设定
你是一位资深的教育内容专家，擅长将教学视频转化为结构化、高价值的知识卡片。

# 核心任务
基于转录内容和精确的SRT-帧匹配关系，生成图文并茂的内容卡片。

{image_strategy}

## 内容质量要求
1. **结构完整性**：包含标题、摘要、分章节、总结、思考等完整结构
2. **内容深度挖掘**：将转录内容展开为详细段落，不仅仅是简单整理
3. **图文精确匹配**：严格按照SRT-帧匹配关系使用图片
4. **知识完整性**：覆盖转录中的所有知识点，不遗漏
5. **视觉丰富性**：充分利用帧资源增强表达效果

## 文体规范
- **开篇**：用「标题」概括视频核心价值
- **摘要**：用「摘要」概括视频核心内容
- **章节**：用「章节名」组织主要内容
- **总结**：用「总结」总结中心思想
- **思考**：用「思考」提出思考问题

**重要要求：必须使用简体中文输出，图片使用绝对路径格式。**

请直接输出完整内容，不要解释说明。"""

    def _build_user_prompt(
        self, transcript: str, matches, frame_list: List[Dict[str, Any]], keyframes_path
    ) -> str:
        """构建用户提示词"""
        frame_names = [f["filename"] for f in frame_list]
        frames_list = ", ".join(frame_names)

        matching_guide = ""
        if matches:
            matching_guide = "\n\n## 🎯 精确匹配指南：\n"
            matching_guide += (
                "**重要**：每段内容都已精确匹配到最佳帧，请严格按照匹配关系使用！\n"
            )
            matching_guide += f"**可用图片**: {frames_list}\n"
        else:
            matching_guide = f"\n\n## 🎯 图片使用指南：\n**可用图片**: {frames_list}\n"

        return f"""请为以下转录内容生成图文并茂的内容卡片：

## 📝 转录内容：
{transcript[:3000] if transcript else '暂无转录内容'}{matching_guide}

**🚨 严格要求**：
1. **只能使用列出的图片文件**：{frames_list}
2. **强制图文混排**：图片必须插入到相关内容段落中
3. **图片格式**：![图片名](file://{keyframes_path}/图片名)
4. **精确匹配**：严格按照SRT-帧匹配关系使用图片
5. **绝对禁止**：将所有图片集中在文章最后"""

    async def _generate_text_only_content(
        self, config: GenerationConfig, transcript: str, stream_callback
    ) -> Dict[str, Any]:
        """生成纯文本内容（无帧时的回退方案）"""
        system_prompt = """你是一位资深的教育内容专家。请基于转录内容生成结构化的知识卡片，包含标题、摘要、章节、总结、思考等完整结构。使用简体中文输出。"""

        user_prompt = f"请为以下转录内容生成结构化知识卡片：\n\n{transcript[:3000] if transcript else '暂无转录内容'}"

        if stream_callback:
            await stream_callback(
                "ai_generating",
                {"type": "content_card", "message": "📝 正在生成纯文本内容..."},
            )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            await stream_callback(
                "ai_content_complete",
                {"type": "content_card", "message": "✅ 内容生成完成"},
            )

            return {
                "success": True,
                "type": "content_card",
                "content": content,
                "format": "text",
            }

    async def _generate_mind_map(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成思维导图"""
        try:
            system_prompt = """你是一个擅长信息结构化和知识整理的专家。
我将提供一个视频或音频的转录文本内容，请你：

分析整体内容的主题和逻辑结构（如：讲解类、叙事类、论证类等）
提炼出一个清晰的思维导图大纲，格式为层级结构（可用 Markdown 的标题或列表表示）
主干不超过 4~6 个核心模块，每个模块下分 2~4 个子点，总节点控制在 15 个以内
每个节点用简洁短语概括，避免完整句子
优先提取：核心观点、关键概念、步骤流程、案例证据、结论建议
忽略口语化表达、重复语句、寒暄和无信息量内容

**重要要求：无论输入语言是什么（中文、方言、英文等），你必须严格使用简体中文输出，绝对不能使用繁体字。即使是专有名词、术语也要转换为简体中文。**

# 思维导图：[视频主题]

- [主节点1]
  - [子节点1.1]
  - [子节点1.2]
- [主节点2]
  - [子节点2.1]
  - [子节点2.2]
  ...

请直接输出思维导图，不要解释说明。"""

            user_prompt = f"请为以下转录内容生成思维导图：\n\n{transcript[:3000] if transcript else '暂无转录内容'}"

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {"type": "mind_map", "message": "🧠 正在生成思维导图..."},
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            # 流式内容推送
            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "mind_map", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "mind_map", "message": "✅ 思维导图生成完成"},
                )

            return {
                "success": True,
                "type": "mind_map",
                "content": content,
                "format": "text",
                "frame_info": frame_info,
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _generate_flashcards(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成闪卡"""
        try:
            # 构建上下文信息
            context_info = ""
            frames = frame_info.get("frames", [])
            if frames:
                context_info = f"""

## 📌 内容背景信息
- 基于视频内容生成的学习闪卡
- 包含 {len(frames)} 个关键时间点的内容
- 注重实用性和记忆效果

### 闪卡设计原则
1. **问题设计**：基于视频关键知识点，设计具有挑战性的问题
2. **答案完整**：不仅给出答案，还要包含理解要点和记忆技巧
3. **实用导向**：结合实际应用场景，让学习更有意义
4. **层次分明**：从基础概念到高级应用，循序渐进
"""

            system_prompt = f"""你是一位资深的教育内容专家和学习闪卡制作大师，擅长将教学视频转化为高质量的学习闪卡。

# 核心任务
基于转录内容生成结构化、高价值的学习闪卡，确保学习效果最佳。

{context_info}

## 内容质量要求
1. **问题精准性**：每个问题都要精准指向核心知识点
2. **答案完整性**：答案要详细、准确，包含关键信息和理解要点
3. **实用价值**：结合实际应用，让知识点更容易理解和记忆
4. **难度梯度**：从基础到进阶，形成完整的学习体系

## 闪卡格式规范
每张闪卡包含：
- **Q**: 问题要简洁明确，具有挑战性
- **A**: 答案要详细易懂，包含：
  - 直接答案
  - 关键理解要点
  - 实际应用提示（如适用）
  - 记忆技巧（如适用）

## 闪卡类型分布
1. **概念理解类**（30%）：核心概念和定义
2. **步骤流程类**（40%）：操作步骤和方法
3. **应用实践类**（20%）：实际应用和案例
4. **注意事项类**（10%）：重要提醒和易错点

**重要要求：无论输入语言是什么（中文、方言、英文等），你必须严格使用简体中文输出，绝对不能使用繁体字。即使是专有名词、术语也要转换为简体中文。**

## 输出要求
- 生成8-12张高质量闪卡
- 每张闪卡之间用"---"分隔
- 确保问题有挑战性，答案有价值
- 注重实用性和学习效果

请直接输出完整闪卡内容，不要解释说明。"""

            user_prompt = f"请为以下转录内容生成高质量的学习闪卡：\n\n{transcript[:3000] if transcript else '暂无转录内容'}"

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {"type": "flashcards", "message": "📚 正在生成学习闪卡..."},
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            # 流式内容推送
            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "flashcards", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "flashcards", "message": "✅ 学习闪卡生成完成"},
                )

            return {
                "success": True,
                "type": "flashcards",
                "content": content,
                "format": "text",
                "frame_info": frame_info,
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _generate_ai_analysis(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成AI分析"""
        try:
            system_prompt = """你是一个专业的AI分析专家。请对提供的转录文本进行深度分析。
分析内容应该包括：
1. 内容主题识别
2. 关键信息提取
3. 内容质量评估
4. 潜在应用场景
5. 改进建议

**重要要求：无论输入语言是什么（中文、方言、英文等），你必须严格使用简体中文输出，绝对不能使用繁体字。即使是专有名词、术语也要转换为简体中文。**

请用JSON格式输出，包含以下字段：
{
    "theme": "主题",
    "key_points": ["关键点1", "关键点2"],
    "quality_score": 8.5,
    "applications": ["应用场景1", "应用场景2"],
    "suggestions": ["建议1", "建议2"]
}"""

            user_prompt = f"请对以下转录内容进行AI分析：\n\n{transcript[:2000] if transcript else '暂无转录内容'}"

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {"type": "ai_analysis", "message": "🤖 正在进行AI智能分析..."},
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            # 流式内容推送
            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "ai_analysis", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "ai_analysis", "message": "✅ AI分析完成"},
                )

            return {
                "success": True,
                "type": "ai_analysis",
                "content": content,
                "format": "json",
                "frame_info": frame_info,
            }
        except Exception as e:
            return {"error": str(e), "success": False}

    # 🧠 新增：智能生成方法（使用动态提示词）
    async def _generate_content_card_smart(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """智能生成内容卡片 - 使用动态提示词"""
        try:
            analysis_result = kwargs.get("analysis_result")
            dynamic_prompts = kwargs.get("dynamic_prompts")

            # 使用动态提示词
            system_prompt = dynamic_prompts["system_prompt"]
            user_prompt_template = dynamic_prompts["user_prompt_template"]

            # 构建用户提示词
            user_prompt = user_prompt_template.format(
                domain=analysis_result.primary_domain.value,
                content_type="内容卡片",
                transcript=transcript[:3000],
                target_audience=analysis_result.target_audience,
                content_style=analysis_result.content_style,
            )

            # 添加图像策略（如果有帧信息）
            if frame_info.get("has_frames", False):
                frames = frame_info.get("frames", [])
                subtitles = kwargs.get("subtitles", [])
                task_id = kwargs.get("task_id", "")

                # 使用内容卡片生成器的智能匹配功能
                return await self.content_card_generator.generate_content_card(
                    config=config,
                    transcript=transcript,
                    frame_info=frame_info,
                    stream_callback=stream_callback,
                    custom_system_prompt=system_prompt,  # 传递自定义系统提示词
                    **kwargs,
                )
            else:
                # 纯文本生成
                if stream_callback:
                    await stream_callback(
                        "ai_generating",
                        {
                            "type": "content_card",
                            "message": f"🎨 正在生成{analysis_result.primary_domain.value}领域内容卡片...",
                        },
                    )

                content = await self.ai_client.generate_content(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                )

                if stream_callback:
                    await stream_callback(
                        "ai_content_chunk", {"type": "content_card", "content": content}
                    )
                    await stream_callback(
                        "ai_content_complete",
                        {"type": "content_card", "message": "✅ 智能内容卡片生成完成"},
                    )

                return {
                    "success": True,
                    "type": "content_card",
                    "content": content,
                    "format": "text",
                    "analysis_result": analysis_result.__dict__,
                }
        except Exception as e:
            logger.error(f"智能内容卡片生成失败: {e}")
            return {"error": str(e), "success": False}

    async def _generate_mind_map_smart(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """智能生成思维导图 - 基于优化版本的完整实现"""
        try:
            analysis_result = kwargs.get("analysis_result")
            subtitles = kwargs.get("subtitles", [])

            # 🎯 角色定义（从配置文件读取）
            role_name = get_role_name(
                analysis_result.primary_domain.value, 
                "content_generator", 
                "内容结构化专家"
            )

            # 检测是否为长视频
            text_length = len(transcript)
            is_long_video = text_length > 10000

            # 构建带时间戳的文本
            timed_text = ""
            if subtitles:
                for sub in subtitles:
                    timed_text += f"[{sub.start}] {sub.content.strip()}\n"
            else:
                # 如果没有字幕，使用原始转录文本
                timed_text = transcript

            # 内容主题上下文
            theme_context = f"""
## 🎯 内容主题上下文
- 主要领域：{analysis_result.primary_domain.value}
- 内容风格：{analysis_result.content_style}
- 目标受众：{analysis_result.target_audience}
- 关键话题：{', '.join(analysis_result.key_topics[:5])}

请基于以上内容特征优化思维导图结构，确保体现该类型内容的特点。
"""

            # STEP 1: 提取结构化大纲
            step1_prompt = f"""# 角色
你是一位专业的{role_name}，擅长将{analysis_result.primary_domain.value}领域内容转化为清晰的思维导图结构。

{theme_context}

# 任务
请根据以下带时间戳的视频字幕，创建一个结构清晰、层次分明的思维导图大纲。

# 特殊要求（针对长视频）
{"- 这是一个较长的教学视频，包含丰富的知识点" if is_long_video else ""}
{"- 需要构建完整的知识体系结构，不能省略重要章节" if is_long_video else ""}
{"- 按照教学逻辑组织内容，体现知识的递进关系" if is_long_video else ""}

# 输入格式说明
- 每行格式为：[HH:MM:SS] 文本内容
- 时间戳表示该内容在视频中出现的时间点

# 输出要求
1. 使用Markdown无序列表格式（- 和空格缩进表示层级）
2. 每个节点应是简洁的关键词或短语（不超过10个字）
3. 在重要节点末尾添加时间戳，格式为 `MM:SS`（例如 `01:23`）
4. 保持逻辑层次：主题 → 章节 → 要点 → 细节（最多4级）
5. 合并相似内容，但保留重要的知识点
6. 优先保留教学重点和关键转折

# 输出格式示例
# 视频主题
- 基础概念
  - 定义解释 `01:23`
  - 重要特征 `02:45`
    - 特征一 `03:10`
    - 特征二 `03:30`
- 实践应用
  - 方法一 `05:20`
    - 步骤详解 `06:15`
  - 方法二 `08:30`

# 重要提示
- 保持输出为纯文本列表
- 时间戳必须准确对应原文内容
- 重点突出教学价值高的内容
- 体现完整的知识结构

# 视频字幕内容
{timed_text[:25000]}"""

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {"type": "mind_map", "message": f"🧠 正在生成{analysis_result.primary_domain.value}领域思维导图..."},
                )

            outline = await self.ai_client.generate_content(
                prompt=step1_prompt,
                system_prompt="你是一位专业的知识架构师，严格按照要求生成结构化思维导图。",
                max_tokens=4096,
                temperature=config.temperature,
            )

            if not outline.strip():
                raise Exception("第一步大纲生成失败")

            # STEP 2: 格式优化（确保Markmap兼容）
            step2_prompt = f"""# 任务
你是一位Markdown格式专家，负责将以下思维导图大纲优化为标准Markmap兼容格式。

# 输入
一个初步的思维导图结构，可能包含不规范的格式。

# 输出要求
1. 严格使用Markdown无序列表
2. 每级缩进使用2个空格
3. 时间戳统一为 `MM:SS` 格式（例如 `01:23`）
4. 每行一个节点，不跨行
5. 节点文本简洁，不超过15个字
6. 保留完整的知识结构层次
7. 确保语法正确，便于Markmap渲染

# 错误格式修正
- 将 "00:01:23" 转换为 "01:23"
- 将 "章节一 [00:01:23]" 转换为 "章节一 `01:23`"
- 修复不正确的缩进层级
- 移除多余的标点符号

# 输出示例
# 教学内容主题
- 理论基础
  - 核心概念 `01:20`
  - 基本原理 `02:45`
    - 原理解释 `03:10`
    - 应用场景 `04:30`
- 实战操作
  - 方法介绍 `06:30`
    - 步骤一 `07:15`
    - 步骤二 `08:45`
  - 注意事项 `10:20`

# 待优化内容
{outline}"""

            final_mind_map = await self.ai_client.generate_content(
                prompt=step2_prompt,
                system_prompt="你是一位Markdown格式专家，严格按照格式要求输出。",
                max_tokens=4096,
                temperature=0.3,  # 降低温度确保格式准确
            )

            # 流式内容推送
            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "mind_map", "content": final_mind_map}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "mind_map", "message": "✅ 思维导图生成完成"},
                )

            return {
                "success": True,
                "type": "mind_map",
                "content": final_mind_map,
                "format": "text",
                "frame_info": frame_info,
                "analysis_result": analysis_result.__dict__,
            }
        except Exception as e:
            logger.error(f"智能思维导图生成失败: {e}")
            return {"error": str(e), "success": False}

    def export_xmind_format(self, markdown_content: str, output_path: str) -> bool:
        """将Markdown思维导图转换为XMind兼容的FreeMind格式"""
        try:
            import xml.etree.ElementTree as ET
            import re

            # 解析Markdown格式的思维导图
            lines = markdown_content.strip().split("\n")

            # 创建根节点
            root = ET.Element("map")
            root.set("version", "1.0.1")

            # 找到主题行
            main_title = "思维导图"
            for line in lines:
                if line.startswith("# "):
                    main_title = line[2:].strip()
                    break

            # 创建中心节点
            node_map = ET.SubElement(root, "node")
            node_map.set("ID", "root")
            node_map.set("TEXT", main_title)

            # 解析层级结构
            current_parents = [node_map]  # 当前父节点栈
            node_id = 1

            for line in lines:
                line = line.rstrip()
                if not line or line.startswith("#"):
                    continue

                # 计算缩进级别
                indent_level = 0
                stripped_line = line.lstrip()
                if stripped_line.startswith("-"):
                    # 计算前导空格数量
                    for char in line:
                        if char == " ":
                            indent_level += 1
                        else:
                            break
                    indent_level = indent_level // 2  # 每2个空格为一级

                    # 提取文本内容
                    text = stripped_line[1:].strip()

                    # 提取时间戳（如果有）
                    timestamp_match = re.search(r"`(\d{2}:\d{2})`", text)
                    if timestamp_match:
                        text = text.replace(timestamp_match.group(), "").strip()
                        timestamp = timestamp_match.group(1)
                    else:
                        timestamp = None

                    if text:  # 只处理非空文本
                        # 调整父节点栈
                        target_level = indent_level + 1  # 相对于根节点的级别
                        if target_level > len(current_parents):
                            # 需要保持当前最后一个节点作为父节点
                            pass
                        else:
                            # 回退到合适的父节点
                            current_parents = current_parents[:target_level]

                        # 创建新节点
                        if current_parents:
                            parent_node = current_parents[-1]
                            new_node = ET.SubElement(parent_node, "node")
                            new_node.set("ID", f"node_{node_id}")
                            new_node.set("TEXT", text)

                            # 添加时间戳注释
                            if timestamp:
                                note = ET.SubElement(new_node, "richcontent")
                                note.set("TYPE", "NOTE")
                                html = ET.SubElement(note, "html")
                                body = ET.SubElement(html, "body")
                                p = ET.SubElement(body, "p")
                                p.text = f"时间: {timestamp}"

                            # 将新节点加入父节点栈
                            current_parents.append(new_node)
                            node_id += 1

            # 生成XML字符串
            xml_str = ET.tostring(root, encoding="unicode", method="xml")

            # 格式化XML
            formatted_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
            formatted_xml += xml_str

            # 写入文件
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(formatted_xml)

            logger.info(f"成功导出思维导图到 FreeMind 格式：{output_path}")
            return True
        except Exception as e:
            logger.error(f"XMind格式导出失败: {e}")
            return False

    def export_anki_format(self, flashcards_content: str, output_path: str) -> bool:
        """将闪卡导出为Anki格式 - 借鉴3.0版本的优秀实现"""
        try:
            import re
            
            # 解析闪卡内容 - 支持多种格式
            cards = []
            
            # 尝试当前版本的Q&A格式
            qa_pattern = r"\*\*Q\*\*:\s*(.+?)\n\*\*A\*\*:\s*(.+?)(?=\n---|\n\*\*Q\*\*|\Z)"
            matches = re.findall(qa_pattern, flashcards_content, re.DOTALL)
            
            if matches:
                cards = [("问答卡", q.strip(), a.strip(), "基础") for q, a in matches]
            else:
                # 尝试3.0版本的标准格式
                pattern1 = r"## 闪卡 \d+ - (.+?)\n\*\*正面\*\*: (.+?)\n\*\*背面\*\*: (.+?)\n\*\*标签\*\*: (.+?)(?=\n\n|\Z)"
                matches = re.findall(pattern1, flashcards_content, re.DOTALL)
                
                if matches:
                    cards = matches
                else:
                    # 尝试更宽松的格式匹配
                    pattern2 = r"##.*?闪卡.*?\n.*?正面.*?[:：]\s*(.+?)\n.*?背面.*?[:：]\s*(.+?)(?:\n.*?标签.*?[:：]\s*(.+?))?(?=\n\n|\n##|\Z)"
                    matches = re.findall(pattern2, flashcards_content, re.DOTALL)
                    cards = [
                        ("通用卡", match[0], match[1], match[2] if len(match) > 2 and match[2] else "基础")
                        for match in matches
                    ]
            
            if not cards:
                logger.warning("无法解析闪卡格式，尝试简单问答格式...")
                # 最后尝试简单的问答格式
                simple_qa_pattern = r"(?:Q|问题|Question)[:：]\s*(.+?)\n(?:A|答案|Answer)[:：]\s*(.+?)(?=\n(?:Q|问题|Question)|\Z)"
                qa_matches = re.findall(simple_qa_pattern, flashcards_content, re.DOTALL | re.IGNORECASE)
                if qa_matches:
                    cards = [("问答卡", q.strip(), a.strip(), "基础") for q, a in qa_matches]
                else:
                    logger.error(f"无法解析任何闪卡格式，内容预览：{flashcards_content[:300]}")
                    return False
            
            # 生成Anki导入格式（CSV）
            anki_content = []
            for card_type, front, back, tags in cards:
                # 清理内容
                front = front.strip().replace("\n", "<br>").replace("\t", " ")
                back = back.strip().replace("\n", "<br>").replace("\t", " ")
                tags = tags.replace("#", "").replace(" ", "_")
                
                # Anki格式：正面\t背面\t标签
                anki_content.append(f"{front}\t{back}\t{tags}")
            
            # 写入文件
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("Front\tBack\tTags\n")  # 头部
                f.write("\n".join(anki_content))
            
            logger.info(f"成功导出 {len(cards)} 张闪卡到 Anki 格式：{output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Anki格式导出失败: {e}")
            return False

    def parse_flashcards_multiple_formats(self, content: str) -> list:
        """解析多种闪卡格式 - 借鉴3.0版本的容错机制"""
        import re
        
        cards = []
        
        # 格式1：当前版本的Q&A格式
        qa_pattern = r"\*\*Q\*\*:\s*(.+?)\n\*\*A\*\*:\s*(.+?)(?=\n---|\n\*\*Q\*\*|\Z)"
        matches = re.findall(qa_pattern, content, re.DOTALL)
        if matches:
            return [{"question": q.strip(), "answer": a.strip(), "type": "qa"} for q, a in matches]
        
        # 格式2：标准闪卡格式
        pattern1 = r"## 闪卡 \d+ - (.+?)\n\*\*正面\*\*: (.+?)\n\*\*背面\*\*: (.+?)\n\*\*标签\*\*: (.+?)(?=\n\n|\Z)"
        matches = re.findall(pattern1, content, re.DOTALL)
        if matches:
            return [
                {
                    "question": front.strip(),
                    "answer": back.strip(),
                    "type": card_type.strip(),
                    "tags": tags.strip()
                }
                for card_type, front, back, tags in matches
            ]
        
        # 格式3：宽松格式
        pattern2 = r"##.*?闪卡.*?\n.*?正面.*?[:：]\s*(.+?)\n.*?背面.*?[:：]\s*(.+?)(?:\n.*?标签.*?[:：]\s*(.+?))?(?=\n\n|\n##|\Z)"
        matches = re.findall(pattern2, content, re.DOTALL)
        if matches:
            return [
                {
                    "question": match[0].strip(),
                    "answer": match[1].strip(),
                    "type": "通用卡",
                    "tags": match[2].strip() if len(match) > 2 and match[2] else "基础"
                }
                for match in matches
            ]
        
        # 格式4：简单问答
        simple_qa_pattern = r"(?:Q|问题|Question)[:：]\s*(.+?)\n(?:A|答案|Answer)[:：]\s*(.+?)(?=\n(?:Q|问题|Question)|\Z)"
        matches = re.findall(simple_qa_pattern, content, re.DOTALL | re.IGNORECASE)
        if matches:
            return [{"question": q.strip(), "answer": a.strip(), "type": "简单问答"} for q, a in matches]
        
        logger.warning(f"无法解析闪卡格式，内容预览：{content[:200]}")
        return []

    async def _generate_flashcards_smart(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """智能生成学习闪卡 - 四段式结构优化版"""
        try:
            analysis_result = kwargs.get("analysis_result")

            # 🎯 角色定义（从配置文件读取）
            role_name = get_role_name(
                analysis_result.primary_domain.value, 
                "flashcard_generator", 
                "学习闪卡专家"
            )

            # 构建四段式提示词
            system_prompt = f"""# 角色
你是一位专业的{role_name}，专门为{analysis_result.primary_domain.value}领域创建高质量的学习闪卡。

# 任务
基于转录内容生成学习闪卡，核心要求：
- 深入理解{analysis_result.primary_domain.value}领域的核心概念和实践要点
- 熟悉该领域的常见问题和学习难点
- 了解{analysis_result.target_audience}的学习需求和认知特点
- 重点关注：{', '.join(analysis_result.key_topics[:5])}

# 约束条件
1. **语言**：简体中文
2. **数量**：8-12张闪卡
3. **类型分布**：
   - 核心概念类（30%）：基础定义和重要原理
   - 实践应用类（40%）：具体操作和方法技巧
   - 问题解决类（20%）：常见问题和解决方案
   - 经验总结类（10%）：关键要点和注意事项
4. **质量标准**：
   - 问题紧密结合{analysis_result.primary_domain.value}领域特色
   - 关注该领域的实际应用和操作要点
   - 适合{analysis_result.target_audience}的认知水平
   - 体现{analysis_result.content_style}的特点

# 输出模板
```
**Q**: {{简洁明确的问题，具有挑战性}}
**A**: {{详细易懂的答案，包含：}}
- 直接答案
- 关键理解要点
- 实际应用提示（如适用）
- 记忆技巧（如适用）

---

**Q**: {{下一个问题}}
**A**: {{对应答案}}
```

请严格按照模板输出，每张闪卡用"---"分隔。"""

            user_prompt = f"""请为以下{analysis_result.primary_domain.value}内容生成专业的学习闪卡：

## 转录内容：
{transcript[:3000]}

## 分析要点：
- 主要领域：{analysis_result.primary_domain.value}
- 内容风格：{analysis_result.content_style}
- 目标受众：{analysis_result.target_audience}
- 核心话题：{', '.join(analysis_result.key_topics[:5])}

请生成8-12张高质量的学习闪卡，确保问题有挑战性，答案有价值。"""

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {
                        "type": "flashcards",
                        "message": f"📚 正在生成{analysis_result.primary_domain.value}领域学习闪卡...",
                    },
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "flashcards", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "flashcards", "message": "✅ 智能学习闪卡生成完成"},
                )

            return {
                "success": True,
                "type": "flashcards",
                "content": content,
                "format": "text",
                "analysis_result": analysis_result.__dict__,
                "frame_info": frame_info,
            }
        except Exception as e:
            logger.error(f"智能学习闪卡生成失败: {e}")
            return {"error": str(e), "success": False}

    async def _generate_ai_analysis_smart(
        self,
        config: GenerationConfig,
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        **kwargs,
    ) -> Dict[str, Any]:
        """智能生成AI分析 - 四段式结构优化版"""
        try:
            analysis_result = kwargs.get("analysis_result")

            # 🎯 角色定义（从配置文件读取）
            role_name = get_role_name(
                analysis_result.primary_domain.value, 
                "ai_analysis", 
                "内容分析专家"
            )

            # 构建四段式提示词
            system_prompt = f"""# 角色
你是一位专业的{role_name}，专门对{analysis_result.primary_domain.value}领域内容进行深度分析和价值评估。

# 任务
基于已有的内容分析结果进行深度分析，核心要求：
- 从{analysis_result.primary_domain.value}领域角度评价内容价值
- 分析内容与目标受众的匹配程度
- 提供专业的改进建议和扩展方向
- 识别具体应用场景和实用价值

# 约束条件
1. **语言**：简体中文
2. **输出格式**：JSON结构
3. **分析深度**：基于以下已知信息进行深度分析
   - 主要领域：{analysis_result.primary_domain.value}
   - 次要领域：{[d.value for d in analysis_result.secondary_domains]}
   - 置信度：{analysis_result.confidence:.2f}
   - 关键话题：{', '.join(analysis_result.key_topics)}
   - 内容风格：{analysis_result.content_style}
   - 目标受众：{analysis_result.target_audience}

# 输出模板
```json
{{
    "content_value_assessment": {{
        "overall_score": 8.5,
        "strengths": ["优势1", "优势2", "优势3"],
        "weaknesses": ["不足1", "不足2"],
        "domain_relevance": "在{analysis_result.primary_domain.value}领域的相关性评价"
    }},
    "audience_matching": {{
        "match_score": 7.8,
        "target_audience": "{analysis_result.target_audience}",
        "suitability_analysis": "受众适配性分析",
        "recommendations": ["建议1", "建议2"]
    }},
    "improvement_suggestions": [
        "针对{analysis_result.primary_domain.value}领域的改进建议1",
        "改进建议2",
        "改进建议3"
    ],
    "application_scenarios": [
        "应用场景1",
        "应用场景2",
        "应用场景3"
    ],
    "extension_directions": [
        "扩展方向1",
        "扩展方向2"
    ]
}}
```

请严格按照JSON格式输出，确保格式正确。"""

            user_prompt = f"""请对以下{analysis_result.primary_domain.value}内容进行深度AI分析：

## 转录内容：
{transcript[:2000]}

## 已知分析结果：
- 主要领域：{analysis_result.primary_domain.value}
- 置信度：{analysis_result.confidence:.2f}
- 关键话题：{', '.join(analysis_result.key_topics)}
- 内容风格：{analysis_result.content_style}
- 目标受众：{analysis_result.target_audience}
- 内容长度：{analysis_result.content_length}

请基于以上信息进行深度分析，输出结构化的JSON分析结果。"""

            # 流式生成通知
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {
                        "type": "ai_analysis",
                        "message": f"🤖 正在进行{analysis_result.primary_domain.value}领域智能分析...",
                    },
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "ai_analysis", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "ai_analysis", "message": "✅ 智能AI分析完成"},
                )

            return {
                "success": True,
                "type": "ai_analysis",
                "content": content,
                "format": "json",
                "analysis_result": analysis_result.__dict__,
                "frame_info": frame_info,
            }
        except Exception as e:
            logger.error(f"智能AI分析生成失败: {e}")
            return {"error": str(e), "success": False}


# 便捷函数
async def create_ai_factory(
    settings: Dict[str, Any], provider: str = "openai"
) -> AIContentFactory:
    """创建AI内容生成工厂"""
    return AIContentFactory(settings, provider)


async def generate_content(
    output_type: str,
    transcript: str = "",
    video_path: str = "",
    audio_path: str = "",
    subtitles: List[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """生成指定类型内容的便捷函数"""
    # 加载settings.json
    settings_path = Path("config/settings.json")
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    factory = await create_ai_factory(settings)
    return await factory.generate(
        output_type, transcript, video_path, audio_path, subtitles, **kwargs
    )


async def generate_all_content(
    transcript: str = "",
    video_path: str = "",
    audio_path: str = "",
    subtitles: List[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """生成所有类型内容的便捷函数"""
    # 加载settings.json
    settings_path = Path("config/settings.json")
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    factory = await create_ai_factory(settings)
    return await factory.generate_all(
        transcript, video_path, audio_path, subtitles, **kwargs
    )
