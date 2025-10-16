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
            content_domain = (
                analysis_result.primary_domain.value if analysis_result else "general"
            )

            # 🧠 尝试语义匹配
            semantic_matches = await self.semantic_matcher.match_frames_to_content(
                frames, transcript, subtitles, content_domain
            )

            if semantic_matches and len(semantic_matches) >= 3:
                # 使用语义匹配结果
                logger.info(f"🎯 使用语义匹配: {len(semantic_matches)} 个匹配")
                image_strategy = (
                    self.semantic_matcher.generate_matching_strategy_prompt(
                        semantic_matches, keyframes_path
                    )
                )
                srt_frame_mapping = None  # 语义匹配不需要SRT映射
            elif subtitles:
                # 回退到SRT时间匹配
                logger.info("⏰ 回退到SRT时间匹配")
                srt_frame_mapping = self._match_srt_to_frames(subtitles, frame_list)
                image_strategy = self._build_srt_matching_strategy(
                    srt_frame_mapping, frame_list, cover_frame, keyframes_path
                )
            else:
                # 使用简单帧策略
                logger.info("📐 使用简单帧策略")
                srt_frame_mapping = None
                image_strategy = self._build_simple_frame_strategy(
                    frame_list, cover_frame, keyframes_path
                )

            # 4. 构建AI提示词
            if custom_system_prompt:
                # 🧠 使用自定义系统提示词（来自智能分析）
                system_prompt = custom_system_prompt + "\n\n" + image_strategy
                logger.info("🎨 使用智能分析生成的自定义系统提示词")
            else:
                # 使用默认系统提示词
                system_prompt = self._build_system_prompt(
                    image_strategy, keyframes_path, content_domain
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

    def _build_system_prompt(
        self, image_strategy: str, keyframes_path, content_domain: str = "general"
    ) -> str:
        """构建系统提示词 - 四段式结构优化版"""

        # 🎯 角色定义（从配置文件读取）
        from biz.routes.settings_api import get_role_name
        role_name = get_role_name(content_domain, "content_card", "视频知识萃取专家")

        return f"""# 角色
你是一位专业的{role_name}，擅长将视频内容转化为结构化、高价值、图文精准对齐的知识卡片。

# 任务
基于转录内容和语义匹配结果，生成图文并茂的内容卡片。核心要求：
- **语义对齐优先**：图片必须与其匹配的语义段落同时出现
- **内容深度展开**：将匹配段落扩展为完整讲解，而非简单复述
- **结构化呈现**：确保知识点完整覆盖，逻辑清晰

{image_strategy}

# 约束条件
1. **语言**：简体中文
2. **图片规则**：
   - 仅使用 `image_strategy` 中列出的图片
   - 图片必须插入在**匹配段落的正文中**
   - 格式：`![图片名](file://{keyframes_path}/图片名)`
3. **禁用区域**：`# 总结` 和 `# 思考` 段落严禁插入图片
4. **格式禁忌**：
   - ❌ 禁止 `## # 摘要`、`## ## 步骤` 等错误标题
   - ✅ 正确：`# 摘要`、`## 操作步骤`
5. **🚫 严禁AI助手语言**：
   - ❌ 绝对禁止："当然可以！"、"以下是"、"我来为您"、"让我"
   - ❌ 绝对禁止："希望对您有帮助"、"欢迎告诉我"、"需要其他版本"
   - ❌ 绝对禁止：任何AI角色扮演、客服语言、推广话语
   - ✅ 要求：直接开始内容，直接结束内容，零AI痕迹

# 输出模板
```
# {{视频核心主题}}

# 摘要
{{3-5句话概括全文价值，突出知识点和实用性}}

## {{章节1：基于语义段落1}}
{{将匹配段落扩展为详细内容，在相关位置插入图片}}
![xxx.jpg](file://{keyframes_path}/xxx.jpg)

## {{章节2：基于语义段落2}}
{{扩展内容，确保图文语义对齐}}

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
        """构建用户提示词 - 完全基于语义匹配结果 + Few-shot示例"""

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
                            }
                        )
                        used_segments.add(seg_key)

        # 🎯 构建语义匹配指南
        if semantic_segments:
            guide = "## 🎯 语义匹配映射（请严格遵循）\n"
            for i, seg in enumerate(semantic_segments[:5]):  # 最多5条
                guide += (
                    f'- **图片**: `{seg["frame"]}`\n'
                    f'  **匹配段落**: "{seg["text"][:50]}..."\n'
                    f'  **置信度**: {seg["score"]:.2f} | **类型**: {seg["reason"]}\n\n'
                )
            if len(semantic_segments) > 5:
                guide += f"...（共 {len(semantic_segments)} 个语义匹配）\n"
        else:
            frame_names = [f["filename"] for f in frame_list]
            frames_list = ", ".join(frame_names)
            guide = f"## ⚠️ 无有效语义匹配，可用图片: {frames_list}\n"

        # 🔥 Few-shot 示例（根据领域动态调整）
        example = self._get_few_shot_example(content_domain, keyframes_path)

        return f"""{example}

【你的任务】
请基于以下转录内容和**语义匹配结果**，生成知识卡片：

## 📝 转录全文（供上下文参考）：
{transcript[:3000] if transcript else '无转录内容'}

{guide}

**关键指令**：
- 每个 `## 章节` 应对应一个语义匹配段落
- 在章节正文中插入匹配的图片（格式：`![xxx.jpg](file://{keyframes_path}/xxx.jpg)`）
- `# 总结` 和 `# 思考` 段落禁止插入任何图片
- 输出纯Markdown，不要额外解释
"""

    async def _generate_text_only_content(
        self, config, transcript: str, stream_callback
    ) -> Dict[str, Any]:
        """生成纯文本内容（无帧时的回退方案）"""
        system_prompt = """你是一位专业视频知识萃取专家，擅长将教学视频转化为结构化、高价值的知识卡片，包含标题、摘要、章节、总结、思考等完整结构。使用简体中文输出。"""

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

    def _get_few_shot_example(self, content_domain: str, keyframes_path: str) -> str:
        """根据内容领域获取Few-shot示例"""

        examples = {
            "cooking": f"""
【输出示例 - 烹饪教学】
# 宫保鸡丁的正宗做法详解

# 摘要
本文系统讲解宫保鸡丁的制作全流程，从食材准备到火候控制。关键技巧包括鸡肉腌制、花生米炸制和酱汁调配，适合家庭厨房复现。

## 食材准备与预处理
首先将鸡胸肉切成1.5厘米见方的丁，加入料酒、淀粉腌制10分钟。同时准备干辣椒段、花椒和炸好的花生米。![frame_00_30.jpg](file://{keyframes_path}/frame_00_30.jpg)

## 烹饪与调味关键
热锅凉油下鸡丁快速滑炒至变色，加入干辣椒和花椒爆香，最后倒入调好的酱汁（生抽2勺、醋1勺、糖1勺）翻炒均匀。

# 总结
宫保鸡丁的核心在于"快炒"和"酸甜平衡"，掌握这两点即可复刻餐厅风味。

# 思考
如何调整配方使其更适合儿童口味？能否用鸡腿肉替代鸡胸肉？
""",
            "exam_review": f"""
【输出示例 - 试卷评讲】
# 数学选择题解题技巧详解

# 摘要
本次评讲重点分析选择题的解题策略，包括排除法、特值法和图像法。通过典型例题演示，帮助学生掌握快速准确的解题思路。

## 排除法的应用技巧
对于复杂的函数题，可以通过代入特殊值快速排除错误选项。如本题中x=0时，只有选项B符合条件。![question_01.jpg](file://{keyframes_path}/question_01.jpg)

## 图像法解决函数问题
当题目涉及函数性质时，画出大致图像能直观判断答案。注意函数的单调性和特殊点的位置。

# 总结
选择题重在方法，掌握排除法、特值法和图像法，能大幅提高解题效率和准确率。

# 思考
在什么情况下应该优先使用排除法？如何快速识别适合用图像法的题目？
""",
            "meeting": f"""
【输出示例 - 会议纪要】
# 产品规划会议纪要

# 摘要
本次会议确定了Q4产品路线图，重点讨论了用户反馈处理、新功能开发优先级和资源分配方案。会议达成3项关键决议，明确了各部门职责。

## 用户反馈处理机制
产品经理汇报了近期用户反馈统计，主要集中在界面优化和性能提升两个方面。![feedback_chart.jpg](file://{keyframes_path}/feedback_chart.jpg) 决定建立快速响应机制，48小时内给出初步方案。

## 新功能开发优先级
技术总监提出了功能开发的优先级排序：1）核心功能优化 2）用户体验改进 3）新特性开发。预计Q4完成前两项，新特性推至Q1。

# 总结
会议明确了Q4工作重点，建立了用户反馈快速响应机制，确保产品迭代节奏稳定推进。

# 思考
如何平衡新功能开发与现有功能优化？用户反馈的优先级如何科学评估？
""",
            "education": f"""
【输出示例 - 教育内容】
# Python函数基础知识详解

# 摘要
本节课介绍Python函数的定义、参数传递和返回值机制。通过实例演示函数的创建和调用过程，帮助初学者建立函数编程思维。

## 函数的定义与语法
Python中使用def关键字定义函数，基本语法为def function_name(parameters)。函数名应该具有描述性，参数可以设置默认值。![function_syntax.jpg](file://{keyframes_path}/function_syntax.jpg)

## 参数传递机制
Python支持位置参数、关键字参数和可变参数。理解不同参数类型的使用场景，能让代码更加灵活和可读。

# 总结
函数是代码复用的基础，掌握函数定义、调用和参数传递，是Python编程的重要基础技能。

# 思考
什么时候应该将代码封装成函数？如何设计函数的参数结构更合理？
""",
            "meeting": f"""
【输出示例 - 会议纪要】
# 产品规划会议纪要

# 摘要
本次会议确定了Q4产品路线图，重点讨论了用户反馈处理、新功能开发优先级和资源分配方案。会议达成3项关键决议，明确了各部门职责和时间节点。

## 用户反馈处理机制优化
产品经理汇报了近期用户反馈统计，主要集中在界面优化和性能提升两个方面。![feedback_chart.jpg](file://{keyframes_path}/feedback_chart.jpg) 决定建立快速响应机制，技术部门负责48小时内给出初步方案，产品部门跟进用户沟通。

## 新功能开发优先级确认
技术总监提出了功能开发的优先级排序：1）核心功能优化（优先级最高）2）用户体验改进（中等优先级）3）新特性开发（较低优先级）。预计Q4完成前两项，新特性推至Q1开发。

## 资源分配与时间安排
人力资源部确认了项目人员配置，开发团队增加2名前端工程师，测试团队保持现有规模。项目里程碑设定为每两周一次评审，月底进行阶段性总结。

# 总结
会议明确了Q4工作重点，建立了用户反馈快速响应机制，确保产品迭代节奏稳定推进。各部门职责分工明确，时间节点具体可执行。

# 思考
如何平衡新功能开发与现有功能优化的资源投入？用户反馈的优先级评估标准是否需要进一步细化？
""",
        }

        return examples.get(content_domain, examples["education"])

    def _post_process_content(self, content: str) -> str:
        """后处理内容 - 修复常见格式错误并移除AI第一人称话语"""
        import re

        # 🚫 移除AI第一人称开头话语
        # 匹配常见的AI开头模式
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
            content = re.sub(pattern, "", content, flags=re.MULTILINE | re.DOTALL)

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
