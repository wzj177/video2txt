#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI内容生成工厂
支持内容卡片生成
集成智能帧提取功能
"""

import logging
import json
import sys
import re
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
# 导入设置API中的角色映射函数和提示词模板函数
from biz.routes.settings_api import get_role_name
from biz.services.template_skill_service import (
    template_skill_service,
    ROLE_TEMPLATE_CATEGORIES,
)

logger = logging.getLogger(__name__)


class OutputType(Enum):
    """AI输出类型枚举"""

    CONTENT_CARD = "content_card"
    MIND_MAP = "mind_map"
    FLASHCARDS = "flashcards"


@dataclass
class GenerationConfig:
    """生成配置"""

    output_type: OutputType
    language: str = "zh"
    model: str = "default"
    max_tokens: int = 2000
    temperature: float = 0.7


@dataclass
class StaticDomain:
    value: str


@dataclass
class StaticAnalysisResult:
    primary_domain: StaticDomain
    secondary_domains: List[StaticDomain]
    confidence: float
    key_topics: List[str]
    content_style: str
    target_audience: str
    content_length: str
    visual_elements: List[str]


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
        self._var_pattern = re.compile(r"{(?P<key>[a-zA-Z0-9_]+)}")

    def _format_prompt(self, template: Optional[str], variables: Dict[str, Any]) -> Optional[str]:
        if not template:
            return template

        def replace(match):
            key = match.group("key")
            return str(variables.get(key, match.group(0)))

        return self._var_pattern.sub(replace, template)

    def _apply_skill_template(
        self,
        template_category: str,
        template_vars: Dict[str, Any],
        dynamic_prompts: Dict[str, str],
        role_key: Optional[str] = None,
        role_category: str = "content_card",
        media_type: Optional[str] = None,
    ) -> Dict[str, str]:
        render_vars = dict(template_vars)
        # transcript和timed_transcript在具体生成阶段根据上下文注入，提前保留占位符
        render_vars["transcript"] = "{transcript}"
        render_vars["timed_transcript"] = "{timed_transcript}"
        if media_type == "video":
            render_vars.setdefault("image_strategy", "{image_strategy}")
            render_vars.setdefault("keyframes_path", "{keyframes_path}")
            render_vars.setdefault("media_duration", "{media_duration}")
            render_vars.setdefault("cover_frame", "{cover_frame}")
            render_vars.setdefault("frame_list", "{frame_list}")
            render_vars.setdefault("frame_count", "{frame_count}")
            render_vars.setdefault("mapping_count", "{mapping_count}")
        prompts = template_skill_service.render_role_template_parts(
            role_key or "general",
            role_category or template_category,
            render_vars,
        )
        if not prompts:
            return dynamic_prompts

        system_prompt = prompts.get("system_prompt")
        user_prompt = prompts.get("user_prompt")

        if media_type == "audio":
            system_prompt = prompts.get("audio_system_prompt") or system_prompt
            user_prompt = prompts.get("audio_user_prompt") or user_prompt
        elif media_type == "video":
            system_prompt = prompts.get("video_system_prompt") or system_prompt
            user_prompt = prompts.get("video_user_prompt") or user_prompt

        if system_prompt:
            selected_skill_key = template_skill_service.get_skill_for_role(
                role_key or "general", role_category or template_category
            )
            system_prompt = template_skill_service.build_system_prompt(
                role_key or "general",
                system_prompt,
                render_vars,
                selected_skill_key=selected_skill_key,
                categories=list(ROLE_TEMPLATE_CATEGORIES),
            )
            dynamic_prompts["system_prompt"] = system_prompt

        if user_prompt:
            dynamic_prompts["user_prompt_template"] = user_prompt

        return dynamic_prompts

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

    def _format_mmss(self, value: Any) -> str:
        """将秒数或timedelta格式化为 mm:ss"""
        try:
            if hasattr(value, "total_seconds"):
                seconds = float(value.total_seconds())
            else:
                seconds = float(value or 0)
        except Exception:
            seconds = 0.0
        seconds = max(seconds, 0.0)
        minutes = int(seconds // 60)
        sec = int(seconds % 60)
        return f"{minutes:02d}:{sec:02d}"

    def _build_timed_transcript(self, subtitles: List[Dict[str, Any]]) -> str:
        """构建带时间点的转录文本（mm:ss）"""
        if not subtitles:
            return ""
        lines = []
        for subtitle in subtitles:
            start = subtitle.get("start", 0)
            end = subtitle.get("end", 0)
            text = subtitle.get("text") or subtitle.get("content") or ""
            if not text:
                continue
            line = f"[{self._format_mmss(start)}-{self._format_mmss(end)}] {text}"
            lines.append(line)
        return "\n".join(lines)

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
            output_type: 输出类型 (content_card)
            transcript: 转录文本内容
            video_path: 视频文件路径（可选）
            audio_path: 音频文件路径（可选）
            subtitles: 字幕列表（可选）
            **kwargs: 其他参数

        Returns:
            生成结果
        """
        try:
            logger.info(f"AI工厂generate方法被调用，output_type={output_type}")
            logger.info(f"参数检查: subtitles数量={len(subtitles) if subtitles else 0}")
            logger.info(f"kwargs键: {list(kwargs.keys())}")

            # 验证输出类型
            if output_type not in [t.value for t in OutputType]:
                raise ValueError(f"不支持的输出类型: {output_type}")

            #  第一步：确定内容角色（不启用智能识别）
            content_role = kwargs.get("content_role") or "general"
            if content_role == "auto":
                content_role = "general"

            analysis_result = StaticAnalysisResult(
                primary_domain=StaticDomain(content_role),
                secondary_domains=[],
                confidence=1.0,
                key_topics=[],
                content_style="通用",
                target_audience="通用用户",
                content_length="中等",
                visual_elements=[],
            )

            domain_value = content_role
            dynamic_prompts: Dict[str, str] = {}

            role_category_map = {
                "content_card": "content_card",
                "mind_map": "mind_map",
                "flashcards": "flashcards",
            }
            template_role_category = role_category_map.get(output_type, "content_card")
            template_role_name = get_role_name(
                domain_value, template_role_category, "内容专家"
            )
            key_topics_value = getattr(analysis_result, "key_topics", [])
            if isinstance(key_topics_value, list):
                key_topics_str = ", ".join(key_topics_value[:8])
            else:
                key_topics_str = str(key_topics_value) if key_topics_value else ""

            template_vars = {
                "role_name": template_role_name,
                "domain": domain_value,
                "target_audience": getattr(
                    analysis_result, "target_audience", "通用用户"
                ),
                "key_topics": key_topics_str,
                "content_style": getattr(
                    analysis_result, "content_style", "清晰简洁"
                ),
                "transcript": transcript or "",
                "content_type": output_type,
                "timed_transcript": transcript or "",
            }

            frame_info_type = (frame_info or {}).get("type")
            if frame_info_type == "video" or video_path:
                media_type = "video"
            elif audio_path:
                media_type = "audio"
            else:
                media_type = None

            dynamic_prompts = self._apply_skill_template(
                output_type,
                template_vars,
                dynamic_prompts,
                role_key=domain_value,
                role_category=template_role_category,
                media_type=media_type,
            )

            # 获取配置
            config = GenerationConfig(
                output_type=OutputType(output_type),
                language=kwargs.get("language", "zh"),
                model=kwargs.get("model", "default"),
                max_tokens=kwargs.get("max_tokens", 2000),
                temperature=kwargs.get("temperature", 0.7),
            )

            # 验证增强版转录文件是否存在（仅视频文件必需）
            enhanced_transcript_file = kwargs.get("enhanced_transcript_file")
            frame_info_type = kwargs.get("frame_info", {}).get("type", "video")
            is_video = frame_info_type == "video"

            logger.info(f"文件类型检查: type={frame_info_type}, is_video={is_video}")

            if is_video:
                # 视频文件需要增强版转录（包含帧映射）
                # 特殊处理：如果明确传递None，说明是纯文本模式（无帧）或摘要生成等不需要增强版转录的场景
                if enhanced_transcript_file is None:
                    logger.info(
                        "纯文本模式或摘要生成：跳过增强版转录文件验证（视频无关键帧或特殊场景）"
                    )
                elif (
                        not enhanced_transcript_file
                        or not Path(enhanced_transcript_file).exists()
                ):
                    error_msg = "视频AI内容生成必须使用增强版转录文件(transcription_format.json)，当前文件不存在或未传递"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                else:
                    logger.info(
                        f"视频AI内容生成使用增强版转录: {enhanced_transcript_file}"
                    )

                # 验证增强版映射的有效性（仅当使用增强版转录时）
                if enhanced_transcript_file is not None:
                    if not subtitles or not any(
                            "frame" in segment for segment in subtitles
                    ):
                        error_msg = "传递的subtitles缺少帧映射信息，无法进行AI内容生成"
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    frame_mapping_count = sum(1 for s in subtitles if s.get("frame"))
                    logger.info(
                        f"验证通过：{frame_mapping_count} 个时间段包含帧映射信息"
                    )
            else:
                # 音频文件不需要增强版转录和帧映射
                logger.info(f"音频文件处理模式，跳过增强版转录验证")

            #  关键修复：使用传入的帧信息，而不是重新处理
            if frame_info is None:
                # 如果没有传入帧信息，则进行处理（向后兼容）
                frame_info = await self._process_frames(
                    video_path, audio_path, subtitles, **kwargs
                )

            #  第二步：使用动态提示词生成内容
            kwargs.update(
                {
                    "analysis_result": analysis_result,
                    "dynamic_prompts": dynamic_prompts,
                    "subtitles": subtitles,  # 关键修复：确保subtitles参数被传递
                    "content_role": content_role,
                }
            )

            # 根据类型生成内容
            if output_type == OutputType.CONTENT_CARD.value:
                logger.info("即将调用 _generate_content_card_smart")
                logger.info(f"调用前kwargs: {list(kwargs.keys())}")
                logger.info(f"调用前frame_info: {frame_info}")
                return await self._generate_content_card_smart(
                    config, transcript, frame_info, stream_callback, **kwargs
                )
            elif output_type == OutputType.MIND_MAP.value:
                return await self._generate_template_text(
                    output_type, config, transcript, frame_info, stream_callback, **kwargs
                )
            elif output_type == OutputType.FLASHCARDS.value:
                return await self._generate_template_text(
                    output_type, config, transcript, frame_info, stream_callback, **kwargs
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
            return {"success": True, "results": results, "message": "内容生成完成"}

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
            "使用了向后兼容的帧处理方法，建议从video_service传递frame_info"
        )

        frame_info = {
            "frames": [],
            "cover_frame": None,
            "frame_dir": "",
            "has_frames": False,
        }

        try:
            if video_path and subtitles:
                # 使用固定间隔提取（2秒一帧）
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

                logger.info(f"固定间隔提取了 {len(frames)} 个视频关键帧（2秒间隔）")

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

                logger.info(f"生成了 {len(frames)} 个音频可视化图像")

        except Exception as e:
            logger.error(f"帧处理失败: {e}")

        return frame_info

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
            logger.info("🚀 进入 _generate_content_card_smart 方法")
            logger.info(f"kwargs键: {list(kwargs.keys())}")
            logger.info(f"frame_info: {frame_info}")
            logger.info(f"kwargs中subtitles数量: {len(kwargs.get('subtitles', []))}")
            if kwargs.get("subtitles"):
                logger.info(f"kwargs中第一个subtitle: {kwargs.get('subtitles')[0]}")

            analysis_result = kwargs.get("analysis_result")
            dynamic_prompts = kwargs.get("dynamic_prompts") or {}
            system_prompt_template = dynamic_prompts.get("system_prompt", "")
            user_prompt_template = dynamic_prompts.get("user_prompt_template", "")

            primary_domain = (
                getattr(analysis_result, "primary_domain", None)
                if analysis_result
                else None
            )
            domain_value = (
                primary_domain.value
                if primary_domain and hasattr(primary_domain, "value")
                else "general"
            )
            runtime_prompt_vars = {
                "domain": domain_value,
                "content_type": "内容卡片",
                "transcript": (transcript or "")[:3000],
                "timed_transcript": (transcript or "")[:3000],
                "target_audience": getattr(analysis_result, "target_audience", "通用受众")
                if analysis_result
                else "通用受众",
                "content_style": getattr(analysis_result, "content_style", "通俗易懂")
                if analysis_result
                else "通俗易懂",
            }
            # 添加图像策略（如果有帧信息）
            if frame_info.get("has_frames", False):
                frames = frame_info.get("frames", [])
                subtitles = kwargs.get("subtitles", [])
                task_id = kwargs.get("task_id", "")

                # 调试日志
                logger.info(
                    f"AI生成器调试: subtitles数量={len(subtitles)}, kwargs键={list(kwargs.keys())}"
                )
                logger.info(
                    f"kwargs中的subtitles数量: {len(kwargs.get('subtitles', []))}"
                )
                if subtitles and len(subtitles) > 0:
                    logger.info(f"第一个subtitle: {subtitles[0]}")
                if kwargs.get("subtitles") and len(kwargs.get("subtitles", [])) > 0:
                    logger.info(f"kwargs中第一个subtitle: {kwargs.get('subtitles')[0]}")

                # 使用内容卡片生成器的智能匹配功能
                return await self.content_card_generator.generate_content_card(
                    config=config,
                    transcript=transcript,
                    frame_info=frame_info,
                    stream_callback=stream_callback,
                    custom_system_prompt=system_prompt_template,  # 传递模板或自定义系统提示词
                    custom_user_prompt=user_prompt_template,
                    prompts_composed=True,
                    **kwargs,
                )
            else:
                # 纯文本生成
                system_prompt = self._format_prompt(
                    system_prompt_template, runtime_prompt_vars
                )
                user_prompt = self._format_prompt(
                    user_prompt_template, runtime_prompt_vars
                )

                if stream_callback:
                    await stream_callback(
                        "ai_generating",
                        {
                            "type": "content_card",
                            "message": f"正在生成{domain_value}领域内容卡片...",
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
                        {"type": "content_card", "message": "智能内容卡片生成完成"},
                    )

                return {
                    "success": True,
                    "type": "content_card",
                    "content": content,
                    "format": "text",
                    "analysis_result": (
                        analysis_result.__dict__
                        if analysis_result and hasattr(analysis_result, "__dict__")
                        else {}
                    ),
                    # 🆕 添加提示词信息
                    "prompts": {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "domain": (domain_value if analysis_result else "通用"),
                        "role_name": (
                            config.content_role
                            if hasattr(config, "content_role")
                            else "内容专家"
                        ),
                    },
                }
        except Exception as e:
            logger.error(f"智能内容卡片生成失败: {e}")
            return {"error": str(e), "success": False}

    async def _generate_template_text(
            self,
            output_type: str,
            config: GenerationConfig,
            transcript: str,
            frame_info: Dict[str, Any],
            stream_callback=None,
            **kwargs,
    ) -> Dict[str, Any]:
        """基于模板生成文本类内容（思维导图/学习闪卡）"""
        try:
            analysis_result = kwargs.get("analysis_result")
            dynamic_prompts = kwargs.get("dynamic_prompts") or {}
            system_prompt_template = dynamic_prompts.get("system_prompt", "")
            user_prompt_template = dynamic_prompts.get("user_prompt_template", "")

            primary_domain = (
                getattr(analysis_result, "primary_domain", None)
                if analysis_result
                else None
            )
            domain_value = (
                primary_domain.value
                if primary_domain and hasattr(primary_domain, "value")
                else "general"
            )
            role_name = get_role_name(domain_value, output_type, "内容专家")

            runtime_prompt_vars = {
                "domain": domain_value,
                "role_name": role_name,
                "target_audience": getattr(analysis_result, "target_audience", "通用受众")
                if analysis_result
                else "通用受众",
                "content_style": getattr(analysis_result, "content_style", "通俗易懂")
                if analysis_result
                else "通俗易懂",
                "key_topics": ", ".join(getattr(analysis_result, "key_topics", [])[:8])
                if analysis_result
                else "",
                "transcript": (transcript or "")[:6000],
                "timed_transcript": "",
                "content_type": output_type,
            }
            subtitles = kwargs.get("subtitles") or []
            timed_transcript = self._build_timed_transcript(subtitles)
            if timed_transcript:
                runtime_prompt_vars["timed_transcript"] = timed_transcript[:6000]
            else:
                runtime_prompt_vars["timed_transcript"] = (transcript or "")[:6000]

            system_prompt = self._format_prompt(
                system_prompt_template, runtime_prompt_vars
            )
            user_prompt = self._format_prompt(
                user_prompt_template, runtime_prompt_vars
            )

            if stream_callback:
                await stream_callback(
                    "ai_generating",
                    {
                        "type": output_type,
                        "message": f"正在生成{role_name}内容...",
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
                    "ai_content_chunk", {"type": output_type, "content": content}
                )
                await stream_callback(
                    "ai_content_complete",
                    {"type": output_type, "message": "内容生成完成"},
                )

            return {
                "success": True,
                "type": output_type,
                "content": content,
                "format": "text",
                "frame_info": frame_info,
                "analysis_result": (
                    analysis_result.__dict__
                    if analysis_result and hasattr(analysis_result, "__dict__")
                    else {}
                ),
                "prompts": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "role_name": role_name,
                    "domain": domain_value,
                },
            }
        except Exception as e:
            logger.error(f"模板内容生成失败: {e}")
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
