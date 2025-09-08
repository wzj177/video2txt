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
        logger.info("🎨 内容卡片生成器初始化完成")

    async def _generate_text_only_content(
        self, config, transcript: str, stream_callback=None
    ) -> Dict[str, Any]:
        """生成纯文本内容卡片（音频文件使用）"""
        try:
            logger.info("🎵 生成音频内容卡片（无视觉元素）")

            # 构建音频专用的系统提示词
            system_prompt = """# 角色设定
你是一位资深的教育内容专家，擅长将音频内容转化为结构化、高价值的知识卡片。

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
- 保持专业性和可读性的平衡
"""

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
                "format": "markdown",
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

            # 3. SRT与帧的精确匹配
            if subtitles:
                srt_frame_mapping = self._match_srt_to_frames(subtitles, frame_list)
                image_strategy = self._build_srt_matching_strategy(
                    srt_frame_mapping, frame_list, cover_frame, keyframes_path
                )
            else:
                srt_frame_mapping = None
                image_strategy = self._build_simple_frame_strategy(
                    frame_list, cover_frame, keyframes_path
                )

            # 4. 构建AI提示词
            system_prompt = self._build_system_prompt(image_strategy, keyframes_path)
            user_prompt = self._build_user_prompt(
                transcript, srt_frame_mapping, frame_list, keyframes_path
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

            # 6. 返回结果
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
                "format": "markdown",
                "frame_info": frame_info,
            }

        except Exception as e:
            logger.error(f"生成内容卡片失败: {e}")
            return {"error": str(e), "success": False}

    def _convert_frame_data(self, frames: List) -> List[Dict[str, Any]]:
        """转换帧数据格式"""
        frame_list = []
        for filename, timestamp in frames:
            timestamp_seconds = (
                timestamp.total_seconds()
                if hasattr(timestamp, "total_seconds")
                else float(timestamp)
            )
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
- 📁 **图片路径**: ![图片名](file://{keyframes_path}/图片名)
- 📝 **图片名**：图片文件名，不包含路径，比如：data/outputs/video_20250906_211458_669/keyframes/00_02.jpg 的图片名就是00_02.jpg
{mapping_info}

### 📋 使用规则：
1. **优先使用精确匹配帧**：描述特定内容时，使用对应的匹配帧
2. **语义对应原则**：图片与文字内容必须在时间和语义上对应
3. **过渡帧补充**：章节过渡时使用未匹配帧
4. **强制图文混排**：图片必须插入到相关段落中，不能集中在文末
5. **🚫 禁用区域**：「总结」和「思考」段落严禁插入任何图片

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
4. **🚫 禁用区域**：「总结」和「思考」段落严禁插入任何图片

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
- **开篇**：用「# 标题」概括视频核心价值
- **摘要**：用「# 摘要」概括视频核心内容  
- **章节**：用「## 章节名」组织主要内容
- **总结**：用「# 总结」总结中心思想（🚫 此段落严禁插入图片）
- **思考**：用「# 思考」提出思考问题（🚫 此段落严禁插入图片）

## 🚫 图片禁用区域
- **总结段落**：严禁在「# 总结」段落中插入任何图片
- **思考段落**：严禁在「# 思考」段落中插入任何图片
- **理由**：这两个段落是概括性和反思性内容，不需要具体的视觉辅助

## ⚠️ Markdown格式严格要求
**绝对禁止使用多余的#符号**：
- ❌ 错误格式：`## # 摘要`、`## ## 步骤一`、`## # 总结`
- ✅ 正确格式：`# 摘要`、`## 步骤一`、`# 总结`
- **规则**：一级标题只用一个#，二级标题只用两个##，绝不重复使用

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
4. **图片名**：图片文件名，不包含路径，比如：data/outputs/video_20250906_211458_669/keyframes/00_02.jpg 的图片名就是00_02.jpg
5. **语义优先匹配**：图片应该与其周围2-3句话的语义内容高度相关
6. **禁用区域**：「总结」和「思考」段落严禁插入图片
7. **绝对禁止**：将所有图片集中在文章最后

### 🎯 智能匹配策略：
- **写到某个概念时**：立即插入该概念出现时间点的对应图片
- **描述操作步骤时**：在步骤说明中插入操作演示的对应图片  
- **引用数据图表时**：在数据分析段落插入图表出现时的图片
- **强调重点内容时**：在重点段落插入关键时刻的图片

**🚨 Markdown格式严格限制（SenseVoice专用）**：
- ❌ **绝对禁止**：`## # 摘要`、`## ## 步骤一`、`## # 总结` 等多余#符号
- ✅ **正确格式**：`# 摘要`、`## 步骤一`、`# 总结`
- **规则**：每个标题只使用对应数量的#，不要重复或叠加使用"""

    async def _generate_text_only_content(
        self, config, transcript: str, stream_callback
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

        if stream_callback:
            await stream_callback(
                "ai_content_complete",
                {"type": "content_card", "message": "✅ 内容生成完成"},
            )

        return {
            "success": True,
            "type": "content_card",
            "content": content,
            "format": "markdown",
        }
