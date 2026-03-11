#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 模板技能模型
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, ForeignKey, UniqueConstraint

from .base import BaseModel


class TemplateSkill(BaseModel):
    """提示词模板（Skill风格）"""

    __tablename__ = "template_skills"

    skill_key = Column(String(100), unique=True, nullable=False)  # content_card
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)  # content_card
    scenario = Column(String(50))  # 可选：education / emotion / etc
    description = Column(String(500))

    # 完整的 SKILL Markdown 文本
    skill_markdown = Column(Text, nullable=False)

    # prompt_schema 存储不同 prompt 部分（system_prompt/user_prompt/...）
    prompt_schema = Column(JSON, nullable=False, default=dict)
    variables = Column(JSON, default=list)
    tags = Column(JSON, default=list)

    is_default = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<TemplateSkill(key={self.skill_key}, category={self.category})>"


class RoleTemplateMapping(BaseModel):
    """角色到提示词模板的映射"""

    __tablename__ = "role_template_mappings"
    __table_args__ = (UniqueConstraint("role_key", "category", name="uq_role_category"),)

    role_key = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    skill_key = Column(String(100), ForeignKey("template_skills.skill_key"), nullable=False)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<RoleTemplateMapping(role={self.role_key}, category={self.category}, skill={self.skill_key})>"


class TemplateRole(BaseModel):
    """提示词角色（用于拼接系统提示词）"""

    __tablename__ = "template_roles"

    role_key = Column(String(100), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(String(500))
    system_prompt = Column(Text, default="")
    icon = Column(String(50))

    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<TemplateRole(key={self.role_key}, name={self.name})>"


class RoleTemplate(BaseModel):
    """角色下的提示词模板（按内容类型）"""

    __tablename__ = "role_templates"
    __table_args__ = (UniqueConstraint("role_key", "category", name="uq_role_template"),)

    role_key = Column(String(100), ForeignKey("template_roles.role_key"), nullable=False)
    category = Column(String(50), nullable=False)  # content_card
    base_skill_key = Column(String(100), ForeignKey("template_skills.skill_key"))

    name = Column(String(200))
    description = Column(String(500))
    skill_markdown = Column(Text, nullable=False)
    prompt_schema = Column(JSON, nullable=False, default=dict)

    old_content = Column(Text)
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<RoleTemplate(role={self.role_key}, category={self.category})>"
