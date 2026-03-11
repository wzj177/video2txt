#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词模板（Skill）服务
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from sqlalchemy import select

from biz.database.connection import get_database_manager
from biz.database.repositories import (
    TemplateSkillRepository,
    RoleTemplateMappingRepository,
    TemplateRoleRepository,
    RoleTemplateRepository,
)
from biz.models.template import RoleTemplate

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_SKILL_DIR = PROJECT_ROOT / "config" / "template_skills"
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"
SETTINGS_EXAMPLE_FILE = PROJECT_ROOT / "config" / "settings.example.json"

PROMPT_SECTION_PATTERN = re.compile(r"prompt", re.IGNORECASE)
CODE_FENCE_PATTERN = re.compile(r"^```[\w-]*\n(?P<body>.*?)\n```$", re.DOTALL)

ROLE_TEMPLATE_CATEGORIES = (
    "content_card",
    "mind_map",
    "flashcards",
)

GLOBAL_SYSTEM_CONSTRAINTS = """# 全局约束
- 只能基于转录文本 / 时间点 / 关键帧信息生成内容
- 禁止新增转录中未出现的事实、建议、方法论或案例
- 时间点必须来自输入内容
- 不臆测画面细节，图片仅用于定位
- 信息不足时明确说明“未提及/无法判断”
"""

ROLE_CATEGORY_TO_SKILL_CATEGORY = {
    "content_card": "content_card",
    "mind_map": "mind_map",
    "flashcards": "flashcards",
}

DEFAULT_ROLE_KEYS = (
    "general",
    "education",
    "meeting",
    "emotion",
)


@dataclass
class SkillRecord:
    """内部使用的模板表示"""

    skill_key: str
    name: str
    category: str
    scenario: Optional[str]
    description: Optional[str]
    prompt_schema: Dict[str, str]
    variables: List[Dict[str, Any]]
    tags: List[str]
    skill_markdown: str
    is_default: bool = True
    is_active: bool = True
    record_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.record_id,
            "skill_key": self.skill_key,
            "name": self.name,
            "category": self.category,
            "scenario": self.scenario,
            "description": self.description,
            "prompt_schema": self.prompt_schema,
            "variables": self.variables,
            "tags": self.tags,
            "skill_markdown": self.skill_markdown,
            "is_default": self.is_default,
            "is_active": self.is_active,
        }


@dataclass
class RoleRecord:
    """角色信息"""

    role_key: str
    name: str
    description: Optional[str]
    system_prompt: str
    icon: Optional[str]
    is_default: bool = False
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_key": self.role_key,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "icon": self.icon,
            "is_default": self.is_default,
            "is_active": self.is_active,
        }


@dataclass
class RoleTemplateRecord:
    """角色模板信息"""

    role_key: str
    category: str
    name: Optional[str]
    description: Optional[str]
    skill_markdown: str
    prompt_schema: Dict[str, str]
    is_active: bool = True
    base_skill_key: Optional[str] = None
    old_content: Optional[str] = None
    record_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.record_id,
            "role_key": self.role_key,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "skill_markdown": self.skill_markdown,
            "prompt_schema": self.prompt_schema,
            "is_active": self.is_active,
            "base_skill_key": self.base_skill_key,
            "old_content": self.old_content,
        }


class TemplateSkillService:
    """管理 Skill 风格提示词模板的服务"""

    def __init__(self):
        self._cache: Dict[str, SkillRecord] = {}
        self._default_skills: List[SkillRecord] = self._load_default_skills()
        self._role_cache: Dict[str, RoleRecord] = {}
        self._role_template_cache: Dict[str, Dict[str, RoleTemplateRecord]] = {}
        self._legacy_role_mapping_cache: Dict[str, Dict[str, str]] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._refresh_cache_from_defaults()

    async def _ensure_initialized(self):
        """确保在执行需要数据库的操作前已完成初始化"""
        if self._initialized:
            return
        await self.initialize()

    def _refresh_cache_from_defaults(self):
        """将默认模板写入缓存（用于数据库尚未加载时的兜底）"""
        self._cache = {record.skill_key: record for record in self._default_skills}
        self._role_cache = self._build_default_role_cache()
        self._role_template_cache = self._build_default_role_template_cache()
        self._legacy_role_mapping_cache = self._build_default_role_mapping()

    def _load_roles_from_settings(self) -> Dict[str, Dict[str, Any]]:
        """从配置文件中读取角色配置"""
        for path in (SETTINGS_FILE, SETTINGS_EXAMPLE_FILE):
            try:
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                roles = data.get("roles") or {}
                if isinstance(roles, dict) and roles:
                    return roles
            except Exception as exc:
                logger.warning("读取角色配置失败 %s: %s", path, exc)
        return {}

    def _build_default_role_cache(self) -> Dict[str, RoleRecord]:
        """构建默认角色缓存"""
        roles: Dict[str, RoleRecord] = {}
        raw_roles = self._load_roles_from_settings()

        if raw_roles:
            for role_key, config in raw_roles.items():
                name = config.get("name") or config.get("label") or role_key
                description = config.get("description") or ""
                icon = config.get("icon") or ""
                system_prompt = config.get("system_prompt") or f"你是一名{name}"
                roles[role_key] = RoleRecord(
                    role_key=role_key,
                    name=name,
                    description=description,
                    system_prompt=system_prompt,
                    icon=icon,
                    is_default=role_key in DEFAULT_ROLE_KEYS,
                    is_active=True,
                )

        if "general" not in roles:
            roles["general"] = RoleRecord(
                role_key="general",
                name="通用专家",
                description="通用内容分析与整理",
                system_prompt="你是一名通用专家",
                icon="✨",
                is_default=True,
                is_active=True,
            )

        return roles

    def _build_default_role_template_cache(
        self,
    ) -> Dict[str, Dict[str, RoleTemplateRecord]]:
        """基于默认模板构建角色模板缓存"""
        cache: Dict[str, Dict[str, RoleTemplateRecord]] = {}
        roles = self._role_cache or self._build_default_role_cache()

        for role_key in roles.keys():
            role_map: Dict[str, RoleTemplateRecord] = {}
            for category in ROLE_TEMPLATE_CATEGORIES:
                base = self._find_default_skill(category)
                if not base:
                    continue
                role_map[category] = RoleTemplateRecord(
                    role_key=role_key,
                    category=category,
                    name=base.name,
                    description=base.description,
                    skill_markdown=base.skill_markdown,
                    prompt_schema=base.prompt_schema,
                    is_active=True,
                    base_skill_key=base.skill_key,
                )
            cache[role_key] = role_map
        return cache

    async def initialize(self):
        """确保数据库已同步默认模板并刷新缓存"""
        async with self._lock:
            db_manager = get_database_manager()
            async with db_manager.get_session() as session:
                template_repo = TemplateSkillRepository(session)
                mapping_repo = RoleTemplateMappingRepository(session)
                role_repo = TemplateRoleRepository(session)
                role_template_repo = RoleTemplateRepository(session)

                if not self._initialized:
                    for record in self._default_skills:
                        existing = await template_repo.get_by_key(record.skill_key)
                        if existing:
                            if existing.is_default and existing.skill_markdown != record.skill_markdown:
                                existing.name = record.name
                                existing.category = record.category
                                existing.scenario = record.scenario
                                existing.description = record.description
                                existing.prompt_schema = record.prompt_schema
                                existing.variables = record.variables
                                existing.tags = record.tags
                                existing.skill_markdown = record.skill_markdown
                                await session.flush()

                                role_templates = await session.execute(
                                    select(RoleTemplate).where(
                                        RoleTemplate.base_skill_key == record.skill_key
                                    )
                                )
                                for tpl in role_templates.scalars():
                                    if tpl.old_content:
                                        continue
                                    tpl.name = record.name
                                    tpl.description = record.description
                                    tpl.skill_markdown = record.skill_markdown
                                    tpl.prompt_schema = record.prompt_schema
                                await session.flush()
                            continue
                        await template_repo.create(
                            skill_key=record.skill_key,
                            name=record.name,
                            category=record.category,
                            scenario=record.scenario,
                            description=record.description,
                            prompt_schema=record.prompt_schema,
                            variables=record.variables,
                            tags=record.tags,
                            skill_markdown=record.skill_markdown,
                            is_default=True,
                            is_active=True,
                        )
                    await self._ensure_roles(role_repo)
                    await self._ensure_role_templates(
                        role_repo, role_template_repo
                    )
                    await self._ensure_role_mappings(mapping_repo)
                    self._initialized = True

                await self._reload_cache(template_repo)
                await self._reload_role_mapping_cache(mapping_repo)
                await self._reload_role_cache(role_repo)
                await self._reload_role_template_cache(role_template_repo)

            logger.info("模板技能服务已初始化，缓存模板数量: %s", len(self._cache))

    def get_prompt(self, template_type: str, prompt_part: str = "system_prompt") -> str:
        """获取指定模板的某个提示词部分"""
        record = self._cache.get(template_type)
        if not record:
            return ""
        return record.prompt_schema.get(prompt_part, "")

    def get_prompt_map(self) -> Dict[str, Dict[str, str]]:
        """返回旧版API兼容结构"""
        return {
            key: record.prompt_schema for key, record in self._cache.items() if record
        }

    def get_template_meta(self, skill_key: Optional[str]) -> Optional[Dict[str, Any]]:
        """返回模板的基础元数据"""
        if not skill_key:
            return None
        record = self._cache.get(skill_key)
        if not record:
            return None
        return record.to_dict()

    def get_skill_for_role(self, role_key: Optional[str], category: str) -> str:
        """根据角色与类别获取实际使用的模板key"""
        role_key = (role_key or "general").strip() or "general"
        normalized = self._normalize_role_category(category)

        template = self._get_role_template_record(role_key, normalized)
        if not template:
            template = self._get_role_template_record("general", normalized)

        if template and template.base_skill_key:
            skill_key = template.base_skill_key
        else:
            skill_key = normalized

        if skill_key not in self._cache:
            # 兜底使用默认模板
            default_key = ROLE_CATEGORY_TO_SKILL_CATEGORY.get(normalized)
            if default_key in self._cache:
                skill_key = default_key
            elif self._cache:
                skill_key = next(iter(self._cache.keys()))
            else:
                skill_key = ""

        return skill_key

    async def list_role_mappings(self) -> Dict[str, Dict[str, str]]:
        """获取当前的角色-模板映射"""
        await self._ensure_initialized()
        mapping: Dict[str, Dict[str, str]] = {
            category: {} for category in ROLE_CATEGORY_TO_SKILL_CATEGORY
        }
        for role_key, role_map in self._role_template_cache.items():
            for category, template in role_map.items():
                category_map = mapping.setdefault(category, {})
                category_map[role_key] = (
                    template.base_skill_key or template.category
                )
        return json.loads(json.dumps(mapping))

    async def update_role_mappings(
        self, mappings: Dict[str, Dict[str, str]]
    ) -> None:
        """批量更新角色模板映射"""
        await self._ensure_initialized()
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = RoleTemplateMappingRepository(session)
            for category, role_map in (mappings or {}).items():
                if category not in ROLE_CATEGORY_TO_SKILL_CATEGORY:
                    continue
                for role_key, skill_key in (role_map or {}).items():
                    if not skill_key:
                        continue
                    await repo.upsert(role_key, category, skill_key)

            await self._reload_role_mapping_cache(repo)

    async def list_roles(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        await self._ensure_initialized()
        roles = [
            role
            for role in self._role_cache.values()
            if include_inactive or role.is_active
        ]
        roles.sort(key=lambda item: (not item.is_default, item.name))
        return [role.to_dict() for role in roles]

    def get_role(self, role_key: Optional[str]) -> Optional[RoleRecord]:
        if not role_key:
            return None
        return self._role_cache.get(role_key)

    def get_role_name(
        self, role_key: Optional[str], default: str = "内容专家"
    ) -> str:
        role_key = (role_key or "").strip()
        record = self._role_cache.get(role_key) or self._role_cache.get("general")
        return record.name if record else default

    def get_role_map(self) -> Dict[str, str]:
        return {
            key: role.name
            for key, role in self._role_cache.items()
            if role.is_active
        }

    def get_role_content_types(self, role_key: Optional[str]) -> List[str]:
        role_key = (role_key or "general").strip() or "general"
        role_map = self._role_template_cache.get(role_key)
        if not role_map:
            role_map = self._role_template_cache.get("general") or {}
        return [
            key
            for key, item in role_map.items()
            if key in ROLE_TEMPLATE_CATEGORIES and item.is_active
        ]

    async def list_role_templates(
        self, role_key: str, include_inactive: bool = True
    ) -> List[Dict[str, Any]]:
        await self._ensure_initialized()
        role_map = self._role_template_cache.get(role_key) or {}
        records = [
            template
            for template in role_map.values()
            if template.category in ROLE_TEMPLATE_CATEGORIES
            and (include_inactive or template.is_active)
        ]
        records.sort(key=lambda item: item.category)
        return [record.to_dict() for record in records]

    async def create_role(
        self,
        role_key: str,
        name: str,
        description: str = "",
        system_prompt: str = "",
        icon: str = "",
        content_categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        role_key = (role_key or "").strip()
        if not role_key:
            raise ValueError("角色标识不能为空")
        if not name:
            raise ValueError("角色名称不能为空")

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            role_repo = TemplateRoleRepository(session)
            role_template_repo = RoleTemplateRepository(session)

            existing = await role_repo.get_by_key(role_key)
            if existing:
                raise ValueError("角色已存在")

            role = await role_repo.create(
                role_key=role_key,
                name=name,
                description=description,
                system_prompt=system_prompt or f"你是一名{name}",
                icon=icon,
                is_default=False,
                is_active=True,
            )
            active_categories = None
            if content_categories:
                active_categories = {
                    self._normalize_role_category(category)
                    for category in content_categories
                    if category
                }
            await self._ensure_role_templates(
                role_repo,
                role_template_repo,
                only_role=role_key,
                active_categories=active_categories,
            )

        await self.refresh_cache()
        return RoleRecord(
            role_key=role.role_key,
            name=role.name,
            description=role.description,
            system_prompt=role.system_prompt or "",
            icon=role.icon,
            is_default=role.is_default,
            is_active=role.is_active,
        ).to_dict()

    async def update_role(self, role_key: str, **kwargs) -> Dict[str, Any]:
        await self._ensure_initialized()
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            role_repo = TemplateRoleRepository(session)
            role = await role_repo.get_by_key(role_key)
            if not role:
                raise ValueError("角色不存在")

            allowed = {"name", "description", "system_prompt", "icon", "is_active"}
            for key, value in kwargs.items():
                if key in allowed and value is not None:
                    setattr(role, key, value)

            await session.flush()
            await session.refresh(role)

        await self.refresh_cache()
        return {
            "role_key": role.role_key,
            "name": role.name,
            "description": role.description,
            "system_prompt": role.system_prompt,
            "icon": role.icon,
            "is_default": role.is_default,
            "is_active": role.is_active,
        }

    async def delete_role(self, role_key: str) -> None:
        await self._ensure_initialized()
        if role_key == "general":
            raise ValueError("通用角色不可删除")

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            role_repo = TemplateRoleRepository(session)
            role_template_repo = RoleTemplateRepository(session)
            role = await role_repo.get_by_key(role_key)
            if not role:
                return

            templates = await role_template_repo.list_by_role(role_key)
            for tpl in templates:
                await role_template_repo.delete(tpl.id)
            await role_repo.delete(role.id)

        await self.refresh_cache()

    async def update_role_template(
        self,
        role_key: str,
        category: str,
        skill_markdown: str,
        is_active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        if not skill_markdown:
            raise ValueError("模板内容不能为空")

        normalized = self._normalize_role_category(category)
        record = self._build_record_from_markdown(skill_markdown)

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            role_template_repo = RoleTemplateRepository(session)
            existing = await role_template_repo.get_by_role_and_category(
                role_key, normalized
            )
            if existing:
                existing.old_content = existing.skill_markdown
                existing.skill_markdown = skill_markdown
                existing.prompt_schema = record.prompt_schema
                existing.name = record.name
                existing.description = record.description
                if is_active is not None:
                    existing.is_active = is_active
                await session.flush()
                await session.refresh(existing)
                updated = existing
            else:
                base = self._find_default_skill(normalized)
                updated = await role_template_repo.create(
                    role_key=role_key,
                    category=normalized,
                    name=record.name,
                    description=record.description,
                    skill_markdown=skill_markdown,
                    prompt_schema=record.prompt_schema,
                    old_content=None,
                    is_active=True if is_active is None else is_active,
                    base_skill_key=base.skill_key if base else None,
                )

        await self.refresh_cache()
        return RoleTemplateRecord(
            role_key=updated.role_key,
            category=updated.category,
            name=updated.name,
            description=updated.description,
            skill_markdown=updated.skill_markdown,
            prompt_schema=updated.prompt_schema or {},
            is_active=updated.is_active,
            base_skill_key=getattr(updated, "base_skill_key", None),
            old_content=updated.old_content,
            record_id=updated.id,
        ).to_dict()

    async def toggle_role_template(
        self, role_key: str, category: str, is_active: bool
    ) -> None:
        await self._ensure_initialized()
        normalized = self._normalize_role_category(category)
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = RoleTemplateRepository(session)
            existing = await repo.get_by_role_and_category(role_key, normalized)
            if not existing:
                raise ValueError("角色模板不存在")
            existing.is_active = is_active
            await session.flush()

        await self.refresh_cache()

    async def reset_role_template(self, role_key: str, category: str) -> Dict[str, Any]:
        await self._ensure_initialized()
        normalized = self._normalize_role_category(category)
        base = self._find_default_skill(normalized)
        if not base:
            raise ValueError("未找到默认模板")

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = RoleTemplateRepository(session)
            existing = await repo.get_by_role_and_category(role_key, normalized)
            if not existing:
                existing = await repo.create(
                    role_key=role_key,
                    category=normalized,
                    name=base.name,
                    description=base.description,
                    skill_markdown=base.skill_markdown,
                    prompt_schema=base.prompt_schema,
                    old_content=None,
                    is_active=True,
                    base_skill_key=base.skill_key,
                )
            else:
                existing.old_content = existing.skill_markdown
                existing.skill_markdown = base.skill_markdown
                existing.prompt_schema = base.prompt_schema
                existing.name = base.name
                existing.description = base.description
                existing.base_skill_key = base.skill_key
                existing.is_active = True
                await session.flush()

        await self.refresh_cache()
        return await self.get_role_template_info(role_key, normalized)

    async def restore_role_template(
        self, role_key: str, category: str
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        normalized = self._normalize_role_category(category)
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = RoleTemplateRepository(session)
            existing = await repo.get_by_role_and_category(role_key, normalized)
            if not existing or not existing.old_content:
                raise ValueError("暂无可回退内容")
            current = existing.skill_markdown
            restored = existing.old_content
            record = self._build_record_from_markdown(restored)
            existing.skill_markdown = restored
            existing.prompt_schema = record.prompt_schema
            existing.name = record.name
            existing.description = record.description
            existing.old_content = current
            await session.flush()

        await self.refresh_cache()
        return await self.get_role_template_info(role_key, normalized)

    async def get_role_template_info(
        self, role_key: str, category: str
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        normalized = self._normalize_role_category(category)
        role_map = self._role_template_cache.get(role_key) or {}
        template = role_map.get(normalized)
        if not template:
            return {}
        return template.to_dict()

    def render_role_template(
        self,
        role_key: Optional[str],
        category: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """渲染角色模板（拼接角色系统提示词）"""
        role_key = (role_key or "general").strip() or "general"
        normalized = self._normalize_role_category(category)
        template = self._get_role_template_record(role_key, normalized)
        if not template:
            template = self._get_role_template_record("general", normalized)

        if template and template.is_active:
            prompt_schema = template.prompt_schema or {}
        else:
            fallback = self._find_default_skill(normalized)
            prompt_schema = fallback.prompt_schema if fallback else {}

        variables = variables or {}
        rendered: Dict[str, str] = {}
        for part, template_text in (prompt_schema or {}).items():
            try:
                rendered[part] = template_text.format(**variables)
            except Exception:
                rendered[part] = template_text

        role_record = self._role_cache.get(role_key) or self._role_cache.get("general")
        if role_record and role_record.system_prompt:
            try:
                role_prompt = role_record.system_prompt.format(**variables)
            except Exception:
                role_prompt = role_record.system_prompt
            role_prompt = role_prompt.strip()
            if role_prompt:
                if rendered.get("audio_system_prompt") or rendered.get("video_system_prompt"):
                    if rendered.get("audio_system_prompt"):
                        rendered["audio_system_prompt"] = (
                            role_prompt + "\n\n" + rendered["audio_system_prompt"]
                        )
                    if rendered.get("video_system_prompt"):
                        rendered["video_system_prompt"] = (
                            role_prompt + "\n\n" + rendered["video_system_prompt"]
                        )
                else:
                    system_prompt = rendered.get("system_prompt", "")
                    if system_prompt:
                        rendered["system_prompt"] = (
                            role_prompt + "\n\n" + system_prompt
                        )
                    else:
                        rendered["system_prompt"] = role_prompt

        return rendered

    def render_role_template_parts(
        self,
        role_key: Optional[str],
        category: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """渲染角色模板（不拼接角色系统提示词）"""
        role_key = (role_key or "general").strip() or "general"
        normalized = self._normalize_role_category(category)
        template = self._get_role_template_record(role_key, normalized)
        if not template:
            template = self._get_role_template_record("general", normalized)

        if template and template.is_active:
            prompt_schema = template.prompt_schema or {}
        else:
            fallback = self._find_default_skill(normalized)
            prompt_schema = fallback.prompt_schema if fallback else {}

        variables = variables or {}
        rendered: Dict[str, str] = {}
        for part, template_text in (prompt_schema or {}).items():
            try:
                rendered[part] = template_text.format(**variables)
            except Exception:
                rendered[part] = template_text

        return rendered

    def get_role_prompt(
        self, role_key: Optional[str], variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """获取角色系统提示词"""
        role_key = (role_key or "general").strip() or "general"
        role_record = self._role_cache.get(role_key) or self._role_cache.get("general")
        if not role_record or not role_record.system_prompt:
            return ""
        variables = variables or {}
        try:
            role_prompt = role_record.system_prompt.format(**variables)
        except Exception:
            role_prompt = role_record.system_prompt
        return role_prompt.strip()

    def list_available_skill_summaries(
        self, categories: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """列出可用模板摘要"""
        records = [
            record
            for record in self._cache.values()
            if record
            and record.is_active
            and (not categories or record.category in categories)
        ]
        if categories:
            order_map = {value: idx for idx, value in enumerate(categories)}

            def _sort_key(rec: SkillRecord):
                return (order_map.get(rec.category, 999), rec.skill_key)

            records.sort(key=_sort_key)
        else:
            records.sort(key=lambda rec: rec.skill_key)

        summaries: List[Dict[str, str]] = []
        for record in records:
            summaries.append(
                {
                    "skill_key": record.skill_key,
                    "name": record.name,
                    "description": record.description or "",
                    "category": record.category,
                }
            )
        return summaries

    def build_skill_hint(
        self,
        selected_skill_key: Optional[str] = None,
        categories: Optional[List[str]] = None,
    ) -> str:
        skills = self.list_available_skill_summaries(categories)
        if not skills:
            return ""
        lines = ["# 可用内容模板（Skills）"]
        for skill in skills:
            desc = skill.get("description") or skill.get("name") or ""
            label = f"{skill['skill_key']}: {desc}".strip()
            lines.append(f"- {label}")
        if selected_skill_key:
            lines.append(f"\n当前已启用模板：`{selected_skill_key}`")
        return "\n".join(lines)

    def build_system_prompt(
        self,
        role_key: Optional[str],
        template_prompt: str,
        variables: Optional[Dict[str, Any]] = None,
        selected_skill_key: Optional[str] = None,
        categories: Optional[List[str]] = None,
    ) -> str:
        """组合系统提示词（全局约束 + 角色 + 模板 + Skills提示）"""
        parts = []
        constraints = GLOBAL_SYSTEM_CONSTRAINTS.strip()
        if constraints:
            parts.append(constraints)
        role_prompt = self.get_role_prompt(role_key, variables)
        if role_prompt:
            parts.append(role_prompt)
        if template_prompt:
            parts.append(template_prompt)
        skill_hint = self.build_skill_hint(selected_skill_key, categories)
        if skill_hint:
            parts.append(skill_hint)
        return "\n\n".join([part for part in parts if part]).strip()

    def render_template(
        self, skill_key: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """根据变量渲染模板各个 prompt 部分"""

        record = self._cache.get(skill_key)
        if not record:
            return {}

        variables = variables or {}
        rendered: Dict[str, str] = {}
        for part, template in (record.prompt_schema or {}).items():
            try:
                rendered[part] = template.format(**variables)
            except Exception:
                # 如果变量不足，保留原模板以避免抛出异常
                rendered[part] = template
        return rendered

    async def list_templates(
        self, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出所有模板（优先从数据库获取）"""
        await self._ensure_initialized()
        if category and category not in ROLE_TEMPLATE_CATEGORIES:
            return []
        if not self._initialized:
            # 尚未完成数据库加载，返回默认模板
            records = (
                [rec for rec in self._default_skills if rec.category == category]
                if category
                else self._default_skills
            )
            return [rec.to_dict() for rec in records]

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = TemplateSkillRepository(session)
            templates = await repo.list_by_category(category)
            return [
                SkillRecord(
                    skill_key=tpl.skill_key,
                    name=tpl.name,
                    category=tpl.category,
                    scenario=tpl.scenario,
                    description=tpl.description,
                    prompt_schema=tpl.prompt_schema or {},
                    variables=tpl.variables or [],
                    tags=tpl.tags or [],
                    skill_markdown=tpl.skill_markdown,
                    is_default=tpl.is_default,
                    is_active=tpl.is_active,
                    record_id=tpl.id,
                ).to_dict()
                for tpl in templates
                if tpl.category in ROLE_TEMPLATE_CATEGORIES
            ]

    async def create_template(self, skill_markdown: str, is_active: bool = True):
        """保存新模板"""
        await self._ensure_initialized()
        payload = self._build_record_from_markdown(skill_markdown)
        payload.is_active = is_active
        payload.is_default = False

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = TemplateSkillRepository(session)
            if await repo.get_by_key(payload.skill_key):
                raise ValueError(f"模板 {payload.skill_key} 已存在")
            await repo.create(
                skill_key=payload.skill_key,
                name=payload.name,
                category=payload.category,
                scenario=payload.scenario,
                description=payload.description,
                prompt_schema=payload.prompt_schema,
                variables=payload.variables,
                tags=payload.tags,
                skill_markdown=payload.skill_markdown,
                is_default=False,
                is_active=is_active,
            )

        await self.refresh_cache()

    async def update_template(
        self, template_id: str, skill_markdown: str, is_active: bool = True
    ):
        """更新已有模板"""
        await self._ensure_initialized()
        payload = self._build_record_from_markdown(skill_markdown)
        payload.is_active = is_active

        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = TemplateSkillRepository(session)
            instance = await repo.get_by_id(template_id)
            if not instance:
                raise ValueError("模板不存在")

            payload.skill_key = instance.skill_key  # 保持主键稳定
            instance.name = payload.name
            instance.category = payload.category
            instance.scenario = payload.scenario
            instance.description = payload.description
            instance.prompt_schema = payload.prompt_schema
            instance.variables = payload.variables
            instance.tags = payload.tags
            instance.skill_markdown = payload.skill_markdown
            instance.is_active = is_active
            await session.flush()

        await self.refresh_cache()

    async def delete_template(self, template_id: str):
        await self._ensure_initialized()
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            repo = TemplateSkillRepository(session)
            await repo.delete(template_id)
        await self.refresh_cache()

    async def refresh_cache(self):
        """从数据库重新加载缓存"""
        async with self._lock:
            db_manager = get_database_manager()
            async with db_manager.get_session() as session:
                template_repo = TemplateSkillRepository(session)
                mapping_repo = RoleTemplateMappingRepository(session)
                role_repo = TemplateRoleRepository(session)
                role_template_repo = RoleTemplateRepository(session)
                await self._reload_cache(template_repo)
                await self._reload_role_mapping_cache(mapping_repo)
                await self._reload_role_cache(role_repo)
                await self._reload_role_template_cache(role_template_repo)

    # ------------------------------------------------------------------ #
    # 解析/构建逻辑
    # ------------------------------------------------------------------ #
    def _load_default_skills(self) -> List[SkillRecord]:
        records: List[SkillRecord] = []
        if not DEFAULT_SKILL_DIR.exists():
            logger.warning("默认模板目录不存在: %s", DEFAULT_SKILL_DIR)
            return records

        for skill_file in DEFAULT_SKILL_DIR.glob("*/SKILL.md"):
            try:
                markdown = skill_file.read_text(encoding="utf-8")
                records.append(self._build_record_from_markdown(markdown))
            except Exception as exc:
                logger.error("加载模板 %s 失败: %s", skill_file, exc)
        return records

    async def _reload_cache(self, repo: TemplateSkillRepository):
        templates = await repo.get_all(limit=500)
        self._cache = {
            tpl.skill_key: SkillRecord(
                skill_key=tpl.skill_key,
                name=tpl.name,
                category=tpl.category,
                scenario=tpl.scenario,
                description=tpl.description,
                prompt_schema=tpl.prompt_schema or {},
                variables=tpl.variables or [],
                tags=tpl.tags or [],
                skill_markdown=tpl.skill_markdown,
                is_default=tpl.is_default,
                is_active=tpl.is_active,
                record_id=tpl.id,
            )
            for tpl in templates
            if tpl.is_active
        }

    async def _reload_role_cache(self, repo: TemplateRoleRepository):
        roles = await repo.get_all(limit=500)
        self._role_cache = {
            role.role_key: RoleRecord(
                role_key=role.role_key,
                name=role.name,
                description=role.description,
                system_prompt=role.system_prompt or "",
                icon=role.icon,
                is_default=role.is_default,
                is_active=role.is_active,
            )
            for role in roles
        }

    async def _reload_role_template_cache(self, repo: RoleTemplateRepository):
        templates = await repo.get_all(limit=5000)
        cache: Dict[str, Dict[str, RoleTemplateRecord]] = {}
        for tpl in templates:
            if tpl.category not in ROLE_TEMPLATE_CATEGORIES:
                continue
            role_map = cache.setdefault(tpl.role_key, {})
            role_map[tpl.category] = RoleTemplateRecord(
                role_key=tpl.role_key,
                category=tpl.category,
                name=tpl.name,
                description=tpl.description,
                skill_markdown=tpl.skill_markdown,
                prompt_schema=tpl.prompt_schema or {},
                is_active=tpl.is_active,
                base_skill_key=tpl.base_skill_key,
                old_content=tpl.old_content,
                record_id=tpl.id,
            )
        self._role_template_cache = cache

    async def _ensure_roles(self, repo: TemplateRoleRepository) -> None:
        defaults = self._build_default_role_cache()
        existing = await repo.get_all(limit=1000)
        existing_keys = {item.role_key for item in existing}
        for role_key, record in defaults.items():
            if role_key in existing_keys:
                continue
            await repo.create(
                role_key=record.role_key,
                name=record.name,
                description=record.description,
                system_prompt=record.system_prompt,
                icon=record.icon,
                is_default=record.is_default,
                is_active=record.is_active,
            )

    async def _ensure_role_templates(
        self,
        role_repo: TemplateRoleRepository,
        role_template_repo: RoleTemplateRepository,
        only_role: Optional[str] = None,
        active_categories: Optional[Set[str]] = None,
    ) -> None:
        roles = await role_repo.get_all(limit=1000)
        if only_role:
            roles = [role for role in roles if role.role_key == only_role]

        base_map: Dict[str, SkillRecord] = {}
        categories = ROLE_TEMPLATE_CATEGORIES
        if active_categories:
            categories = tuple(sorted(active_categories))
        for category in categories:
            base = self._find_default_skill(category)
            if base:
                base_map[category] = base

        for role in roles:
            existing = await role_template_repo.list_by_role(role.role_key)
            existing_categories = {tpl.category for tpl in existing}
            for category, base in base_map.items():
                if category in existing_categories:
                    continue
                is_active = True
                if active_categories is not None:
                    is_active = category in active_categories
                await role_template_repo.create(
                    role_key=role.role_key,
                    category=category,
                    base_skill_key=base.skill_key,
                    name=base.name,
                    description=base.description,
                    skill_markdown=base.skill_markdown,
                    prompt_schema=base.prompt_schema,
                    old_content=None,
                    is_active=is_active,
                )

    def _normalize_role_category(self, category: str) -> str:
        return ROLE_CATEGORY_TO_SKILL_CATEGORY.get(category, category)

    def _get_role_template_record(
        self, role_key: str, category: str
    ) -> Optional[RoleTemplateRecord]:
        role_map = self._role_template_cache.get(role_key) or {}
        record = role_map.get(category)
        if record and record.is_active:
            return record
        return None

    def _find_default_skill(self, category: str) -> Optional[SkillRecord]:
        candidates = [
            rec
            for rec in (self._cache.values() or [])
            if rec.category == category and rec.is_active
        ]
        if candidates:
            for rec in candidates:
                if rec.is_default:
                    return rec
            return candidates[0]

        candidates = [
            rec
            for rec in self._default_skills
            if rec.category == category and rec.is_active
        ]
        if candidates:
            for rec in candidates:
                if rec.is_default:
                    return rec
            return candidates[0]

        return next(iter(self._default_skills), None)

    async def _ensure_role_mappings(
        self, repo: RoleTemplateMappingRepository
    ) -> None:
        """确保所有角色类别都有默认模板映射"""
        defaults = self._build_default_role_mapping()
        existing = await repo.get_all(limit=2000)
        existing_pairs = {(item.role_key, item.category) for item in existing}

        for category, role_map in defaults.items():
            for role_key, skill_key in role_map.items():
                if not skill_key:
                    continue
                if (role_key, category) in existing_pairs:
                    continue
                await repo.upsert(role_key, category, skill_key)

    def _build_default_role_mapping(self) -> Dict[str, Dict[str, str]]:
        """兼容旧版角色映射结构"""
        defaults: Dict[str, Dict[str, str]] = {
            category: {} for category in ROLE_CATEGORY_TO_SKILL_CATEGORY
        }
        role_keys = list(self._role_cache.keys()) or list(
            self._build_default_role_cache().keys()
        )
        for role_category, skill_category in ROLE_CATEGORY_TO_SKILL_CATEGORY.items():
            base = self._find_default_skill(skill_category)
            if not base:
                continue
            category_map = defaults.setdefault(role_category, {})
            for role_key in role_keys:
                category_map.setdefault(role_key, base.skill_key)
        return defaults

    async def _reload_role_mapping_cache(
        self, repo: RoleTemplateMappingRepository
    ) -> None:
        """从数据库加载角色模板映射"""
        mappings = await repo.get_all(limit=5000)
        cache: Dict[str, Dict[str, str]] = {
            category: {} for category in ROLE_CATEGORY_TO_SKILL_CATEGORY
        }
        for mapping in mappings:
            category_map = cache.setdefault(mapping.category, {})
            category_map[mapping.role_key] = mapping.skill_key

        # 如果数据库为空，保持默认映射
        if any(cache.values()):
            self._legacy_role_mapping_cache = cache
        else:
            self._legacy_role_mapping_cache = self._build_default_role_mapping()

    def _build_record_from_markdown(self, markdown: str) -> SkillRecord:
        frontmatter, body = self._split_frontmatter(markdown)
        sections = self._parse_sections(body)

        metadata = frontmatter.get("metadata") or {}
        prompt_schema: Dict[str, str] = {}
        for key, value in sections.items():
            norm_key = self._normalize_heading(key)
            if PROMPT_SECTION_PATTERN.search(norm_key):
                prompt_schema[norm_key] = self._strip_code_block(value)

        if not prompt_schema:
            raise ValueError("模板中未检测到 prompt 段落")

        skill_key = frontmatter.get("slug") or self._slugify(
            frontmatter.get("name") or "template"
        )

        record = SkillRecord(
            skill_key=skill_key,
            name=frontmatter.get("name") or skill_key,
            category=frontmatter.get("category") or skill_key,
            scenario=frontmatter.get("scenario"),
            description=frontmatter.get("description"),
            prompt_schema=prompt_schema,
            variables=metadata.get("variables", []),
            tags=metadata.get("tags", []),
            skill_markdown=markdown,
            is_default=frontmatter.get("is_default", True),
            is_active=frontmatter.get("is_active", True),
        )
        if record.category not in ROLE_TEMPLATE_CATEGORIES:
            allowed = ", ".join(ROLE_TEMPLATE_CATEGORIES)
            raise ValueError(f"模板类别不支持，请使用 {allowed}")
        return record

    def _split_frontmatter(self, markdown: str) -> (Dict[str, Any], str):
        lines = markdown.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, markdown

        end_idx = None
        for idx, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = idx
                break

        if end_idx is None:
            return {}, markdown

        frontmatter_text = "\n".join(lines[1:end_idx])
        body = "\n".join(lines[end_idx + 1 :])
        try:
            data = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - 配置文件格式错误
            logger.error("解析模板Frontmatter失败: %s", exc)
            data = {}
        return data, body

    def _parse_sections(self, body: str) -> Dict[str, str]:
        sections: Dict[str, str] = {}
        current_key = None
        buffer: List[str] = []

        for line in body.splitlines():
            if line.startswith("## "):
                if current_key:
                    sections[current_key] = "\n".join(buffer).strip()
                current_key = line[3:].strip()
                buffer = []
            else:
                buffer.append(line)

        if current_key:
            sections[current_key] = "\n".join(buffer).strip()

        return sections

    def _strip_code_block(self, content: str) -> str:
        text = content.strip()
        match = CODE_FENCE_PATTERN.match(text)
        if match:
            return match.group("body").strip()
        return text

    def _normalize_heading(self, heading: str) -> str:
        return heading.strip().lower().replace(" ", "_")

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
        return slug.strip("_") or "template"


template_skill_service = TemplateSkillService()
