#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容卡片生成器 - SRT与帧精确匹配版本
专门处理视频转录内容的结构化生成，支持图文并茂的内容卡片
"""

import datetime
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

# 导入语义匹配器
from ..semantic_frame_matcher import SemanticFrameMatcher, semantic_match_frames

logger = logging.getLogger(__name__)


class ContentCardGenerator:
    """内容卡片生成器 - 专门处理SRT与帧的精确匹配"""

    def __init__(self, ai_client, storage_path: Path):
        """
        初始化内容卡片生成器

        Args:
            ai_client: AI客户端实例
            storage_path: 存储路径
        """
        self.ai_client = ai_client
        self.storage_path = storage_path
        # 🧠 初始化语义匹配器
        self.semantic_matcher = SemanticFrameMatcher(ai_client)
        logger.info("🎨 内容卡片生成器初始化完成（集成语义匹配）")

    async def _generate_text_only_content(
        self, config, transcript: str, stream_callback=None
    ) -> Dict[str, Any]:
        """生成纯文本内容卡片（音频文件使用）"""
        try:
            logger.info("🎵 生成音频内容卡片（无视觉元素）")

            # 从配置文件中获取系统提示词模板
            from biz.routes.settings_api import get_prompt_template

            system_prompt_template = get_prompt_template(
                "content_card", "audio_system_prompt"
            )

            # 如果没有配置模板，则使用默认模板
            if not system_prompt_template:
                system_prompt_template = """# 角色设定
你是一位专业的{role_name}，擅长将{domain}领域的音频内容转化为结构化、高价值的知识卡片。

# 核心任务
基于音频转录内容，生成结构化的内容卡片，专注于文字内容的价值提炼。

## 质量标准
1. **结构清晰**：合理的标题层次和段落组织
2. **内容精炼**：提取核心观点，去除冗余表达
3. **逻辑连贯**：确保内容流畅，逻辑清晰
4. **价值突出**：突出关键信息和核心价值
5. **适合阅读**：适合快速阅读和理解

## 文体规范
- **开篇**：用「# 标题」概括音频核心价值
- **摘要**：用「# 摘要」概括音频核心内容  
- **章节**：用「## 章节名」组织主要内容
- **总结**：用「# 总结」总结中心思想
- **思考**：用「# 思考」提出思考问题

## 注意事项
- 这是音频内容，无视觉元素，专注于文字价值
- 使用恰当的emoji丰富表达，但不要过度使用
- 保持专业性和可读性的平衡"""

            # 获取角色名称
            from biz.routes.settings_api import get_role_name

            role_name = get_role_name("general", "content_card", "音频内容专家")

            # 格式化系统提示词
            system_prompt = system_prompt_template.format(
                role_name=role_name, domain="通用"
            )

            user_prompt = f"""请为以下音频转录内容生成结构化的内容卡片：

{transcript}

请生成一个结构清晰、内容精炼的知识卡片。"""

            # 生成内容
            if stream_callback:
                # 流式生成
                content = ""
                async for chunk in self.ai_client.stream_chat(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                ):
                    content += chunk
                    stream_callback(chunk)
            else:
                # 一次性生成
                content = await self.ai_client.chat(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                )

            return {
                "success": True,
                "type": "content_card",
                "content": content,
                "format": "text",
                "has_images": False,
                "source_type": "audio",
            }

        except Exception as e:
            logger.error(f"❌ 生成音频内容卡片失败: {e}")
            return {"error": str(e), "success": False}

    async def generate_content_card(
        self,
        config,  # GenerationConfig
        transcript: str,
        frame_info: Dict[str, Any],
        stream_callback=None,
        custom_system_prompt: str = None,  # 🧠 新增：支持自定义系统提示词
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容卡片 - 主入口方法"""
        try:
            # 1. 基础信息提取
            frames = frame_info.get("frames", [])
            cover_frame = frame_info.get("cover_frame", "")
            task_id = kwargs.get("task_id", "")
            subtitles = kwargs.get("subtitles", [])

            # 获取存储路径
            keyframes_path = self.storage_path / task_id / "keyframes"

            # 2. 帧数据处理
            if not frames:
                return await self._generate_text_only_content(
                    config, transcript, stream_callback
                )

            # 转换帧数据格式
            frame_list = self._convert_frame_data(frames)
            logger.info(f"🎨 处理 {len(frame_list)} 个提取的帧")

            # 3. 智能帧匹配：优先使用语义匹配，回退到时间匹配
            analysis_result = kwargs.get("analysis_result")

            # 🎯 优先使用用户指定的角色，其次才是智能分析结果
            force_domain = kwargs.get("force_domain")
            if force_domain:
                content_domain = force_domain
                logger.info(f"🎯 使用用户指定角色: {content_domain}")
            else:
                content_domain = (
                    analysis_result.primary_domain.value
                    if analysis_result
                    else "general"
                )
                logger.info(f"🤖 使用智能分析角色: {content_domain}")

            # 🧠 尝试语义匹配
            semantic_matches = await self.semantic_matcher.match_frames_to_content(
                frames, transcript, subtitles, content_domain
            )

            if semantic_matches and len(semantic_matches) >= 3:
                logger.info("🧠 使用语义匹配策略")
                image_strategy = (
                    self.semantic_matcher.generate_matching_strategy_prompt(
                        semantic_matches, keyframes_path
                    )
                )
                srt_frame_mapping = None  # 语义匹配不需要SRT映射
            elif subtitles:
                logger.info("⏰ 回退到SRT时间匹配")
                srt_frame_mapping = self._match_srt_to_frames(subtitles, frame_list)
                image_strategy = self._build_srt_matching_strategy(
                    srt_frame_mapping, frame_list, cover_frame, keyframes_path
                )
            else:
                logger.info("📐 使用简单帧策略")
                srt_frame_mapping = None
                image_strategy = self._build_simple_frame_strategy(
                    frame_list, cover_frame, keyframes_path
                )

            # 4. 构建AI提示词
            # 🕐 获取视频时长信息
            media_duration = kwargs.get("media_duration", 0)

            if custom_system_prompt:
                system_prompt = custom_system_prompt
                logger.info("🎨 使用智能分析生成的自定义系统提示词")
            else:
                system_prompt = self._build_system_prompt(
                    image_strategy, keyframes_path, content_domain, media_duration
                )

            user_prompt = self._build_user_prompt(
                transcript,
                srt_frame_mapping or semantic_matches,
                frame_list,
                keyframes_path,
                content_domain,
            )

            # 5. 生成内容
            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {"type": "content_card", "message": "🎨 正在生成内容卡片..."},
                )

            content = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            # 6. 后处理兜底 - 修复格式错误
            content = self._post_process_content(content)

            # 7. 返回结果
            if stream_callback:
                await stream_callback(
                    "ai_content_chunk", {"type": "content_card", "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": "content_card", "message": "✅ 内容卡片生成完成"},
                )

            return {
                "success": True,
                "type": "content_card",
                "content": content,
                "format": "text",
                "frame_info": frame_info,
                "prompts": {  # 🆕 返回提示词信息
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "image_strategy": image_strategy,
                    "content_domain": content_domain,
                    "frame_count": len(frame_list),
                    "semantic_matches": (
                        len(semantic_matches) if semantic_matches else 0
                    ),
                },
            }

        except Exception as e:
            logger.error(f"生成内容卡片失败: {e}")
            return {"error": str(e), "success": False}

    def _convert_frame_data(self, frames: List) -> List[Dict[str, Any]]:
        """转换帧数据格式为统一格式"""
        frame_list = []
        for frame in frames:
            # 支持不同的帧数据格式
            if isinstance(frame, dict):
                filename = frame.get("filename", "")
                timestamp_seconds = frame.get("timestamp", 0)
            elif isinstance(frame, tuple) and len(frame) >= 2:
                # 处理元组格式：('01_08.jpg', datetime.timedelta(seconds=68))
                filename = frame[0]
                timestamp_obj = frame[1]
                if hasattr(timestamp_obj, "total_seconds"):
                    timestamp_seconds = timestamp_obj.total_seconds()
                else:
                    timestamp_seconds = float(timestamp_obj) if timestamp_obj else 0
                logger.info(f"🔧 转换帧数据: {filename} -> {timestamp_seconds}秒")
            else:
                filename = str(frame)
                timestamp_seconds = 0

            frame_list.append({"filename": filename, "timestamp": timestamp_seconds})
        return frame_list

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

        # 添加语义匹配建议
        mapping_info += "\n### 💡 智能语义匹配建议：\n"
        mapping_info += (
            "**匹配原则**：图片应该与其前后2-3句话的语义内容相关，而不仅仅是时间对应\n"
        )
        mapping_info += "**使用策略**：\n"
        mapping_info += "- 📖 **概念解释时**：使用该概念出现时间点的帧\n"
        mapping_info += "- 🔧 **操作演示时**：使用操作步骤对应的帧\n"
        mapping_info += "- 📊 **数据展示时**：使用图表或数据出现时的帧\n"
        mapping_info += "- 🎯 **重点强调时**：使用关键内容对应的帧\n"
        mapping_info += "- 📚 **章节过渡时**：使用过渡性帧来分隔不同主题\n"

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
- 📁 **图片路径**: ![图片名](keyframes/图片名)
- 📝 **图片名**：图片文件名，不包含路径，比如：data/outputs/video_20250906_211458_669/keyframes/00_02.jpg 的图片名就是00_02.jpg

{mapping_info}

### 📋 关键帧使用规则：
1. **封面图片**：开头摘要部分必须包含一张封面图片
2. **章节关键图**：每个主要章节（## 标题）都应该有对应的关键帧
3. **核心概念图**：重要概念解释时必须配图说明
4. **流程演示图**：步骤流程类内容必须配对应帧图
5. **语义精确匹配**：图片与文字内容必须在时间和语义上高度对应
6. **关键位置强制配图**：
   - 📖 开头部分（摘要后）：1张封面图
   - 🔧 核心章节开头：每个重要章节1张图
   - 📊 关键概念处：概念解释配图
   - 🎯 总结前：可选择性使用图片
7. **图片分布要求**：确保至少50%的主要章节都有配图
8. **强制图文混排**：图片必须插入到相关段落中，不能集中在文末
9. **🚫禁用区域**：「总结」和「思考」段落严禁插入任何图片

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

### 📋 关键帧使用规则：
1. **封面图片**：开头摘要部分必须包含一张封面图片
2. **章节关键图**：每个主要章节（## 标题）都应该有对应的关键帧
3. **时间对应原则**：根据内容时间点选择最接近的帧
4. **关键位置强制配图**：
   - 📖 开头部分（摘要后）：1张封面图
   - 🔧 核心章节开头：每个重要章节1张图
   - 📊 关键概念处：概念解释配图
5. **图片分布要求**：确保至少50%的主要章节都有配图
6. **强制图文混排**：图片必须插入到相关段落中，不能集中在文末
7. **🚫 禁用区域**：「总结」和「思考」段落严禁插入图片

**⚠️ 严禁使用未列出的图片文件名！**
"""

    def _build_system_prompt(
        self,
        image_strategy: str,
        keyframes_path,
        content_domain: str = "general",
        media_duration: float = 0,
    ) -> str:
        """构建系统提示词 - 四段式结构优化版"""

        # 🎯 角色定义（从配置文件读取）
        from biz.routes.settings_api import get_role_name

        role_name = get_role_name(content_domain, "content_card", "视频知识萃取专家")

        # 🕐 时长信息格式化
        duration_info = ""
        if media_duration > 0:
            minutes = int(media_duration // 60)
            seconds = int(media_duration % 60)
            duration_info = f"""
# 视频时长信息
**重要提醒**：该视频总时长为 {minutes}分{seconds}秒（{media_duration:.1f}秒）
- **帧时间约束**：所有关键帧的时间戳必须在 00:00 到 {minutes:02d}:{seconds:02d} 范围内
- **帧时间验证**：如果策略中包含超出视频时长的帧，请忽略这些帧
- **帧位置选择**：优先选择视频前2/3部分的关键帧，确保时间有效性
"""

        return f"""# 角色
你是一位专业的{role_name}，擅长将视频内容转化为结构化、高价值、图文精准对齐的知识卡片。

{duration_info}

# 任务
基于转录内容和语义匹配结果，生成图文并茂的内容卡片。核心要求：
- **语义对齐优先**：图片必须与其匹配的语义段落同时出现
- **内容深度展开**：将匹配段落扩展为完整讲解，而非简单复述
- **结构化呈现**：确保知识点完整覆盖，逻辑清晰

{image_strategy}

# 约束条件
1. **语言**：简体中文
2. **关键帧使用策略**：
   - 仅使用 `image_strategy` 中列出的图片
   - **必须在关键位置插入图片**：开头摘要后、每个主要章节开头
   - 格式：`![图片名](keyframes/图片名)`
   - **确保至少50%的主要章节都有配图**
   - **章节配图要求**：每个重要的 `## 章节` 都应该有对应的关键帧
   - **语义匹配优先**：图片与章节内容在语义上必须高度相关
3. **禁用区域**：`# 总结` 和 `# 思考` 段落严禁插入图片
4. **格式禁忌**：
   - ❌ 禁止 `## # 摘要`、`## ## 步骤`等错误标题
   - ✅ 正确：`# 摘要`、`## 操作步骤`
5. **🚫 严禁AI助手语言**：
   - ❌ 绝对禁止："当然可以！"、"以下是"、"我来为您"、"让我"
   - ❌ 绝对禁止："希望对您有帮助"、"欢迎告诉我"、"需要其他版本"
   - ❌ 绝对禁止：任何AI角色扮演、客服语言、推广话语
   - ✅ 要求：直接开始内容，直接结束内容，零AI痕迹

# 输出模板（关键帧使用示例）
```
# {{视频核心主题}}

# 摘要
{{3-5句话概括全文价值，突出知识点和实用性}}
![封面图.jpg](keyframes/封面图.jpg)

## {{章节1：基于语义段落1}}
{{将匹配段落扩展为详细内容}}
![章节1相关图.jpg](keyframes/章节1相关图.jpg)
{{继续该章节的详细内容}}

## {{章节2：基于语义段落2}}
{{扩展内容，确保图文语义对齐}}
![章节2相关图.jpg](keyframes/章节2相关图.jpg)

## {{章节3：基于语义段落3}}
{{继续扩展内容，合理使用更多图片}}
![章节3相关图.jpg](keyframes/章节3相关图.jpg)

# 总结
{{提炼中心思想，无图纯文本}}

# 思考
{{提出2-3个启发性问题，无图纯文本}}
```

请严格按照模板输出，不要添加额外解释。"""

    def _build_user_prompt(
        self,
        transcript: str,
        matches,
        frame_list: List[Dict[str, Any]],
        keyframes_path,
        content_domain: str = "general",
    ) -> str:
        """构建用户提示词-完全基于语义匹配结果 + Few-shot示例"""

        # 🎯 提取语义匹配段落（去重）
        semantic_segments = []
        used_segments = set()

        if matches:
            for match in matches:
                # 处理不同类型的匹配结果
                if hasattr(match, "matched_text_segment"):
                    # 语义匹配结果
                    seg_key = match.matched_text_segment[:60]
                    if seg_key not in used_segments:
                        semantic_segments.append(
                            {
                                "text": match.matched_text_segment,
                                "frame": match.frame_filename,
                                "score": getattr(match, "semantic_score", 0.8),
                                "reason": getattr(match, "match_reason", "语义匹配"),
                                "start_time": getattr(match, "start_time", 0),
                                "end_time": getattr(match, "end_time", 0),
                            }
                        )
                        used_segments.add(seg_key)
                else:
                    # SRT时间匹配结果（向后兼容）
                    seg_key = match.get("content", "")[:60]
                    if seg_key not in used_segments:
                        semantic_segments.append(
                            {
                                "text": match.get("content", ""),
                                "frame": match.get("frame", {}).get("filename", ""),
                                "score": 0.7,
                                "reason": match.get("match_quality", "时间匹配"),
                                "start_time": match.get("start_time", 0),
                                "end_time": match.get("end_time", 0),
                            }
                        )
                        used_segments.add(seg_key)

        # 🎯 构建语义匹配指南
        if semantic_segments:
            guide = "## 🎯 语义匹配映射（请严格遵循）\n"
            guide += "**重要要求**：使用30%左右的匹配图片，重点突出核心内容\n"
            guide += "**关键帧策略**：在关键位置（如封面、主要章节开头）插入图片，避免过度使用\n"
            for i, seg in enumerate(semantic_segments[:8]):  # 限制显示前8个
                start_min, start_sec = divmod(int(seg["start_time"]), 60)
                end_min, end_sec = divmod(int(seg["end_time"]), 60)
                guide += (
                    f"- **时间范围**: {start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d}\n"
                    f'  **图片**: `{seg["frame"]}`\n'
                    f'  **匹配段落**: "{seg["text"][:50]}..."\n'
                    f'  **置信度**: {seg["score"]:.2f} | **类型**: {seg["reason"]}\n\n'
                )
            if len(semantic_segments) > 8:
                guide += f"...（共 {len(semantic_segments)} 个语义匹配）\n"
        else:
            frame_names = [f["filename"] for f in frame_list]
            frames_list = ", ".join(frame_names)
            guide = f"## ⚠️ 无有效语义匹配，可用图片: {frames_list}\n"
            guide += "**重要要求**：使用30%左右的可用图片，重点突出核心内容\n"
            guide += "**关键帧策略**：在关键位置（如封面、主要章节开头）插入图片，避免过度使用\n"

        # 🔥 Few-shot 示例（根据领域动态调整）
        example = self._get_few_shot_example(content_domain, keyframes_path, frame_list)

        return f"""{example}

【你的任务】
请基于以下转录内容和**语义匹配结果**，生成知识卡片：

## 📝 转录全文（供上下文参考）：
{transcript[:3000] if transcript else '无转录内容'}

{guide}

**关键指令**：
- **封面图必须**：开头摘要后必须有一张封面图片
- **章节配图要求**：每个重要的 `## 章节` 都应该有对应的关键帧
- **确保图片分布**：至少50%的主要章节都必须有配图
- 在章节正文中插入匹配的图片（格式：`![xxx.jpg](keyframes/xxx.jpg)`）
- **禁用区域**：`# 总结` 和 `# 思考` 段落禁止插入任何图片
- **关键位置强制配图**：摘要后、核心章节开头、重要概念处
- 输出纯文本，不要额外解释
"""

    def _get_few_shot_example(
        self, content_domain: str, keyframes_path: str, frame_list: list
    ) -> str:
        """根据内容领域获取Few-shot示例 - 使用实际的帧文件名"""

        # 🎯 从实际的帧列表中随机选择示例帧（避免固定文件名导致AI学习错误模式）
        import random

        if frame_list and len(frame_list) >= 4:
            # 随机选择4个不同的帧作为示例
            selected_frames = random.sample(frame_list, 4)
            example_frames = [frame["filename"] for frame in selected_frames]
        else:
            # 如果帧数不足，使用通用命名
            example_frames = [
                "frame_00_02.jpg",  # 封面帧
                "frame_00_30.jpg",  # 第一章节帧
                "frame_02_15.jpg",  # 第二章节帧
                "frame_03_45.jpg",  # 第三章节帧
            ]

        examples = {
            "cooking": f"""
【输出示例 - 烹饪教学】
# 宫保鸡丁的正宗做法详解

# 摘要
本文系统讲解宫保鸡丁的制作全流程，从食材准备到火候控制。关键技巧包括鸡肉腌制、花生米炸制和酱汁调配，适合家庭厨房复现。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 食材准备与预处理
首先将鸡胸肉切成1.5厘米见方的丁，加入料酒、淀粉腌制10分钟。同时准备干辣椒段、花椒和炸好的花生米。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 烹饪与调味关键
热锅凉油下鸡丁快速滑炒至变色，加入干辣椒和花椒爆香，最后倒入调好的酱汁（生抽2勺、醋1勺、糖1勺）翻炒均匀。
![{example_frames[2]}](keyframes/{example_frames[2]})

## 装盘与收尾技巧
出锅前撒上葱花和剩余的花生米，装盘时注意色彩搭配，提升视觉效果。掌握火候是关键，避免鸡肉过老影响口感。
![{example_frames[3]}](keyframes/{example_frames[3]})

# 总结
宫保鸡丁的核心在于"快炒"和"酸甜平衡"，掌握这两点即可复刻餐厅风味。

# 思考
如何调整配方使其更适合儿童口味？能否用鸡腿肉替代鸡胸肉？
""",
            "it": f"""
【输出示例 - IT技术】
# Docker容器化部署实战指南

# 摘要
本文详细介绍Docker容器技术的核心概念和实际应用，包括镜像构建、容器管理和网络配置。通过实例演示，帮助开发者掌握现代应用部署方式。
![{example_frames[0]}](keyframes/{example_frames[0]})

## Docker镜像构建原理
Docker镜像是由多层文件系统组成的只读模板，每一层代表Dockerfile中的一条指令。理解分层机制有助于优化镜像大小和构建速度。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 容器网络配置实践
Docker提供多种网络模式，包括bridge、host和overlay。在微服务架构中，合理配置容器网络是确保服务间通信的关键。
![{example_frames[2]}](keyframes/{example_frames[2]})

## 生产环境部署策略
容器编排工具如Docker Compose和Kubernetes能够简化大规模容器部署。通过健康检查、滚动更新等机制，确保服务的高可用性。
![{example_frames[3]}](keyframes/{example_frames[3]})

# 总结
Docker容器化技术通过标准化部署环境，大幅提升了应用的可移植性和运维效率。

# 思考
如何在生产环境中实现容器的高可用部署？容器安全有哪些需要注意的要点？
""",
            "finance": f"""
【输出示例 - 金融分析】
# 股票投资的风险管理策略

# 摘要
本文介绍股票投资中的核心风险管理策略，包括资产配置、止损设置和风险评估方法。通过实例分析，帮助投资者建立科学的投资决策体系。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 资产配置：分散投资降低风险
合理的资产配置是风险管理的第一步。通过将资金分散投资于不同行业、不同市值的股票，可以有效降低单一股票波动对整体投资组合的影响。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 止损策略：控制最大亏损
设置合理的止损点是保护投资本金的重要手段。常见的止损方法包括固定比例止损、技术指标止损和时间止损。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
科学的风险管理是实现长期稳定收益的关键，投资者应建立完整的风险控制体系。

# 思考
如何根据个人风险承受能力制定合适的投资策略？在市场剧烈波动时如何调整风险管理措施？
""",
            "beauty": f"""
【输出示例 - 美妆护肤】
# 夏季防晒护肤全攻略

# 摘要
本文详细介绍夏季防晒的重要性及正确护肤步骤，包括防晒产品选择、补涂技巧和晒后修复方法。帮助读者建立科学的夏季护肤routine。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 防晒产品选择：SPF与PA值解读
选择防晒产品时需要关注SPF（防晒伤）和PA（防黑）值。日常通勤建议SPF30+，户外活动建议SPF50+。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 正确涂抹技巧：用量与手法
防晒霜的用量要足够，面部约需一元硬币大小。涂抹时要均匀推开，重点照顾容易忽略的部位如耳后、颈部。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
夏季防晒是护肤的重中之重，正确的防晒和修复能有效保护肌肤健康。

# 思考
不同肤质应如何选择适合的防晒产品？物理防晒和化学防晒有何区别？
""",
            "health": f"""
【输出示例 - 健康养生】
# 秋季养生保健指南

# 摘要
本文介绍秋季养生的核心原则和实用方法，包括饮食调理、作息调整和运动建议。帮助读者适应季节变化，保持身体健康。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 饮食调理：润燥养阴
秋季气候干燥，应多食用润燥养阴的食物，如梨、百合、银耳等。避免辛辣刺激食物，以防加重秋燥症状。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 作息调整：早睡早起
秋季应顺应自然规律，早睡早起，保证充足睡眠。建议晚上10点前入睡，早上6点左右起床。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
秋季养生关键在于顺应自然，通过合理饮食和规律作息，为冬季做好准备。

# 思考
如何根据个人体质调整秋季养生方案？秋季运动有哪些注意事项？
""",
            "fitness": f"""
【输出示例 - 健身运动】
# 新手健身入门完整指南

# 摘要
本文为健身初学者提供全面的入门指导，包括训练计划制定、动作标准执行和营养补充建议。通过科学的方法，帮助新手建立正确的健身习惯。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 基础训练计划：循序渐进原则
新手应从基础动作开始，每周3-4次训练，每次30-45分钟。重点掌握深蹲、卧推、硬拉等复合动作的标准姿势。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 营养补充：合理饮食搭配
健身期间要保证蛋白质摄入充足，建议每公斤体重摄入1.2-1.6克蛋白质。同时要合理控制碳水化合物和脂肪的比例。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
健身是一个循序渐进的过程，坚持科学训练和合理饮食，才能达到理想的健身效果。

# 思考
如何平衡有氧运动和力量训练？新手如何避免运动损伤？
""",
            "parenting": f"""
【输出示例 - 育儿教育】
# 幼儿期阅读习惯培养指南

# 摘要
本文介绍如何在幼儿期培养孩子的阅读兴趣和习惯，包括绘本选择、亲子阅读技巧和环境营造方法。帮助家长为孩子奠定良好的学习基础。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 绘本选择：年龄适宜性原则
选择绘本时要考虑孩子的年龄特点和认知水平。2-3岁适合简单的图画书，4-5岁可以选择故事情节较丰富的绘本。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 亲子阅读技巧：互动式引导
阅读过程中要鼓励孩子提问和表达，通过角色扮演、故事续编等方式增强互动性，让阅读变成愉快的亲子时光。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
培养幼儿阅读习惯需要家长的耐心引导和长期坚持，为孩子未来的学习发展打下坚实基础。

# 思考
如何处理孩子对某些绘本的过度依恋？数字化阅读工具是否适合幼儿使用？
""",
            "biography": f"""
【输出示例 - 人物志讲解】
# 马克·吐温：美国文学巨匠的人生传奇

# 摘要
马克·吐温以《汤姆·索亚历险记》享誉世界，他从密西西比河船员成长为美国国民作家，用幽默讽刺针砭时弊，晚年虽遭家庭变故，仍以乐观精神影响后世。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 从船员到作家的转变
年轻的塞缪尔·克莱门斯在密西西比河上当船员时，接触到各色人物和社会百态，这段经历为他后来的创作提供了丰富素材。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 文学创作的黄金时期
《汤姆·索亚历险记》和《哈克贝利·费恩历险记》的问世，标志着美国本土文学的成熟，马克·吐温用儿童视角反映成人世界的复杂。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
马克·吐温不仅是伟大的作家，更是美国精神的代表，他用文学作品诠释了自由、平等和人性的光辉。

# 思考
如何理解马克·吐温作品中的社会批判意识？他的幽默风格对现代文学有何启发？
""",
            "movie": f"""
【输出示例 - 电影讲解】
# 《肖申克的救赎》：希望与自由的终极赞歌

# 摘要
安迪·杜佛兰在肖申克监狱的19年，从绝望到希望，从囚徒到自由人，这不仅是一个越狱故事，更是关于人性尊严、友情力量和永不放弃信念的深刻寓言。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 冤案入狱：命运的残酷转折
银行家安迪因妻子外遇案被判终身监禁，从中产阶级生活跌入地狱般的监狱，面对残酷现实时展现的冷静和智慧为后续发展埋下伏笔。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 监狱求生：智慧与尊严的较量
通过为狱警报税赢得尊重，建立图书馆传播知识，安迪用知识和技能在绝境中创造价值，证明精神自由比身体自由更重要。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
《肖申克的救赎》告诉我们，希望是最美好的东西，也许是世界上最好的东西，美好的东西从不消失。

# 思考
为什么这部电影能够跨越文化差异，成为全球观众心中的经典？它反映了怎样的普世价值？
""",
            "chinese_anime": f"""
【输出示例 - 中国动漫讲解】
# 《哪吒之魔童降世》：国漫崛起的里程碑之作

# 摘要
这部动画电影颠覆传统哪吒形象，以"我命由我不由天"诠释反抗宿命的精神，融合现代审美与传统文化，票房突破50亿，标志着国产动画的全面崛起。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 颠覆性角色设计：丑萌哪吒的魅力
抛弃传统美少年形象，塑造顽劣不羁的"魔童"哪吒，通过夸张表情和动作设计，让角色更具现代感和亲和力，打破观众对神话人物的固有印象。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 技术革新：国产动画的工业化探索
采用国际先进制作技术，特效场面震撼人心，从角色建模到场景渲染都达到国际一流水准，证明中国动画在技术层面已具备世界竞争力。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
《哪吒》的成功不仅在于技术突破，更在于文化自信的回归，为国产动画提供了可复制的成功模式。

# 思考
国漫如何在保持民族特色的同时融入国际元素？技术进步对动画创作带来了哪些新可能？
""",
            "japanese_anime": f"""
【输出示例 - 日本动漫讲解】
# 《你的名字》：时空交错中的青春与命运

# 摘要
新海诚用绝美画面和诗意叙事，讲述了一个跨越时空的爱情故事。通过身体互换、彗星灾难、时间错位等超现实元素，探讨命运、记忆与情感的深刻主题。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 视觉奇观：新海诚的光影美学
每一帧都可以做壁纸的画面质量，从都市霓虹到乡村风光，光影变化细腻入微，将动画的视觉表现力推向极致，营造出超越现实的美感体验。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 情感共鸣：青春记忆的诗意表达
通过身体互换的奇幻设定，表达青春期的困惑和成长，男女主角的情感发展既浪漫又真实，触动观众内心最柔软的青春回忆。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
《你的名字》以超现实的设定承载现实的情感，成为新时代日本动画电影的代表作品。

# 思考
新海诚如何通过动画语言表达现代都市人的孤独感？动画与真人电影在情感表达上有何不同？
""",
            "education": f"""
【输出示例 - 教育内容】
# Python函数基础知识详解

# 摘要
本节课介绍Python函数的定义、参数传递和返回值机制。通过实例演示函数的创建和调用过程，帮助初学者建立函数编程思维。
![{example_frames[0]}](keyframes/{example_frames[0]})

## 函数的定义与语法
Python中使用def关键字定义函数，基本语法为def function_name(parameters)。函数名应该具有描述性，参数可以设置默认值。
![{example_frames[1]}](keyframes/{example_frames[1]})

## 参数传递机制
Python支持位置参数、关键字参数和可变参数。理解不同参数类型的使用场景，能让代码更加灵活和可读。
![{example_frames[2]}](keyframes/{example_frames[2]})

# 总结
函数是代码复用的基础，掌握函数定义、调用和参数传递，是Python编程的重要基础技能。

# 思考
什么时候应该将代码封装成函数？如何设计函数的参数结构更合理？
""",
        }

        # 根据领域返回对应示例，如果没有找到则使用教育示例
        return examples.get(content_domain, examples["education"])

    def _post_process_content(self, content: str) -> str:
        """后处理内容：移除AI第一人称话语并修复格式错误"""
        import re

        # 🚫 移除AI第一人称开头话语
        ai_intro_patterns = [
            r"^当然可以！.*?[\n\r]+",
            r"^好的[！，。]*.*?为您.*?[\n\r]+",
            r"^根据.*?内容.*?以下是.*?[\n\r]+",
            r"^以下是.*?为.*?设计的.*?[\n\r]+",
            r"^我来为您.*?[\n\r]+",
            r"^让我.*?为您.*?[\n\r]+",
            r"^这里是.*?内容卡片.*?[\n\r]+",
            r"^当然可以！以下是一张专为.*?[\n\r]+",
            r"^.*?专为.*?设计的.*?内容卡片.*?[\n\r]+",
        ]

        for pattern in ai_intro_patterns:
            content = re.sub(pattern, "", content, flags=re.MULTILINE)

        # 🚫 移除AI第一人称结尾话语
        # 匹配常见的AI结尾模式
        ai_outro_patterns = [
            r"[\n\r]+---[\n\r]*📚.*?欢迎继续探索.*?$",
            r"[\n\r]+这些卡片既可用于.*?告诉我哦！.*?$",
            r"[\n\r]+需要.*?版.*?也可以告诉我.*?$",
            r"[\n\r]+希望这.*?对您有帮助.*?$",
            r"[\n\r]+如果您需要.*?请告诉我.*?$",
            r"[\n\r]+以上就是.*?如有需要.*?$",
            r"[\n\r]+想提升.*?欢迎访问.*?自己。.*?$",
            r"[\n\r]+.*?欢迎访问.*?www\..*?$",
            r"[\n\r]+.*?需要PPT版.*?告诉我.*?$",
            r"[\n\r]+需要我将这张卡片做成.*?欢迎告诉我.*?$",
            r"[\n\r]+.*?欢迎告诉我~.*?$",
            r"[\n\r]+.*?告诉我~.*?$",
        ]

        for pattern in ai_outro_patterns:
            content = re.sub(pattern, "", content, flags=re.MULTILINE | re.DOTALL)

        # 🚫 移除多余的分隔线和AI提示语
        content = re.sub(r"^---+[\n\r]*", "", content, flags=re.MULTILINE)
        content = re.sub(
            r"[\n\r]+---+[\n\r]*$", "", content, flags=re.MULTILINE | re.DOTALL
        )

        # 移除AI角色扮演的话语
        content = re.sub(
            r"📌.*?欢迎.*?网.*?www\..*?[\n\r]+", "", content, flags=re.MULTILINE
        )
        content = re.sub(
            r"🎧.*?语音小贴士.*?回味空间。[\n\r]+",
            "",
            content,
            flags=re.MULTILINE | re.DOTALL,
        )

        # 修复多余的#符号（SenseVoice专用）
        content = re.sub(r"#{2,}\s*#\s*(摘要|总结|思考)", r"# \1", content)
        content = re.sub(r"#{3,}\s*#{2,}\s*([^#\n]+)", r"## \1", content)

        # 修复标题格式
        content = re.sub(r"^##\s*#\s*([^#\n]+)", r"# \1", content, flags=re.MULTILINE)
        content = re.sub(
            r"^###\s*##\s*([^#\n]+)", r"## \1", content, flags=re.MULTILINE
        )

        # 确保标题前后有空行
        content = re.sub(r"\n(#{1,2}\s+[^\n]+)\n", r"\n\n\1\n\n", content)

        # 清理多余的空行
        content = re.sub(r"\n{3,}", "\n\n", content)

        # 清理开头和结尾的空行
        content = content.strip()

        logger.info("✅ 内容后处理完成，移除了AI第一人称话语并修复了格式错误")
        return content
