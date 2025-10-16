#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 设置API路由
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import json
import os
import requests
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 创建设置API路由器
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

# 配置文件路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "settings.json"


def load_settings() -> Dict[str, Any]:
    """加载设置配置"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # 默认配置
            return {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-3.5-turbo",
                    "max_tokens": 2000,
                },
                "ollama": {
                    "installed": False,
                    "base_url": "http://localhost:11434",
                    "models": [],
                },
                "system": {
                    "default_language": "zh",
                    "storage_path": str(PROJECT_ROOT / "data" / "outputs"),
                    "max_concurrent": 3,
                },
            }
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


def get_role_mapping(category: str = "content_generator") -> Dict[str, str]:
    """获取角色映射配置
    
    Args:
        category: 角色类别 (content_generator, flashcard_generator, ai_analysis, content_card)
    
    Returns:
        角色映射字典
    """
    try:
        settings = load_settings()
        role_mapping = settings.get("role_mapping", {})
        
        # 获取指定类别的角色映射
        category_mapping = role_mapping.get(category, {})
        
        # 如果指定类别不存在，返回默认的content_generator映射
        if not category_mapping:
            category_mapping = role_mapping.get("content_generator", {})
        
        # 如果还是没有，返回默认映射
        if not category_mapping:
            category_mapping = {
                "education": "教育内容专家",
                "exam_review": "试卷评讲专家", 
                "cooking": "美食知识专家",
                "travel": "旅行攻略专家",
                "meeting": "会议管理专家",
                "technology": "科技内容专家",
                "business": "商业分析专家",
                "general": "内容专家",
            }
            
        return category_mapping
    except Exception as e:
        logger.error(f"获取角色映射失败: {e}")
        # 返回默认映射
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


def get_role_name(domain: str, category: str = "content_generator", default: str = "内容专家") -> str:
    """获取指定领域的角色名称
    
    Args:
        domain: 领域名称
        category: 角色类别
        default: 默认角色名称
    
    Returns:
        角色名称
    """
    try:
        role_mapping = get_role_mapping(category)
        return role_mapping.get(domain, default)
    except Exception as e:
        logger.error(f"获取角色名称失败: {e}")
        return default


def get_prompt_template(template_type: str, prompt_part: str = "system_prompt") -> str:
    """从配置文件获取提示词模板
    
    Args:
        template_type: 模板类型 (mind_map, flashcards, ai_analysis)
        prompt_part: 提示词部分 (system_prompt, user_prompt)
    
    Returns:
        提示词模板字符串
    """
    try:
        settings = load_settings()
        prompt_templates = settings.get("prompt_templates", {})
        template = prompt_templates.get(template_type, {})
        
        return template.get(prompt_part, "")
        
    except Exception as e:
        logger.error(f"读取提示词模板失败: {e}")
        return ""


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


@settings_router.get("/role_mapping")
async def get_role_mapping_api() -> Dict[str, Any]:
    """获取角色映射配置API"""
    try:
        settings = load_settings()
        role_mapping = settings.get("role_mapping", {})
        
        return {"success": True, "data": role_mapping}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


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

        # 隐藏敏感信息
        # if settings.get("openai", {}).get("api_key"):
        #     api_key = settings["openai"]["api_key"]
        #     settings["openai"]["api_key"] = "sk-" + "*" * 20 + api_key[-8:]

        return {"success": True, "data": settings}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}
