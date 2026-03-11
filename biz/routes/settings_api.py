#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 设置API路由
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
import json
import os
import requests
import subprocess
from pathlib import Path
import logging
from pydantic import BaseModel
from copy import deepcopy

from ..services.template_skill_service import template_skill_service

logger = logging.getLogger(__name__)

# 创建设置API路由器
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

# 配置文件路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "settings.json"
ASR_DEFAULTS = {
    "remote_api": {
        "enabled": False,
        "base_url": "",
        "endpoint": "/api/v1/asr/transcribe",
        "api_key": "",
        "auth_type": "header",
        "auth_header": "X-API-Key",
        "timeout": 120,
        "max_retries": 2,
        "extra_headers": {},
        "default_params": {},
        "cloud_provider": "custom",
        "notes": "",
    },
    "parakeet": {
        "selected_model": "tdt-0.6b-v2",
        "model_name": "parakeet-tdt-0.6b-v2",
        "device": "auto",
        "batch_size": 2,
        "segment_duration": 18.0,
        "words_per_segment": 32,
        "diarization": {"enabled": True, "max_speakers": 8},
    },
    "qwen3_asr": {
        "enabled": False,
        "model_name": "qwen3-asr-flash-filetrans",
        "dashscope_api_key": "",
        "base_http_api_url": "",
        "oss_access_key_id": "",
        "oss_access_key_secret": "",
        "oss_endpoint": "",
        "oss_bucket": "",
        "oss_prefix": "qwen3/asr",
        "oss_public_base_url": "",
        "filetrans_use_http": True,
        "filetrans_poll_interval": 5,
        "filetrans_poll_timeout": 3600,
        "num_threads": 4,
        "vad_segment_threshold": 120,
        "max_segment_duration": 180,
        "min_duration_for_vad": 180,
        "tmp_dir": "./data/qwen3/cache",
        "silence": True,
        "realtime_url": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        "realtime_chunk_ms": 200,
        "realtime_send_delay": 0.1,
        "realtime_sample_rate": 16000,
        "realtime_format": "pcm",
        "realtime_finish_timeout": 10,
    },
}


def load_settings() -> Dict[str, Any]:
    """加载设置配置"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # 默认配置
            # 读取setting.example.json
            with open(PROJECT_ROOT / "config" / "settings.example.json", "r", encoding="utf-8") as f:
                return json.load(f)

    except Exception as e:
        logger.error(f"加载设置失败: {e}")
        return {}


def save_settings(settings: Dict[str, Any]) -> bool:
    """保存设置配置"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        return False


class TemplateSkillPayload(BaseModel):
    skill_markdown: str
    is_active: bool = True


class RoleTemplateUpdatePayload(BaseModel):
    mappings: Dict[str, Dict[str, str]]


class RolePayload(BaseModel):
    role_key: str
    name: str
    description: Optional[str] = ""
    system_prompt: Optional[str] = ""
    icon: Optional[str] = ""
    content_categories: Optional[List[str]] = None


class RoleUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


class RoleTemplatePayload(BaseModel):
    skill_markdown: str
    is_active: Optional[bool] = None


class RoleTemplateTogglePayload(BaseModel):
    is_active: bool


def get_role_mapping(category: str = "content_card") -> Dict[str, str]:
    """获取角色映射配置（兼容旧逻辑，默认返回角色名称映射）"""
    try:
        return template_skill_service.get_role_map()
    except Exception as e:
        logger.error(f"获取角色映射失败: {e}")
        return {
            "education": "教育内容专家",
            "exam_review": "试卷评讲专家",
            "cooking": "美食知识专家",
            "travel": "旅行攻略专家",
            "meeting": "会议管理专家",
            "technology": "科技内容专家",
            "business": "商业分析专家",
            "general": "内容专家",
        }


def get_role_name(
    domain: str, category: str = "content_card", default: str = "内容专家"
) -> str:
    """获取指定领域的角色名称

    Args:
        domain: 领域名称
        category: 角色类别
        default: 默认角色名称

    Returns:
        角色名称
    """
    try:
        return template_skill_service.get_role_name(domain, default=default)
    except Exception as e:
        logger.error(f"获取角色名称失败: {e}")
        return default


def get_prompt_template(template_type: str, prompt_part: str = "system_prompt") -> str:
    """从配置文件获取提示词模板

    Args:
        template_type: 模板类型 (content_card)
        prompt_part: 提示词部分 (system_prompt, user_prompt, audio_system_prompt)

    Returns:
        提示词模板字符串
    """
    try:
        prompt = template_skill_service.get_prompt(template_type, prompt_part)
        return prompt or ""
    except Exception as e:  # pragma: no cover - 兜底
        logger.error(f"读取提示词模板失败: {e}")
        return ""


def ensure_asr_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """确保设置里包含ASR默认配置"""
    if "asr" not in settings or not isinstance(settings["asr"], dict):
        settings["asr"] = {}

    asr_settings = settings["asr"]
    for key, default_value in ASR_DEFAULTS.items():
        if key not in asr_settings or not isinstance(asr_settings[key], dict):
            asr_settings[key] = deepcopy(default_value)
        else:
            # 填充缺失字段
            for sub_key, sub_value in default_value.items():
                if sub_key not in asr_settings[key]:
                    asr_settings[key][sub_key] = deepcopy(sub_value)

    return asr_settings


@settings_router.get("/openai")
async def get_openai_settings() -> Dict[str, Any]:
    """获取OpenAI配置"""
    try:
        settings = load_settings()
        openai_config = settings.get("openai", {})

        # 隐藏API密钥的敏感信息
        # if openai_config.get("api_key"):
        #     openai_config["api_key"] = "sk-" + "*" * 20 + openai_config["api_key"][-8:]

        return {"success": True, "data": openai_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/openai")
async def update_openai_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新OpenAI配置"""
    try:
        settings = load_settings()

        # 更新OpenAI配置
        if "openai" not in settings:
            settings["openai"] = {}

        # 只更新提供的字段
        for key, value in config.items():
            if key in ["api_key", "base_url", "model", "max_tokens"]:
                settings["openai"][key] = value

        if save_settings(settings):
            return {"success": True, "message": "OpenAI配置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@settings_router.post("/openai/test")
async def test_openai_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """测试OpenAI连接"""
    try:
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "https://api.openai.com/v1")
        model = config.get("model", "gpt-3.5-turbo")

        if not api_key:
            return {"success": False, "error": "API密钥不能为空"}

        # 测试API连接
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        test_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
            ],
            "max_tokens": config.get("max_tokens", 2000),
        }

        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=test_data,
            timeout=10,
        )

        if response.status_code == 200:
            return {"success": True, "message": "连接成功"}
        else:
            error_msg = f"连接失败: {response.status_code}"
            try:
                error_detail = response.json().get("error", {}).get("message", "")
                if error_detail:
                    error_msg += f" - {error_detail}"
            except:
                pass
            return {"success": False, "error": error_msg}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "连接超时"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "无法连接到服务器"}
    except Exception as e:
        return {"success": False, "error": f"测试失败: {str(e)}"}


@settings_router.get("/ollama")
async def get_ollama_settings() -> Dict[str, Any]:
    """获取Ollama配置"""
    try:
        settings = load_settings()
        ollama_config = settings.get("ollama", {})

        return {"success": True, "data": ollama_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/ollama/detect")
async def detect_ollama() -> Dict[str, Any]:
    """检测Ollama安装状态"""
    try:
        # 检查Ollama是否安装
        try:
            result = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=5
            )
            installed = result.returncode == 0
            version = result.stdout.strip() if installed else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            installed = False
            version = ""

        # 检查Ollama服务是否运行
        running = False
        models = []

        if installed:
            try:
                # 尝试连接Ollama API
                response = requests.get("http://localhost:11434/api/tags", timeout=5)
                if response.status_code == 200:
                    running = True
                    data = response.json()
                    models = [model["name"] for model in data.get("models", [])]
            except:
                pass

        # 更新配置
        settings = load_settings()
        settings["ollama"] = {
            "installed": installed,
            "version": version,
            "running": running,
            "base_url": "http://localhost:11434",
            "models": models,
        }
        save_settings(settings)

        return {
            "success": True,
            "data": {
                "installed": installed,
                "version": version,
                "running": running,
                "models": models,
                "model_count": len(models),
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.get("/system")
async def get_system_settings() -> Dict[str, Any]:
    """获取系统设置"""
    try:
        settings = load_settings()
        system_config = settings.get("system", {})

        return {"success": True, "data": system_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/system")
async def update_system_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新系统设置"""
    try:
        settings = load_settings()

        # 更新系统配置
        if "system" not in settings:
            settings["system"] = {}

        # 只更新提供的字段
        for key, value in config.items():
            if key in ["default_language", "storage_path", "max_concurrent"]:
                settings["system"][key] = value

        # 验证存储路径
        if "storage_path" in config:
            storage_path = Path(config["storage_path"])
            try:
                storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {"success": False, "error": f"无效的存储路径: {str(e)}"}

        if save_settings(settings):
            return {"success": True, "message": "系统设置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@settings_router.get("/asr")
async def get_asr_settings_api() -> Dict[str, Any]:
    """获取语音识别配置（远端API、Parakeet等）"""
    try:
        settings = load_settings()
        asr_settings = ensure_asr_settings(settings)
        return {"success": True, "data": asr_settings}
    except Exception as e:
        logger.error(f"读取ASR配置失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/asr")
async def update_asr_settings_api(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新语音识别配置"""
    try:
        settings = load_settings()
        asr_settings = ensure_asr_settings(settings)

        if "remote_api" in config:
            allowed = {
                "enabled",
                "base_url",
                "endpoint",
                "api_key",
                "auth_type",
                "auth_header",
                "timeout",
                "max_retries",
                "extra_headers",
                "default_params",
                "cloud_provider",
                "notes",
            }
            for key, value in config["remote_api"].items():
                if key in allowed:
                    asr_settings["remote_api"][key] = value

        if "parakeet" in config:
            allowed = {
                "selected_model",
                "model_name",
                "device",
                "batch_size",
                "segment_duration",
                "words_per_segment",
                "diarization",
            }
            for key, value in config["parakeet"].items():
                if key in allowed:
                    asr_settings["parakeet"][key] = value

        if "qwen3_asr" in config:
            qwen_payload = config.get("qwen3_asr") or {}
            if qwen_payload.get("enabled") and "filetrans" in str(
                qwen_payload.get("model_name", "")
            ):
                required = [
                    "oss_access_key_id",
                    "oss_access_key_secret",
                    "oss_endpoint",
                    "oss_bucket",
                ]
                missing = [key for key in required if not qwen_payload.get(key)]
                if missing:
                    return {
                        "success": False,
                        "error": f"filetrans 需要先配置 OSS: {', '.join(missing)}",
                    }
            allowed = {
                "enabled",
                "model_name",
                "context",
                "dashscope_api_key",
                "base_http_api_url",
                "oss_access_key_id",
                "oss_access_key_secret",
                "oss_endpoint",
                "oss_bucket",
                "oss_prefix",
                "oss_public_base_url",
                "filetrans_use_http",
                "filetrans_poll_interval",
                "filetrans_poll_timeout",
                "num_threads",
                "vad_segment_threshold",
                "max_segment_duration",
                "min_duration_for_vad",
                "tmp_dir",
                "silence",
                "realtime_url",
                "realtime_chunk_ms",
                "realtime_send_delay",
                "realtime_sample_rate",
                "realtime_format",
                "realtime_finish_timeout",
            }
            for key, value in config["qwen3_asr"].items():
                if key in allowed:
                    asr_settings["qwen3_asr"][key] = value

        settings["asr"] = asr_settings
        if save_settings(settings):
            return {"success": True, "message": "ASR配置已更新", "data": asr_settings}
        return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        logger.error(f"更新ASR配置失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.get("/role_mapping")
async def get_role_mapping_api() -> Dict[str, Any]:
    """获取角色映射配置API"""
    try:
        settings = load_settings()

        # 优先返回新的roles结构
        roles = settings.get("roles", {})
        if roles:
            return {"success": True, "data": {"roles": roles}}

        # 兼容旧的role_mapping结构
        role_mapping = settings.get("role_mapping", {})
        return {"success": True, "data": {"role_mapping": role_mapping}}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.get("/content_roles")
async def get_content_roles() -> Dict[str, Any]:
    """获取内容角色选项 - 用于前端动态加载"""
    try:
        roles = await template_skill_service.list_roles()
        category_labels = {
            "content_card": "内容卡片",
            "mind_map": "思维导图",
            "flashcards": "学习闪卡",
        }

        role_options: List[Dict[str, Any]] = []

        for role in roles:
            role_key = role["role_key"]
            content_types = template_skill_service.get_role_content_types(role_key)
            icon = role.get("icon") or ""
            label = f"{icon} {role['name']}".strip()
            role_options.append(
                {
                    "value": role_key,
                    "label": label,
                    "icon": icon,
                    "text": role["name"],
                    "description": role.get("description") or "",
                    "system_prompt": role.get("system_prompt") or "",
                    "content_types": content_types,
                    "content_type_labels": category_labels,
                }
            )

        return {
            "success": True,
            "data": {"roles": role_options, "total": len(role_options)},
        }

    except Exception as e:
        logger.error(f"获取内容角色失败: {e}")
        return {"success": False, "error": str(e), "data": {"roles": [], "total": 0}}


@settings_router.get("/roles")
async def list_roles() -> Dict[str, Any]:
    """列出角色"""
    try:
        roles = await template_skill_service.list_roles(include_inactive=True)
        for role in roles:
            role["content_types"] = template_skill_service.get_role_content_types(
                role["role_key"]
            )
        return {"success": True, "data": roles}
    except Exception as e:
        logger.error(f"获取角色列表失败: {e}")
        return {"success": False, "error": str(e), "data": []}


@settings_router.post("/roles")
async def create_role(payload: RolePayload) -> Dict[str, Any]:
    """创建角色"""
    try:
        role = await template_skill_service.create_role(
            role_key=payload.role_key,
            name=payload.name,
            description=payload.description or "",
            system_prompt=payload.system_prompt or "",
            icon=payload.icon or "",
            content_categories=payload.content_categories,
        )
        return {"success": True, "data": role}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"创建角色失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.put("/roles/{role_key}")
async def update_role(role_key: str, payload: RoleUpdatePayload) -> Dict[str, Any]:
    """更新角色"""
    try:
        role = await template_skill_service.update_role(
            role_key,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            icon=payload.icon,
            is_active=payload.is_active,
        )
        return {"success": True, "data": role}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"更新角色失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.delete("/roles/{role_key}")
async def delete_role(role_key: str) -> Dict[str, Any]:
    """删除角色"""
    try:
        await template_skill_service.delete_role(role_key)
        return {"success": True, "message": "角色已删除"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"删除角色失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.get("/roles/{role_key}/templates")
async def list_role_templates(role_key: str) -> Dict[str, Any]:
    """列出角色模板"""
    try:
        templates = await template_skill_service.list_role_templates(role_key)
        return {"success": True, "data": templates}
    except Exception as e:
        logger.error(f"获取角色模板失败: {e}")
        return {"success": False, "error": str(e), "data": []}


@settings_router.put("/roles/{role_key}/templates/{category}")
async def update_role_template(
    role_key: str, category: str, payload: RoleTemplatePayload
) -> Dict[str, Any]:
    """更新角色模板"""
    try:
        template = await template_skill_service.update_role_template(
            role_key=role_key,
            category=category,
            skill_markdown=payload.skill_markdown,
            is_active=payload.is_active,
        )
        return {"success": True, "data": template}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"更新角色模板失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/roles/{role_key}/templates/{category}/toggle")
async def toggle_role_template(
    role_key: str, category: str, payload: RoleTemplateTogglePayload
) -> Dict[str, Any]:
    """启用/停用角色模板"""
    try:
        await template_skill_service.toggle_role_template(
            role_key=role_key, category=category, is_active=payload.is_active
        )
        return {"success": True, "message": "角色模板已更新"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"更新角色模板状态失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/roles/{role_key}/templates/{category}/reset")
async def reset_role_template(role_key: str, category: str) -> Dict[str, Any]:
    """重置角色模板为默认版本"""
    try:
        template = await template_skill_service.reset_role_template(role_key, category)
        return {"success": True, "data": template}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"重置角色模板失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/roles/{role_key}/templates/{category}/restore")
async def restore_role_template(role_key: str, category: str) -> Dict[str, Any]:
    """回退到上一次内容"""
    try:
        template = await template_skill_service.restore_role_template(
            role_key, category
        )
        return {"success": True, "data": template}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"回退角色模板失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/role_mapping")
async def update_role_mapping(role_mapping: Dict[str, Any]) -> Dict[str, Any]:
    """更新角色映射配置"""
    try:
        settings = load_settings()
        settings["role_mapping"] = role_mapping

        if save_settings(settings):
            return {"success": True, "message": "角色映射配置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@settings_router.get("/all")
async def get_all_settings() -> Dict[str, Any]:
    """获取所有设置"""
    try:
        settings = load_settings()

        # 确保返回所有必需的配置
        result = {
            "openai": settings.get("openai", {}),
            "ollama": settings.get("ollama", {}),
            "system": settings.get("system", {}),
            "whisperx": settings.get("whisperx", {}),
            "role_mapping": settings.get("role_mapping", {}),
            "roles": template_skill_service.get_role_map(),
            "prompt_templates": template_skill_service.get_prompt_map(),
        }

        # 隐藏敏感信息
        # if result.get("openai", {}).get("api_key"):
        #     api_key = result["openai"]["api_key"]
        #     result["openai"]["api_key"] = "sk-" + "*" * 20 + api_key[-8:]

        return result
    except Exception as e:
        logger.error(f"获取所有设置失败: {e}")
        return {}


@settings_router.get("/prompt-templates")
async def list_prompt_templates(category: Optional[str] = None) -> Dict[str, Any]:
    """列出全部提示词模板"""
    try:
        templates = await template_skill_service.list_templates(category)
        return {"success": True, "data": templates}
    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/prompt-templates")
async def create_prompt_template(payload: TemplateSkillPayload) -> Dict[str, Any]:
    """创建新的提示词模板"""
    try:
        await template_skill_service.create_template(
            payload.skill_markdown, payload.is_active
        )
        return {"success": True, "message": "模板已创建"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"创建模板失败: {e}")
        return {"success": False, "error": f"创建失败: {str(e)}"}


@settings_router.put("/prompt-templates/{template_id}")
async def update_prompt_template(
    template_id: str, payload: TemplateSkillPayload
) -> Dict[str, Any]:
    """更新指定模板"""
    try:
        await template_skill_service.update_template(
            template_id, payload.skill_markdown, payload.is_active
        )
        return {"success": True, "message": "模板已更新"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"更新模板失败: {e}")
        return {"success": False, "error": f"更新失败: {str(e)}"}


@settings_router.delete("/prompt-templates/{template_id}")
async def delete_prompt_template(template_id: str) -> Dict[str, Any]:
    """删除模板"""
    try:
        await template_skill_service.delete_template(template_id)
        return {"success": True, "message": "模板已删除"}
    except Exception as e:
        logger.error(f"删除模板失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.get("/prompt-templates/resolve")
async def resolve_prompt_template(
    role: str = Query("general"), category: str = Query("content_card")
) -> Dict[str, Any]:
    """解析角色在指定类别下实际使用的模板"""
    try:
        template = await template_skill_service.get_role_template_info(role, category)
        if template:
            return {
                "success": True,
                "data": {
                    "role": role,
                    "category": category,
                    "template": template,
                },
            }

        skill_key = template_skill_service.get_skill_for_role(role, category)
        if not skill_key:
            return {"success": False, "error": "未找到匹配的模板", "data": {}}

        meta = template_skill_service.get_template_meta(skill_key) or {}
        return {
            "success": True,
            "data": {
                "role": role,
                "category": category,
                "skill_key": skill_key,
                "template_name": meta.get("name", skill_key),
                "scenario": meta.get("scenario"),
                "description": meta.get("description"),
                "prompt_schema": meta.get("prompt_schema", {}),
                "variables": meta.get("variables", []),
            },
        }
    except Exception as e:
        logger.error(f"解析模板失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@settings_router.get("/prompt-templates/role-mappings")
async def get_prompt_template_role_mappings() -> Dict[str, Any]:
    """返回角色到模板的映射"""
    try:
        mappings = await template_skill_service.list_role_mappings()
        return {"success": True, "data": mappings}
    except Exception as e:
        logger.error(f"获取角色模板映射失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/prompt-templates/role-mappings")
async def update_prompt_template_role_mappings(
    payload: RoleTemplateUpdatePayload,
) -> Dict[str, Any]:
    """更新角色到模板的映射"""
    try:
        await template_skill_service.update_role_mappings(payload.mappings)
        return {"success": True, "message": "角色模板映射已更新"}
    except Exception as e:
        logger.error(f"更新角色模板映射失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/whisperx")
async def update_whisperx_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新WhisperX配置"""
    try:
        settings = load_settings()

        # 更新Hugging Face Token
        if "system" not in settings:
            settings["system"] = {}
        if "huggingface" not in settings["system"]:
            settings["system"]["huggingface"] = {}

        if "hf_token" in config:
            settings["system"]["huggingface"]["token"] = config["hf_token"]
            settings["system"]["huggingface"]["enable_whisperx"] = True

        # 更新WhisperX配置
        if "whisperx" not in settings:
            settings["whisperx"] = {}

        # 更新提供的字段
        if "model_size" in config:
            settings["whisperx"]["model_size"] = config["model_size"]
        if "device" in config:
            settings["whisperx"]["device"] = config["device"]
        if "batch_size" in config:
            settings["whisperx"]["batch_size"] = config["batch_size"]

        # 保存配置
        if save_settings(settings):
            return {"success": True, "message": "WhisperX配置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        logger.error(f"更新WhisperX配置失败: {e}")
        return {"success": False, "error": str(e)}


@settings_router.post("/whisperx/test")
async def test_whisperx_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """测试WhisperX配置"""
    try:
        hf_token = config.get("hf_token", "")
        model_size = config.get("model_size", "base")

        # 测试结果
        result = {
            "success": True,
            "model_size": model_size,
            "device": "auto",
            "hf_token_valid": False,
        }

        # 检测可用设备
        try:
            import torch

            if torch.cuda.is_available():
                result["device"] = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                result["device"] = "mps"
            else:
                result["device"] = "cpu"
        except ImportError:
            result["device"] = "cpu"

        # 验证Hugging Face Token
        if hf_token:
            try:
                headers = {"Authorization": f"Bearer {hf_token}"}
                response = requests.get(
                    "https://huggingface.co/api/whoami", headers=headers, timeout=10
                )

                if response.status_code == 200:
                    result["hf_token_valid"] = True
                    user_info = response.json()
                    result["hf_username"] = user_info.get("name", "unknown")
                else:
                    result["hf_token_valid"] = False
                    result["error"] = f"Token验证失败: HTTP {response.status_code}"
            except requests.exceptions.Timeout:
                result["error"] = "连接超时，请检查网络"
            except requests.exceptions.ConnectionError:
                result["error"] = "无法连接到Hugging Face，请检查网络"
            except Exception as e:
                result["error"] = f"Token验证失败: {str(e)}"
        else:
            result["message"] = "未配置Hugging Face Token，说话人分离功能将不可用"

        # 检查WhisperX是否已安装
        try:
            import whisperx

            result["whisperx_installed"] = True
            result["whisperx_version"] = (
                whisperx.__version__ if hasattr(whisperx, "__version__") else "unknown"
            )
        except ImportError:
            result["success"] = False
            result["error"] = "WhisperX未安装，请运行: pip install whisperx"
            result["whisperx_installed"] = False

        return result

    except Exception as e:
        logger.error(f"测试WhisperX配置失败: {e}")
        return {
            "success": False,
            "error": f"测试失败: {str(e)}",
        }
