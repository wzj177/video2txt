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


def get_role_mapping(category: str = "content_generator") -> Dict[str, str]:
    """获取角色映射配置

    Args:
        category: 角色类别 (content_generator, flashcard_generator, ai_analysis, content_card)

    Returns:
        角色映射字典
    """
    try:
        settings = load_settings()

        # 新的配置结构：从roles中提取指定类别的映射
        roles = settings.get("roles", {})
        if roles:
            category_mapping = {}
            for role_key, role_config in roles.items():
                if isinstance(role_config, dict) and category in role_config:
                    category_mapping[role_key] = role_config[category]

            if category_mapping:
                return category_mapping

        # 兼容旧的role_mapping结构
        role_mapping = settings.get("role_mapping", {})
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


def get_role_name(
    domain: str, category: str = "content_generator", default: str = "内容专家"
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
        role_mapping = get_role_mapping(category)
        return role_mapping.get(domain, default)
    except Exception as e:
        logger.error(f"获取角色名称失败: {e}")
        return default


def get_prompt_template(template_type: str, prompt_part: str = "system_prompt") -> str:
    """从配置文件获取提示词模板

    Args:
        template_type: 模板类型 (mind_map, flashcards, ai_analysis, content_card)
        prompt_part: 提示词部分 (system_prompt, user_prompt, audio_system_prompt)

    Returns:
        提示词模板字符串
    """
    try:
        settings = load_settings()
        prompt_templates = settings.get("prompt_templates", {})
        template = prompt_templates.get(template_type, {})

        # 特殊处理 content_card 类型的 audio_system_prompt
        if template_type == "content_card" and prompt_part == "audio_system_prompt":
            return template.get("audio_system_prompt", "")

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
        settings = load_settings()

        # 新的配置结构：从roles中提取content_card映射
        roles = settings.get("roles", {})
        content_card_roles = {}

        if roles:
            for role_key, role_config in roles.items():
                if isinstance(role_config, dict) and "content_card" in role_config:
                    content_card_roles[role_key] = role_config["content_card"]

        # 兼容旧的role_mapping结构
        if not content_card_roles:
            role_mapping = settings.get("role_mapping", {})
            content_card_roles = role_mapping.get("content_card", {})

        # 如果还是没有配置，返回默认的角色选项
        if not content_card_roles:
            content_card_roles = {
                "education": "教育学习专家",
                "exam_review": "试卷评讲专家",
                "meeting": "会议纪要专家",
                "cooking": "烹饪美食专家",
                "travel": "旅游探索专家",
                "technology": "科技数码专家",
                "business": "商业财经专家",
                "health": "健康养生专家",
                "lifestyle": "生活方式专家",
                "entertainment": "娱乐休闲专家",
                "emotion": "情感心理专家",
                "finance": "金融投资专家",
                "beauty": "美容护肤专家",
                "male": "男性内容专家",
                "female": "女性内容专家",
                "fitness": "运动健身专家",
                "parenting": "育儿教育专家",
            }  # 构建前端需要的格式 - 包含显示文本、图标和描述
        role_options = []

        # 默认选项：智能识别
        role_options.append(
            {
                "value": "auto",
                "label": "🤖 智能识别（推荐）",
                "icon": "🤖",
                "text": "智能识别模式",
                "description": "系统将自动分析内容类型，选择最适合的生成策略",
            }
        )

        # 角色选项映射 - 定义图标和描述
        role_display_config = {
            "education": {
                "icon": "📚",
                "label": "教育学习",
                "description": "专注于知识传授和学习要点，适合教学视频和课程内容",
            },
            "exam_review": {
                "icon": "📝",
                "label": "试卷评讲",
                "description": "重点分析题目解答和考点，适合试卷讲解和习题分析",
            },
            "meeting": {
                "icon": "💼",
                "label": "会议纪要",
                "description": "提取决议要点和行动计划，适合会议录音和讨论内容",
            },
            "cooking": {
                "icon": "🍳",
                "label": "烹饪美食",
                "description": "突出制作步骤和技巧要点，适合美食教学和菜谱分享",
            },
            "travel": {
                "icon": "✈️",
                "label": "旅游探索",
                "description": "强调体验分享和实用攻略，适合旅行记录和景点介绍",
            },
            "technology": {
                "icon": "💻",
                "label": "科技数码",
                "description": "注重技术原理和操作指南，适合科技评测和教程内容",
            },
            "business": {
                "icon": "💰",
                "label": "商业财经",
                "description": "分析商业逻辑和市场趋势，适合商业分析和财经讨论",
            },
            "health": {
                "icon": "🏥",
                "label": "健康养生",
                "description": "关注健康知识和养生方法，适合医疗科普和健康指导",
            },
            "lifestyle": {
                "icon": "🏠",
                "label": "生活方式",
                "description": "展现生活品质和实用建议，适合生活分享和经验交流",
            },
            "entertainment": {
                "icon": "🎬",
                "label": "娱乐休闲",
                "description": "突出娱乐价值和观点评论，适合影视评论和娱乐内容",
            },
            "emotion": {
                "icon": "💝",
                "label": "情感心理",
                "description": "深度解析情感表达和心理状态，适合情感类和心理分析内容",
            },
            "finance": {
                "icon": "📈",
                "label": "金融投资",
                "description": "专业解读投资策略和金融产品，适合理财教学和投资分析",
            },
            "beauty": {
                "icon": "💄",
                "label": "美容护肤",
                "description": "专注美容技巧和护肤知识，适合化妆教程和护肤分享",
            },
            "male": {
                "icon": "👨",
                "label": "男性内容",
                "description": "面向男性用户的内容优化，适合男性兴趣和生活内容",
            },
            "female": {
                "icon": "👩",
                "label": "女性内容",
                "description": "面向女性用户的内容优化，适合女性兴趣和生活内容",
            },
            "fitness": {
                "icon": "💪",
                "label": "运动健身",
                "description": "强调训练方法和健身技巧，适合运动教学和健身指导",
            },
            "parenting": {
                "icon": "👶",
                "label": "育儿教育",
                "description": "专注育儿经验和教育方法，适合亲子内容和教育分享",
            },
        }

        # 根据配置生成角色选项
        for role_key, role_name in content_card_roles.items():
            display_config = role_display_config.get(
                role_key,
                {
                    "icon": "👤",
                    "label": role_name,
                    "description": f"专业的{role_name}，提供该领域的专业内容分析",
                },
            )

            role_options.append(
                {
                    "value": role_key,
                    "label": f"{display_config['icon']} {display_config['label']}",
                    "icon": display_config["icon"],
                    "text": f"{display_config['label']}模式",
                    "description": display_config["description"],
                    "expert_name": role_name,
                }
            )

        return {
            "success": True,
            "data": {"roles": role_options, "total": len(role_options)},
        }

    except Exception as e:
        logger.error(f"获取内容角色失败: {e}")
        return {"success": False, "error": str(e), "data": {"roles": [], "total": 0}}


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
            "roles": settings.get("roles", {}),
            "prompt_templates": settings.get("prompt_templates", {}),
        }

        # 隐藏敏感信息
        # if result.get("openai", {}).get("api_key"):
        #     api_key = result["openai"]["api_key"]
        #     result["openai"]["api_key"] = "sk-" + "*" * 20 + api_key[-8:]

        return result
    except Exception as e:
        logger.error(f"获取所有设置失败: {e}")
        return {}


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
