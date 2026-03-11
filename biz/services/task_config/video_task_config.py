#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频任务配置的后置处理
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from biz.services.template_skill_service import template_skill_service

logger = logging.getLogger(__name__)

ALLOWED_AI_TYPES = {"content_card", "mind_map", "flashcards"}


def _normalize_role_key(role_key: str) -> str:
    value = (role_key or "").strip()
    if not value or value == "auto":
        return "general"
    return value


def _normalize_ai_types(types: List[str]) -> List[str]:
    if not types:
        return []
    return [item for item in types if item in ALLOWED_AI_TYPES]


def finalize_video_task_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """创建任务后置处理：统一角色与AI输出类型"""
    if not isinstance(config, dict):
        return {}

    role_key = _normalize_role_key(config.get("content_role"))
    if not template_skill_service.get_role(role_key):
        logger.warning("内容角色不存在，回退为general: %s", role_key)
        role_key = "general"
    config["content_role"] = role_key

    ai_output_types = _normalize_ai_types(config.get("ai_output_types") or [])
    if not ai_output_types:
        allowed = template_skill_service.get_role_content_types(role_key)
        ai_output_types = _normalize_ai_types(allowed)
        if not ai_output_types:
            ai_output_types = ["content_card"]
    config["ai_output_types"] = ai_output_types

    return config
